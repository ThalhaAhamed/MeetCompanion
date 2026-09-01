"""
Authentication and Authorization middleware for MCP Tool endpoints.
Ensures every MCP request is securely bound to an authenticated Organization.
"""
import uuid
from typing import Optional
from fastapi import Header, HTTPException, status
from app.config import settings


def verify_mcp_token(authorization: Optional[str] = Header(None)) -> uuid.UUID:
    """
    Validates Bearer token from MCP requests.
    Returns the authenticated Organization UUID.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header for MCP server",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization scheme. Expected 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate token
    if token != settings.MCP_AUTH_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid MCP authorization token",
        )

    # In production, look up organization_id from token/api_key table
    return uuid.UUID(settings.DEFAULT_ORG_ID)
