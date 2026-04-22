"""Re-export shared pytest fixtures from the top-level test conftest.

The plugin test directory is not a descendant of ``app/tests/``, so pytest's
default conftest discovery cannot reach the ``test_engine`` / ``db_session``
fixtures defined there.  Importing them into this local conftest makes them
visible to every test in this sub-tree without duplicating their setup.
"""

from app.tests.conftest import (  # noqa: F401 — fixtures need to be importable by pytest
    clean_db,
    client,
    client_with_existdb,
    db_session,
    mock_existdb,
    seeded_admin,
    seeded_designer,
    seeded_editorinchief,
    seeded_roles,
    seeded_user,
    test_engine,
)
