"""Help plugin service tests — no network, temp help_docs root."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.plugins.help import service
from app.plugins.help.schemas import HelpTreeNode


@pytest.fixture
def help_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the service at a fresh temp directory and reset the cache."""
    (tmp_path / "index.md").write_text("# Welcome\n\nIntro paragraph.\n")
    section = tmp_path / "01-basics"
    section.mkdir()
    (section / "index.md").write_text("# Basics\n\nSection landing.\n")
    (section / "01-roles.md").write_text(
        "# Roles\n\nUser, Editor, Admin.\n\n- Editor edits\n- Admin rules\n"
    )
    (section / "02-login.md").write_text(
        "# Logging in\n\nUse your email and password.\n"
    )
    (tmp_path / "img").mkdir()
    (tmp_path / "img" / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\nstub")
    # Files that must be ignored by the tree walker
    (tmp_path / ".hidden.md").write_text("# Hidden\n")
    (tmp_path / "_draft.md").write_text("# Draft\n")

    monkeypatch.setattr(service.settings, "help_docs_root", tmp_path)
    service.reset_cache()
    return tmp_path


def test_get_page_renders_root(help_root: Path) -> None:
    page = service.get_page("")
    assert page is not None
    assert page.title == "Welcome"
    assert "Intro paragraph" in page.html
    # Root breadcrumb is just (("", title))
    assert page.breadcrumb == [("", "Welcome")]


def test_get_page_renders_nested(help_root: Path) -> None:
    page = service.get_page("01-basics/01-roles")
    assert page is not None
    assert page.title == "Roles"
    assert "<li>Editor edits</li>" in page.html
    # Breadcrumb: Help → Basics → Roles
    labels = [label for _, label in page.breadcrumb]
    assert labels == ["Help", "Basics", "Roles"]


def test_get_page_returns_none_for_missing(help_root: Path) -> None:
    assert service.get_page("does/not/exist") is None


def test_get_page_rejects_traversal(help_root: Path) -> None:
    # The leading ../ escapes the root; resolve + is_inside must reject.
    assert service.get_page("../etc/passwd") is None
    assert service.get_page("01-basics/../../etc/passwd") is None


def test_get_page_index_of_section(help_root: Path) -> None:
    page = service.get_page("01-basics/")
    assert page is not None
    assert page.title == "Basics"


def test_build_tree_structure(help_root: Path) -> None:
    tree = service.build_tree()
    # Root index.md is omitted (frontend renders it separately).
    # The tree exposes only "01-basics" section.
    assert len(tree) == 1
    section = tree[0]
    assert section.is_section is True
    assert section.path == "01-basics"
    assert section.title == "Basics"
    # Two pages under the section, alphabetically sorted by filename.
    paths = [c.path for c in section.children]
    assert paths == ["01-basics/01-roles", "01-basics/02-login"]
    # Section's own index.md is not listed as a sibling page.
    assert all(not c.path.endswith("/index") for c in section.children)


def test_build_tree_skips_hidden_and_underscore(help_root: Path) -> None:
    tree = service.build_tree()
    flat = _flatten(tree)
    assert not any(".hidden" in n.path or "_draft" in n.path for n in flat)


def _flatten(nodes: list[HelpTreeNode]) -> list[HelpTreeNode]:
    out: list[HelpTreeNode] = []
    for n in nodes:
        out.append(n)
        if n.children:
            out.extend(_flatten(n.children))
    return out


def test_search_finds_matches(help_root: Path) -> None:
    hits = service.search("editor", limit=10)
    assert len(hits) >= 1
    titles = [h.title for h in hits]
    assert "Roles" in titles


def test_search_case_insensitive_and_multi_term(help_root: Path) -> None:
    hits = service.search("EDITOR admin", limit=10)
    assert any(h.title == "Roles" for h in hits)
    assert all("<mark>" in h.snippet for h in hits)


def test_search_rejects_short_query(help_root: Path) -> None:
    assert service.search("") == []
    assert service.search("a") == []


def test_asset_roundtrip(help_root: Path) -> None:
    result = service.get_asset("img/logo.png")
    assert result is not None
    file, content_type = result
    assert file.read_bytes().startswith(b"\x89PNG")
    assert content_type == "image/png"


def test_asset_rejects_non_whitelisted_extension(help_root: Path, tmp_path: Path) -> None:
    bad = help_root / "img" / "evil.exe"
    bad.write_bytes(b"\x4d\x5a")  # MZ header
    assert service.get_asset("img/evil.exe") is None


def test_asset_rejects_traversal(help_root: Path) -> None:
    assert service.get_asset("../etc/passwd") is None
    assert service.get_asset("img/../../etc/passwd") is None


def test_render_sanitises_inline_html(help_root: Path) -> None:
    page = help_root / "evil.md"
    page.write_text("# Evil\n\n<script>alert(1)</script>\n\nSafe text.\n")
    # Markdown-it with html=False already drops block-level <script>, but
    # we assert the output has no script tag regardless.
    rendered = service.get_page("evil")
    assert rendered is not None
    assert "<script" not in rendered.html.lower()
    assert "Safe text" in rendered.html


def test_cache_invalidates_on_mtime_change(help_root: Path) -> None:
    page = service.get_page("01-basics/01-roles")
    assert page is not None and "Editor edits" in page.html

    target = help_root / "01-basics" / "01-roles.md"
    target.write_text("# Roles\n\nRewritten content here.\n")
    import os
    # Bump mtime explicitly — some filesystems have second-level precision
    # so same-second rewrites do not otherwise trigger a reload.
    stat = target.stat()
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10_000_000))

    page2 = service.get_page("01-basics/01-roles")
    assert page2 is not None
    assert "Rewritten content here" in page2.html


def test_img_src_rewritten_to_plugin_endpoint(help_root: Path) -> None:
    page = help_root / "with_img.md"
    page.write_text("# With Image\n\n![alt](./img/logo.png)\n")
    rendered = service.get_page("with_img")
    assert rendered is not None
    assert "/api/v1/plugins/help/assets/img/logo.png" in rendered.html
