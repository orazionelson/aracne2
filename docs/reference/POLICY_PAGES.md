# `policy_pages` — institutional declarations as live forms

## Overview

`policy_pages` is the non-native plugin shipped in Milestone 3
(FUTURE_IDEAS §27). It turns the institutional declarations a
deployment must produce — mission, privacy / DPIA, storage policy,
continuity plan, CTS self-assessment, citation guide, editorial
board, etc. — into live forms inside Aracne2 with public
rendering, multi-locale support (IT / EN), append-only versioning,
and delegation through a singleton `PolicyManager` capability role
(see [CAPABILITY_ROLES.md](CAPABILITY_ROLES.md)).

For the user-facing how-to (where the page lives, how to fill the
form, how to publish) see the in-app help at
**Help → Reference → Policy pages**, source
[`backend/help_docs/05-reference/06-policy-pages.md`](../../backend/help_docs/05-reference/06-policy-pages.md).

For the original spec see [TO_DO.md](../TO_DO.md).

For the §24 footer-iterator that surfaces the public link see
[PUBLIC_NAVIGATION.md](PUBLIC_NAVIGATION.md).

---

## Architecture in one paragraph

```
Admin / PolicyManager (browser)
   │  POST /api/v1/policy-pages/<slug>/save
   │  POST /api/v1/policy-pages/<slug>/publish
   ▼
service.py
   │  validate_content (template-driven)
   │  save_draft → new policy_page_versions row
   │  publish_version → policy_pages.published_version_id := vN
   │
public visitor (browser)
   │  GET /api/v1/policies/<url_slug>?lang=it
   ▼
service.build_render_context
   │  resolves localized values + invokes platform fields' source()
   │  → Jinja2 _default.md.j2 → markdown-it → HTML
```

Two-table data model mirrors `document_versions` from M1 §7 — the
codebase has one mental model for "thing with edit history".
Save = new row; Publish = pointer flip; Unpublish = clear the
pointer. The public route 404s when there's no published version.

---

## File map

```
backend/app/plugins/policy_pages/
├── __init__.py
├── plugin.py               # PluginMeta, advertises public_navigation
├── router.py               # 8 endpoints (admin + public)
├── schemas.py              # Pydantic for the REST surface
├── service.py              # CRUD + validation + render context
├── platform.py             # 10 platform-introspection helpers
├── templates/
│   ├── __init__.py         # load_all() — 12 slugs hardcoded
│   ├── _base.py            # PolicyTemplate / Field dataclasses
│   ├── mission.py
│   ├── privacy_dpia.py
│   ├── storage_policy.py
│   ├── continuity_plan.py
│   ├── preservation_plan.py
│   ├── appraisal_policy.py
│   ├── incident_response.py
│   ├── citation_guide.py
│   ├── editorial_board.py
│   ├── funding_staffing.py
│   ├── expert_directory.py
│   └── cts_self_assessment.py
├── public_md/
│   └── _default.md.j2      # shared Markdown template all 12 use
└── tests/test_service.py

backend/app/models/
└── policy_page.py          # PolicyPage + PolicyPageVersion ORM

backend/alembic/versions/
└── 0080_policy_pages.py    # two new tables, circular FK on alter

frontend/src/
├── stores/policyPages.ts   # Pinia store (list + form + versions + manager card)
├── components/policy-pages/FieldRenderer.vue   # per-Field renderer
└── views/
    ├── admin/PolicyPagesView.vue           # master/detail editor
    └── public/PolicyPagesIndexView.vue     # /policies index
    └── public/PolicyPagePublicView.vue     # /policies/<slug>
```

---

## Data model

### Table `policy_pages`

```
policy_pages
─────────────────────────────
id                    UUID PK
template_slug         VARCHAR(64) UNIQUE     — references templates/<slug>.py
slug                  VARCHAR(128) UNIQUE    — URL slug (kebab form)
published_version_id  UUID FK → policy_page_versions.id (nullable)
created_at            TIMESTAMPTZ
updated_at            TIMESTAMPTZ
```

One row per built-in template instance (max 12 rows per
deployment). Lazy creation: the row exists only after the operator
first opens the form. `published_version_id IS NULL` means the
policy is in draft only — public 404s; only Editor+ readers see
the form.

### Table `policy_page_versions`

