"""collection_validation — service for full-collection XML validation runs.

Starts an asyncio background task that validates every document in a collection
against the attached TEI schema, storing incremental progress in PostgreSQL so
the frontend can poll for live updates.

The background task opens its own AsyncSession (independent of the request
session) and commits after each document so progress is immediately visible.
The request session commits explicitly before the task is launched to ensure
the run row is readable by the task right away.
"""

import asyncio
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainValidationError, NotFoundError
from app.db.existdb import existdb_client
from app.db.postgres import AsyncSessionLocal
from app.models.collection_validation_run import CollectionValidationRun, ValidationRunStatus
from app.models.tei_schema import TeiSchema
from app.models.user import User
from app.schemas.collection_validation import CollectionValidationRunResponse
from app.services.schemas import validate_xml
from app.services.xmldb import _assert_eic, _get_or_404, _natural_sort_key

logger = structlog.get_logger()


async def start_validation_run(
    db: AsyncSession,
    collection_id: str,
    actor: User,
    role: str,
) -> CollectionValidationRunResponse:
    """Create a validation run record and launch the background task.

    Commits the session explicitly before launching the task so the run row
    is visible to the background task's independent DB session immediately.
    """
    _assert_eic(role)
    col = await _get_or_404(db, collection_id)

    if not col.schema_id:
        raise DomainValidationError(
            "NO_SCHEMA", "This collection has no TEI schema attached."
        )
    schema = await db.get(TeiSchema, col.schema_id)
    if schema is None or not schema.validation_filename:
        raise DomainValidationError(
            "NO_VALIDATION_FILE", "The schema attached to this collection has no validation file."
        )

    run = CollectionValidationRun(
        collection_id=col.id,
        started_by=actor.id,
        schema_id=col.schema_id,
        status=ValidationRunStatus.pending,
        started_at=datetime.now(UTC),
    )
    db.add(run)
    await db.flush()  # populate run.id

    # Commit before launching the task — the task needs to read this row.
    await db.commit()

    asyncio.create_task(
        _run_validation_task(run.id, col.slug, str(col.schema_id)),
        name=f"validate-{col.slug}-run-{run.id}",
    )
    logger.info(
        "collection_validation_started",
        slug=col.slug,
        run_id=run.id,
        actor=actor.username,
    )
    return CollectionValidationRunResponse.model_validate(run)


async def get_validation_run(
    db: AsyncSession,
    collection_id: str,
    run_id: int,
    actor: User,
    role: str,
) -> CollectionValidationRunResponse:
    _assert_eic(role)
    col = await _get_or_404(db, collection_id)
    run = await db.scalar(
        select(CollectionValidationRun).where(
            CollectionValidationRun.id == run_id,
            CollectionValidationRun.collection_id == col.id,
        )
    )
    if run is None:
        raise NotFoundError("Validation run not found.")
    return CollectionValidationRunResponse.model_validate(run)


async def get_latest_validation_run(
    db: AsyncSession,
    collection_id: str,
    actor: User,
    role: str,
) -> CollectionValidationRunResponse | None:
    _assert_eic(role)
    col = await _get_or_404(db, collection_id)
    run = await db.scalar(
        select(CollectionValidationRun)
        .where(CollectionValidationRun.collection_id == col.id)
        .order_by(CollectionValidationRun.started_at.desc())
        .limit(1)
    )
    if run is None:
        return None
    return CollectionValidationRunResponse.model_validate(run)


async def _run_validation_task(run_id: int, slug: str, schema_id_str: str) -> None:
    """Background task: validate every document in the collection.

    Opens its own database session. Never raises — all errors are caught and
    persisted on the run record so the frontend can surface them.
    """
    schema_id = uuid.UUID(schema_id_str)

    async with AsyncSessionLocal() as db:
        try:
            run = await db.get(CollectionValidationRun, run_id)
            if run is None:
                logger.error("validation_task_run_not_found", run_id=run_id)
                return

            schema = await db.get(TeiSchema, schema_id)
            if schema is None or not schema.validation_filename:
                run.status = ValidationRunStatus.failed
                run.error_message = "Schema or validation file no longer exists."
                run.completed_at = datetime.now(UTC)
                await db.commit()
                return

            try:
                filenames = await existdb_client.list_collection(slug)
            except Exception as exc:
                run.status = ValidationRunStatus.failed
                run.error_message = f"Could not list collection documents: {exc}"
                run.completed_at = datetime.now(UTC)
                await db.commit()
                return

            filenames.sort(key=_natural_sort_key)
            run.status = ValidationRunStatus.running
            run.doc_count = len(filenames)
            run.results = {"documents": []}
            await db.commit()

            doc_results: list[dict] = []
            error_count = 0

            for filename in filenames:
                try:
                    xml_bytes = await existdb_client.get_document(slug, filename)
                    result = validate_xml(xml_bytes, schema)
                    doc_results.append({
                        "filename": filename,
                        "valid": result.valid,
                        "errors": [e.model_dump() for e in result.errors],
                    })
                    if not result.valid:
                        error_count += 1
                except Exception as exc:
                    logger.warning(
                        "validation_task_doc_error",
                        slug=slug,
                        filename=filename,
                        error=str(exc),
                    )
                    doc_results.append({
                        "filename": filename,
                        "valid": False,
                        "errors": [{"line": 0, "col": 0, "message": str(exc), "path": None}],
                    })
                    error_count += 1

                # Persist progress after every document.
                run.validated_count = len(doc_results)
                run.error_count = error_count
                run.results = {"documents": list(doc_results)}
                await db.commit()

            run.status = ValidationRunStatus.done
            run.completed_at = datetime.now(UTC)
            await db.commit()

            logger.info(
                "collection_validation_done",
                slug=slug,
                run_id=run_id,
                total=len(filenames),
                errors=error_count,
            )

        except Exception as exc:
            logger.error(
                "collection_validation_task_failed",
                slug=slug,
                run_id=run_id,
                error=str(exc),
            )
            try:
                async with AsyncSessionLocal() as db2:
                    run2 = await db2.get(CollectionValidationRun, run_id)
                    if run2 and run2.status not in (
                        ValidationRunStatus.done, ValidationRunStatus.failed
                    ):
                        run2.status = ValidationRunStatus.failed
                        run2.error_message = str(exc)
                        run2.completed_at = datetime.now(UTC)
                        await db2.commit()
            except Exception:
                pass
