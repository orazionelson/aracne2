# `public_navigation` capability

## Overview

`public_navigation` is the fourth UI auto-cabling capability declared
by `PluginMeta` (after `inline_authority`, `collection_deposit`,
`website_deposit`). A plugin advertises that it ships a public-facing
page; the SPA's three public-layout components iterate the active
plugins' descriptors and surface a link to that page **without** any
plugin-specific edit to `PublicHeader`, `PublicHomeSection`, or
`PublicFooter`.

Each link is gated by a per-plugin admin toggle stored in
`system_settings` under `public_link_<plugin_name>_enabled`, default
`"false"` — activating a plugin never auto-publishes its public
surface; the Admin must consciously flip the toggle from
**Public Pages → Pagine → Plugin links**.

For the user-facing how-to (where the toggles live) see the in-app
help page at **Help → Publishing → Plugin links on the public site**,
source [`backend/help_docs/04-publishing/07-plugin-links.md`](../../backend/help_docs/04-publishing/07-plugin-links.md).

For the original brainstorm see
[TO_DO.md](../TO_DO.md).

---

## Capability declaration

In the plugin's `plugin.py`:

```python
from app.core.plugin_base import PluginBase, PluginMeta

class Plugin(PluginBase):
    meta = PluginMeta(
        id="my_plugin",
        name="My Plugin",
        version="1.0.0",
        native=False,
        description="...",
        capabilities=("public_navigation",),
        ui_descriptor={
            "public_navigation": {
                "component": "MyPluginPublicView",
                "url": "/my-plugin",
                "section": "header",
                "label_key": "my_plugin.public_link_label",
                "label_en": "My plugin",
                "label_it": "Mio plugin",
                "icon": "sparkles",
                "priority": 100,
            }
        },
    )
    router = router
```

### Descriptor fields

| Field | Type | Purpose |
|---|---|---|
| `component` | string | Vue component name in `PUBLIC_PAGE_COMPONENTS` (registry below). Currently informational — each plugin still registers its own SPA route; the field exists to support a future dynamic-host renderer. |
| `url` | string | Path the link points to (e.g. `/search-nl`). The plugin owns this route in the SPA router. |
| `section` | enum | One of `"header"`, `"home_quick_links"`, `"footer"`. Decides which layout iterator surfaces the link. |
| `label_key` | string \| omitted | Optional vue-i18n key. Wins over `label_<lang>` when the key is registered in the locale file. |
| `label_en` / `label_it` | string \| omitted | Plain-string fallback per language. Used when no `label_key` resolves. |
| `icon` | string \| omitted | Heroicon name. Currently informational — not yet rendered by the iterators (reserved for future polish). |
| `priority` | int (default 100) | Sort key, ascending. Lower = leftmost / first. Ties broken by plugin name. |

### Section semantics

| Section | Where it renders | Visual treatment |
|---|---|---|
| `header` | [`frontend/src/components/layout/PublicHeader.vue`](../../frontend/src/components/layout/PublicHeader.vue) | Right-aligned navbar `router-link` next to existing entries (Search, Sign in / Dashboard) |
| `home_quick_links` | [`frontend/src/components/PublicHomeSection.vue`](../../frontend/src/components/PublicHomeSection.vue) | Tile grid below the WYSIWYG intro, hidden when the array is empty |
| `footer` | [`frontend/src/components/layout/PublicFooter.vue`](../../frontend/src/components/layout/PublicFooter.vue) | Inline link row above the © / powered-by line |

The plugin declares **one** section. Operators do not get a per-link
slot override in v1; if a plugin should also appear elsewhere, it
declares a second descriptor entry (currently unsupported — the
loader expects exactly one block under `public_navigation`).

---

## Backend

### Auto-creation of the toggle row

When a plugin declaring `public_navigation` is activated through the
admin UI, [`activate_plugin`](../../backend/app/services/plugins.py)
upserts a `public_link_<name>_enabled = "false"` row in
`system_settings`. Native plugins (always active) and
already-installed-and-active deployments are covered by the
[`sync_registry`](../../backend/app/core/plugin_loader.py) path,
which performs the same idempotent insert at every backend boot.

### Public exposure on `UiConfigResponse`

[`backend/app/services/settings.py:_build_public_nav`](../../backend/app/services/settings.py)
walks active plugins, intersects with the per-plugin toggle, drops
malformed descriptors silently, and returns a list of
[`PublicNavEntry`](../../backend/app/schemas/settings.py) objects on
`UiConfigResponse.public_nav`:

