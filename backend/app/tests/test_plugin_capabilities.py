"""Capability auto-cabling contract — loader sync + registry coherence.

Two complementary surfaces are checked:

1. ``sync_registry`` writes ``capabilities`` and ``ui_descriptor`` from
   PluginMeta verbatim into the DB row, both on first install (insert
   path) and on subsequent boots (update path). This is the contract
   the frontend relies on when it reads ``GET /plugins`` and
   auto-cables the editor toolbar / Deposita tabs.

2. Every concrete plugin shipping a capability points at a Vue
   component name that exists in the matching frontend registry
   (``components/lookup/registry.ts``,
   ``components/deposit/registry.ts``,
   ``components/website-deposit/registry.ts``). A typo here would
   silently render an empty toolbar slot or skip a deposit tab — we
   already burned an hour on a "RorPanel" vs "RorLinkPanel" mismatch,
   so the static cross-check pays its keep.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.plugin_base import PluginBase, PluginMeta
from app.core.plugin_loader import PluginLoader
from app.models.plugin import Plugin, PluginStatus

# ── Helpers ───────────────────────────────────────────────────────────────────


# The Python package layout is app/tests/<file>.py — so parents[1] is
# always app/, regardless of whether we run from the repo root, from
# inside the Docker container (where backend/ is mounted at /app and
# the frontend lives outside the mount), or from a checkout in CI.
_APP_DIR = Path(__file__).resolve().parents[1]
_BACKEND_PLUGINS = _APP_DIR / "plugins"

# The frontend tree is *not* mounted into the backend container. When
# running the suite under `docker compose exec backend pytest …` the
# registry .ts files are unreachable, so the cross-tree coherence
# test is skipped rather than failed. CI / local-checkout runs that
# can see the frontend tree get the full check.
_REPO_ROOT_CANDIDATES: list[Path] = [
    Path(__file__).resolve().parents[3],          # repo checkout: backend/app/tests/...
    Path("/repo"),                                 # mounted-repo convention used by some CI images
    Path(__file__).resolve().parents[2] / "..",   # backward-compat fallback
]


def _find_frontend_src() -> Path | None:
    """Return frontend/src/ if any candidate root holds it, else None."""
    for root in _REPO_ROOT_CANDIDATES:
        candidate = (root / "frontend" / "src").resolve()
        if candidate.is_dir():
            return candidate
    return None


def _registry_paths(frontend_src: Path) -> dict[str, Path]:
    """Capability tag → registry file relative to a known frontend/src."""
    return {
        "inline_authority": frontend_src / "components" / "lookup" / "registry.ts",
        "collection_deposit": frontend_src / "components" / "deposit" / "registry.ts",
        "website_deposit": frontend_src / "components" / "website-deposit" / "registry.ts",
    }


def _parse_registry(ts_path: Path) -> set[str]:
    """Extract the component-name keys from a frontend registry .ts file.

    Each registry uses the literal pattern
    ``ComponentName: defineAsyncComponent(...)`` — we don't need a
    real TS parser, just a regex over the LHS of every entry.
    """
    text = ts_path.read_text(encoding="utf-8")
    return set(re.findall(r"^\s*([A-Z][A-Za-z0-9_]+)\s*:", text, re.MULTILINE))


def _iter_real_plugin_metas() -> list[PluginMeta]:
    """Return every PluginMeta declared by a non-_*/_native plugin.

    Imports each plugin.py once to instantiate its Plugin class, then
    yields the meta. Skips _native/ (capabilities don't apply there)
    and _lib/ (shared modules, no plugin.py).
    """
    metas: list[PluginMeta] = []
    for entry in sorted(_BACKEND_PLUGINS.iterdir()):
        if not entry.is_dir() or entry.name.startswith("_"):
            continue
        plugin_py = entry / "plugin.py"
        if not plugin_py.is_file():
            continue
        # Import via the same dotted path the loader uses.
        import importlib

        module = importlib.import_module(f"app.plugins.{entry.name}.plugin")
        for _, obj in vars(module).items():
            if (
                isinstance(obj, type)
                and issubclass(obj, PluginBase)
                and obj is not PluginBase
            ):
                metas.append(obj.meta)
                break
    return metas


# ── Loader sync ───────────────────────────────────────────────────────────────


class _DummyPlugin(PluginBase):
    """Minimal PluginBase subclass declaring two capabilities."""

    meta = PluginMeta(
        id="dummy_capability_plugin",
        name="Dummy Capability Plugin",
        version="0.0.0",
        native=False,
        description="Test fixture — never shipped, never mounted.",
        capabilities=("inline_authority", "collection_deposit"),
        ui_descriptor={
            "inline_authority": {
                "component": "DummyLinkPanel",
                "label_key": "lookups.dummy",
                "icon_color": "text-amber-500",
                "apply": "ref",
                "initial_context": "selection",
                "priority": 999,
            },
            "collection_deposit": {
                "component": "DummyCollectionDepositPanel",
                "label": "Dummy",
                "priority": 999,
            },
        },
    )
    # PluginBase requires ``router`` to be set; the loader test never
    # mounts it, so a bare APIRouter is enough.
    router = APIRouter()


@pytest.mark.asyncio
async def test_sync_registry_writes_capabilities_on_insert(
    db_session: AsyncSession,
) -> None:
    """First-boot path: a brand-new plugin row carries both fields."""
    loader = PluginLoader()
    loader._discovered = {_DummyPlugin.meta.id: _DummyPlugin}

    await loader.sync_registry(db_session)

    row = await db_session.scalar(
        select(Plugin).where(Plugin.name == _DummyPlugin.meta.id)
    )
    assert row is not None
    assert row.capabilities == ["inline_authority", "collection_deposit"]
    assert row.ui_descriptor is not None
    assert row.ui_descriptor["inline_authority"]["component"] == "DummyLinkPanel"
    assert row.ui_descriptor["collection_deposit"]["component"] == (
        "DummyCollectionDepositPanel"
    )
    # Non-native plugins start inactive.
    assert row.status == PluginStatus.inactive


@pytest.mark.asyncio
async def test_sync_registry_overwrites_capabilities_on_reboot(
    db_session: AsyncSession,
) -> None:
    """Second-boot path: stale capabilities in the DB are replaced.

    A previous Aracne2 boot may have written outdated capabilities
    (e.g. before a plugin author added a new descriptor or removed
    one). The loader is the source of truth on every restart, so the
    DB must reflect PluginMeta exactly — never a leftover.
    """
    # Seed a row with stale capability data, mimicking an older boot.
    db_session.add(
        Plugin(
            name=_DummyPlugin.meta.id,
            display_name="stale name",
            status=PluginStatus.inactive,
            is_native=False,
            capabilities=["something_legacy"],
            ui_descriptor={"something_legacy": {"component": "OldPanel"}},
        )
    )
    await db_session.flush()

    loader = PluginLoader()
    loader._discovered = {_DummyPlugin.meta.id: _DummyPlugin}
    await loader.sync_registry(db_session)

    row = await db_session.scalar(
        select(Plugin).where(Plugin.name == _DummyPlugin.meta.id)
    )
    assert row is not None
    assert row.display_name == _DummyPlugin.meta.name
    assert row.capabilities == ["inline_authority", "collection_deposit"]
    assert row.ui_descriptor is not None
    assert "something_legacy" not in row.ui_descriptor
    assert row.ui_descriptor["inline_authority"]["component"] == "DummyLinkPanel"


@pytest.mark.asyncio
async def test_sync_registry_handles_plugin_without_capabilities(
    db_session: AsyncSession,
) -> None:
    """A plugin with no capability declarations writes [] / None — not NULL/missing."""

    class _BarePlugin(PluginBase):
        meta = PluginMeta(
            id="bare_plugin",
            name="Bare Plugin",
            version="0.0.0",
            native=False,
            description="No capabilities declared.",
        )
        router = APIRouter()

    loader = PluginLoader()
    loader._discovered = {_BarePlugin.meta.id: _BarePlugin}
    await loader.sync_registry(db_session)

    row = await db_session.scalar(
        select(Plugin).where(Plugin.name == _BarePlugin.meta.id)
    )
    assert row is not None
    assert row.capabilities == []
    assert row.ui_descriptor is None


# ── Coherence: backend declarations vs frontend registries ────────────────────


def test_every_capability_descriptor_resolves_to_a_registry_entry() -> None:
    """For every capability declared by a real plugin, the named Vue
    component exists in the matching frontend registry.

    The frontend registry is the only place where component-name
    strings are bound to actual ``.vue`` files (Vite needs the path
    literal at build time for code-splitting), so a typo on either
    side renders nothing — silently. This test fails loudly instead.

    Skipped when the frontend tree isn't reachable (e.g. running
    `pytest` inside a backend-only Docker container). CI and local
    repo-checkout runs always see it.
    """
    frontend_src = _find_frontend_src()
    if frontend_src is None:
        pytest.skip(
            "frontend/src/ not reachable from this run "
            "(probably a backend-only container); coherence is checked "
            "in repo-rooted runs and CI."
        )
    registries = {tag: _parse_registry(p) for tag, p in _registry_paths(frontend_src).items()}
    registry_paths = _registry_paths(frontend_src)

    failures: list[str] = []
    for meta in _iter_real_plugin_metas():
        if not meta.capabilities or meta.ui_descriptor is None:
            continue
        for tag in meta.capabilities:
            entry = meta.ui_descriptor.get(tag)
            if not isinstance(entry, dict):
                failures.append(
                    f"{meta.id}: capability '{tag}' declared but no ui_descriptor entry"
                )
                continue
            component = entry.get("component")
            if not isinstance(component, str) or not component:
                failures.append(
                    f"{meta.id}: capability '{tag}' has no 'component' key"
                )
                continue
            registry = registries.get(tag)
            if registry is None:
                failures.append(
                    f"{meta.id}: capability '{tag}' has no frontend registry "
                    f"in {sorted(registry_paths)}"
                )
                continue
            if component not in registry:
                failures.append(
                    f"{meta.id}: '{tag}.component' = {component!r} not found in "
                    f"{registry_paths[tag]} "
                    f"(registry has: {sorted(registry)})"
                )

    assert not failures, "Capability ↔ registry mismatches:\n  " + "\n  ".join(failures)


def test_inline_authority_descriptors_have_required_keys() -> None:
    """Every ``inline_authority`` descriptor declares the keys the SPA
    reads when wiring the toolbar button + side panel.

    The SPA blindly trusts these keys at render time, so missing or
    malformed values would crash the editor only when the user
    activates the plugin in production — too late.
    """
    required = {"component", "apply", "initial_context"}
    valid_apply = {"ref", "fragment"}
    valid_initial = {"selection", "selection-or-empty", "kind-picker", "doi"}

    failures: list[str] = []
    for meta in _iter_real_plugin_metas():
        if "inline_authority" not in meta.capabilities:
            continue
        entry = (meta.ui_descriptor or {}).get("inline_authority")
        if not isinstance(entry, dict):
            failures.append(f"{meta.id}: missing inline_authority descriptor")
            continue
        missing = required - set(entry)
        if missing:
            failures.append(f"{meta.id}: missing keys {sorted(missing)}")
            continue
        if entry["apply"] not in valid_apply:
            failures.append(
                f"{meta.id}: apply={entry['apply']!r} not in {valid_apply}"
            )
        if entry["initial_context"] not in valid_initial:
            failures.append(
                f"{meta.id}: initial_context={entry['initial_context']!r} "
                f"not in {valid_initial}"
            )

    assert not failures, "inline_authority descriptor issues:\n  " + "\n  ".join(failures)


def test_deposit_descriptors_have_required_keys() -> None:
    """``collection_deposit`` and ``website_deposit`` descriptors must
    declare ``component`` (registry key). ``label`` / ``label_key`` and
    ``priority`` are optional."""
    failures: list[str] = []
    for tag in ("collection_deposit", "website_deposit"):
        for meta in _iter_real_plugin_metas():
            if tag not in meta.capabilities:
                continue
            entry = (meta.ui_descriptor or {}).get(tag)
            if not isinstance(entry, dict):
                failures.append(f"{meta.id}: missing {tag} descriptor")
                continue
            if not isinstance(entry.get("component"), str) or not entry["component"]:
                failures.append(f"{meta.id}: {tag} has no 'component'")

    assert not failures, "deposit descriptor issues:\n  " + "\n  ".join(failures)
