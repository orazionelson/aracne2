"""Re-export shared pytest fixtures from the top-level test conftest.

Same trick as the Zenodo plugin: the plugin test directory sits outside
``app/tests/``, so pytest's default conftest walk doesn't reach it and
``db_session`` etc. would be invisible.
"""

from app.tests.conftest import (  # noqa: F401 — pytest fixture discovery by import
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