```jsonc
{
  "data": {
    // …existing fields…
    "public_nav": [
      {
        "plugin_name": "nl_search",
        "section": "home_quick_links",
        "url": "/search-nl",
        "component": "NlSearchPublicView",
        "label_key": "nl_search.public_link_label",
        "label_en": "Natural-language search",
        "label_it": "Cerca in linguaggio naturale",
        "icon": "sparkles",
        "priority": 100
      }
    ]
  }
}
```

The endpoint is **public** (no auth) — anonymous public visitors
need it to render the home page.

### Validation

`_build_public_nav` drops:

- entries with an unknown `section` value;
- entries missing `component` or `url` (or those not strings);
- plugins whose toggle is not `"true"`;
- plugins not currently `active`.

A misconfigured plugin therefore degrades to "no link" rather than
crashing the public config endpoint.

---

## Frontend

### Component registry

[`frontend/src/components/public-pages/registry.ts`](../../frontend/src/components/public-pages/registry.ts)
mirrors `LOOKUP_COMPONENTS` / `DEPOSIT_COMPONENTS` /
`WEBSITE_DEPOSIT_COMPONENTS`. Adding a new public-navigation plugin
is a single line:

```ts
export const PUBLIC_PAGE_COMPONENTS: Record<string, Component> = {
  NlSearchPublicView: defineAsyncComponent(
    () => import("@/views/public/NlSearchPublicView.vue"),
  ),
  // future plugins land one line each
};
```

### Iteration helper

[`frontend/src/composables/usePublicNav.ts`](../../frontend/src/composables/usePublicNav.ts)
exposes two helpers used by all three layout components:

```ts
const headerLinks = usePublicNav("header");        // ComputedRef<PublicNavEntry[]>
const labelFor    = usePublicNavLabel();           // (entry) => string
```

`publicNavLabel` resolves the label in this order:
1. `label_key` via vue-i18n when the key is registered;
2. `label_<active locale>`;
3. `label_en` as universal fallback;
4. `plugin_name` (last resort).

### Route registration

Each plugin still adds its own route in [`frontend/src/router/index.ts`](../../frontend/src/router/index.ts)
under `meta.layout: "public"`. The descriptor's `url` is purely a
link target — the SPA router resolves it the usual way.

### Admin toggle UI

[`frontend/src/views/admin/PublicPagesView.vue`](../../frontend/src/views/admin/PublicPagesView.vue)
auto-generates a toggle row inside the **Pagine** tab for every
active plugin advertising the capability. The section name is shown
read-only (the descriptor decides the slot in v1; admins toggle on/off only).

---

## REST surface

No new endpoints. Admins flip the per-plugin toggle through the
existing
`PUT /api/v1/settings/public_link_<plugin_name>_enabled` surface
that powers every other system setting.

---

## Tests

| Path | Coverage |
|---|---|
| [`backend/app/tests/test_public_navigation.py`](../../backend/app/tests/test_public_navigation.py) | activate idempotency, sync_registry path, hidden-when-toggle-off, hidden-when-plugin-inactive, exposed-with-full-descriptor, priority+name sort order, malformed-descriptor drop |

---

## Adding a new public-navigation plugin

Checklist for a future plugin author:

1. Declare `capabilities=("public_navigation",)` and a matching
   `ui_descriptor.public_navigation` block in `plugin.py`.
2. Register a Vue component in `PUBLIC_PAGE_COMPONENTS` (one line).
3. Register the SPA route under `PublicLayout` in
   [`frontend/src/router/index.ts`](../../frontend/src/router/index.ts).
4. Add the i18n keys for `label_key` (if used) to both
   `frontend/src/locales/en.json` and `it.json`.
5. Activate the plugin from `/admin/plugins`.
6. Flip the per-plugin toggle on from
   **Public Pages → Pagine → Plugin links**.

The only file that knows the plugin exists is the plugin itself
plus those two registry entries — no edit to `PublicHeader` /
`PublicHomeSection` / `PublicFooter` is required.

---

## Future plugins on the radar

The brainstorm in [TO_DO.md](../TO_DO.md) lists three
candidate consumers beyond `nl_search` (the first to ship): a
`public_maps` plugin, a `public_timeline` plugin, and a
`public_usage` analytics page. Each lands as a one-PR addition with
the checklist above.
