"""
Answer questions typed into a live meeting's chat.

MeetStream's voice agents hear the room but never read the chat panel, and
no webhook carries chat messages. So for an agent in "chat" or "both" mode
the server polls the bot's chat while the call is live, picks out messages
addressed to the bot, answers them from the workspace (services/ask) and
posts the reply back through the bot. A listener lives for one bot; it
starts when the bot is launched and stops when the meeting ends.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

#: How a member's agent takes part in a call.
MODE_VOICE = "voice"    # the MeetStream voice agent only (the default)
MODE_CHAT = "chat"      # no voice agent; questions typed in the chat, answers in the chat
MODE_BOTH = "both"      # the voice agent, plus chat questions answered in the chat
INTERACTION_MODES = (MODE_VOICE, MODE_CHAT, MODE_BOTH)

#: Seconds between chat polls while the call is live.
POLL_SECONDS = 4.0
#: Back off to this after repeated poll failures (MeetStream hiccup, bot not up yet).
SLOW_POLL_SECONDS = 15.0
#: Give up after this long - a listener must never outlive a forgotten meeting.
MAX_LIFETIME_SECONDS = 6 * 3600
#: Meeting statuses during which the chat is worth reading.
LIVE_STATUSES = {"joining", "in_meeting", "recording", "in_progress"}
#: A reply longer than this is cut: chat panels are not for essays.
MAX_REPLY_CHARS = 900

_listeners: Dict[str, "asyncio.Task[None]"] = {}


def address_pattern(bot_name: str) -> "re.Pattern[str]":
    """
    A chat message is for the bot when it starts with the bot's name (with
    or without @) or with /ask. Everything else in the chat is the humans'.
    """
    name = re.escape(bot_name.strip())
    # (?![\w]) rather than \b: a name ending in a non-word character, like
    # "Ada (v2)", has no word boundary after it.
    return re.compile(rf"^\s*(?:@?{name}|/ask)(?!\w)[\s:,\-—]*(.*)$", re.IGNORECASE | re.DOTALL)


def extract_question(text: str, bot_name: str) -> Optional[str]:
    match = address_pattern(bot_name).match(text or "")
    if not match:
        return None
    question = match.group(1).strip()
    return question or None


def is_listening(bot_id: str) -> bool:
    task = _listeners.get(bot_id)
    return task is not None and not task.done()


def start(*, bot_id: str, meeting_id: uuid.UUID, org_id: uuid.UUID, bot_name: str, api_key_owner_id: Optional[uuid.UUID]) -> None:
    """Begin answering chat questions for this bot. Idempotent per bot."""
    if is_listening(bot_id):
        return
    _listeners[bot_id] = asyncio.create_task(
        _run(bot_id=bot_id, meeting_id=meeting_id, org_id=org_id, bot_name=bot_name, api_key_owner_id=api_key_owner_id),
        name=f"meeting-chat:{bot_id}",
    )
    logger.info("Chat listener started for bot %s (%s mode)", bot_id, "chat")


def stop(bot_id: str) -> None:
    task = _listeners.pop(bot_id, None)
    if task and not task.done():
        task.cancel()
        logger.info("Chat listener stopped for bot %s", bot_id)


def stop_all() -> None:
    for bot_id in list(_listeners):
        stop(bot_id)


async def resume_live_meetings() -> int:
    """
    After a restart, pick the listeners back up for calls still in progress
    that were launched in a chat mode. Returns how many were resumed.
    """
    from sqlalchemy import select

    from app.database.connection import AsyncSessionLocal
    from app.models.database import Meeting

    resumed = 0
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(Meeting).where(Meeting.status.in_(LIVE_STATUSES), Meeting.meetstream_bot_id.is_not(None))
            )
        ).scalars().all()
        for meeting in rows:
            attrs = meeting.custom_attributes or {}
            if attrs.get("interaction_mode") not in (MODE_CHAT, MODE_BOTH):
                continue
            start(
                bot_id=meeting.meetstream_bot_id,
                meeting_id=meeting.id,
                org_id=meeting.organization_id,
                bot_name=attrs.get("bot_name") or "Meet Companion",
                api_key_owner_id=meeting.created_by_user_id,
            )
            resumed += 1
    return resumed


async def answer_question(db, org_id: uuid.UUID, question: str) -> str:
    """The reply to post for one question - always something, never an exception."""
    from app.services.ask import LLMConfigError, LLMError, NothingToAnswerFrom, ask_workspace

    try:
        result = await ask_workspace(db, org_id, question, chat_style=True)
        answer = (result.get("answer") or "").strip()
    except NothingToAnswerFrom:
        answer = "I don't have any notes, meetings or documents to answer that from yet."
    except LLMConfigError:
        answer = "I can't answer right now: no AI provider is set up for this workspace. An owner can add one in Settings."
    except LLMError as exc:
        logger.warning("Chat answer failed: %s", exc)
        answer = "Sorry, I couldn't get an answer just now. Please try again in a moment."
    if len(answer) > MAX_REPLY_CHARS:
        answer = answer[: MAX_REPLY_CHARS - 1].rstrip() + "…"
    return answer


async def _run(*, bot_id: str, meeting_id: uuid.UUID, org_id: uuid.UUID, bot_name: str, api_key_owner_id: Optional[uuid.UUID]) -> None:
    from app.database.connection import AsyncSessionLocal
    from app.database.repositories import MeetingRepository
    from app.services.meetstream import meetstream_client

    api_key: Optional[str] = None
    if api_key_owner_id:
        try:
            from app.services.agents import get_meetstream_api_key

            async with AsyncSessionLocal() as db:
                api_key = await get_meetstream_api_key(db, api_key_owner_id)
        except Exception as exc:  # noqa: BLE001 - fall back to the deployment key
            logger.warning("Chat listener for %s could not load the member's MeetStream key: %s", bot_id, exc)

    started = datetime.now(timezone.utc)
    seen: set[str] = set()
    primed = False
    failures = 0
    try:
        while (datetime.now(timezone.utc) - started).total_seconds() < MAX_LIFETIME_SECONDS:
            # Is the call still on? A stopped/failed meeting ends the listener
            # even when the webhook that would have stopped it never arrived.
            async with AsyncSessionLocal() as db:
                meeting = await MeetingRepository(db).get_by_id_unscoped(meeting_id)
            if meeting is None or meeting.status not in LIVE_STATUSES:
                break

            try:
                data = await meetstream_client.get_chats(bot_id, api_key=api_key)
                failures = 0
            except Exception as exc:  # noqa: BLE001 - keep polling
                failures += 1
                if failures in (1, 5, 20):
                    logger.info("Chat poll for %s failed (%d): %s", bot_id, failures, exc)
                await asyncio.sleep(SLOW_POLL_SECONDS if failures >= 3 else POLL_SECONDS)
                continue

            messages = list(data.get("chatMessages") or [])
            if not primed:
                # Whatever was in the chat before the bot was ready is history,
                # not questions for it.
                seen.update(m.get("messageId") for m in messages if m.get("messageId"))
                primed = True
            else:
                for m in messages:
                    mid = m.get("messageId")
                    if not mid or mid in seen:
                        continue
                    seen.add(mid)
                    sender = (m.get("speakerDisplayName") or m.get("speakerName") or "").strip()
                    if sender.lower() == bot_name.strip().lower():
                        continue  # our own replies come back through the same feed
                    question = extract_question(m.get("text") or "", bot_name)
                    if not question:
                        continue
                    async with AsyncSessionLocal() as db:
                        reply = await answer_question(db, org_id, question)
                    try:
                        await meetstream_client.send_bot_message(bot_id, reply, api_key=api_key)
                    except Exception as exc:  # noqa: BLE001 - one lost reply must not end the listener
                        logger.warning("Could not post chat reply for %s: %s", bot_id, exc)
            await asyncio.sleep(POLL_SECONDS)
    except asyncio.CancelledError:
        pass
    finally:
        _listeners.pop(bot_id, None)
        logger.info("Chat listener finished for bot %s", bot_id)
