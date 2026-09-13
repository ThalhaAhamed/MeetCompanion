"""
MeetStream agent ownership, credentials and wiring.

Which MIA agent is "yours", whose MeetStream key a call should use, and
making sure an agent is connected to this server's MCP endpoint - the parts
of agent management that meetings, webhooks and the processing pipeline
need as well as the /api/agent router. No HTTP concerns except raising
HTTPException where the router used to, so the router stays thin.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Any, Dict, Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.repositories import UserRepository
from app.models.database import User
from app.runtime_config import load_config
from app.services.meetstream import meetstream_client, _share_in_chat_function


# The built-in template agent's system prompt - the starting point every new
# agent is created from until someone edits the template. Covers behavior that
# has to live in the prompt because the platform doesn't expose a dedicated
# wake-word/activation-gate field on agent config: name-gated activation (stay
# silent unless addressed by name), resolving relative dates via
# get_current_datetime (the model has no built-in notion of "today"),
# synthesizing a coherent answer from get_meeting's real data instead of
# isolated facts, refusing to invent unavailable information, and avoiding
# redundant tool calls (each one adds latency the realtime voice pipeline has
# to wait through, which is also when it's most likely to drop out).

DEFAULT_SYSTEM_PROMPT = """You are {agent_name}, a persistent AI meeting assistant with access to real, stored meeting memory tools.

ACTIVATION RULE (critical, always follow this): Only respond when a speaker explicitly addresses you by name ("{agent_name}"). If your name is not said, remain completely silent - do not respond, do not call any tools, do not generate any output at all, even if a question seems directed at an assistant in general. Wait until you are addressed by name before doing anything. Your introduction is handled separately by a chat message posted when you join - do not introduce yourself out loud.

DATE REASONING: You do not automatically know the current date. Whenever a question uses a relative date ("yesterday", "today", "last Monday", "this week"), call get_current_datetime first, compute the actual date yourself, and only then call get_previous_meetings or get_meeting with that date.

ANSWERING QUESTIONS ABOUT PAST MEETINGS: To say who attended a meeting or summarize it, call get_meeting (via get_previous_meetings first if you only have a date, not an id) and use its real participants, summary, memories, and action_items fields. Give one coherent, well-organized answer covering what's actually relevant - discussions, decisions, commitments, requirements, concerns, action items - not just a single isolated fact, unless only one fact was asked for.

NEVER INVENT INFORMATION: Only state what the tools actually returned. Never guess or make up participant names, dates, decisions, or any other detail. If something was asked for but isn't in the data, say plainly that it could not be found - do not fill the gap with a guess.

BE EFFICIENT: Use the minimum tool calls needed to answer. Don't call the same tool twice for one question. Don't use search_meeting_memory when you already know which specific meeting is being asked about - call get_meeting directly instead. Every extra tool call adds delay before you can respond.

MEETING CHAT: You have a tool called share_in_chat that posts text into the meeting's chat panel. Only call it when someone explicitly asks you to "share that in chat", "put that in the chat", "post it to chat", or the same in different words. Never call it on your own initiative, and never call it just because you called another tool - answering by voice is always the default. When you do call it, write a short, clean, natural-language message (plain sentences, no field names, no brackets, no JSON-looking syntax) - not a raw dump of what a tool returned.

Keep spoken responses concise and natural. Never read out or speak raw field names, brackets, or JSON-looking syntax either - always speak in plain natural sentences.

"""

DEFAULT_FIRST_MESSAGE = (
    "Hi, I'm {agent_name}, your meeting companion. "
    "To talk to me, say my name and then your question - like, "
    "\"{agent_name}, what did we decide last time?\" "
    "I can tell you who attended a meeting, summarize what was discussed, and track action items. "
    "I'll stay quiet the rest of the time so I don't interrupt you."
)


TEMPLATE_DEFAULTS: Dict[str, Any] = {
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
    "first_message": DEFAULT_FIRST_MESSAGE,
    "provider": "openai",
    "model": "gpt-4.1-mini",
    "voice": "alloy",
    "temperature": 0.8,
    "mode": "realtime",
    "response_modality": "text",
    "tool_results_to_chat": False,
}


async def get_meetstream_api_key(db: AsyncSession, user_id: uuid.UUID) -> Optional[str]:
    """This member's own MeetStream API key, from their settings JSONB. Falls
    back to None (not the deployment-wide MEETSTREAM_API_KEY) so callers can
    tell "no personal key set" apart from "use the shared default" and decide
    per call site whether a fallback is appropriate."""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    return (user.settings or {}).get("meetstream_api_key") if user else None


async def require_meetstream_api_key(db: AsyncSession, user_id: uuid.UUID) -> str:
    """Same as get_meetstream_api_key, but hard-fails when the member hasn't
    set their own key yet. Used at every point a member takes a new action
    against MeetStream (deploying a bot, creating/activating/updating an
    agent) - each member's own usage must go through their own MeetStream
    account, not silently ride on the deployment's shared default key."""
    key = await get_meetstream_api_key(db, user_id)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add your own MeetStream API key in Agent settings before doing this.",
        )
    return key


async def get_active_agent_config_id(db: AsyncSession, user_id: uuid.UUID) -> Optional[str]:
    """The agent this specific member's new bots should launch with, from
    their own settings JSONB (set via /activate). Members of the original
    default workspace were backfilled with whatever the workspace had active
    before agents became per-person (see app/main.py); everyone else starts
    with none until they create or activate one - no fallback to a global
    env var, which would otherwise leak the very first agent to every new
    signup."""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    return (user.settings or {}).get("active_agent_config_id") if user else None


