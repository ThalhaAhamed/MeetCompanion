"""
Bot watcher: keeps a launched bot's meeting current without webhooks.

Everything after "Launch bot" used to depend on MeetStream calling back -
bot.inmeeting, bot.stopped, transcription.processed. On a laptop install
with no public URL those calls never arrive, so a meeting sat at "joining"
for the whole call and nothing was extracted afterwards until someone
pressed Reprocess. This asks MeetStream instead: while a meeting is live,
or has ended and its transcript has not been picked up, its bot's status is
polled and the meeting is moved through the same states the webhooks drive.
Once MeetStream reports a finished transcription run, the meeting is
claimed and the usual pipeline runs. Webhooks that do arrive still work;
whichever side learns of the transcript first claims it, the other finds
nothing to do.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

import httpx

from app.database.connection import get_db_context
from app.database.repositories import MeetingRepository
from app.models.database import Meeting

logger = logging.getLogger(__name__)

POLL_SECONDS = 20
#: A bot MeetStream still calls live this long after launch is not coming back.
STALE_LIVE_AFTER = timedelta(hours=24)
#: How long after the call ends to keep waiting for MeetStream's transcript.
TRANSCRIPT_WAIT = timedelta(hours=6)
#: A finished bot with no transcription run at all: give the listing this
#: long to catch up before concluding there is none.
NO_RUN_GRACE = timedelta(minutes=10)
#: Extractions started per sweep. An install that has been offline, or one
#: upgraded with a backlog of calls, is caught up a few at a time rather
#: than with a dozen LLM runs at once.
MAX_STARTS_PER_SWEEP = 3

#: MeetStream's bot states (see their "Debugging bots" guide) as this app's.
REMOTE_TO_LOCAL = {
    "scheduled": "joining",
    "joining": "joining",
    "inwaitingroom": "joining",
    "inmeeting": "in_meeting",
    "recording": "recording",
    "leaving": "stopped",
    "stopped": "stopped",
    "kicked": "stopped",
    "mediaprocessing": "stopped",
    "done": "completed",
    "mediaexpired": "completed",
    "failed": "failed",
    "denied": "failed",
    "notallowed": "failed",
}
FAILURE_REASONS = {
    "denied": "The meeting host did not admit the bot.",
    "notallowed": "The meeting did not allow the bot in (a locked meeting, or one that needs a signed-in account).",
    "failed": "MeetStream reported that the bot failed.",
}
TRANSCRIPT_READY = ("success", "completed", "complete", "done", "ready")
TRANSCRIPT_FAILED = ("failed", "error")

NO_TRANSCRIPT_MESSAGE = (
    "MeetStream produced no transcript for this call. If nobody spoke while the bot "
    "was in the meeting there is nothing to process; otherwise use Reprocess later."
)


def no_transcript_message(reason: Optional[str] = None) -> str:
    if not reason:
        return NO_TRANSCRIPT_MESSAGE
    return (
        f"MeetStream could not transcribe this call ({reason.rstrip('.')}). If nobody spoke "
        "while the bot was in the meeting there is nothing to process; otherwise use Reprocess later."
    )


def normalise_remote(remote: Any) -> str:
    return str(remote or "").replace("_", "").replace(" ", "").lower()


def local_status(remote: Any) -> Optional[str]:
    """This app's meeting status for a MeetStream bot state; None if unknown."""
    return REMOTE_TO_LOCAL.get(normalise_remote(remote))


