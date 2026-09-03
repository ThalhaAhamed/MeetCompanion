"""
MIA Agent Configuration Endpoints.
Read, create, update, and switch between the MeetStream MIA agent(s) on this
account. "Active" agent (the one new bots launch with) is resolved from the
org's settings JSONB (set via /activate) with a fallback to the
MEETSTREAM_AGENT_CONFIG_ID env var - so switching which agent is active
doesn't require an env var change + redeploy.
"""
import uuid
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database.connection import get_db
from app.database.repositories import OrganizationRepository
from app.services.meetstream import meetstream_client, _share_in_chat_function
from app.api.deps import get_current_org_id
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
async def get_agent_credentials(org_id: uuid.UUID = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)):
    """
    Masked view of the provider credentials this deployment is actually
    configured with - the MIA agent's own model/voice provider is visible
    already via GET /api/agent (MeetStream doesn't expose that provider's API
    key to us at all, they hold it), but the credentials our own backend uses
    (MeetStream API access, the LLM that extracts meeting memory, MCP auth)
    were previously invisible anywhere in the dashboard. The MCP token shown
    is this workspace's own, not a global shared one.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_by_id(org_id)
    mcp_token = org.mcp_token if org else None
    return {
        "meetstream_api_key": {
            "configured": bool(settings.MEETSTREAM_API_KEY),
            "masked_value": _mask_secret(settings.MEETSTREAM_API_KEY),
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
    if scheme.lower() != "bearer" or not token or not await resolve_org_by_mcp_token(token, db):
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")

    bot_id = (body.bot or {}).get("bot_id")
    message = (body.args or {}).get("message")
    if not bot_id or not message:
        raise HTTPException(status_code=400, detail="bot.bot_id and args.message are required")

    try:
        await meetstream_client.send_bot_message(bot_id, message)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"MeetStream API error: {e}")

    return {"status": "sent"}


async def get_active_agent_config_id(db: AsyncSession, org_id: uuid.UUID) -> Optional[str]:
    """The agent new bots should launch with: this workspace's org-settings
    override if set, else the MEETSTREAM_AGENT_CONFIG_ID this app was
    originally configured with (only meaningful for the original default
    workspace, since that's a single global env var)."""
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_by_id(org_id)
    override = (org.settings or {}).get("active_agent_config_id") if org else None
    if override:
        return override
    if str(org_id) == settings.DEFAULT_ORG_ID:
        return settings.MEETSTREAM_AGENT_CONFIG_ID or None
    return None


@router.get("")
async def get_current_agent(org_id: uuid.UUID = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)):
    """Fetch this workspace's currently active agent config."""
    agent_config_id = await get_active_agent_config_id(db, org_id)
    if not agent_config_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active agent configured")
    try:
        cfg = await meetstream_client.get_mia_agent(agent_config_id)
        return _redact_secrets(cfg)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MeetStream API error: {e}")


@router.get("/list")
async def list_agents(org_id: uuid.UUID = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)):
    """
    List MIA agent configs, flagging this workspace's active one. Note: this
    still lists every agent on the underlying MeetStream account (MeetStream
    itself has no workspace concept), not just ones this workspace created -
    only the active-agent flag and MCP wiring are workspace-scoped.
    """
    try:
        agents = await meetstream_client.list_mia_agents()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MeetStream API error: {e}")
    active_id = await get_active_agent_config_id(db, org_id)
    result = _redact_secrets(agents)
    for cfg in result.get("agent_configs", []):
        cfg["IsActive"] = cfg.get("AgentConfigID") == active_id
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
async def create_agent(body: AgentCreateRequest, org_id: uuid.UUID = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)):
    """Create a brand new MIA agent, pre-wired to this workspace's own MCP
    token so it can recall this workspace's meeting memory immediately. Set
    activate=false to create without switching to it."""
    if not settings.MCP_SERVER_URL:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MCP_SERVER_URL is not configured on this deployment")

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_by_id(org_id)
    if not org or not org.mcp_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This workspace has no MCP token configured")

    first_message = body.first_message.strip() or _DEFAULT_FIRST_MESSAGE.format(agent_name=body.agent_name)

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
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MeetStream API error: {e}")

    new_id = (result.get("agent_config") or result).get("AgentConfigID")
    if body.activate and new_id:
        await org_repo.update_settings(org_id, {"active_agent_config_id": new_id})
        await db.commit()

    return _redact_secrets(result)


class ActivateRequest(BaseModel):
    agent_config_id: str


async def _ensure_mcp_wired(agent_config_id: str, mcp_token: Optional[str]) -> None:
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
        current = await meetstream_client.get_mia_agent(agent_config_id)
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
        await meetstream_client.update_mia_agent_settings(agent_config_id=agent_config_id, agent=current_agent)
    except Exception:
        pass


@router.post("/activate")
async def activate_agent(body: ActivateRequest, org_id: uuid.UUID = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)):
    """Switch which agent this workspace's new bots launch with, without touching env vars or redeploying."""
    org_repo = OrganizationRepository(db)
    org = await org_repo.update_settings(org_id, {"active_agent_config_id": body.agent_config_id})
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    await db.commit()
    await _ensure_mcp_wired(body.agent_config_id, org.mcp_token)
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
async def update_current_agent(body: AgentUpdateRequest, org_id: uuid.UUID = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)):
    """
    Partially update an MIA agent's model/agent blocks (this workspace's
    active one, unless agent_config_id is given explicitly). MeetStream
    replaces each block wholesale, so we fetch the current config first and
    merge the requested fields in.
    """
    agent_config_id = body.agent_config_id or await get_active_agent_config_id(db, org_id)
    if not agent_config_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No agent_config_id provided or configured")

    try:
        current = await meetstream_client.get_mia_agent(agent_config_id)
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
            org = await org_repo.get_by_id(org_id)
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
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MeetStream API error: {e}")