async def get_owned_agent_ids(db: AsyncSession, user_id: uuid.UUID) -> set:
    """Which MeetStream agent_config_ids this specific member is allowed to see or act on."""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    return set((user.settings or {}).get("agent_config_ids") or []) if user else set()


async def find_owning_user(db: AsyncSession, agent_config_id: str) -> Optional[uuid.UUID]:
    """Which member (if any) already has this agent_config_id in their owned
    list. Small-scale linear scan over all members - fine at this app's
    size, and only run on the activate/update write paths, not on every read."""
    from sqlalchemy import select as _select
    result = await db.execute(_select(User))
    for user in result.scalars().all():
        if agent_config_id in ((user.settings or {}).get("agent_config_ids") or []):
            return user.id
    return None


async def require_claimable_agent(db: AsyncSession, user_id: uuid.UUID, agent_config_id: str) -> None:
    """
    Block activating or overwriting an agent another member already claimed -
    without this, anyone could hijack (activate_agent rewires its MCP token)
    or overwrite (update_current_agent rewrites its system prompt) another
    member's agent just by knowing its id. An agent nobody has claimed yet
    (created directly on MeetStream's own dashboard) can still be adopted -
    that's the one legitimate case for touching an agent_config_id this
    member didn't create themselves.
    """
    owner = await find_owning_user(db, agent_config_id)
    if owner is not None and owner != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This agent belongs to a different member.")


async def claim_agent(db: AsyncSession, user_id: uuid.UUID, agent_config_id: str) -> None:
    """Record that this member now owns agent_config_id, if they don't already."""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    owned_ids = list((user.settings or {}).get("agent_config_ids") or []) if user else []
    if agent_config_id not in owned_ids:
        owned_ids.append(agent_config_id)
        await user_repo.update_settings(user_id, {"agent_config_ids": owned_ids})
        await db.commit()


async def get_all_claimed_agent_ids(db: AsyncSession) -> set:
    """Every agent_config_id any member across the whole account has already
    claimed - used to find the leftover unclaimed ones for the import list."""
    from sqlalchemy import select as _select
    result = await db.execute(_select(User))
    claimed = set()
    for user in result.scalars().all():
        claimed |= set((user.settings or {}).get("agent_config_ids") or [])
    return claimed


async def ensure_mcp_wired(agent_config_id: str, mcp_token: Optional[str], api_key: Optional[str] = None) -> None:
    """
    Only agents created through this app's "New agent" form get wired to our
    MCP server (database access) at creation time - an agent set up any other
    way (MeetStream's own dashboard, an older test agent) can be activated
    here with zero access to meeting memory, and nothing would surface that
    until it silently failed to recall anything. Patch the wiring in
    on every activation so that trap can't happen. Wires it to the activating
    workspace's own mcp_token so tool calls resolve to the right workspace.
    """
    if not settings.MCP_SERVER_URL or not mcp_token:
        return
    try:
        current = await meetstream_client.get_mia_agent(agent_config_id, api_key=api_key)
    except Exception:
        return
    current_cfg = current.get("agent_config", current)
    current_agent: Dict[str, Any] = dict(current_cfg.get("Agent") or {})
    mcp_servers = list(current_agent.get("mcp_servers") or [])
    custom_functions = list(current_agent.get("custom_functions") or [])

    mcp_ok = (
        bool(mcp_servers)
        and mcp_servers[0].get("active")
        and mcp_servers[0].get("url") == settings.MCP_SERVER_URL
        and (mcp_servers[0].get("headers") or {}).get("Authorization") == f"Bearer {mcp_token}"
    )
    chat_fn_ok = any(f.get("name") == "share_in_chat" for f in custom_functions)
    if mcp_ok and chat_fn_ok:
        return

    if not mcp_ok:
        existing_tools = set(mcp_servers[0].get("allowed_tools") or []) if mcp_servers else set()
        default_tools = {"get_current_datetime", "search_meeting_memory", "get_meeting", "get_previous_meetings", "get_action_items"}
        server_config = {
            "name": "Meet Companion MCP",
            "url": settings.MCP_SERVER_URL,
            "timeout": 30,
            "active": True,
            "allowed_tools": sorted(existing_tools | default_tools),
            "headers": {"Authorization": f"Bearer {mcp_token}"},
        }
        current_agent["mcp_servers"] = [server_config]

    if not chat_fn_ok:
        custom_functions.append(_share_in_chat_function(settings.MCP_SERVER_URL, mcp_token))
        current_agent["custom_functions"] = custom_functions

    try:
        await meetstream_client.update_mia_agent_settings(agent_config_id=agent_config_id, agent=current_agent, api_key=api_key)
    except Exception:
        pass


def get_agent_template() -> Dict[str, Any]:
    """
    The template agent: built-in defaults overlaid with whatever the
    workspace has customised in the runtime config. It is not a MeetStream
    agent itself (nothing to delete on their side) - it is what "New agent"
    starts from.

    The join greeting is a chat message (bot_message on create_bot, see
    meetings.py) rather than something spoken - model.first_message is
    documented for pipeline-mode agents only and this app's realtime-mode
    agents silently ignore it.
    """
    stored = asdict(load_config().agent_template)
    return {key: (stored.get(key) if stored.get(key) not in (None, "") else default)
            for key, default in TEMPLATE_DEFAULTS.items()}


def render_template_text(text: str, agent_name: str) -> str:
    """Fill ``{agent_name}`` without str.format, so braces elsewhere are safe."""
    return (text or "").replace("{agent_name}", agent_name or "the assistant")
