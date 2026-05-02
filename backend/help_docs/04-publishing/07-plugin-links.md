# Plugin links on the public site

Some plugins ship a public-facing page — a search box, a map, a
timeline, a usage dashboard. Aracne2 lets you decide, per plugin,
**whether** that page's link appears on the public home / header /
footer, without you ever having to edit code.

The toggles live in **Admin → Public Pages → Pagine → Plugin links**.

## What you'll see

Once a plugin that supports public links is **active** (in
**Admin → Plugins**), it appears in the *Plugin links* card with a
single on/off switch and a small "Slot:" hint:

| Slot value | Where the link will appear if you turn it on |
|---|---|
| `header` | The right-hand side of the public navbar, next to **Sign in** / **Search** |
| `home_quick_links` | A tile grid below the homepage cover text (above the collection list) |
| `footer` | The footer row of every public page |

The plugin author chose the slot when they wrote the plugin; you
control the on/off.

## Default is off

Activating a plugin **never** auto-publishes its public link. The
toggle starts off so you can configure the plugin first
(API keys, budgets, content choices) before exposing it to public
visitors.

When you flip the toggle on:

- the link appears immediately (no backend restart needed),
- public visitors see it on their next page load,
- search-engine crawlers will pick it up the next time they crawl
  the site (the link is rendered in plain HTML).

When you flip the toggle off:

- the link disappears immediately,
- direct URLs to the plugin's page (e.g. `/search-nl`) still work —
  the toggle only governs *visibility*, not access. If you also
  want to disable the page entirely, deactivate the plugin from
  **Admin → Plugins**.

## What happens if no plugins are listed

Until you activate at least one plugin that ships a public-facing
page, the *Plugin links* card shows a "no plugins" message. That is
the normal state for a fresh deployment.

## Examples of plugins that use this

- **Natural-language search** (`nl_search`) — adds a "*Cerca in
  linguaggio naturale*" / "*Natural-language search*" tile below
  the homepage cover. See
  [Natural-language search](/help/page?path=03-advanced/08-nl-search).
- Future plugins on the radar (a public map, a timeline, a usage
  dashboard) will use the same toggle.

## Tips

- Test a new plugin in **Admin → Plugins** first; flip the public
  toggle on only when you are happy with how it behaves.
- If you reorganise the deployment's home page, remember the
  homepage cover text (in **Public Pages → Homepage**) renders
  *above* the plugin tiles — keep the cover text concise so the
  tiles stay above the fold.
- Reordering the links is governed by the plugin's `priority` (a
  number the author sets). Two plugins with the same priority sort
  by name. There is no per-deployment override of the order in v1
  — it has rarely been requested.

---

Technical reference: [`docs/reference/PUBLIC_NAVIGATION.md`](../../docs/reference/PUBLIC_NAVIGATION.md).
