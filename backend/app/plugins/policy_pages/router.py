"""HTTP entrypoint for ``policy_pages`` — Phase PP-A skeleton.

The actual REST surface lands in Phase PP-F once the engine,
templates, pre-fill helpers, and PolicyManager role are in place.
This module exists in Phase A so the plugin module is importable
and the loader can hot-mount the (currently empty) router on
activate.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/policy-pages", tags=["policy_pages"])
