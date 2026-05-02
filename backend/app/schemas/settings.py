from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator


class SettingResponse(BaseModel):
    key: str
    value: str
    type: str
    description: str | None
    updated_at: datetime

    model_config = {"from_attributes": True}


PublicNavSection = Literal["header", "home_quick_links", "footer"]


class PublicNavEntry(BaseModel):
    """One link surfaced on the public site by an active plugin.

    Plugins advertise these via the ``public_navigation`` capability
    in ``PluginMeta.ui_descriptor``; the platform exposes them on
    ``UiConfigResponse.public_nav`` only when the matching
    ``public_link_<plugin_name>_enabled`` system_setting is ``"true"``.
    The frontend layout components iterate the array filtered by
    ``section`` and sort by ``priority`` ascending.
    """

    plugin_name: str
    section: PublicNavSection
    url: str
    component: str
    label_key: str | None = None
    label_en: str | None = None
    label_it: str | None = None
    icon: str | None = None
    priority: int = 100


class UiConfigResponse(BaseModel):
    platform_name: str
    platform_logo_url: str
    navbar_bg_color: str
    public_home_enabled: bool
    home_show_collections: bool
    home_show_search: bool
    home_show_login_button: bool
    has_custom_homepage_css: bool
    home_propagate_css: bool
    evt_enabled: bool
    # When ``public_search_engine_enabled`` is true and ``public_search_engine_slug``
    # is non-empty, the public navbar shows a "Search" entry pointing at
    # /search, which embeds the built engine identified by the slug.
    public_search_engine_enabled: bool
    public_search_engine_slug: str
    # When false, the public-document iframe auto-grows to its content
    # height (no fixed box, parent page scrolls). Default true keeps
    # the historical fixed-height frame.
    public_pages_doc_frame_enabled: bool
    # Free-form intro HTML rendered above the collection list on the
    # public homepage. Empty when no intro has been authored yet.
    home_intro_html: str
    # Plugin-declared public links, surfaced by ``public_navigation``-
    # capable active plugins whose admin toggle is on. Empty when no
    # plugin advertises the capability or none of them is enabled.
    public_nav: list[PublicNavEntry] = []


class LogoUploadResponse(BaseModel):
    url: str


class HomepageCssUploadResponse(BaseModel):
    url: str


class SettingUpdate(BaseModel):
    value: str

    @field_validator("value")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("value cannot be empty")
        return v
