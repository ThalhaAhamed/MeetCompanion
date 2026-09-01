"""
Unit and integration tests for MCP Protocol server and tool authorization.
"""
import pytest
import uuid
from app.config import settings
from app.mcp.tools import MCP_TOOL_DEFINITIONS


@pytest.mark.asyncio
async def test_mcp_unauthorized(client):
    # No Authorization header
    resp = await client.post("/mcp", json={"method": "initialize"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_mcp_forbidden_token(client):
    # Invalid Bearer token
    headers = {"Authorization": "Bearer wrong_token_xyz"}
    resp = await client.post("/mcp", json={"method": "initialize"}, headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_mcp_initialize(client):
    headers = {"Authorization": f"Bearer {settings.MCP_AUTH_TOKEN}"}
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {}
    }
    resp = await client.post("/mcp", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 1
    assert "capabilities" in data["result"]
    assert "tools" in data["result"]["capabilities"]


@pytest.mark.asyncio
async def test_mcp_tools_list(client):
    headers = {"Authorization": f"Bearer {settings.MCP_AUTH_TOKEN}"}
    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    resp = await client.post("/mcp", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    tools = data["result"]["tools"]
    tool_names = [t["name"] for t in tools]

    assert "search_meeting_memory" in tool_names
    assert "get_meeting" in tool_names
    assert "get_previous_meetings" in tool_names
    assert "get_action_items" in tool_names


@pytest.mark.asyncio
async def test_mcp_rest_tools_list(client):
    headers = {"Authorization": f"Bearer {settings.MCP_AUTH_TOKEN}"}
    resp = await client.get("/mcp/tools", headers=headers)
    assert resp.status_code == 200
    tools = resp.json()["tools"]
    assert len(tools) == len(MCP_TOOL_DEFINITIONS)
    tool_names = [t["name"] for t in tools]
    # Read tools
    assert "search_meeting_memory" in tool_names
    assert "get_meeting" in tool_names
    assert "get_previous_meetings" in tool_names
    assert "get_action_items" in tool_names
    # Write tools
    assert "add_meeting_memory" in tool_names
    assert "add_meeting_note" in tool_names
    assert "create_action_item" in tool_names
    assert "update_action_item" in tool_names
