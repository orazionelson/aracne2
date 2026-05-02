"""``aracne import``: bulk-upload XML documents from a directory.

Walks the input directory for ``*.xml`` files (no recursion in v1),
checks each filename against the same regex the backend enforces, then
either skips, overwrites or fails on conflicts according to
``--on-conflict``. Concurrency uses ``concurrent.futures.ThreadPoolExecutor``
because the underlying ``httpx.Client`` is sync — running multiple
threads against the same client is supported by httpx.
"""

from __future__ import annotations

import json as _json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

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

console = Console()

# Mirrors the validator in ``backend/app/services/xmldb.py:_validate_filename``.
_FILENAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-]*\.xml$")


class OnConflict(str, Enum):
    """Policy applied when the destination already has a document with the
    same filename. ``skip`` is the default: re-importing the same corpus
    leaves existing rows untouched."""

    skip = "skip"
    overwrite = "overwrite"
    fail = "fail"


@dataclass
class _Outcome:
    filename: str
    status: str  # "uploaded" | "skipped" | "overwritten" | "failed" | "invalid_filename"
    error: str | None = None


def _list_candidates(directory: Path) -> list[Path]:
    """Return the *.xml files directly under *directory*, sorted.

    No recursion in v1 — explicit user request keeps the import
    boundary clear and avoids surprising "I dragged the wrong folder
    in" disasters.
    """
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix == ".xml")


def _classify(
    filename: str, existing: set[str], on_conflict: OnConflict
) -> str:
    """Return one of: 'create', 'overwrite', 'skip', 'conflict'."""
    if filename not in existing:
        return "create"
    if on_conflict is OnConflict.skip:
        return "skip"
    if on_conflict is OnConflict.overwrite:
        return "overwrite"
    return "conflict"


def _upload_one(
    client: ApiClient,
    *,
    collection_id: str,
    path: Path,
    existing: set[str],
    on_conflict: OnConflict,
) -> _Outcome:
    """Upload a single file according to *on_conflict*. Never raises."""
    filename = path.name
    if not _FILENAME_RE.match(filename):
        return _Outcome(
            filename=filename,
            status="invalid_filename",
            error=(
                "Filename must match ^[a-zA-Z0-9][a-zA-Z0-9_\\-]*\\.xml$ "
                "— rename it before importing."
            ),
        )

    decision = _classify(filename, existing, on_conflict)
    try:
        if decision == "skip":
            return _Outcome(filename=filename, status="skipped")
        if decision == "conflict":
            return _Outcome(
                filename=filename,
                status="failed",
                error="A document with this filename already exists.",
            )

        body = path.read_bytes()
        if decision == "create":
            client.post_multipart(
                f"/collections/{collection_id}/documents",
                files={"file": (filename, body, "application/xml")},
            )
            return _Outcome(filename=filename, status="uploaded")
        # decision == "overwrite"
        client.put(
            f"/collections/{collection_id}/documents/{filename}",
            content=body,
            content_type="application/xml",
        )
        return _Outcome(filename=filename, status="overwritten")
    except ApiError as exc:
        return _Outcome(
            filename=filename,
            status="failed",
            error=f"{exc.code}: {exc.message}",
        )
    except OSError as exc:
        return _Outcome(
            filename=filename,
            status="failed",
            error=f"Could not read file: {exc}",
        )


def import_documents(
    collection: str = typer.Option(
        ..., "--collection", help="Target collection slug or UUID."
    ),
    dir_: Path = typer.Option(
        ...,
        "--dir",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Directory containing the XML files to upload.",
    ),
    on_conflict: OnConflict = typer.Option(
        OnConflict.skip,
        "--on-conflict",
        case_sensitive=False,
        help="Behaviour when a filename already exists in the collection.",
    ),
    concurrency: int = typer.Option(
        4, "--concurrency", min=1, max=16, help="Parallel uploads."
    ),
    profile: str = typer.Option(
        DEFAULT_PROFILE, "--profile", help="Config profile name."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Print a single machine-readable JSON object instead of progress."
    ),
) -> None:
    try:
        prof = load_profile(profile)
    except ProfileNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    candidates = _list_candidates(dir_)
    if not candidates:
        typer.secho(
            f"No *.xml files in {dir_}.", fg=typer.colors.YELLOW, err=True
        )
        raise typer.Exit(code=1)

    with ApiClient(prof.host, prof.token) as client:
        # One round-trip to learn what's already on the server, then we
        # decide locally what each file needs without further GETs.
        try:
            existing_docs = client.get(f"/collections/{collection}/documents")
        except ApiError as exc:
            typer.secho(
                f"Could not list collection: {exc.code}: {exc.message}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1) from exc
        existing: set[str] = {
            (d.get("filename") if isinstance(d, dict) else "")
            for d in (existing_docs or [])
        }
        existing.discard("")

        outcomes: list[_Outcome] = []
        if json_output:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = [
                    pool.submit(
                        _upload_one,
                        client,
                        collection_id=collection,
                        path=p,
                        existing=existing,
                        on_conflict=on_conflict,
                    )
                    for p in candidates
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
                task = progress.add_task("Uploading", total=len(candidates))
                with ThreadPoolExecutor(max_workers=concurrency) as pool:
                    futures = [
                        pool.submit(
                            _upload_one,
                            client,
                            collection_id=collection,
                            path=p,
                            existing=existing,
                            on_conflict=on_conflict,
                        )
                        for p in candidates
                    ]
                    for fut in as_completed(futures):
                        outcome = fut.result()
                        outcomes.append(outcome)
                        progress.update(task, advance=1)

    counts = {
        "uploaded": sum(1 for o in outcomes if o.status == "uploaded"),
        "overwritten": sum(1 for o in outcomes if o.status == "overwritten"),
        "skipped": sum(1 for o in outcomes if o.status == "skipped"),
        "failed": sum(1 for o in outcomes if o.status == "failed"),
        "invalid_filename": sum(1 for o in outcomes if o.status == "invalid_filename"),
    }

    if json_output:
        typer.echo(
            _json.dumps(
                {
                    "ok": counts["failed"] == 0 and counts["invalid_filename"] == 0,
                    "collection": collection,
                    "on_conflict": on_conflict.value,
                    "summary": counts,
                    "results": [
                        {
                            "filename": o.filename,
                            "status": o.status,
                            "error": o.error,
                        }
                        for o in sorted(outcomes, key=lambda x: x.filename)
                    ],
                }
            )
        )
    else:
        for outcome in sorted(outcomes, key=lambda o: o.filename):
            if outcome.status in ("uploaded", "overwritten"):
                console.print(f"  [green]✓[/green] {outcome.filename} → {outcome.status}")
            elif outcome.status == "skipped":
                console.print(
                    f"  [yellow]–[/yellow] {outcome.filename} → skipped (already present)"
                )
            else:
                console.print(
                    f"  [red]✗[/red] {outcome.filename} → "
                    f"{outcome.status}: {outcome.error or ''}"
                )

        console.print()
        console.print(
            f"[bold]Summary[/bold]: "
            f"{counts['uploaded']} uploaded, "
            f"{counts['overwritten']} overwritten, "
            f"{counts['skipped']} skipped, "
            f"{counts['failed']} failed, "
            f"{counts['invalid_filename']} invalid filename"
        )

    if counts["failed"] > 0 or counts["invalid_filename"] > 0:
        raise typer.Exit(code=2)