```
policy_page_versions
─────────────────────────────
id                UUID PK
policy_page_id    UUID FK → policy_pages.id ON DELETE CASCADE
version_number    INT                       — monotonic per page
content_jsonb     JSONB                     — Field values keyed by name
content_sha256    VARCHAR(64)               — digest of canonical JSON
message           TEXT NULL                 — Save message (optional)
saved_by_id       UUID FK → users.id ON DELETE SET NULL
saved_at          TIMESTAMPTZ

UNIQUE (policy_page_id, version_number)
```

Append-only — no retention cap (per Q9 of the M3 brainstorm).

### Migration

[`backend/alembic/versions/0080_policy_pages.py`](../../backend/alembic/versions/0080_policy_pages.py)
creates both tables. The FK from `policy_pages.published_version_id`
to `policy_page_versions.id` is created with `use_alter=True` to
break the circular reference (versions also FK back to pages).

---

## The PolicyTemplate / Field engine

### Field kinds

[`templates/_base.py`](../../backend/app/plugins/policy_pages/templates/_base.py).

| `kind` | Use for | Localizable? |
|---|---|---|
| `text` | Single-line text | yes |
| `textarea` | Multi-line text | yes |
| `integer` | Bounded number | no |
| `enum` | Pick-one | no |
| `rows` | Multi-row sub-form | per sub-field |
| `platform` | Read-only, server-resolved | n/a |

A field declares `localized=True` to make the value a per-locale
dict (`{"it": "...", "en": "..."}`); the form editor then shows
side-by-side IT / EN tabs.

### Platform fields (the auto-refresh magic)

A field with `kind="platform"` carries a zero-argument `source`
callable invoked at render time. The published policy page
auto-refreshes when the deployment state changes (e.g. operator
upgrades eXist-db) — no admin action needed.

```python
Field("postgres_version", "platform", source=postgres_version)
```

10 helpers ship in [`platform.py`](../../backend/app/plugins/policy_pages/platform.py):
`python_version`, `aracne_version`, `postgres_version`,
`existdb_version`, `plugin_active`, `system_setting`,
`active_deposit_targets`, `published_collection_count`,
`schema_catalogue`, `retention_defaults`. They are synchronous
wrappers around async DB calls so they're safe to invoke from
inside Jinja2 (which is sync). A source raising never crashes the
public render — the resolver catches the exception and falls
through to `None`, and the Markdown template renders `—`.

### Built-in templates (the 12)

[`templates/__init__.py`](../../backend/app/plugins/policy_pages/templates/__init__.py)
hardcodes the 12-slug catalogue. Adding a new template is a one-
line addition there + a new module file under `templates/`.

| Template | Categories | Highlights |
|---|---|---|
| `mission` | core, cts:R1 | Mission, scope, target community, durability |
| `privacy_dpia` | core, cts:R4 | DPO, lawful basis, takedown SLA + platform PII fields list |
| `storage_policy` | cts:R9 | RPO/RTO, key custodian + platform postgres/existdb versions |
| `continuity_plan` | cts:R3 | Successor institution + platform deposit targets list |
| `preservation_plan` | cts:R10 | Format-migration plan + schema catalogue |
| `appraisal_policy` | cts:R8 | Acceptance / rejection / deaccessioning |
| `incident_response` | cts:R16 | Contacts + escalation + disclosure timeline |
| `citation_guide` | core | Suggested citation + DOI badge status |
| `editorial_board` | core | Multi-row member table |
| `funding_staffing` | core, cts:R5 | Funding + roles + succession |
| `expert_directory` | core, cts:R6 | Multi-row expert table |
| `cts_self_assessment` | cts:meta | One operator declaration per R1–R16 |

Operators that don't pursue CTS use the `core`-tagged subset and
ignore the `cts:*` ones.

---

## REST API surface

### Admin (Editor+ read, PolicyManager + Admin write)

All under `/api/v1/policy-pages/`.

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/policy-pages` | E+ | List of all 12 templates + their state |
| `GET` | `/policy-pages/{slug}` | E+ | Hydrate form (descriptor + latest content + platform values) |
| `GET` | `/policy-pages/{slug}/versions` | E+ | Version history |
| `POST` | `/policy-pages/{slug}/save` | PolicyManager + Admin | New draft version |
| `POST` | `/policy-pages/{slug}/publish` | PolicyManager + Admin | Promote a version to public |
| `POST` | `/policy-pages/{slug}/unpublish` | PolicyManager + Admin | Hide from public |

The write endpoints use `Depends(require_capability("PolicyManager"))`
which Admin always passes — any user explicitly granted the
`PolicyManager` role also passes. See
[CAPABILITY_ROLES.md](CAPABILITY_ROLES.md) for the role
machinery.

### Public (anonymous)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/policies` | List of currently-published policies |
| `GET` | `/policies/{url_slug}?lang=it` | Render one as HTML |

