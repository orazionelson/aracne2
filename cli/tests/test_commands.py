"""End-to-end tests for the four typer subcommands.

We bypass the ``aracne`` console script and call the command functions
directly with a ``CliRunner`` from typer / click so the test stays
lightweight (no subprocess spawn) but still exercises the full command
parsing path.
"""

from __future__ import annotations

import json as _json
import zipfile
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from typer.testing import CliRunner

from aracne_cli.api import ApiClient
from aracne_cli.cli import app
from aracne_cli.commands.export import _parse_as_of, _resolve_version_at
from aracne_cli.config import Profile, save_profile

runner = CliRunner()


def _api_with_routes(routes):
    """Helper used by tests that patch the ApiClient constructor."""
    transport = httpx.MockTransport(
        lambda request: routes.get(
            (request.method, request.url.path),
            httpx.Response(
                status_code=404,
                json={"error": {"code": "NOT_FOUND", "message": "no route"}},
            ),
        )(request)
        if callable(routes.get((request.method, request.url.path)))
        else routes.get(
            (request.method, request.url.path),
            httpx.Response(
                status_code=404,
                json={"error": {"code": "NOT_FOUND", "message": "no route"}},
            ),
        )
    )
    return transport


def _patched_client(transport):
    """A drop-in for ``ApiClient(host, token)`` that injects *transport*.

    Used as ``patch("aracne_cli.commands.X.ApiClient", side_effect=...)``.
    """

    def _factory(host, token, *, timeout=30.0, transport_kw=None):
        return ApiClient(host, token, timeout=timeout, transport=transport)

    return _factory


# ── login ───────────────────────────────────────────────────────────────


def test_login_writes_profile_after_verifying_token(isolated_config: Path) -> None:
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            status_code=200,
            json={
                "data": {
                    "username": "alice",
                    "role": "EditorInChief",
                    "display_name": "Alice",
                }
            },
        )
    )

    with patch(
        "aracne_cli.commands.login.ApiClient",
        side_effect=lambda host, token, **_: ApiClient(
            host, token, transport=transport
        ),
    ):
        result = runner.invoke(
            app,
            ["login", "--host", "https://example.org", "--json"],
            input="aracne2_pat_thetoken\n",
        )

    assert result.exit_code == 0, result.output
    payload = _json.loads(result.output.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["username"] == "alice"
    assert payload["role"] == "EditorInChief"


def test_login_rejects_invalid_token(isolated_config: Path) -> None:
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            status_code=401,
            json={"error": {"code": "INVALID_PAT", "message": "Bad token"}},
        )
    )
    with patch(
        "aracne_cli.commands.login.ApiClient",
        side_effect=lambda host, token, **_: ApiClient(
            host, token, transport=transport
        ),
    ):
        result = runner.invoke(
            app,
            ["login", "--host", "https://example.org", "--json"],
            input="aracne2_pat_bad\n",
        )
    assert result.exit_code == 1
    payload = _json.loads(result.output.strip().splitlines()[-1])
    assert payload["ok"] is False
    assert payload["code"] == "INVALID_PAT"


# ── whoami ──────────────────────────────────────────────────────────────


def test_whoami_with_missing_profile(isolated_config: Path) -> None:
    result = runner.invoke(app, ["whoami", "--json"])
    assert result.exit_code == 1
    payload = _json.loads(result.output.strip().splitlines()[-1])
    assert payload["ok"] is False
    assert "Profile 'default' not found" in payload["error"]


