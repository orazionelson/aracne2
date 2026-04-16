"""Tests for db/seed.py — idempotency and correctness of seed functions.

seed_tei_schemas is the only non-trivial seeding function that can be
meaningfully exercised at the unit/integration level: it reads a bundled
file and writes to the filesystem, which can be redirected via tmp_path
without starting a real PostgreSQL database.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed import seed_tei_schemas
from app.models.tei_schema import SchemaFormat, TeiSchema


@pytest.mark.asyncio
async def test_seed_tei_schemas_creates_row_and_file(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """seed_tei_schemas creates a TeiSchema DB row and copies the .rng file."""
    with patch("app.db.seed.settings") as mock_cfg:
        mock_cfg.schemas_dir = tmp_path
        await seed_tei_schemas(db_session)

    rows = list(await db_session.scalars(select(TeiSchema)))
    assert len(rows) == 1
    row = rows[0]
    assert row.name == "TEI All (P5 v4.11.0)"
    assert row.validation_format == SchemaFormat.rng
    # Verify the file was copied to schemas_dir/<id>/validation.rng
    dest = tmp_path / str(row.id) / "validation.rng"
    assert dest.exists(), f"Expected validation.rng at {dest}"
    assert dest.stat().st_size > 0


@pytest.mark.asyncio
async def test_seed_tei_schemas_is_idempotent(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """Calling seed_tei_schemas twice does not create duplicate rows."""
    with patch("app.db.seed.settings") as mock_cfg:
        mock_cfg.schemas_dir = tmp_path
        await seed_tei_schemas(db_session)
        await seed_tei_schemas(db_session)

    rows = list(await db_session.scalars(select(TeiSchema)))
    assert len(rows) == 1, "Duplicate TeiSchema rows created by seed"


@pytest.mark.asyncio
async def test_seed_tei_schemas_skips_missing_bundled_file(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """If the bundled source file is missing, seed logs a warning and skips it
    rather than raising an exception.  No DB row should be created."""
    # Redirect _BUNDLED_SCHEMAS_DIR to an empty directory so no .rng file exists.
    with (
        patch("app.db.seed.settings") as mock_cfg,
        patch("app.db.seed._BUNDLED_SCHEMAS_DIR", tmp_path / "empty"),
    ):
        mock_cfg.schemas_dir = tmp_path
        (tmp_path / "empty").mkdir()
        await seed_tei_schemas(db_session)  # should not raise

    rows = list(await db_session.scalars(select(TeiSchema)))
    assert rows == [], "No rows should be created when the bundled file is missing"
