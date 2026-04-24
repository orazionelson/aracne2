"""Adapter-tests don't need DB/session fixtures — adapters are pure
HTTP clients driven by ``httpx.MockTransport``. This conftest exists
only so the plugin tests aren't swept into ``app/tests/conftest.py``
which spins up the full SQLite stack."""
