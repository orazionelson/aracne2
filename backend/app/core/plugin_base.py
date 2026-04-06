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
