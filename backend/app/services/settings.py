from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.core.encryption import SENSITIVE_KEYS, decrypt_value, encrypt_value, mask_value
from app.core.exceptions import DomainValidationError, NotFoundError
from app.models.plugin import Plugin, PluginStatus
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.schemas.settings import (
    HomepageCssUploadResponse,
    LogoUploadResponse,
    PublicNavEntry,
    SettingResponse,
    SettingUpdate,
    UiConfigResponse,
)

# Allowed MIME types / extensions for logo upload.
_LOGO_ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
_LOGO_URL = "/api/v1/settings/logo/file"

_CSS_FILENAME = "custom_homepage.css"
_CSS_URL = "/api/v1/settings/homepage-css/file"

_MAX_CSS_BYTES = 512 * 1024       # 512 KB
_MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB


def _validate_value(key: str, value: str, type_: str) -> None:
    if type_ == "int":
        try:
            int(value)
        except ValueError:
            raise DomainValidationError(
                code="INVALID_SETTING_VALUE",
                message=f"Setting '{key}' requires an integer value",
            )
    elif type_ == "bool":
        if value not in ("true", "false"):
            raise DomainValidationError(
                code="INVALID_SETTING_VALUE",
                message=f"Setting '{key}' requires 'true' or 'false'",
            )


def _to_response(row: SystemSetting) -> SettingResponse:
    """Build a SettingResponse, masking the value for sensitive keys."""
    r = SettingResponse.model_validate(row)
    if row.key in SENSITIVE_KEYS:
        r.value = mask_value(row.value)
    return r


async def list_settings(db: AsyncSession) -> list[SettingResponse]:
    rows = await db.scalars(select(SystemSetting).order_by(SystemSetting.key))
    return [_to_response(r) for r in rows]


async def get_setting(db: AsyncSession, key: str) -> SettingResponse:
    row = await db.get(SystemSetting, key)
    if not row:
        raise NotFoundError(f"Setting '{key}' not found")
    return _to_response(row)


async def get_decrypted_setting(db: AsyncSession, key: str) -> str:
    """Return the plaintext value of a setting, decrypting if necessary.

    For use by internal services (e.g. the AI provider dispatcher) that need
    the actual value.  Never call this from a router — use get_setting() there.
    """
    row = await db.get(SystemSetting, key)
    if not row:
        return ""
    if key in SENSITIVE_KEYS:
        return decrypt_value(row.value, app_settings.jwt_secret)
    return row.value


def get_homepage_css_path() -> Path | None:
    """Return the path of the uploaded custom homepage CSS, or None if absent."""
    p = app_settings.media_dir / _CSS_FILENAME
    return p if p.exists() else None


def get_logo_path() -> Path | None:
    """Return the path of the uploaded logo file, or None if no file is present."""
    media = app_settings.media_dir
    if not media.exists():
        return None
    for ext in _LOGO_ALLOWED_EXT:
        p = media / f"logo{ext}"
        if p.exists():
            return p
    return None


