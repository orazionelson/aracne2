"""``public_navigation`` capability — end-to-end coverage.

Five concerns are checked:

1. ``activate_plugin`` idempotently creates the matching
   ``public_link_<name>_enabled`` system_setting (default ``"false"``)
   when the activated plugin advertises ``public_navigation``, and
   does NOT create one for plugins lacking the capability.

2. ``sync_registry`` covers the same row creation path for plugins
   discovered with the capability — handles natives and the boot of
   a deployment whose plugin landed before the toggle existed.

3. ``get_public_config`` exposes ``public_nav`` only when the
   matching toggle is ``"true"`` and the plugin is ``active``.
   Inactive plugins, missing toggle, or ``"false"`` toggle all hide
   the entry.

4. Entries are sorted by ``priority`` ascending, ties by
   ``plugin_name``.

5. Malformed descriptors (missing ``url``, unknown ``section``)
   are silently dropped — never crash the public config endpoint
   that public visitors hit on every page load.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.plugin_base import PluginBase, PluginMeta
from app.core.plugin_loader import PluginLoader
from app.models.plugin import Plugin, PluginStatus
from app.models.system_setting import SystemSetting
from app.services.plugins import activate_plugin
from app.services.settings import get_public_config, public_link_setting_key


def _make_plugin_row(
    *,
    name: str,
    descriptor: dict[str, object] | None,
    status: PluginStatus = PluginStatus.active,
) -> Plugin:
    return Plugin(
        name=name,
        display_name=name.replace("_", " ").title(),
        status=status,
        is_native=False,
        capabilities=(["public_navigation"] if descriptor is not None else []),
        ui_descriptor=({"public_navigation": descriptor} if descriptor else None),
    )


# ── activate_plugin upserts the toggle row ────────────────────────────────────


@pytest.mark.asyncio
async def test_activate_creates_public_link_toggle_when_capability_advertised(
    db_session: AsyncSession,
) -> None:
    db_session.add(
        _make_plugin_row(
            name="dummy_pub_nav",
            descriptor={
                "component": "DummyPubNavView",
                "url": "/dummy",
                "section": "header",
                "label_en": "Dummy",
            },
            status=PluginStatus.inactive,
        )
    )
    await db_session.flush()

    await activate_plugin(db_session, "dummy_pub_nav")

    row = await db_session.get(
        SystemSetting, public_link_setting_key("dummy_pub_nav")
    )
    assert row is not None
    assert row.value == "false"
    assert row.type == "bool"


@pytest.mark.asyncio
async def test_activate_no_toggle_when_capability_absent(
    db_session: AsyncSession,
) -> None:
    db_session.add(
        Plugin(
            name="plain_plugin",
            display_name="Plain",
            status=PluginStatus.inactive,
            is_native=False,
            capabilities=[],
            ui_descriptor=None,
        )
    )
    await db_session.flush()

    await activate_plugin(db_session, "plain_plugin")

    row = await db_session.get(
        SystemSetting, public_link_setting_key("plain_plugin")
    )
    assert row is None


@pytest.mark.asyncio
async def test_activate_is_idempotent_on_existing_toggle(
    db_session: AsyncSession,
) -> None:
    """Re-activating a previously-deactivated plugin must not stomp the toggle."""
    db_session.add(
        _make_plugin_row(
            name="dummy_pub_nav",
            descriptor={
                "component": "DummyPubNavView",
                "url": "/dummy",
                "section": "header",
            },
            status=PluginStatus.inactive,
        )
    )
    db_session.add(
        SystemSetting(
            key=public_link_setting_key("dummy_pub_nav"),
            value="true",
            type="bool",
            description="user-flipped this on previously",
        )
    )
    await db_session.flush()

    await activate_plugin(db_session, "dummy_pub_nav")

    row = await db_session.get(
        SystemSetting, public_link_setting_key("dummy_pub_nav")
    )
    assert row is not None
    assert row.value == "true"


# ── sync_registry path ────────────────────────────────────────────────────────


class _PubNavPlugin(PluginBase):
    meta = PluginMeta(
        id="sync_pub_nav_plugin",
        name="Sync Pub Nav Plugin",
        version="0.0.0",
        native=False,
        description="Test fixture — never shipped.",
        capabilities=("public_navigation",),
        ui_descriptor={
            "public_navigation": {
                "component": "SyncPubNavView",
                "url": "/sync-pub-nav",
                "section": "footer",
                "priority": 50,
            }
        },
    )
    router = APIRouter()


@pytest.mark.asyncio
async def test_sync_registry_creates_toggle_for_pub_nav_plugin(
    db_session: AsyncSession,
) -> None:
    loader = PluginLoader()
    loader._discovered = {_PubNavPlugin.meta.id: _PubNavPlugin}

    await loader.sync_registry(db_session)

    row = await db_session.get(
        SystemSetting, public_link_setting_key(_PubNavPlugin.meta.id)
    )
    assert row is not None
    assert row.value == "false"


# ── get_public_config exposure ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_public_nav_hidden_when_toggle_off(
    db_session: AsyncSession,
) -> None:
    db_session.add(
        _make_plugin_row(
            name="off_plugin",
            descriptor={
                "component": "OffView",
                "url": "/off",
                "section": "header",
            },
        )
    )
    db_session.add(
        SystemSetting(
            key=public_link_setting_key("off_plugin"),
            value="false",
            type="bool",
        )
    )
    await db_session.flush()

    cfg = await get_public_config(db_session)
    assert all(e.plugin_name != "off_plugin" for e in cfg.public_nav)


@pytest.mark.asyncio
async def test_public_nav_hidden_when_plugin_inactive(
    db_session: AsyncSession,
) -> None:
    db_session.add(
        _make_plugin_row(
            name="inactive_plugin",
            descriptor={
                "component": "InactiveView",
                "url": "/inactive",
                "section": "header",
            },
            status=PluginStatus.inactive,
        )
    )
    db_session.add(
        SystemSetting(
            key=public_link_setting_key("inactive_plugin"),
            value="true",
            type="bool",
        )
    )
    await db_session.flush()

    cfg = await get_public_config(db_session)
    assert all(e.plugin_name != "inactive_plugin" for e in cfg.public_nav)


@pytest.mark.asyncio
async def test_public_nav_exposed_when_active_and_enabled(
    db_session: AsyncSession,
) -> None:
    db_session.add(
        _make_plugin_row(
            name="on_plugin",
            descriptor={
                "component": "OnView",
                "url": "/on",
                "section": "home_quick_links",
                "label_key": "on_plugin.public_link",
                "label_en": "On",
                "label_it": "Acceso",
                "icon": "sparkles",
                "priority": 25,
            },
        )
    )
    db_session.add(
        SystemSetting(
            key=public_link_setting_key("on_plugin"),
            value="true",
            type="bool",
        )
    )
    await db_session.flush()

    cfg = await get_public_config(db_session)
    matches = [e for e in cfg.public_nav if e.plugin_name == "on_plugin"]
    assert len(matches) == 1
    entry = matches[0]
    assert entry.section == "home_quick_links"
    assert entry.url == "/on"
    assert entry.component == "OnView"
    assert entry.label_key == "on_plugin.public_link"
    assert entry.label_en == "On"
    assert entry.label_it == "Acceso"
    assert entry.icon == "sparkles"
    assert entry.priority == 25


@pytest.mark.asyncio
async def test_public_nav_sorted_by_priority_then_name(
    db_session: AsyncSession,
) -> None:
    for name, prio in [
        ("zebra_plugin", 200),
        ("alpha_plugin", 50),
        ("beta_plugin", 50),
    ]:
        db_session.add(
            _make_plugin_row(
                name=name,
                descriptor={
                    "component": f"{name.title().replace('_', '')}View",
                    "url": f"/{name}",
                    "section": "footer",
                    "priority": prio,
                },
            )
        )
        db_session.add(
            SystemSetting(
                key=public_link_setting_key(name),
                value="true",
                type="bool",
            )
        )
    await db_session.flush()

    cfg = await get_public_config(db_session)
    names_in_order = [
        e.plugin_name
        for e in cfg.public_nav
        if e.plugin_name in {"zebra_plugin", "alpha_plugin", "beta_plugin"}
    ]
    assert names_in_order == ["alpha_plugin", "beta_plugin", "zebra_plugin"]


@pytest.mark.asyncio
async def test_public_nav_drops_invalid_descriptors(
    db_session: AsyncSession,
) -> None:
    """Missing url, unknown section, non-string component — all dropped silently."""
    db_session.add(
        _make_plugin_row(
            name="bad_section",
            descriptor={
                "component": "BadView",
                "url": "/bad",
                "section": "sidebar",  # not in {header, home_quick_links, footer}
            },
        )
    )
    db_session.add(
        _make_plugin_row(
            name="missing_url",
            descriptor={
                "component": "MissingUrlView",
                "section": "header",
            },
        )
    )
    for name in ("bad_section", "missing_url"):
        db_session.add(
            SystemSetting(
                key=public_link_setting_key(name),
                value="true",
                type="bool",
            )
        )
    await db_session.flush()

    cfg = await get_public_config(db_session)
    names = {e.plugin_name for e in cfg.public_nav}
    assert "bad_section" not in names
    assert "missing_url" not in names