def test_whoami_with_valid_profile(isolated_config: Path) -> None:
    save_profile(
        Profile(name="default", host="https://h", token="aracne2_pat_t")
    )
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            status_code=200,
            json={
                "data": {
                    "username": "bob",
                    "role": "Editor",
                    "display_name": "Bob",
                }
            },
        )
    )
    with patch(
        "aracne_cli.commands.whoami.ApiClient",
        side_effect=lambda host, token, **_: ApiClient(
            host, token, transport=transport
        ),
    ):
        result = runner.invoke(app, ["whoami", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.output.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["username"] == "bob"


# ── import ──────────────────────────────────────────────────────────────


def _import_routes(existing_filenames: list[str], *, fail_filename: str | None = None):
    """Build a route map for the import flow.

    The collection list returns the canned filenames; uploads succeed
    unless the filename is in *fail_filename*.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method
        if method == "GET" and path == "/api/v1/collections/c1/documents":
            return httpx.Response(
                status_code=200,
                json={
                    "data": [
                        {"filename": fn} for fn in existing_filenames
                    ]
                },
            )
        if method == "POST" and path == "/api/v1/collections/c1/documents":
            # multipart upload — read multipart form
            return httpx.Response(
                status_code=201,
                json={"data": {"filename": "ok.xml"}},
            )
        if method == "PUT" and path.startswith(
            "/api/v1/collections/c1/documents/"
        ):
            filename = path.rsplit("/", 1)[-1]
            if fail_filename and filename == fail_filename:
                return httpx.Response(
                    status_code=409,
                    json={
                        "error": {
                            "code": "DOCUMENT_BUSY",
                            "message": "boom",
                        }
                    },
                )
            return httpx.Response(
                status_code=200,
                json={"data": {"filename": filename}},
            )
        return httpx.Response(
            status_code=404, json={"error": {"code": "NOT_FOUND", "message": "x"}}
        )

    return httpx.MockTransport(handler)


def test_import_skip_default(isolated_config: Path, tmp_path: Path) -> None:
    save_profile(Profile(name="default", host="https://h", token="aracne2_pat_t"))
    src = tmp_path / "src"
    src.mkdir()
    (src / "doc1.xml").write_bytes(b"<TEI/>")
    (src / "doc2.xml").write_bytes(b"<TEI/>")

    transport = _import_routes(existing_filenames=["doc1.xml"])

    with patch(
        "aracne_cli.commands.import_.ApiClient",
        side_effect=lambda host, token, **_: ApiClient(
            host, token, transport=transport
        ),
    ):
        result = runner.invoke(
            app,
            [
                "import",
                "--collection",
                "c1",
                "--dir",
                str(src),
                "--json",
            ],
        )
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.output.strip().splitlines()[-1])
    assert payload["summary"] == {
        "uploaded": 1,
        "overwritten": 0,
        "skipped": 1,
        "failed": 0,
        "invalid_filename": 0,
    }


def test_import_overwrite_replaces_existing(
    isolated_config: Path, tmp_path: Path
) -> None:
    save_profile(Profile(name="default", host="https://h", token="aracne2_pat_t"))
    src = tmp_path / "src"
    src.mkdir()
    (src / "doc1.xml").write_bytes(b"<TEI/>")

    transport = _import_routes(existing_filenames=["doc1.xml"])
    with patch(
        "aracne_cli.commands.import_.ApiClient",
        side_effect=lambda host, token, **_: ApiClient(
            host, token, transport=transport
        ),
    ):
        result = runner.invoke(
            app,
            [
                "import",
                "--collection",
                "c1",
                "--dir",
                str(src),
                "--on-conflict",
                "overwrite",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.output.strip().splitlines()[-1])
    assert payload["summary"]["overwritten"] == 1
    assert payload["summary"]["uploaded"] == 0


def test_import_fail_aborts_on_conflict(
    isolated_config: Path, tmp_path: Path
) -> None:
    save_profile(Profile(name="default", host="https://h", token="aracne2_pat_t"))
    src = tmp_path / "src"
    src.mkdir()
    (src / "doc1.xml").write_bytes(b"<TEI/>")

    transport = _import_routes(existing_filenames=["doc1.xml"])
    with patch(
        "aracne_cli.commands.import_.ApiClient",
        side_effect=lambda host, token, **_: ApiClient(
            host, token, transport=transport
        ),
    ):
        result = runner.invoke(
            app,
            [
                "import",
                "--collection",
                "c1",
                "--dir",
                str(src),
                "--on-conflict",
                "fail",
                "--json",
            ],
        )
    assert result.exit_code == 2
    payload = _json.loads(result.output.strip().splitlines()[-1])
    assert payload["summary"]["failed"] == 1


def test_import_rejects_bad_filename(
    isolated_config: Path, tmp_path: Path
) -> None:
    save_profile(Profile(name="default", host="https://h", token="aracne2_pat_t"))
    src = tmp_path / "src"
    src.mkdir()
    # underscore + dot in front of letter is fine; a leading hyphen is not
    # per the regex ^[a-zA-Z0-9][a-zA-Z0-9_-]*\.xml$
    (src / "-bad.xml").write_bytes(b"<TEI/>")
    (src / "good.xml").write_bytes(b"<TEI/>")

    transport = _import_routes(existing_filenames=[])
    with patch(
        "aracne_cli.commands.import_.ApiClient",
        side_effect=lambda host, token, **_: ApiClient(
            host, token, transport=transport
        ),
    ):
        result = runner.invoke(
            app,
            [
                "import",
                "--collection",
                "c1",
                "--dir",
                str(src),
                "--json",
            ],
        )
    payload = _json.loads(result.output.strip().splitlines()[-1])
    assert payload["summary"]["invalid_filename"] == 1
    assert payload["summary"]["uploaded"] == 1
    assert result.exit_code == 2


# ── export ──────────────────────────────────────────────────────────────


def _export_routes(*, with_versions: bool = False):
    docs = [{"filename": "doc1.xml"}, {"filename": "doc2.xml"}]

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path == "/api/v1/collections/c1":
            return httpx.Response(
                status_code=200,
                json={"data": {"id": "c1", "slug": "c1", "title": "Test"}},
            )
        if request.method == "GET" and path == "/api/v1/collections/c1/documents":
            return httpx.Response(status_code=200, json={"data": docs})
        if request.method == "GET" and path.startswith(
            "/api/v1/collections/c1/documents/"
        ):
            # /content terminus → raw XML; otherwise it's the version list.
            if path.endswith("/content"):
                return httpx.Response(
                    status_code=200,
                    content=b"<TEI version='archived'/>",
                    headers={"Content-Type": "application/xml"},
                )
            if path.endswith("/versions"):
                if with_versions:
                    return httpx.Response(
                        status_code=200,
                        json={
                            "data": [
                                {
                                    "version_number": 7,
                                    "created_at": "2026-04-15T00:00:00Z",
                                    "origin": "publication",
                                },
                                {
                                    "version_number": 4,
                                    "created_at": "2026-03-10T00:00:00Z",
                                    "origin": "publication",
                                },
                            ]
                        },
                    )
                return httpx.Response(status_code=200, json={"data": []})
            # raw current-state download
            return httpx.Response(
                status_code=200,
                content=b"<TEI version='current'/>",
                headers={"Content-Type": "application/xml"},
            )
        return httpx.Response(
            status_code=404,
            json={"error": {"code": "NOT_FOUND", "message": "x"}},
        )

    return httpx.MockTransport(handler)


def test_export_without_as_of_writes_current_bodies(
    isolated_config: Path, tmp_path: Path
) -> None:
    save_profile(Profile(name="default", host="https://h", token="aracne2_pat_t"))
    transport = _export_routes()
    output = tmp_path / "corpus.zip"

    with patch(
        "aracne_cli.commands.export.ApiClient",
        side_effect=lambda host, token, **_: ApiClient(
            host, token, transport=transport
        ),
    ):
        result = runner.invoke(
            app,
            [
                "export",
                "--collection",
                "c1",
                "--output",
                str(output),
                "--json",
            ],
        )

    assert result.exit_code == 0, result.output
    assert output.exists()
    with zipfile.ZipFile(output) as zf:
        names = sorted(zf.namelist())
        manifest = _json.loads(zf.read("manifest.json").decode("utf-8"))
        body = zf.read("documents/doc1.xml")
    assert "manifest.json" in names
    assert "documents/doc1.xml" in names
    assert b"current" in body
    assert manifest["as_of"] is None


def test_export_with_as_of_picks_publication_version(
    isolated_config: Path, tmp_path: Path
) -> None:
    save_profile(Profile(name="default", host="https://h", token="aracne2_pat_t"))
    transport = _export_routes(with_versions=True)
    output = tmp_path / "q1.zip"
    with patch(
        "aracne_cli.commands.export.ApiClient",
        side_effect=lambda host, token, **_: ApiClient(
            host, token, transport=transport
        ),
    ):
        result = runner.invoke(
            app,
            [
                "export",
                "--collection",
                "c1",
                "--output",
                str(output),
                "--as-of",
                "2026-04-01",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.output
    with zipfile.ZipFile(output) as zf:
        manifest = _json.loads(zf.read("manifest.json").decode("utf-8"))
    # 2026-03-10 is <= 2026-04-01; 2026-04-15 is not. So version 4 wins.
    versions = {d["filename"]: d["version_number"] for d in manifest["documents"]}
    assert versions == {"doc1.xml": 4, "doc2.xml": 4}


def test_export_skips_when_no_publication_at_or_before_date(
    isolated_config: Path, tmp_path: Path
) -> None:
    save_profile(Profile(name="default", host="https://h", token="aracne2_pat_t"))
    transport = _export_routes(with_versions=False)
    output = tmp_path / "empty.zip"
    with patch(
        "aracne_cli.commands.export.ApiClient",
        side_effect=lambda host, token, **_: ApiClient(
            host, token, transport=transport
        ),
    ):
        result = runner.invoke(
            app,
            [
                "export",
                "--collection",
                "c1",
                "--output",
                str(output),
                "--as-of",
                "2025-01-01",
                "--json",
            ],
        )
    assert result.exit_code == 0
    payload = _json.loads(result.output.strip().splitlines()[-1])
    assert payload["summary"]["written"] == 0
    assert payload["summary"]["skipped"] == 2


# ── parse_as_of helper ──────────────────────────────────────────────────


def test_parse_as_of_accepts_date() -> None:
    dt = _parse_as_of("2026-04-01")
    assert dt.year == 2026 and dt.month == 4 and dt.day == 1
    assert dt.utcoffset() is not None


def test_parse_as_of_rejects_garbage() -> None:
    import typer

    with pytest.raises(typer.BadParameter):
        _parse_as_of("yesterday")
