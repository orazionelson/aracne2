"""MCP plugin router — single Streamable-HTTP endpoint at ``POST /mcp``.

The MCP "Streamable HTTP" transport posts a JSON-RPC 2.0 envelope to
a single URL; we authenticate via the bearer token, dispatch through
``server.dispatch``, and return the JSON response.

Notifications (requests without an ``id``) get an empty 200 — JSON-RPC
mandates "no response". Single-request and batched-array forms are
both supported.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_async_session
from app.middleware.rate_limiter import limiter
from app.plugins.mcp_server.auth import McpAuthError, authenticate
from app.plugins.mcp_server.server import dispatch


router = APIRouter(prefix="/mcp", tags=["mcp"])


def _auth_error_response(exc: McpAuthError) -> JSONResponse:
    """Render a McpAuthError as a JSON-RPC -32001 response with HTTP 401."""
    body: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": -32001, "message": exc.message},
    }
    return JSONResponse(status_code=401, content=body)


@router.post("")
@limiter.limit("60/minute")
async def mcp_endpoint(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> Response:
    """Single MCP Streamable-HTTP entrypoint — JSON-RPC 2.0 over POST."""
    try:
        ctx = await authenticate(request, db)
    except McpAuthError as exc:
        return _auth_error_response(exc)

    try:
        payload = await request.json()
    except Exception:
        body = {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "Parse error: body is not valid JSON"},
        }
        return JSONResponse(status_code=400, content=body)

    # JSON-RPC supports batch (array of requests) and single (object).
    if isinstance(payload, list):
        responses: list[dict[str, Any]] = []
        for req in payload:
            if not isinstance(req, dict):
                responses.append(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32600, "message": "Invalid Request"},
                    }
                )
                continue
            r = await dispatch(req, db=db, ctx=ctx)
            if r:  # skip empty (notification) responses
                responses.append(r)
        return JSONResponse(content=responses)

    if not isinstance(payload, dict):
        return JSONResponse(
            status_code=400,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "Invalid Request"},
            },
        )

    response = await dispatch(payload, db=db, ctx=ctx)
    if not response:
        # Notification — no body, but Streamable-HTTP wants a 202.
        return Response(status_code=202)
    return JSONResponse(content=response)


@router.get("")
async def mcp_get_handshake() -> Response:
    """Some clients probe with GET before posting. Return 200 + empty body
    so they consider the endpoint reachable; the real work happens via POST."""
    return Response(status_code=200, media_type="application/json", content="{}")
