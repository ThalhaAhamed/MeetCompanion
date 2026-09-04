"""
MIA Agent Configuration Endpoints.
Read, create, update, and switch between MeetStream MIA agents. Each agent
belongs to the individual member who created/activated it (tracked in
User.settings), not the shared workspace - meeting memory is workspace-wide,
but "which agent is mine" is personal, the same way a Slack workspace is
shared while each person's own bot/app connections aren't.
"""
import uuid
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database.connection import get_db
from app.database.repositories import OrganizationRepository, UserRepository, MeetingRepository
from app.models.database import User
from app.services.meetstream import meetstream_client, _share_in_chat_function
from app.api.deps import get_current_org_id, get_current_user
from app.mcp.auth import resolve_org_by_mcp_token

router = APIRouter(prefix="/api/agent", tags=["agent"])

_SECRET_KEY_PATTERN = ("key", "secret", "token", "password", "authorization")

# Prepended to every newly created agent's system prompt. Covers behavior that
# has to live in the prompt because the platform doesn't expose a dedicated
# wake-word/activation-gate field on agent config: name-gated activation (stay
# silent unless addressed by name), resolving relative dates via
# get_current_datetime (the model has no built-in notion of "today"),
# synthesizing a coherent answer from get_meeting's real data instead of
# isolated facts, refusing to invent unavailable information, and avoiding
# redundant tool calls (each one adds latency the realtime voice pipeline has
# to wait through, which is also when it's most likely to drop out).
_ACTIVATION_POLICY_TEMPLATE = """You are {agent_name}, a persistent AI meeting assistant with access to real, stored meeting memory tools.

ACTIVATION RULE (critical, always follow this): Only respond when a speaker explicitly addresses you by name ("{agent_name}"). If your name is not said, remain completely silent - do not respond, do not call any tools, do not generate any output at all, even if a question seems directed at an assistant in general. Wait until you are addressed by name before doing anything. Your introduction is handled separately by a chat message posted when you join - do not introduce yourself out loud.

DATE REASONING: You do not automatically know the current date. Whenever a question uses a relative date ("yesterday", "today", "last Monday", "this week"), call get_current_datetime first, compute the actual date yourself, and only then call get_previous_meetings or get_meeting with that date.

ANSWERING QUESTIONS ABOUT PAST MEETINGS: To say who attended a meeting or summarize it, call get_meeting (via get_previous_meetings first if you only have a date, not an id) and use its real participants, summary, memories, and action_items fields. Give one coherent, well-organized answer covering what's actually relevant - discussions, decisions, commitments, requirements, concerns, action items - not just a single isolated fact, unless only one fact was asked for.

NEVER INVENT INFORMATION: Only state what the tools actually returned. Never guess or make up participant names, dates, decisions, or any other detail. If something was asked for but isn't in the data, say plainly that it could not be found - do not fill the gap with a guess.

BE EFFICIENT: Use the minimum tool calls needed to answer. Don't call the same tool twice for one question. Don't use search_meeting_memory when you already know which specific meeting is being asked about - call get_meeting directly instead. Every extra tool call adds delay before you can respond.

MEETING CHAT: You have a tool called share_in_chat that posts text into the meeting's chat panel. Only call it when someone explicitly asks you to "share that in chat", "put that in the chat", "post it to chat", or the same in different words. Never call it on your own initiative, and never call it just because you called another tool - answering by voice is always the default. When you do call it, write a short, clean, natural-language message (plain sentences, no field names, no brackets, no JSON-looking syntax) - not a raw dump of what a tool returned.

Keep spoken responses concise and natural. Never read out or speak raw field names, brackets, or JSON-looking syntax either - always speak in plain natural sentences.

"""

_DEFAULT_FIRST_MESSAGE = (
    "Hi, I'm {agent_name}, your meeting companion. "
    "To talk to me, say my name and then your question - like, "
    "\"{agent_name}, what did we decide last time?\" "
    "I can tell you who attended a meeting, summarize what was discussed, and track action items. "
    "I'll stay quiet the rest of the time so I don't interrupt you."
)


