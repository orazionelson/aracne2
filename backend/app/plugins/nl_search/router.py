"""HTTP entrypoint for ``nl_search`` — Phase NLS-A skeleton.

The actual SSE endpoint lands in Phase NLS-D once the orchestrator and
the provider adapters are in place. This module exists in Phase A so
the plugin module is importable, the loader can mount the (currently
empty) router on activate, and the descriptor / settings work end-to-
end before any LLM code runs.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/nl-search", tags=["nl_search"])