def transcription_runs(runs: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    The bot's real transcription runs. MeetStream lists the platform's own
    caption file alongside them (provider "meeting_captions", always
    "Success", no transcript_id); that is not a transcript this app can fetch.
    """
    return [r for r in runs if r.get("transcript_id")]


def ready_transcript_id(runs: Iterable[Dict[str, Any]]) -> Optional[str]:
    """The transcript id of a finished transcription run, newest first."""
    for run in transcription_runs(runs):
        if str(run.get("status", "")).lower() in TRANSCRIPT_READY:
            return str(run["transcript_id"])
    return None


def transcription_failure(runs: Iterable[Dict[str, Any]]) -> Optional[str]:
    """
    MeetStream's reason when every transcription run for the bot failed (and
    there was at least one); None while any is still running or succeeded.
    """
    real = transcription_runs(runs)
    if not real or not all(str(r.get("status", "")).lower() in TRANSCRIPT_FAILED for r in real):
        return None
    return str(real[0].get("error") or real[0].get("message") or "").strip() or "transcription failed"


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    # SQLite hands timestamps back naive; they were stored as UTC.
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class BotWatcher:
    def __init__(self, client=None, pipeline=None, poll_seconds: float = POLL_SECONDS):
        self._client = client
        self._pipeline = pipeline
        self.poll_seconds = poll_seconds
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    @property
    def client(self):
        if self._client is None:
            from app.services.meetstream import meetstream_client

            self._client = meetstream_client
        return self._client

    @property
    def pipeline(self):
        if self._pipeline is None:
            from app.services.processing import processing_pipeline

            self._pipeline = processing_pipeline
        return self._pipeline

    # -- lifecycle -------------------------------------------------------

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self.run(), name="bot-watcher")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await self.sweep()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # the loop must outlive any one bad sweep
                logger.warning("Bot watcher sweep failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_seconds)
            except asyncio.TimeoutError:
                pass

    # -- one pass --------------------------------------------------------

    async def sweep(self) -> List[uuid.UUID]:
        """Bring every awaited meeting up to date; returns the ids sent to the pipeline."""
        claimed: List[tuple[uuid.UUID, str]] = []
        async with get_db_context() as db:
            repo = MeetingRepository(db)
            for meeting in await repo.list_awaiting_bot():
                try:
                    transcript_id = await self.sync_meeting(db, meeting, may_claim=len(claimed) < MAX_STARTS_PER_SWEEP)
                except Exception as exc:
                    logger.warning("Bot watcher could not update meeting %s: %s", meeting.id, exc)
                    await db.rollback()
                    continue
                await db.commit()
                if transcript_id:
                    claimed.append((meeting.id, transcript_id))
        for meeting_id, transcript_id in claimed:
            self.pipeline.start_in_background(meeting_id, transcript_id=transcript_id)
        return [m for m, _ in claimed]

    async def sync_meeting(self, db, meeting: Meeting, *, may_claim: bool = True) -> Optional[str]:
        """
        Reconcile one meeting with its bot. Returns the transcript id when
        this call claimed the meeting for processing, else None. With
        may_claim off the status is still followed, but a ready transcript
        waits for a later sweep.
        """
        from app.services.agents import get_meetstream_api_key

        repo = MeetingRepository(db)
        api_key = await get_meetstream_api_key(db, meeting.created_by_user_id) if meeting.created_by_user_id else None
        now = datetime.now(timezone.utc)

        try:
            remote = await self.client.get_bot_status(meeting.meetstream_bot_id, api_key=api_key)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                await repo.update_status(
                    meeting.id,
                    status="failed",
                    processing_status="failed",
                    processing_error="MeetStream no longer knows this bot.",
                )
            return None

        status = local_status(remote)
        if status is None:
            logger.info("Bot %s: unknown MeetStream state %r", meeting.meetstream_bot_id, remote)
            status = meeting.status

        if status == "failed":
            reason = FAILURE_REASONS.get(normalise_remote(remote), FAILURE_REASONS["failed"])
            await repo.update_status(meeting.id, status="failed", processing_status="failed", processing_error=reason)
            return None

        changes: Dict[str, Any] = {}
        if status != meeting.status:
            changes["status"] = status
        if status in ("in_meeting", "recording") and meeting.started_at is None:
            changes["started_at"] = now
        if status in ("stopped", "completed") and meeting.ended_at is None:
            changes["ended_at"] = now
        if changes:
            await repo.update_status(meeting.id, **changes)

        if status in MeetingRepository.LIVE_STATUSES:
            if now - _aware(meeting.created_at) > STALE_LIVE_AFTER:
                await repo.update_status(
                    meeting.id,
                    status="failed",
                    processing_status="failed",
                    processing_error="MeetStream never reported this bot leaving the call; it was given up on after a day.",
                )
            return None

        # Ended. Anything to process?
        if meeting.processing_status != "pending":
            return None
        ended_at = _aware(changes.get("ended_at") or meeting.ended_at) or now
        runs = await self.client.list_bot_transcriptions(meeting.meetstream_bot_id, api_key=api_key)
        transcript_id = ready_transcript_id(runs)
        no_runs_for_done_bot = not transcription_runs(runs) and status == "completed" and now - ended_at > NO_RUN_GRACE
        if not transcript_id and no_runs_for_done_bot:
            # Last resort: the id MeetStream handed out when the bot was created.
            transcript_id = meeting.meetstream_transcript_id
        if transcript_id:
            if not may_claim:
                return None
            claimed = await repo.claim_for_processing(meeting.id, transcript_id)
            return transcript_id if claimed else None
        failure = transcription_failure(runs)
        if failure or no_runs_for_done_bot or now - ended_at > TRANSCRIPT_WAIT:
            await repo.update_status(meeting.id, processing_status="failed", processing_error=no_transcript_message(failure))
        return None


bot_watcher = BotWatcher()
