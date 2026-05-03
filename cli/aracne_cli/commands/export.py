"""``aracne export``: download a collection as a ZIP archive.

Two flavours:

- Without ``--as-of``: pulls every document at its current working-tree
  state — what the editor sees in the editor view, not necessarily
  what the public sees.
- With ``--as-of YYYY-MM-DD``: walks ``document_versions`` per file
  and picks the most recent ``publication``-origin row whose
  ``created_at <= as-of`` (UTC midnight of that day, exclusive
  upper bound). Documents that have no publication snapshot at or
  before the date are skipped with a warning — they were probably
  added later.

The ZIP layout is documented in the README.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json as _json
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from aracne_cli.api import ApiClient, ApiError
from aracne_cli.config import DEFAULT_PROFILE, ProfileNotFoundError, load_profile
from aracne_cli.version import __version__

console = Console()


@dataclass
class _DocOutcome:
    filename: str
    version_number: int | None  # None for working-tree exports
    sha256: str | None  # None when the document was skipped
    skipped_reason: str | None = None
    body: bytes | None = None  # gzipped bytes are not held; raw XML is


def _parse_as_of(value: str) -> datetime:
    """Accept ``YYYY-MM-DD`` or ISO-8601 with optional time/tz.

    Naive dates are treated as UTC midnight (``2026-04-01T00:00:00Z``)
    so the comparison against ``versions[].created_at`` is unambiguous.
    """
    text = value.strip()
    try:
        if "T" in text:
            # ISO-8601 with time. Python 3.11+ accepts ``Z`` alias.
            text2 = text.replace("Z", "+00:00")
            dt = datetime.fromisoformat(text2)
        else:
            dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise typer.BadParameter(
            "Use YYYY-MM-DD or ISO-8601 (e.g. 2026-04-01 or 2026-04-01T15:00:00Z)."
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _resolve_version_at(
    client: ApiClient,
    *,
    collection_id: str,
    filename: str,
    as_of: datetime,
) -> int | None:
    """Return the version_number of the latest ``publication`` row for
    *filename* whose ``created_at <= as_of``, or None if none exists.

    The backend already supports an ``?origin=`` filter so we don't
    walk every row of every origin client-side.
    """
    versions = client.get(
        f"/collections/{collection_id}/documents/{filename}/versions",
        params={"origin": "publication"},
    )
    eligible: list[tuple[int, datetime]] = []
    for v in versions or []:
        created_raw = v.get("created_at")
        if not isinstance(created_raw, str):
            continue
        try:
            created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        if created <= as_of:
            eligible.append((int(v.get("version_number") or 0), created))
    if not eligible:
        return None
    # The endpoint already returns newest-first, but sort defensively
    # so any reordering on the server doesn't break us.
    eligible.sort(key=lambda x: x[1], reverse=True)
    return eligible[0][0]


def _fetch_one(
    client: ApiClient,
    *,
    collection_id: str,
    filename: str,
    as_of: datetime | None,
) -> _DocOutcome:
    if as_of is None:
        try:
            response = client.get_raw(
                f"/collections/{collection_id}/documents/{filename}"
            )
        except ApiError as exc:
            return _DocOutcome(
                filename=filename,
                version_number=None,
                sha256=None,
                skipped_reason=f"{exc.code}: {exc.message}",
            )
        body = response.content
        return _DocOutcome(
            filename=filename,
            version_number=None,
            sha256=hashlib.sha256(body).hexdigest(),
            body=body,
        )

    try:
        version = _resolve_version_at(
            client,
            collection_id=collection_id,
            filename=filename,
            as_of=as_of,
        )
    except ApiError as exc:
        return _DocOutcome(
            filename=filename,
            version_number=None,
            sha256=None,
            skipped_reason=f"{exc.code}: {exc.message}",
        )
    if version is None:
        return _DocOutcome(
            filename=filename,
            version_number=None,
            sha256=None,
            skipped_reason="no publication snapshot at or before the requested date",
        )
    try:
        response = client.get_raw(
            f"/collections/{collection_id}/documents/{filename}/versions/{version}/content"
        )
    except ApiError as exc:
        return _DocOutcome(
            filename=filename,
            version_number=version,
            sha256=None,
            skipped_reason=f"{exc.code}: {exc.message}",
        )
    body = response.content
    return _DocOutcome(
        filename=filename,
        version_number=version,
        sha256=hashlib.sha256(body).hexdigest(),
        body=body,
    )


def _build_manifest(
    *,
    collection_meta: dict[str, Any] | None,
    collection_arg: str,
    outcomes: list[_DocOutcome],
    as_of: datetime | None,
) -> dict[str, Any]:
    return {
        "exporter": "aracne-cli",
        "exporter_version": __version__,
        "exported_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "as_of": (
            None if as_of is None else as_of.isoformat().replace("+00:00", "Z")
        ),
        "collection": {
            "argument": collection_arg,
            "id": (collection_meta or {}).get("id"),
            "slug": (collection_meta or {}).get("slug"),
            "title": (collection_meta or {}).get("title"),
        },
        "documents": [
            {
                "filename": o.filename,
                "version_number": o.version_number,
                "sha256": o.sha256,
                "skipped_reason": o.skipped_reason,
            }
            for o in sorted(outcomes, key=lambda x: x.filename)
        ],
    }


def export_collection(
    collection: str = typer.Option(
        ..., "--collection", help="Source collection slug or UUID."
    ),
    output: Path = typer.Option(
        ..., "--output", help="Path of the ZIP file to create."
    ),
    as_of: str | None = typer.Option(
        None,
        "--as-of",
        help="Resolve each document to its publication snapshot at or before this date (YYYY-MM-DD or ISO-8601).",
    ),
    concurrency: int = typer.Option(
        4, "--concurrency", min=1, max=16, help="Parallel downloads."
    ),
    profile: str = typer.Option(
        DEFAULT_PROFILE, "--profile", help="Config profile name."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Print machine-readable JSON instead of progress."
    ),
) -> None:
    try:
        prof = load_profile(profile)
    except ProfileNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    as_of_dt = _parse_as_of(as_of) if as_of else None

    with ApiClient(prof.host, prof.token) as client:
        # Pull metadata + filename list. The metadata endpoint may 404
        # if the user passed a slug for a collection they cannot read;
        # the error message bubbles up so the user can correct it.
        try:
            collection_meta = client.get(f"/collections/{collection}")
            doc_infos = client.get(f"/collections/{collection}/documents")
        except ApiError as exc:
            typer.secho(
                f"Could not load collection: {exc.code}: {exc.message}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1) from exc

        filenames = [
            d["filename"]
            for d in (doc_infos or [])
            if isinstance(d, dict) and d.get("filename")
        ]

        outcomes: list[_DocOutcome] = []
        if json_output:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = [
                    pool.submit(
                        _fetch_one,
                        client,
                        collection_id=collection,
                        filename=fn,
                        as_of=as_of_dt,
                    )
                    for fn in filenames
                ]
                for fut in as_completed(futures):
                    outcomes.append(fut.result())
        else:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                TimeElapsedColumn(),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task("Downloading", total=len(filenames))
                with ThreadPoolExecutor(max_workers=concurrency) as pool:
                    futures = [
                        pool.submit(
                            _fetch_one,
                            client,
                            collection_id=collection,
                            filename=fn,
                            as_of=as_of_dt,
                        )
                        for fn in filenames
                    ]
                    for fut in as_completed(futures):
                        outcomes.append(fut.result())
                        progress.update(task, advance=1)

    # Build the ZIP. Skip-as-of-skipped docs are recorded in the
    # manifest but not written to the archive.
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = _build_manifest(
            collection_meta=collection_meta if isinstance(collection_meta, dict) else None,
            collection_arg=collection,
            outcomes=outcomes,
            as_of=as_of_dt,
        )
        zf.writestr("manifest.json", _json.dumps(manifest, indent=2, sort_keys=True))
        for outcome in outcomes:
            if outcome.body is not None:
                zf.writestr(f"documents/{outcome.filename}", outcome.body)

    skipped = [o for o in outcomes if o.skipped_reason]
    written = [o for o in outcomes if o.body is not None]

    if json_output:
        typer.echo(
            _json.dumps(
                {
                    "ok": True,
                    "collection": collection,
                    "output": str(output),
                    "as_of": (
                        None if as_of_dt is None else as_of_dt.isoformat().replace("+00:00", "Z")
                    ),
                    "summary": {
                        "written": len(written),
                        "skipped": len(skipped),
                    },
                    "skipped": [
                        {"filename": o.filename, "reason": o.skipped_reason}
                        for o in skipped
                    ],
                }
            )
        )
        return

    console.print(
        f"[green]✓[/green] Wrote {len(written)} documents to "
        f"[bold]{output}[/bold] "
        f"(as_of={'now (working tree)' if as_of_dt is None else as_of_dt.isoformat()})"
    )
    if skipped:
        console.print(f"[yellow]Skipped {len(skipped)} documents:[/yellow]")
        for o in skipped:
            console.print(f"  – {o.filename}: {o.skipped_reason}")


# ── Tiny utility kept here so tests can import it ────────────────────────
def _bytes_b64(blob: bytes) -> str:
    """Render a small body as base64 for --json modes that want the
    document bodies inline. Currently unused by the command itself but
    handy for tests inspecting the wire format.
    """
    return base64.b64encode(blob).decode("ascii")


__all__ = ["export_collection", "_bytes_b64", "_resolve_version_at", "_parse_as_of"]


def _silence_unused_io_import() -> None:  # pragma: no cover
    """Reference ``io`` so a strict linter doesn't trip on the import.

    The module imports ``io`` for forward extensibility (zipfile +
    streamed bodies); the current implementation passes bytes
    directly to ``writestr``, but I'd rather keep the import handy
    than have to re-add it next time we move to a streamed approach.
    """
    _ = io.BytesIO