async def get_public_config(db: AsyncSession) -> UiConfigResponse:
    """Return the UI configuration settings that the frontend needs at boot (no auth)."""
    keys = {
        "platform_name", "platform_logo_url", "navbar_bg_color",
        "public_home_enabled", "home_show_collections", "home_show_search",
        "home_show_login_button", "home_propagate_css", "evt_enabled",
        "public_search_engine_enabled", "public_search_engine_slug",
        "public_pages_doc_frame_enabled", "home_intro_html",
    }
    rows = await db.scalars(select(SystemSetting).where(SystemSetting.key.in_(keys)))
    values = {r.key: r.value for r in rows}
    # ``evt_enabled`` on the public config combines the system-setting
    # toggle with the plugin's activation state: when the EVT plugin is
    # inactive the setting is irrelevant — the "Read in EVT" button
    # would point at an unmounted endpoint.
    evt_setting_on = values.get("evt_enabled", "false") == "true"
    evt_plugin_active = await _is_plugin_active(db, "evt")
    # Mirror the EVT pattern: the "Search" header entry only lights up
    # when the toggle is on AND a slug has been chosen. An orphan slug
    # (engine deleted) just hides the link instead of producing a
    # broken /search page — the iframe target check happens server-
    # side at render time.
    se_enabled = values.get("public_search_engine_enabled", "false") == "true"
    se_slug = values.get("public_search_engine_slug", "").strip()
    public_nav = await _build_public_nav(db)
    return UiConfigResponse(
        platform_name=values.get("platform_name", "Aracne2"),
        platform_logo_url=values.get(
            "platform_logo_url",
            "/aracne-icons/lockup/aracne-lockup-vertical-512.png",
        ),
        navbar_bg_color=values.get("navbar_bg_color", "#1e40af"),
        public_home_enabled=values.get("public_home_enabled", "false") == "true",
        home_show_collections=values.get("home_show_collections", "true") == "true",
        home_show_search=values.get("home_show_search", "true") == "true",
        home_show_login_button=values.get("home_show_login_button", "true") == "true",
        has_custom_homepage_css=get_homepage_css_path() is not None,
        home_propagate_css=values.get("home_propagate_css", "false") == "true",
        evt_enabled=evt_setting_on and evt_plugin_active,
        public_search_engine_enabled=se_enabled and bool(se_slug),
        public_search_engine_slug=se_slug,
        public_pages_doc_frame_enabled=values.get(
            "public_pages_doc_frame_enabled", "true"
        ) == "true",
        home_intro_html=values.get("home_intro_html", ""),
        public_nav=public_nav,
    )


_PUBLIC_NAV_VALID_SECTIONS = ("header", "home_quick_links", "footer")


def public_link_setting_key(plugin_name: str) -> str:
    """Conventional system_settings key gating a plugin's public link.

    Toggle is ``"true"`` / ``"false"``; default ``"false"`` so an
    activated plugin never auto-publishes its public surface.
    """
    return f"public_link_{plugin_name}_enabled"


async def _build_public_nav(db: AsyncSession) -> list[PublicNavEntry]:
    """Assemble the ``public_nav`` array from active plugins' descriptors.

    A plugin contributes one entry when:
    - its row in ``plugins`` is ``active``,
    - its ``ui_descriptor`` carries a ``public_navigation`` block,
    - the matching ``public_link_<name>_enabled`` setting is ``"true"``.

    Entries with an unknown ``section`` value are dropped. The list is
    sorted by ``priority`` ascending, ties broken by ``plugin_name``.
    """
    plugin_rows = list(
        await db.scalars(
            select(Plugin).where(Plugin.status == PluginStatus.active)
        )
    )
    candidates: list[tuple[str, dict[str, object]]] = []
    for p in plugin_rows:
        desc = p.ui_descriptor or {}
        block = desc.get("public_navigation") if isinstance(desc, dict) else None
        if isinstance(block, dict):
            candidates.append((p.name, block))
    if not candidates:
        return []

    toggle_keys = [public_link_setting_key(name) for name, _ in candidates]
    toggle_rows = await db.scalars(
        select(SystemSetting).where(SystemSetting.key.in_(toggle_keys))
    )
    toggles = {r.key: r.value for r in toggle_rows}

    out: list[PublicNavEntry] = []
    for name, block in candidates:
        if toggles.get(public_link_setting_key(name)) != "true":
            continue
        section = block.get("section")
        if section not in _PUBLIC_NAV_VALID_SECTIONS:
            continue
        component = block.get("component")
        url = block.get("url")
        if not isinstance(component, str) or not isinstance(url, str):
            continue
        out.append(
            PublicNavEntry(
                plugin_name=name,
                section=section,  # type: ignore[arg-type]
                url=url,
                component=component,
                label_key=block.get("label_key") if isinstance(block.get("label_key"), str) else None,
                label_en=block.get("label_en") if isinstance(block.get("label_en"), str) else None,
                label_it=block.get("label_it") if isinstance(block.get("label_it"), str) else None,
                icon=block.get("icon") if isinstance(block.get("icon"), str) else None,
                priority=int(block.get("priority", 100)) if isinstance(block.get("priority", 100), int) else 100,
            )
        )
    out.sort(key=lambda e: (e.priority, e.plugin_name))
    return out


