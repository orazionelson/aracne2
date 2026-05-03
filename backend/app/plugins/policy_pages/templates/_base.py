"""``PolicyTemplate`` / ``Field`` declarative engine.

Phase PP-C of Milestone 3. Each built-in template module under
``app.plugins.policy_pages.templates`` exports a ``TEMPLATE``
constant of type :class:`PolicyTemplate` that describes:

- the template's URL slug, title key, categories;
- the ordered list of :class:`Field` objects that make up the
  form;
- the Markdown public-render template the frontend renders.

Field types in v1:

- ``text``      — single-line, optionally multi-locale.
- ``textarea``  — multi-line (paragraph), optionally multi-locale.
- ``integer``   — bounded number; never multi-locale.
- ``enum``      — pick-one from ``options``.
- ``rows``      — repeating sub-form (multi-row table). Each row
                  has its own list of sub-fields.
- ``platform``  — read-only; the value is computed at render time
                  by the ``source`` callable defined per platform-
                  helper. The form editor renders these greyed-out
                  with the current evaluated value.

A field can declare ``localized=True`` to make the value a
``{"it": "...", "en": "..."}`` dict instead of a plain string.
The engine validates either shape on save; the form editor
renders side-by-side IT / EN tabs only for localized fields.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal


FieldKind = Literal[
    "text", "textarea", "integer", "enum", "rows", "platform"
]


@dataclass(frozen=True)
class Field:
    """One form field inside a :class:`PolicyTemplate`.

    Attributes:

    - ``name`` — Python identifier; the key under which the value
      is stored in ``content_jsonb``. Stable across template
      revisions; renaming requires a data migration.
    - ``kind`` — see :data:`FieldKind`.
    - ``label_key`` — vue-i18n key for the form label. Resolves to
      both EN and IT in the locale files; the admin UI picks per
      its current locale. Falls back to ``name``.
    - ``hint_key`` — optional secondary key for the help text shown
      under the field.
    - ``required`` — whether the field must be non-empty on Save.
    - ``localized`` — when True, the value is a per-locale dict.
      Only meaningful for ``text`` / ``textarea`` / ``rows`` (rows'
      sub-fields each carry their own ``localized`` flag).
    - ``options`` — enum choices, one of which the value must be.
    - ``min`` / ``max`` — integer bounds.
    - ``rows_fields`` — for ``kind="rows"``, the sub-form's field list.
    - ``source`` — for ``kind="platform"``, a zero-argument callable
      invoked at render time. Returns the value to splice into the
      Markdown template. Side-effect-free expected.
    """

    name: str
    kind: FieldKind
    label_key: str | None = None
    hint_key: str | None = None
    required: bool = False
    localized: bool = False
    options: tuple[str, ...] = ()
    min: int | None = None
    max: int | None = None
    rows_fields: tuple["Field", ...] = ()
    source: Callable[[], Any] | None = None

    def is_platform(self) -> bool:
        return self.kind == "platform"

    def to_descriptor(self) -> dict[str, Any]:
        """Return the JSON-serialisable shape the SPA receives.

        ``source`` callables are intentionally NOT serialised — the
        SPA never needs them; their evaluated value reaches the
        public render via the backend's render path. The form
        editor receives only ``current_value`` (filled in by the
        service layer at the moment the form is fetched).
        """
        return {
            "name": self.name,
            "kind": self.kind,
            "label_key": self.label_key,
            "hint_key": self.hint_key,
            "required": self.required,
            "localized": self.localized,
            "options": list(self.options),
            "min": self.min,
            "max": self.max,
            "rows_fields": [f.to_descriptor() for f in self.rows_fields],
            "is_platform": self.is_platform(),
        }


@dataclass(frozen=True)
class PolicyTemplate:
    """One built-in policy template.

    Attributes:

    - ``slug`` — module name; doubles as the URL slug derived to
      kebab-case (``"storage_policy"`` → ``/policies/storage-policy``).
    - ``title_key`` — vue-i18n key for the human-facing title.
    - ``categories`` — free-form tags (``"core"``, ``"cts:R7"``,
      …) that the admin UI uses for filtering / grouping.
    - ``fields`` — ordered list of :class:`Field` objects.
    - ``public_template`` — Markdown filename inside
      ``app/plugins/policy_pages/public_md/`` that renders the
      public page.
    """

    slug: str
    title_key: str
    categories: tuple[str, ...]
    fields: tuple[Field, ...]
    public_template: str

    def url_slug(self) -> str:
        """Kebab-case form of the module slug, used in the public URL."""
        return self.slug.replace("_", "-")

    def field_by_name(self, name: str) -> Field | None:
        for f in self.fields:
            if f.name == name:
                return f
        return None

    def operator_fields(self) -> tuple[Field, ...]:
        """Subset that the operator actually fills in on the form."""
        return tuple(f for f in self.fields if not f.is_platform())

    def platform_fields(self) -> tuple[Field, ...]:
        """Subset that auto-resolves at render time."""
        return tuple(f for f in self.fields if f.is_platform())

    def to_descriptor(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "url_slug": self.url_slug(),
            "title_key": self.title_key,
            "categories": list(self.categories),
            "fields": [f.to_descriptor() for f in self.fields],
        }


__all__ = ["Field", "FieldKind", "PolicyTemplate"]
