"""MCP JSON-RPC dispatcher.

Implements the subset of MCP we expose over Streamable HTTP:

* ``initialize`` — handshake, returns server name + version + capabilities
* ``ping``      — empty round-trip the client uses to check liveness
* ``tools/list``  — every registered tool with its JSON Schema
* ``tools/call``  — dispatch to the registered handler
* ``resources/list`` — three URI templates (collection / document / entity)
* ``resources/read`` — resolve a URI through the resources module

Anything else maps to JSON-RPC error ``-32601 Method not found``.

The MCP wire format wraps tool / resource results in a ``content``
list of ``{"type": "text", "text": "..."}`` blocks. We always return
JSON-encoded strings — the LLM client unfolds them transparently.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, DomainValidationError
from app.plugins.mcp_server.auth import McpAuthContext
from app.plugins.mcp_server.resources import (
    list_resource_templates,
    read_resource,
)
from app.plugins.mcp_server.tools.collections import (
    GET_COLLECTION_SCHEMA,
    GET_DOCUMENT_SOURCE_SCHEMA,
    LIST_COLLECTIONS_SCHEMA,
    LIST_DOCUMENTS_SCHEMA,
    get_collection,
    get_document_source,
    list_collections,
    list_documents,
)
from app.plugins.mcp_server.tools.entities import (
    FIND_ENTITY_OCCURRENCES_SCHEMA,
    SEARCH_ENTITIES_SCHEMA,
    find_entity_occurrences,
    search_entities,
)


SERVER_NAME = "aracne2"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"


ToolHandler = Callable[
    [AsyncSession, McpAuthContext, dict[str, Any]],
    Awaitable[Any],
]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    schema: dict[str, Any]
    handler: ToolHandler


TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="list_collections",
        description=(
            "List public, published collections visible to this token "
            "(scoped to the corpus). Returns slug, title, description, "
            "and publication date."
        ),
        schema=LIST_COLLECTIONS_SCHEMA,
        handler=list_collections,
    ),
    ToolSpec(
        name="get_collection",
        description=(
            "Fetch a single collection by slug. Includes description, "
            "license id, schema id, target date, and document count."
        ),
        schema=GET_COLLECTION_SCHEMA,
        handler=get_collection,
    ),
    ToolSpec(
        name="list_documents",
        description=(
            "List the TEI document filenames inside a collection."
        ),
        schema=LIST_DOCUMENTS_SCHEMA,
        handler=list_documents,
    ),
    ToolSpec(
        name="get_document_source",
        description=(
            "Return the raw TEI XML of a single document. Truncated at "
            "2 MB; the response carries a hint when truncation occurs."
        ),
        schema=GET_DOCUMENT_SOURCE_SCHEMA,
        handler=get_document_source,
    ),
    ToolSpec(
        name="search_entities",
        description=(
            "Search the named-entities index. Returns canonical form, "
            "TEI tag type, authority URI, and occurrence count for the "
            "matches that appear inside the corpus."
        ),
        schema=SEARCH_ENTITIES_SCHEMA,
        handler=search_entities,
    ),
    ToolSpec(
        name="find_entity_occurrences",
        description=(
            "List the document occurrences of one indexed entity, with "
            "the surrounding context. Filtered to the corpus."
        ),
        schema=FIND_ENTITY_OCCURRENCES_SCHEMA,
        handler=find_entity_occurrences,
    ),
]


_TOOLS_BY_NAME: dict[str, ToolSpec] = {t.name: t for t in TOOLS}


# ── JSON-RPC dispatch ─────────────────────────────────────────────────────────


def _err(req_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def _ok(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _wrap_text(payload: Any) -> list[dict[str, Any]]:
    """MCP content envelope — always JSON-encode the tool result."""
    return [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, default=str)}]


async def dispatch(
    payload: dict[str, Any],
    *,
    db: AsyncSession,
    ctx: McpAuthContext,
) -> dict[str, Any]:
    """Handle a single JSON-RPC 2.0 request and return the response object."""
    req_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}

    if method == "initialize":
        return _ok(
            req_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                },
            },
        )

    if method == "ping":
        return _ok(req_id, {})

    if method == "notifications/initialized":
        # Notification, no response — but JSON-RPC notifications carry no id.
        return {}

    if method == "tools/list":
        return _ok(
            req_id,
            {
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": t.schema,
                    }
                    for t in TOOLS
                ]
            },
        )

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        spec = _TOOLS_BY_NAME.get(name) if isinstance(name, str) else None
        if spec is None:
            return _err(req_id, -32602, f"Unknown tool: {name!r}")
        try:
            result = await spec.handler(db, ctx, args)
        except NotFoundError as exc:
            return _ok(
                req_id,
                {"content": _wrap_text({"error": str(exc)}), "isError": True},
            )
        except DomainValidationError as exc:
            return _ok(
                req_id,
                {"content": _wrap_text({"error": exc.message, "code": exc.code}), "isError": True},
            )
        return _ok(req_id, {"content": _wrap_text(result), "isError": False})

    if method == "resources/list":
        return _ok(req_id, {"resourceTemplates": list_resource_templates(), "resources": []})

    if method == "resources/read":
        uri = params.get("uri")
        if not isinstance(uri, str):
            return _err(req_id, -32602, "resources/read requires uri:str")
        try:
            entry = await read_resource(db, ctx, uri)
        except NotFoundError as exc:
            return _err(req_id, -32602, str(exc))
        return _ok(req_id, {"contents": [entry]})

    return _err(req_id, -32601, f"Method not found: {method!r}")