def build_agent_system_prompt(agent_name: str, custom_instructions: str = "") -> str:
    """Wrap the activation/date/no-hallucination policy around whatever
    additional instructions the caller wants this agent to have.

    The join greeting is a chat message (bot_message on create_bot, see
    meetings.py) rather than something spoken - model.first_message is
    documented for pipeline-mode agents only and this app's realtime-mode
    agents silently ignore it, and prompting the model to self-initiate
    speech turned out to be unreliable in practice.
    """
    name = agent_name or "the assistant"
    policy = _ACTIVATION_POLICY_TEMPLATE.format(agent_name=name)
    return policy + (custom_instructions or "").strip()


def _redact_secrets(value):
    """Recursively strip anything that looks like a credential before it leaves our API."""
    if isinstance(value, dict):
        return {
            k: ("***redacted***" if any(p in k.lower() for p in _SECRET_KEY_PATTERN) else _redact_secrets(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_secrets(v) for v in value]
    return value


def _mask_secret(value: Optional[str]) -> Optional[str]:
    """Show enough of a credential to identify it (which key is configured, and
    that it's the right one) without ever exposing the full value. Short values
    (under 10 chars) are fully redacted rather than partially shown, since a
    short secret's middle chars aren't enough to hide the rest."""
    if not value:
        return None
    if len(value) < 10:
        return "***"
    return f"{value[:6]}…{value[-4:]}"


@router.get("/credentials")
async def get_agent_credentials(user: User = Depends(get_current_user), org_id: uuid.UUID = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)):
    """
    Masked view of the provider credentials this deployment is actually
    configured with - the MIA agent's own model/voice provider is visible
    already via GET /api/agent (MeetStream doesn't expose that provider's API
    key to us at all, they hold it), but the credentials our own backend uses
    (MeetStream API access, the LLM that extracts meeting memory, MCP auth)
    were previously invisible anywhere in the dashboard. The MCP token shown
    is this workspace's own, not a global shared one. meetstream_api_key
    reflects this member's own key if they've set one, falling back to the
    deployment's shared default otherwise - same precedence used when their
    bots actually deploy.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_by_id(org_id)
    mcp_token = org.mcp_token if org else None
    own_key = await get_meetstream_api_key(db, user.id)
    effective_key = own_key or settings.MEETSTREAM_API_KEY
    return {
        "meetstream_api_key": {
            "configured": bool(effective_key),
            "masked_value": _mask_secret(effective_key),
            "is_personal": bool(own_key),
        },
        "memory_extraction_llm": {
            "provider": settings.LLM_PROVIDER,
            "model": {
                "openai": settings.OPENAI_MODEL,
                "groq": settings.GROQ_MODEL,
                "anthropic": settings.ANTHROPIC_MODEL,
            }.get(settings.LLM_PROVIDER),
            "api_key_configured": bool({
                "openai": settings.OPENAI_API_KEY,
                "groq": settings.GROQ_API_KEY,
                "anthropic": settings.ANTHROPIC_API_KEY,
            }.get(settings.LLM_PROVIDER)),
            "masked_api_key": _mask_secret({
                "openai": settings.OPENAI_API_KEY,
                "groq": settings.GROQ_API_KEY,
                "anthropic": settings.ANTHROPIC_API_KEY,
            }.get(settings.LLM_PROVIDER)),
        },
        "mcp_auth_token": {
            "configured": bool(mcp_token),
            "masked_value": _mask_secret(mcp_token),
        },
        "mcp_server_url": settings.MCP_SERVER_URL,
    }


class ChatRelayRequest(BaseModel):
    name: Optional[str] = None
    bot: Optional[Dict[str, Any]] = None
    args: Optional[Dict[str, Any]] = None


@router.post("/chat-relay")
async def chat_relay(body: ChatRelayRequest, authorization: Optional[str] = Header(default=None), db: AsyncSession = Depends(get_db)):
    """
    Custom-function endpoint registered on the agent (see build_agent_system_prompt
    / create_mia_agent) as "share_in_chat" - the only way the agent can post text
    into the meeting chat. Exempted from the browser session gate (MeetStream
    calls this directly, not a browser) but still requires a valid workspace's
    own MCP bearer token, so it can't be hit by anyone else.
    """
    scheme, _, token = (authorization or "").partition(" ")
    org_id = await resolve_org_by_mcp_token(token, db) if scheme.lower() == "bearer" and token else None
    if not org_id:
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")

    bot_id = (body.bot or {}).get("bot_id")
    message = (body.args or {}).get("message")
    if not bot_id or not message:
        raise HTTPException(status_code=400, detail="bot.bot_id and args.message are required")

    # A valid token only proves *a* workspace, not that it's this bot's
    # workspace - without this, any workspace's own token could post into
    # another workspace's live meeting chat by supplying its bot_id.
    meeting_repo = MeetingRepository(db)
    meeting = await meeting_repo.get_by_bot_id(bot_id)
    if not meeting or meeting.organization_id != org_id:
        raise HTTPException(status_code=403, detail="This bot does not belong to your workspace.")

    try:
        await meetstream_client.send_bot_message(bot_id, message)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"MeetStream API error: {e}")

    return {"status": "sent"}


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


class ApiKeyRequest(BaseModel):
    meetstream_api_key: str


@router.put("/api-key")
async def set_meetstream_api_key(body: ApiKeyRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Store this member's own MeetStream API key so their bots/agents deploy
    and bill against their own MeetStream account instead of the deployment's
    shared default key."""
    key = body.meetstream_api_key.strip()
    if not key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="meetstream_api_key cannot be empty")
    user_repo = UserRepository(db)
    await user_repo.update_settings(user.id, {"meetstream_api_key": key})
    await db.commit()
    return {"meetstream_api_key": {"configured": True, "masked_value": _mask_secret(key)}}