`lang` defaults to the platform's `default_language` setting,
then to English. `url_slug` is the kebab form of the template
slug (e.g. `storage-policy` for `storage_policy`).

The HTML in the response comes from a controlled markdown-it
pipeline (`html: false`) so the SPA can `v-html` it safely.

---

## Validation and storage shape

`service.validate_content()`:

1. Iterates the template's fields.
2. Drops platform-field entries silently — the form might echo
   them back; they're never stored.
3. For each operator field: enforces `required`, `min/max`,
   `options` membership, the localized `{it, en}` shape, and the
   recursive shape of `rows` sub-fields.
4. Returns the canonical dict that gets stored under
   `policy_page_versions.content_jsonb`.

Empty optional fields are NOT persisted (kept `null` in the JSONB)
so the canonical SHA-256 stays stable across no-op edits.

---

## Render context

`service.build_render_context()` returns the dict
`public_md/_default.md.j2` iterates:

```jsonc
{
  "title": "policy.storage_policy.title",
  "locale": "en",
  "version": {"number": 3, "saved_at": "...", "saved_by": "..."},
  "sections": [
    {
      "name": "postgres_version",
      "label": "policy.platform.postgres_version",
      "kind": "platform",
      "value": "16.2",
      "row_labels": [],
      "rows": []
    },
    …
  ]
}
```

Localized fields resolve via `requested locale → en → any present`.
The frontend receives the rendered HTML; the SPA's vue-i18n
handles label resolution again client-side, which is why the
backend uses the `label_key` literal as the section heading
(rather than the platform's locale catalogue, which lives in the
frontend bundle).

---

## Public navigation

The plugin advertises the `public_navigation` capability in its
`PluginMeta` (per the M1 §24 primitive):

```python
ui_descriptor={
    "public_navigation": {
        "component": "PolicyPagesIndexView",
        "url": "/policies",
        "section": "footer",
        "label_key": "policy_pages.public_link_label",
        "label_en": "Policies",
        "label_it": "Politiche",
        "priority": 200,
    }
}
```

When an Admin flips the `public_link_policy_pages_enabled` toggle
in **Public Pages → Pagine → Plugin links**, the §24 footer
iterator surfaces a single "Policies" link in the public footer
pointing at `/policies`. The URL itself works regardless of the
toggle (per Q7 decision: single index link).

---

## PDF export

**Not shipped in v1.** The per-policy public view ships a Print
button that uses `window.print()` plus a small `@media print`
stylesheet that hides app chrome so the printed PDF carries only
the policy body and the version footer baked in by the Markdown
template. Server-rendered byte-deterministic PDFs are tracked as
[TO_DO.md](../TO_DO.md) — an opt-in sidecar
container so the ~80 MB of native libs only ship for deployments
that explicitly enable it.

---

## Tests

| Path | Coverage |
|---|---|
| [`backend/app/plugins/policy_pages/tests/test_service.py`](../../backend/app/plugins/policy_pages/tests/test_service.py) | 11 service-level tests — validation matrix, save/publish/unpublish round-trip, locale fallback, platform-source-raises-never-crash |
| [`backend/app/tests/test_capability_roles.py`](../../backend/app/tests/test_capability_roles.py) | PolicyManager singleton transfer, audit-row shape, REST round-trip |

---

## Open follow-ups

- **Server-side deterministic PDF** — see [TO_DO.md](../TO_DO.md).
- **Sitemap + JSON-LD inclusion**: when the platform ships a
  shared sitemap aggregator the policies index can plug in there;
  for v1 the SPA renders enough HTML for a crawler.
- **Per-template custom Markdown layout**: today every template
  uses `_default.md.j2`. A complex policy could swap that for its
  own template by changing the `public_template` field on the
  module — the engine is ready for it.
- **Custom user-supplied templates**: out of scope for v1. The
  engine could grow a dynamic-discovery layer (e.g. uploaded
  template modules) when an institution asks for one.
