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
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database.connection import get_db
from app.database.repositories import OrganizationRepository
from app.services.meetstream import meetstream_client

router = APIRouter(prefix="/api/agent", tags=["agent"])

_SECRET_KEY_PATTERN = ("key", "secret", "token", "password", "authorization")


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


async def get_active_agent_config_id(db: AsyncSession) -> Optional[str]:
    """The agent new bots should launch with: org-settings override if set, else the
    MEETSTREAM_AGENT_CONFIG_ID this app was originally configured with."""
    org_id = uuid.UUID(settings.DEFAULT_ORG_ID)
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_by_id(org_id)
    override = (org.settings or {}).get("active_agent_config_id") if org else None
    return override or settings.MEETSTREAM_AGENT_CONFIG_ID or None


@router.get("")
async def get_current_agent(db: AsyncSession = Depends(get_db)):
    """Fetch the currently active agent config."""
    agent_config_id = await get_active_agent_config_id(db)
    if not agent_config_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active agent configured")
    try:
        cfg = await meetstream_client.get_mia_agent(agent_config_id)
        return _redact_secrets(cfg)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MeetStream API error: {e}")


@router.get("/list")
async def list_agents(db: AsyncSession = Depends(get_db)):
    """List every MIA agent config on this MeetStream account, flagging the active one."""
    try:
        agents = await meetstream_client.list_mia_agents()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MeetStream API error: {e}")
    active_id = await get_active_agent_config_id(db)
    result = _redact_secrets(agents)
    for cfg in result.get("agent_configs", []):
        cfg["IsActive"] = cfg.get("AgentConfigID") == active_id
    return result


class AgentCreateRequest(BaseModel):
    agent_name: str
    system_prompt: str = "You are a helpful AI meeting assistant with access to persistent meeting memory tools. Keep responses concise and natural."
    first_message: str = "Hello! I am your persistent meeting companion. I remember past discussions, action items, and decisions."
    provider: str = "openai"
    model: str = "gpt-4.1"
    voice: str = "alloy"
    temperature: float = 0.8
    mode: str = "realtime"
    response_modality: str = "text"
    tool_results_to_chat: bool = True
    activate: bool = True


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_agent(body: AgentCreateRequest, db: AsyncSession = Depends(get_db)):
    """Create a brand new MIA agent, pre-wired to our MCP server so it can recall
    meeting memory immediately. Set activate=false to create without switching to it."""
    if not settings.MCP_SERVER_URL:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MCP_SERVER_URL is not configured on this deployment")

    try:
        result = await meetstream_client.create_mia_agent(
            agent_name=body.agent_name,
            system_prompt=body.system_prompt,
            first_message=body.first_message,
            provider=body.provider,
            model=body.model,
            voice=body.voice,
            temperature=body.temperature,
            mode=body.mode,
            mcp_server_url=settings.MCP_SERVER_URL,
            mcp_auth_token=settings.MCP_AUTH_TOKEN,
            response_modality=body.response_modality,
            tool_results_to_chat=body.tool_results_to_chat,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MeetStream API error: {e}")

    new_id = (result.get("agent_config") or result).get("AgentConfigID")
    if body.activate and new_id:
        org_id = uuid.UUID(settings.DEFAULT_ORG_ID)
        org_repo = OrganizationRepository(db)
        await org_repo.update_settings(org_id, {"active_agent_config_id": new_id})
        await db.commit()

    return _redact_secrets(result)


class ActivateRequest(BaseModel):
    agent_config_id: str


@router.post("/activate")
async def activate_agent(body: ActivateRequest, db: AsyncSession = Depends(get_db)):
    """Switch which agent new bots launch with, without touching env vars or redeploying."""
    org_id = uuid.UUID(settings.DEFAULT_ORG_ID)
    org_repo = OrganizationRepository(db)
    org = await org_repo.update_settings(org_id, {"active_agent_config_id": body.agent_config_id})
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    await db.commit()
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
async def update_current_agent(body: AgentUpdateRequest, db: AsyncSession = Depends(get_db)):
    """
    Partially update an MIA agent's model/agent blocks (the active one, unless
    agent_config_id is given explicitly). MeetStream replaces each block wholesale,
    so we fetch the current config first and merge the requested fields in.
    """
    agent_config_id = body.agent_config_id or await get_active_agent_config_id(db)
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
            mcp_servers[0] = {**mcp_servers[0], "url": body.mcp_server_url}
        else:
            mcp_servers = [{"url": body.mcp_server_url, "timeout": 10, "allowed_tools": [
                "search_meeting_memory", "get_meeting", "get_previous_meetings", "get_action_items"
            ]}]
        current_agent["mcp_servers"] = mcp_servers

    try:
        return await meetstream_client.update_mia_agent_settings(
            agent_config_id=agent_config_id,
            agent=current_agent,
            model=current_model,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MeetStream API error: {e}")
