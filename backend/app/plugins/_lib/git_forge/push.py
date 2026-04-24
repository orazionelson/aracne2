"""Forge-agnostic orchestration helpers.

Each plugin's service layer calls ``push_collection_to_forge`` after
building a ``DepositManifest`` from the collection's TEI files. The
helpers here handle the per-link PAT override vs. global plugin PAT
resolution and provide a uniform error surface.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.encryption import decrypt_value
from app.plugins._lib.git_forge.adapter import GitForgeAdapter
from app.plugins._lib.git_forge.errors import GitForgeError
from app.plugins._lib.git_forge.models import (
    CommitResult,
    DepositManifest,
    RepoRef,
)


@dataclass(frozen=True)
class TokenSources:
    """Inputs for :func:`resolve_token`.

    ``override_ciphertext`` is the per-link PAT column (nullable,
    Fernet-encrypted when set); ``global_ciphertext`` is the same
    thing at plugin scope; ``jwt_secret`` is the Fernet derivation
    key — the same value used by ``app.core.encryption``.
    """

    override_ciphertext: str | None
    global_ciphertext: str | None
    jwt_secret: str


def resolve_token(sources: TokenSources) -> str | None:
    """Return the first usable PAT, or ``None`` when neither scope
    is populated. Per-link override wins over plugin-global PAT."""
    for ciphertext in (sources.override_ciphertext, sources.global_ciphertext):
        if not ciphertext:
            continue
        try:
            value = decrypt_value(ciphertext, sources.jwt_secret).strip()
        except Exception:
            # Malformed ciphertext — skip and try the next source.
            continue
        if value:
            return value
    return None


async def push_manifest(
    *,
    adapter: GitForgeAdapter,
    repo: RepoRef,
    manifest: DepositManifest,
    token: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> CommitResult:
    """Thin wrapper over ``adapter.push_manifest`` so services depend
    on the orchestrator rather than the adapter directly — keeps the
    future retry / circuit-breaker logic in one place."""
    return await adapter.push_manifest(
        repo=repo, manifest=manifest, token=token, transport=transport,
    )


# Re-export for consumers
__all__ = [
    "GitForgeError",
    "TokenSources",
    "push_manifest",
    "resolve_token",
]