@router.delete("/api-key")
async def clear_meetstream_api_key(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Remove this member's own MeetStream API key, reverting their future
    bot/agent deployments to the deployment's shared default key."""
    user_repo = UserRepository(db)
    await user_repo.update_settings(user.id, {"meetstream_api_key": None})
    await db.commit()
    return {"meetstream_api_key": {"configured": False, "masked_value": None}}


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


async def _get_owned_agent_ids(db: AsyncSession, user_id: uuid.UUID) -> set:
    """Which MeetStream agent_config_ids this specific member is allowed to see or act on."""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    return set((user.settings or {}).get("agent_config_ids") or []) if user else set()


@router.post("/release-duplicate-claims")
async def release_duplicate_claims(org_id: uuid.UUID = Depends(get_current_org_id), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    One-time fix: an earlier ownership reset left some agent_config_ids
    claimed by more than one member in this workspace at once (e.g. a member
    kept their prior active agent as their one claim, then a later claim-all
    also added it to someone else) - _find_owning_user's linear scan then
    non-deterministically blocks whichever member it hits second with
    "belongs to a different member". Strips every agent_config_id the
    calling member owns out of every OTHER member's claim list, leaving the
    calling member as sole owner. Meant to be called once and then removed,
    not a permanent endpoint.
    """
    from sqlalchemy import select as _select
    my_ids = await _get_owned_agent_ids(db, user.id)
    result = await db.execute(_select(User).where(User.organization_id == org_id, User.id != user.id))
    user_repo = UserRepository(db)
    cleared = []
    for other in result.scalars().all():
        other_ids = set((other.settings or {}).get("agent_config_ids") or [])
        overlap = other_ids & my_ids
        if overlap:
            await user_repo.update_settings(other.id, {"agent_config_ids": sorted(other_ids - overlap)})
            cleared.append({"user_id": str(other.id), "name": other.name, "removed": sorted(overlap)})
    await db.commit()
    return {"cleared": cleared}


async def _find_owning_user(db: AsyncSession, agent_config_id: str) -> Optional[uuid.UUID]:
    """Which member (if any) already has this agent_config_id in their owned
    list. Small-scale linear scan over all members - fine at this app's
    size, and only run on the activate/update write paths, not on every read."""
    from sqlalchemy import select as _select
    result = await db.execute(_select(User))
    for user in result.scalars().all():
        if agent_config_id in ((user.settings or {}).get("agent_config_ids") or []):
            return user.id
    return None


async def _require_claimable_agent(db: AsyncSession, user_id: uuid.UUID, agent_config_id: str) -> None:
    """
    Block activating or overwriting an agent another member already claimed -
    without this, anyone could hijack (activate_agent rewires its MCP token)
    or overwrite (update_current_agent rewrites its system prompt) another
    member's agent just by knowing its id. An agent nobody has claimed yet
    (created directly on MeetStream's own dashboard) can still be adopted -
    that's the one legitimate case for touching an agent_config_id this
    member didn't create themselves.
    """
    owner = await _find_owning_user(db, agent_config_id)
    if owner is not None and owner != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This agent belongs to a different member.")


async def _claim_agent(db: AsyncSession, user_id: uuid.UUID, agent_config_id: str) -> None:
    """Record that this member now owns agent_config_id, if they don't already."""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    owned_ids = list((user.settings or {}).get("agent_config_ids") or []) if user else []
    if agent_config_id not in owned_ids:
        owned_ids.append(agent_config_id)
        await user_repo.update_settings(user_id, {"agent_config_ids": owned_ids})
        await db.commit()


@router.get("")
async def get_current_agent(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Fetch this member's own currently active agent config."""
    agent_config_id = await get_active_agent_config_id(db, user.id)
    if not agent_config_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active agent configured")
    try:
        cfg = await meetstream_client.get_mia_agent(agent_config_id, api_key=await get_meetstream_api_key(db, user.id))
        return _redact_secrets(cfg)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MeetStream API error: {e}")


@router.get("/list")
async def list_agents(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    List only the MIA agent configs this member owns, flagging the active
    one. MeetStream itself has no per-person concept - every agent on the
    account is visible to any API caller - so ownership is tracked ourselves
    in User.settings["agent_config_ids"], appended to whenever this member
    creates an agent via POST /api/agent. Without this filter, a brand new
    member's Agent Settings page showed every agent anyone else had ever
    created, including their system prompts.
    """
    try:
        agents = await meetstream_client.list_mia_agents(api_key=await get_meetstream_api_key(db, user.id))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MeetStream API error: {e}")
    active_id = await get_active_agent_config_id(db, user.id)
    owned_ids = await _get_owned_agent_ids(db, user.id)
    if active_id:
        owned_ids.add(active_id)

    result = _redact_secrets(agents)
    all_configs = [cfg for cfg in result.get("agent_configs", []) if cfg.get("AgentConfigID") in owned_ids]
    for cfg in all_configs:
        cfg["IsActive"] = cfg.get("AgentConfigID") == active_id
    result["agent_configs"] = all_configs
    return result


class AgentCreateRequest(BaseModel):
    agent_name: str
    system_prompt: str = ""
    first_message: str = ""  # empty -> auto-filled with a name/how-to-use greeting
    provider: str = "openai"
    model: str = "gpt-4.1"
    voice: str = "alloy"
    temperature: float = 0.8
    mode: str = "realtime"
    response_modality: str = "text"
    tool_results_to_chat: bool = False
    activate: bool = True


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_agent(body: AgentCreateRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Create a brand new MIA agent, owned by you personally and pre-wired to
    your workspace's MCP token so it can recall your workspace's meeting
    memory immediately. Set activate=false to create without switching to it."""
    if not settings.MCP_SERVER_URL:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MCP_SERVER_URL is not configured on this deployment")

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_by_id(user.organization_id)
    if not org or not org.mcp_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This workspace has no MCP token configured")

    first_message = body.first_message.strip() or _DEFAULT_FIRST_MESSAGE.format(agent_name=body.agent_name)
    own_key = await require_meetstream_api_key(db, user.id)

    try:
        result = await meetstream_client.create_mia_agent(
            agent_name=body.agent_name,
            system_prompt=build_agent_system_prompt(body.agent_name, body.system_prompt),
            first_message=first_message,
            provider=body.provider,
            model=body.model,
            voice=body.voice,
            temperature=body.temperature,
            mode=body.mode,
            mcp_server_url=settings.MCP_SERVER_URL,
            mcp_auth_token=org.mcp_token,
            response_modality=body.response_modality,
            tool_results_to_chat=body.tool_results_to_chat,
            api_key=own_key,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MeetStream API error: {e}")

    new_id = (result.get("agent_config") or result).get("AgentConfigID")
    if new_id:
        await _claim_agent(db, user.id, new_id)
        if body.activate:
            user_repo = UserRepository(db)
            await user_repo.update_settings(user.id, {"active_agent_config_id": new_id})
            await db.commit()

    return _redact_secrets(result)


class ActivateRequest(BaseModel):
    agent_config_id: str


async def _ensure_mcp_wired(agent_config_id: str, mcp_token: Optional[str], api_key: Optional[str] = None) -> None:
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
            "name": "MeetStream Companion MCP",
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


@router.post("/activate")
async def activate_agent(body: ActivateRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Switch which agent your own new bots launch with, without touching env vars or redeploying."""
    await _require_claimable_agent(db, user.id, body.agent_config_id)
    await _claim_agent(db, user.id, body.agent_config_id)

    user_repo = UserRepository(db)
    await user_repo.update_settings(user.id, {"active_agent_config_id": body.agent_config_id})
    await db.commit()

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_by_id(user.organization_id)
    await _ensure_mcp_wired(body.agent_config_id, org.mcp_token if org else None, api_key=await require_meetstream_api_key(db, user.id))
    return {"active_agent_config_id": body.agent_config_id}


class AgentUpdateRequest(BaseModel):
    agent_config_id: Optional[str] = None
    system_prompt: Optional[str] = None
    first_message: Optional[str] = None
    voice: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    response_modality: Optional[str] = None
    tool_results_to_chat: Optional[bool] = None
    mcp_server_url: Optional[str] = None


@router.put("")
async def update_current_agent(body: AgentUpdateRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Partially update an MIA agent's model/agent blocks (your own active one,
    unless agent_config_id is given explicitly). MeetStream replaces each
    block wholesale, so we fetch the current config first and merge the
    requested fields in.
    """
    agent_config_id = body.agent_config_id or await get_active_agent_config_id(db, user.id)
    if not agent_config_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No agent_config_id provided or configured")
    if body.agent_config_id:
        # Only need to check when the caller explicitly named an id - the
        # fallback (this member's own active agent) is already implicitly
        # owned.
        await _require_claimable_agent(db, user.id, agent_config_id)
        await _claim_agent(db, user.id, agent_config_id)

    own_key = await require_meetstream_api_key(db, user.id)
    try:
        current = await meetstream_client.get_mia_agent(agent_config_id, api_key=own_key)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MeetStream API error: {e}")

    current_cfg = current.get("agent_config", current)
    current_model: Dict[str, Any] = dict(current_cfg.get("Model") or {})
    current_agent: Dict[str, Any] = dict(current_cfg.get("Agent") or {})

    if body.system_prompt is not None:
        current_model["system_prompt"] = body.system_prompt
    if body.first_message is not None:
        current_model["first_message"] = body.first_message
    if body.voice is not None:
        current_model["voice"] = body.voice
    if body.provider is not None:
        current_model["provider"] = body.provider
    if body.model is not None:
        current_model["model"] = body.model
    if body.temperature is not None:
        current_model["temperature"] = body.temperature
    if body.response_modality is not None:
        current_agent["response_modality"] = body.response_modality
    if body.tool_results_to_chat is not None:
        current_agent["tool_results_to_chat"] = body.tool_results_to_chat
    if body.mcp_server_url is not None:
        mcp_servers = list(current_agent.get("mcp_servers") or [])
        if mcp_servers:
            existing_tools = set(mcp_servers[0].get("allowed_tools") or [])
            mcp_servers[0] = {
                **mcp_servers[0],
                "url": body.mcp_server_url,
                "allowed_tools": sorted(existing_tools | {"get_current_datetime"}),
            }
        else:
            org_repo = OrganizationRepository(db)
            org = await org_repo.get_by_id(user.organization_id)
            new_server: Dict[str, Any] = {"url": body.mcp_server_url, "timeout": 10, "allowed_tools": [
                "get_current_datetime", "search_meeting_memory", "get_meeting", "get_previous_meetings", "get_action_items"
            ]}
            if org and org.mcp_token:
                new_server["headers"] = {"Authorization": f"Bearer {org.mcp_token}"}
            mcp_servers = [new_server]
        current_agent["mcp_servers"] = mcp_servers

    try:
        return await meetstream_client.update_mia_agent_settings(
            agent_config_id=agent_config_id,
            agent=current_agent,
            model=current_model,
            api_key=own_key,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MeetStream API error: {e}")