async def _is_plugin_active(db: AsyncSession, plugin_id: str) -> bool:
    """True when a plugin row exists and its status is ``active``."""
    from app.models.plugin import Plugin, PluginStatus

    row = await db.scalar(select(Plugin).where(Plugin.name == plugin_id))
    return row is not None and row.status == PluginStatus.active


async def upload_homepage_css(
    content: bytes,
    filename: str,
    actor: User,
) -> HomepageCssUploadResponse:
    """Save a custom homepage CSS file, replacing any previous one.

    Only ``.css`` files are accepted (max 512 KB).  The file is stored as
    ``custom_homepage.css`` in MEDIA_DIR and served via the public
    ``/settings/homepage-css/file`` endpoint.
    """
    ext = Path(filename).suffix.lower()
    if ext != ".css":
        raise DomainValidationError(
            "INVALID_FILE_TYPE",
            "Only .css files are accepted for the custom homepage stylesheet",
        )
    if len(content) > _MAX_CSS_BYTES:
        raise DomainValidationError(
            "FILE_TOO_LARGE",
            "CSS file must be ≤ 512 KB",
        )
    media = app_settings.media_dir
    media.mkdir(parents=True, exist_ok=True)
    (media / _CSS_FILENAME).write_bytes(content)
    return HomepageCssUploadResponse(url=_CSS_URL)


async def delete_homepage_css(actor: User) -> None:
    """Remove the custom homepage CSS file if present."""
    path = get_homepage_css_path()
    if path is None:
        raise NotFoundError("No custom homepage CSS has been uploaded")
    path.unlink()


async def upload_logo(
    db: AsyncSession,
    content: bytes,
    filename: str,
    actor: User,
) -> LogoUploadResponse:
    """Save a logo image file and update the platform_logo_url setting.

    Removes any previously uploaded logo before saving the new one.
    Accepts images up to 2 MB.
    """
    ext = Path(filename).suffix.lower()
    if ext not in _LOGO_ALLOWED_EXT:
        raise DomainValidationError(
            "INVALID_FILE_TYPE",
            f"Logo must be one of: {', '.join(sorted(_LOGO_ALLOWED_EXT))}",
        )
    if len(content) > _MAX_LOGO_BYTES:
        raise DomainValidationError(
            "FILE_TOO_LARGE",
            "Logo must be ≤ 2 MB",
        )

    media = app_settings.media_dir
    media.mkdir(parents=True, exist_ok=True)

    # Remove any previously uploaded logo (different extension).
    for old_ext in _LOGO_ALLOWED_EXT:
        old = media / f"logo{old_ext}"
        if old.exists():
            old.unlink()

    (media / f"logo{ext}").write_bytes(content)

    # Update the setting so /ui-config reflects the new logo URL.
    row = await db.get(SystemSetting, "platform_logo_url")
    if row:
        row.value = _LOGO_URL
        row.updated_by = actor.id
        row.updated_at = datetime.now(UTC)
    else:
        db.add(SystemSetting(key="platform_logo_url", value=_LOGO_URL, type="string"))
    await db.flush()
    return LogoUploadResponse(url=_LOGO_URL)


async def update_setting(
    db: AsyncSession, key: str, body: SettingUpdate, actor: User
) -> SettingResponse:
    row = await db.get(SystemSetting, key)
    if not row:
        raise NotFoundError(f"Setting '{key}' not found")
    _validate_value(key, body.value, row.type)
    stored_value = (
        encrypt_value(body.value, app_settings.jwt_secret)
        if key in SENSITIVE_KEYS
        else body.value
    )
    row.value = stored_value
    row.updated_by = actor.id
    row.updated_at = datetime.now(UTC)
    await db.flush()
    return _to_response(row)
