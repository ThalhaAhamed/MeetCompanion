"""
MeetStream AI API Client.
Encapsulates all communication with the MeetStream API:
- Bot creation and lifecycle
- MIA Agent configuration
- Transcript retrieval
"""
import httpx
from typing import Optional, Dict, Any, List
from app.config import settings


def _share_in_chat_function(mcp_server_url: str, mcp_auth_token: Optional[str]) -> Dict[str, Any]:
    """
    Custom-function definition for the "share_in_chat" tool - the only path
    the agent has to post into the meeting chat, so it never happens unless
    the LLM explicitly decides to call it (i.e. only when asked). Points at
    our own /api/agent/chat-relay endpoint, which relays to MeetStream's
    send_message API using the actual live bot_id MeetStream supplies.
    """
    relay_url = mcp_server_url.replace("/mcp", "/api/agent/chat-relay")
    func: Dict[str, Any] = {
        "name": "share_in_chat",
        "description": "Post a short message into the meeting's chat panel. Only call this when a speaker explicitly asks you to share, post, or put something in the chat - never on your own initiative.",
        "url": relay_url,
        "method": "POST",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The exact plain-text message to post into the meeting chat - natural language, no field names or JSON-like syntax.",
                }
            },
            "required": ["message"],
        },
    }
    if mcp_auth_token:
        func["headers"] = {"Authorization": f"Bearer {mcp_auth_token}"}
    return func


class MeetStreamClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key or settings.MEETSTREAM_API_KEY
        self.base_url = (base_url or settings.MEETSTREAM_API_BASE_URL).rstrip("/")
        self.headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            self.headers["Authorization"] = f"Token {self.api_key}"

    def _headers(self, api_key: Optional[str] = None) -> Dict[str, str]:
        """Per-call header set - lets a caller supply their own MeetStream API
        key (e.g. a member's personal key from User.settings) instead of the
        instance-wide default, so bots/agents are created and billed against
        the member's own MeetStream account rather than whichever key this
        deployment was constructed with."""
        key = api_key or self.api_key
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Token {key}"
        return headers

    async def create_bot(
        self,
        meeting_link: str,
        agent_config_id: Optional[str] = None,
        callback_url: Optional[str] = None,
        custom_attributes: Optional[Dict[str, Any]] = None,
        bot_name: Optional[str] = None,
        bot_message: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Deploy a MeetStream bot into a meeting.
        If agent_config_id is provided, attaches the MIA agent to the bot.
        """
        payload: Dict[str, Any] = {
            "meeting_link": meeting_link,
            # MeetStream's own built-in transcription provider - unlike deepgram/
            # assemblyai/etc, it needs no separate provider API key configured on
            # the account, so it's a safe default for any MeetStream account.
            "recording_config": {
                "transcript": {
                    "provider": {
                        "meetstream": {}
                    }
                }
            },
        }

        if agent_config_id or settings.MEETSTREAM_AGENT_CONFIG_ID:
            config_id = agent_config_id or settings.MEETSTREAM_AGENT_CONFIG_ID
            payload["agent_config_id"] = config_id

        if callback_url:
            payload["callback_url"] = callback_url

        if custom_attributes:
            payload["custom_attributes"] = custom_attributes

        if bot_name:
            payload["bot_name"] = bot_name

        if bot_message:
            payload["bot_message"] = bot_message

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/bots/create_bot",
                json=payload,
                headers=self._headers(api_key),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_bot(self, bot_id: str, api_key: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve the status and metadata for a specific bot."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/bots/{bot_id}",
                headers=self._headers(api_key),
            )
            resp.raise_for_status()
            return resp.json()

    async def send_bot_message(self, bot_id: str, message: str, api_key: Optional[str] = None) -> Dict[str, Any]:
        """Post a message into the live meeting chat as the bot."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/bots/{bot_id}/send_message",
                json={"message": message},
                headers=self._headers(api_key),
            )
            resp.raise_for_status()
            return resp.json()

    async def remove_bot(self, bot_id: str, api_key: Optional[str] = None) -> Dict[str, Any]:
        """Send a stop signal to remove a bot from its meeting."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/bots/{bot_id}/remove_bot",
                headers=self._headers(api_key),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_transcript(self, transcript_id: str, raw: bool = False, api_key: Optional[str] = None) -> List[Dict[str, Any]] | Dict[str, Any]:
        """
        Retrieve formatted or raw transcript segments for a completed call.
        """
        params = {"raw": "true"} if raw else {}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/transcript/{transcript_id}/get_transcript",
                params=params,
                headers=self._headers(api_key),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_mia_agent(self, agent_config_id: str, api_key: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve a single MIA agent config by id."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/mia",
                params={"agent_config_id": agent_config_id},
                headers=self._headers(api_key),
            )
            resp.raise_for_status()
            return resp.json()

    async def list_mia_agents(self, api_key: Optional[str] = None) -> Dict[str, Any]:
        """List all MIA agent configs on this account."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/mia",
                headers=self._headers(api_key),
            )
            resp.raise_for_status()
            return resp.json()

    async def create_mia_agent(
        self,
        agent_name: str,
        system_prompt: str,
        first_message: str = "",
        provider: str = "openai",
        model: str = "gpt-4.1",
        voice: str = "alloy",
        temperature: float = 0.8,
        mode: str = "realtime",
        mcp_server_url: Optional[str] = None,
        mcp_auth_token: Optional[str] = None,
        response_modality: str = "text",
        tool_results_to_chat: bool = True,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a brand new MIA agent, pre-wired to our own MCP server the same way
        the one existing agent this app was originally configured with is wired -
        so a freshly created agent can recall meeting memory immediately, not just
        after someone manually fixes its MCP config afterward.
        """
        mcp_servers = []
        if mcp_server_url:
            server_config: Dict[str, Any] = {
                "url": mcp_server_url,
                "name": "MeetStream Companion MCP",
                "timeout": 30,
                "active": True,
                "allowed_tools": [
                    "get_current_datetime",
                    "search_meeting_memory",
                    "get_meeting",
                    "get_previous_meetings",
                    "get_action_items",
                ],
            }
            if mcp_auth_token:
                server_config["headers"] = {"Authorization": f"Bearer {mcp_auth_token}"}
            mcp_servers.append(server_config)

        custom_functions = []
        if mcp_server_url:
            custom_functions.append(_share_in_chat_function(mcp_server_url, mcp_auth_token))

        payload = {
            "agent_name": agent_name,
            "mode": mode,
            "model": {
                "provider": provider,
                "model": model,
                "voice": voice,
                "system_prompt": system_prompt,
                "first_message": first_message,
                "temperature": temperature,
            },
            "agent": {
                "mcp_servers": mcp_servers,
                "custom_functions": custom_functions,
                "tool_results_to_chat": tool_results_to_chat,
                "response_modality": response_modality,
            },
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/mia",
                json=payload,
                headers=self._headers(api_key),
            )
            resp.raise_for_status()
            return resp.json()

    async def update_mia_agent_settings(
        self,
        agent_config_id: str,
        agent: Optional[Dict[str, Any]] = None,
        model: Optional[Dict[str, Any]] = None,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Partial update of an existing MIA agent config. `agent` and `model` are merged
        top-level into the PUT payload; MeetStream replaces each nested block wholesale
        (no deep-merge), so callers should pass full blocks, not sparse diffs.
        """
        payload: Dict[str, Any] = {"agent_config_id": agent_config_id}
        if agent is not None:
            payload["agent"] = agent
        if model is not None:
            payload["model"] = model

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.put(
                f"{self.base_url}/api/v1/mia",
                json=payload,
                headers=self._headers(api_key),
            )
            resp.raise_for_status()
            return resp.json()

    async def create_or_update_mia_agent(
        self,
        agent_name: str,
        system_prompt: str,
        mcp_server_url: Optional[str] = None,
        mcp_auth_token: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
        voice: str = "nova",
        agent_config_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new MIA agent (POST) or update an existing one's MCP wiring (PUT)
        with our MCP server, per MeetStream's create-agent-config / update-agent-config docs.
        Updating is a partial update - only agent.mcp_servers/response_type/first_message
        are touched, leaving the agent's existing model/voice/transcriber config alone.
        """
        mcp_servers = []
        if mcp_server_url:
            server_config: Dict[str, Any] = {
                "url": mcp_server_url,
                "allowed_tools": allowed_tools or [
                    "get_current_datetime",
                    "search_meeting_memory",
                    "get_meeting",
                    "get_previous_meetings",
                    "get_action_items"
                ],
                "timeout": 10
            }
            if mcp_auth_token:
                server_config["headers"] = {"Authorization": f"Bearer {mcp_auth_token}"}
            mcp_servers.append(server_config)

        agent_block = {
            # MeetStream docs: response_type must be "action" for the agent
            # to actually invoke tools from mcp_servers during the call.
            "response_type": "action" if mcp_servers else "voice",
            "first_message": "Hello! I am your persistent meeting companion. I remember past discussions, action items, and decisions.",
            "mcp_servers": mcp_servers,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            if agent_config_id:
                payload = {"agent_config_id": agent_config_id, "agent": agent_block}
                resp = await client.put(
                    f"{self.base_url}/api/v1/mia",
                    json=payload,
                    headers=self.headers,
                )
            else:
                payload = {
                    "agent_name": agent_name,
                    "mode": "pipeline",
                    "model": {
                        "provider": "openai",
                        "model": "gpt-4.1",
                        "system_prompt": system_prompt,
                    },
                    "voice": {
                        "provider": "openai",
                        "voice_id": voice,
                    },
                    "transcriber": {
                        "provider": "deepgram",
                        "model": "nova-3",
                        "language": "en",
                    },
                    "agent": agent_block,
                }
                resp = await client.post(
                    f"{self.base_url}/api/v1/mia",
                    json=payload,
                    headers=self.headers,
                )
            resp.raise_for_status()
            return resp.json()


meetstream_client = MeetStreamClient()
