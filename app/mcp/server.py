"""
MCP (Model Context Protocol) Server for MeetStream MIA.
Exposes Streamable HTTP endpoint at /mcp handling JSON-RPC 2.0 requests:
- initialize
- tools/list
- tools/call
Also provides REST compatibility endpoints.
"""
import uuid
import json
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import JSONResponse, Response
from app.mcp.auth import verify_mcp_token
from app.mcp.tools import MCP_TOOL_DEFINITIONS, execute_tool

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.post("")
async def handle_mcp_jsonrpc(
    request: Request,
    org_id: uuid.UUID = Depends(verify_mcp_token),
):
    """
    Standard MCP Streamable HTTP JSON-RPC 2.0 endpoint.
    Handles 'initialize', 'tools/list', and 'tools/call'.
    """
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON in request: {str(e)}"
        )

    jsonrpc_id = body.get("id")
    method = body.get("method")
    params = body.get("params", {})

    # 1. Initialize
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": jsonrpc_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False}
                },
                "serverInfo": {
                    "name": "meetstream-companion-mcp",
                    "version": "1.0.0"
                }
            }
        }

    # 2. Tools List
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": jsonrpc_id,
            "result": {
                "tools": MCP_TOOL_DEFINITIONS
            }
        }

    # 3. Tools Call
    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        try:
            tool_output = await execute_tool(org_id, tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(tool_output, indent=2)
                        }
                    ],
                    "isError": "error" in tool_output
                }
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Tool execution failed: {str(e)}"
                        }
                    ],
                    "isError": True
                }
            }

    # 4. Notifications or unknown methods
    elif method and method.startswith("notifications/"):
        # A bare JSONResponse(content=None) serializes to a 4-byte b"null" body,
        # but a 204 must have zero body bytes - Starlette drops the Content-Length
        # header for 204 while still sending those bytes, so uvicorn raises
        # "Response content longer than Content-Length" and kills the connection,
        # breaking the MCP session right after the standard post-initialize
        # notifications/initialized message. Response() with no content is the
        # only correct way to send an empty body here.
        return Response(status_code=204)

    else:
        return {
            "jsonrpc": "2.0",
            "id": jsonrpc_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}"
            }
        }


# ---- REST Convenience Endpoints ----

@router.get("/tools")
async def list_tools_rest(org_id: uuid.UUID = Depends(verify_mcp_token)):
    """REST endpoint to inspect available MCP tools."""
    return {"tools": MCP_TOOL_DEFINITIONS}


@router.post("/tools/{tool_name}")
async def call_tool_rest(
    tool_name: str,
    arguments: Dict[str, Any],
    org_id: uuid.UUID = Depends(verify_mcp_token),
):
    """REST endpoint to invoke a specific tool."""
    result = await execute_tool(org_id, tool_name, arguments)
    return result
