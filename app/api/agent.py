"""
MIA Agent Configuration Endpoints.
Read and update the MeetStream MIA agent(s) attached to this account.
"""
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from app.config import settings
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


@router.get("")
async def get_current_agent():
    """Fetch the agent config this app is configured to use (MEETSTREAM_AGENT_CONFIG_ID)."""
    if not settings.MEETSTREAM_AGENT_CONFIG_ID:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No MEETSTREAM_AGENT_CONFIG_ID configured")
    try:
        cfg = await meetstream_client.get_mia_agent(settings.MEETSTREAM_AGENT_CONFIG_ID)
        return _redact_secrets(cfg)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MeetStream API error: {e}")


@router.get("/list")
async def list_agents():
    """List every MIA agent config on this MeetStream account."""
    try:
        agents = await meetstream_client.list_mia_agents()
        return _redact_secrets(agents)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MeetStream API error: {e}")


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
async def update_current_agent(body: AgentUpdateRequest):
    """
    Partially update the configured MIA agent's model/agent blocks.
    MeetStream replaces each block wholesale, so we fetch the current config first
    and merge the requested fields in before sending, rather than clobbering the rest.
    """
    agent_config_id = body.agent_config_id or settings.MEETSTREAM_AGENT_CONFIG_ID
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
