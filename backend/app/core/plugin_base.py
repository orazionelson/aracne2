"""
PluginBase — abstract base class for all Aracne2 plugins.

Every plugin (native or non-native) defines a class named ``Plugin``
that inherits from ``PluginBase`` and sets the ``meta`` and ``router``
class variables.

Native plugins (``meta.native = True``) are always loaded and active.
They cannot be deactivated or deleted via the Admin UI.

Non-native plugins start as inactive and can be toggled by Admin.
Changes to activation status take effect after a server restart.
"""

from abc import ABC
from dataclasses import dataclass, field
from typing import ClassVar

from fastapi import APIRouter


@dataclass(frozen=True)
class PluginMeta:
    """Immutable descriptor declared by each plugin."""

    id: str
    """Unique slug. Must match the plugin folder name and Plugin.name in DB."""

    name: str
    """Human-readable display name shown in the Admin UI."""

    version: str
    """Semver string (e.g. "1.0.0")."""

    native: bool
    """True = always active, cannot be deactivated or deleted."""

    description: str
    """Short description shown in the Admin UI."""

    author: str = field(default="Aracne2 Team")
    """Author name shown in the Admin UI."""

    min_role: str = field(default="Admin")
    """Minimum role required to interact with this plugin's UI."""

    capabilities: tuple[str, ...] = field(default_factory=tuple)
    """Tags describing what UI surfaces this plugin populates.

    The platform itself does not interpret them — they are a contract
    between the plugin and the frontend. Today the SPA recognises:

    * ``inline_authority`` — adds a button + side panel to the TEI
      editor toolbar that opens an authority lookup for the current
      selection (Wikidata, ORCID, ROR, …).

    * ``collection_deposit`` — adds a tab to the collection detail
      page's "Deposita" foldable, exposing the per-collection
      configuration / actions for an external deposit target
      (Zenodo, Internet Archive, Codeberg, GitHub, GitLab,
      Dataverse, …). The plugin owns its tab body component.

    The plugin must also declare a matching entry under
    :attr:`ui_descriptor`. Future capabilities follow the same
    shape — a string tag here plus a typed entry there.
    """

    ui_descriptor: dict[str, dict[str, object]] | None = field(default=None)
    """Per-capability UI metadata, keyed by capability name.

    For ``inline_authority`` the dict is shaped::

        {
          "component": "WikidataLinkPanel",   # name in the SPA registry
          "label_key": "lookups.wikidata",    # vue-i18n key
          "icon_color": "text-amber-500",     # Tailwind class on toolbar icon
          "apply": "ref",                     # "ref" | "fragment"
          "initial_context": "selection",     # "selection" | "selection-or-empty" | "kind-picker"
          "priority": 100,                    # toolbar sort key (lower = leftmost)
        }

    For ``collection_deposit`` the dict is shaped::

        {
          "component": "ZenodoCollectionDepositPanel",  # name in the SPA registry
          "label": "Zenodo",                            # tab label (plain text)
          "label_key": "deposits.zenodo",               # optional vue-i18n key (overrides label)
          "priority": 100,                              # tab sort key (lower = leftmost)
        }
    """


class PluginBase(ABC):
    """Abstract base for all Aracne2 plugins.

    Subclasses must set the class variables ``meta`` and ``router``.
    """

    meta: ClassVar[PluginMeta]
    router: ClassVar[APIRouter]

    @classmethod
    def on_activate(cls) -> None:
        """Called once when the plugin is activated via the Admin UI.

        Never called for native plugins (they are always active).
        Override to perform one-time setup (e.g. schedule background tasks).
        """

    @classmethod
    def on_deactivate(cls) -> None:
        """Called once when the plugin is deactivated via the Admin UI.

        Never called for native plugins.
        Override to perform cleanup (e.g. cancel background tasks).
        """
