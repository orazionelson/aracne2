# Extensions catalog

A complete reference of every extension (plugin) that ships with
Aracne2, grouped by purpose. Each plugin is **opt-in**: an Admin
activates it under `/admin/plugins`, pastes credentials (when
needed) on its Configure page, and restarts the backend so the
plugin's routes mount.

When a plugin is inactive its UI is hidden — no dead buttons, no
phantom tabs. Deactivating a plugin later leaves any state it wrote
intact, so re-activation picks up where you left off.

## Quick index

| Category | Plugins |
|---|---|
| **Deposit on external repositories** (DOI minting, archival) | [Zenodo](#zenodo-deposit), [Dataverse](#dataverse-integration), [Internet Archive](#internet-archive) |
| **Push to a git forge** (source + website versioning) | [Codeberg](#codeberg-integration), [GitHub](#github-integration), [GitLab](#gitlab-integration) |
| **External reference lookups** (turn a selection into an authoritative `@ref` URL) | [Wikidata](#wikidata), [ORCID](#orcid), [ROR](#ror), [VIAF](#viaf), [GeoNames](#geonames), [GND](#gnd), [CERL](#cerl-thesaurus), [Peripleo](#peripleo), [Getty AAT](#getty-aat), [OpenAlex](#openalex), [Trismegistos](#trismegistos), [CrossRef](#crossref-doi-resolver) |
| **Content import** | [Zotero Import](#zotero-import) |
| **Viewer & utility** | [EVT Viewer](#evt-viewer), [Help](#help) |

See also: [Depositing on external repositories](/help/page?path=04-publishing/04-external-repositories) for the walk-through, and [External reference lookups](/help/page?path=03-advanced/05-external-reference-lookups) for the editor-side flow of the authority plugins.

---

## Deposit on external repositories

### Zenodo deposit

![Zenodo](img/logos/zenodo.png)
*Logo placeholder — drop `zenodo.png` under `backend/help_docs/img/logos/`.*

Deposits a collection's TEI files (or a website's rendered output) on
**Zenodo** (CERN's research repository), returning a citable DOI on
publish. Supports the sandbox at `https://sandbox.zenodo.org` and
the production `https://zenodo.org`.

- **Where the UI appears**: a "Deposito Zenodo" section on each
  collection detail page; a "Deposit website on Zenodo" section in
  the Website edit page's Deposit tab.
- **Configuration**: Admin → `/admin/plugins/zenodo_deposit/config`.
  Paste a Zenodo API token (Fernet-encrypted at rest).
- **Triggers**: auto on collection publish (toggleable) + manual
  "Re-deposit". Website deposit is manual-only.
- **Choice per deposit**: upload each file individually or bundle
  the collection / website as a single `{slug}.zip`.

---

### Dataverse integration

![Dataverse](img/logos/dataverse.png)
*Logo placeholder — drop `dataverse.png` under `backend/help_docs/img/logos/`.*

Deposits collections or websites on any **Dataverse** instance —
the public sandbox at `https://demo.dataverse.org` or an
institutional Dataverse via the configurable base URL. Mint a DOI
immediately on dataset creation (preallocated; resolves after
publish).

- **Where the UI appears**: "Deposit on Dataverse" section on the
  collection detail page and a parallel section in the Website edit
  page's Deposit tab.
- **Configuration**: Admin → `/admin/plugins/dataverse_integration/config`.
  Token + base URL + default Dataverse *alias* (the sub-Dataverse
  that hosts your datasets) + contact email + publish type
  (major / minor / updatecurrent).
- **Per-deposit override**: a "Use a different alias for this deposit"
  link lets a single collection / website land in a different
  sub-Dataverse than the plugin default.

---

### Internet Archive

![Internet Archive](img/logos/internet-archive.png)
*Logo placeholder — drop `internet-archive.png` under `backend/help_docs/img/logos/`.*

Submits a collection's or website's **public URL** to the Wayback
Machine via Save Page Now 2. The returned snapshot URL is stored
on the entity and surfaced as a badge.

- **Where the UI appears**: "Archived on Wayback" badge +
  Archive / Refresh buttons on each collection detail page; a
  "Save website on Wayback" section in the Website edit page's
  Deposit tab.
- **Configuration**: Admin → `/admin/plugins/internet_archive/config`.
  S3-style access key + secret key (Fernet-encrypted).
- **Triggers**: auto on collection publish (toggleable) + manual
  + Refresh (re-polls pending SPN2 jobs). Websites are manual-only.
- **All rendering modes** (STATIC / HYBRID / DYNAMIC) are valid
  for websites — Wayback just needs an HTML URL.

---

## Push to a git forge

All three forge plugins share the same UX: a Connect form (repo
owner + name + branch + optional per-link PAT override), a Push
button that creates a single commit containing every file, and —
for collections only — a one-shot **Initialize** button that
imports a corpus from the forge into an *empty* Aracne2 collection.

### Codeberg integration

![Codeberg](img/logos/codeberg.png)
*Logo placeholder — drop `codeberg.png` under `backend/help_docs/img/logos/`.*

European-hosted, vendor-neutral git forge powered by Forgejo /
Gitea. The per-link `base_url` accepts any self-hosted Forgejo
(institutional deployments) out of the box.

- **Where the UI appears**: "Codeberg deposit" section on each
  collection detail page (Connect / Push / Initialize / Disconnect);
  parallel section in the Website edit page's Deposit tab.
- **Configuration**: Admin → `/admin/plugins/codeberg_integration/config`.
  Just the global PAT — repo configuration lives per link.
- **PAT scope**: `write:repository`. Get a token at
  `https://codeberg.org/user/settings/applications`.

### GitHub integration

![GitHub](img/logos/github.png)
*Logo placeholder — drop `github.png` under `backend/help_docs/img/logos/`.*

Supports **github.com** and **GitHub Enterprise Server** — the
adapter rewrites API calls to the `/api/v3/` prefix when the
per-link `base_url` points at a GHE instance.

- **Where the UI appears**: "GitHub deposit" section on each
  collection detail page; parallel section on the Website edit
  page's Deposit tab.
- **Configuration**: Admin → `/admin/plugins/github_integration/config`.
- **PAT scope**: `repo` (classic PATs) or `Contents: read & write`
  (fine-grained PATs). Create one at
  `https://github.com/settings/tokens`.

### GitLab integration

![GitLab](img/logos/gitlab.png)
*Logo placeholder — drop `gitlab.png` under `backend/help_docs/img/logos/`.*

Covers **gitlab.com** and any self-hosted GitLab. Nested group
paths are supported — put the full path (e.g.
`group/subgroup`) in the link's `Owner` field.

- **Where the UI appears**: same shape as the other two forges.
- **Configuration**: Admin → `/admin/plugins/gitlab_integration/config`.
- **PAT scope**: `api` (classic) or `write_repository`
  (fine-grained / project-access tokens). Get one at
  `https://gitlab.com/-/user_settings/personal_access_tokens`.

---

## External reference lookups

The authority-lookup family turns an editor's selection inside a
TEI element into an authoritative `@ref` URL. Every plugin in this
family has the same shape: a toolbar chip in the TEI editor opens
a side panel, the editor types a search (or pastes an ID), picks
a hit, and the chosen URI is written as the `@ref` attribute on
the enclosing tag.

For the walk-through see the dedicated page:
[External reference lookups](/help/page?path=03-advanced/05-external-reference-lookups).

### Wikidata

![Wikidata](img/logos/wikidata.png)
*Logo placeholder — `wikidata.png`.*

Free, structured-data cousin of Wikipedia. Best for any named
entity (person, place, organisation, work, event). No auth.
Applies to `<persName>`, `<placeName>`, `<orgName>`, etc.

### ORCID

![ORCID](img/logos/orcid.png)
*Logo placeholder — `orcid.png`.*

Canonical identifier for researchers. Applies to `<persName>`.
No auth for public search.

### ROR

![ROR](img/logos/ror.png)
*Logo placeholder — `ror.png`.*

Research Organization Registry. Applies to `<orgName>` (academic
institutions, funders). No auth.

### VIAF

![VIAF](img/logos/viaf.png)
*Logo placeholder — `viaf.png`.*

Virtual International Authority File — cross-references name
authorities from many national libraries. Applies to `<persName>`.
No auth.

### GeoNames

![GeoNames](img/logos/geonames.png)
*Logo placeholder — `geonames.png`.*

Global gazetteer of named geographic entities. Applies to
`<placeName>`. Requires a free GeoNames username; the plugin ships
with a shared default (`aracne`) that a deployment can override
via the `geonames_username` system setting.

### GND

![GND](img/logos/gnd.png)
*Logo placeholder — `gnd.png`.*

Gemeinsame Normdatei — the German National Library authority file,
via **lobid.org**. Covers persons, places, organisations, works,
subjects. No auth.

### CERL Thesaurus

![CERL](img/logos/cerl.png)
*Logo placeholder — `cerl.png`.*

Authority file for the early-modern book trade (authors, printers,
places, imprints). Especially useful for 15th–18th-century
editions. No auth.

### Peripleo

![Peripleo](img/logos/peripleo.png)
*Logo placeholder — `peripleo.png`.*

Pelagios Network aggregator — Peripleo unifies ancient-world
gazetteers (Pleiades, iDAI, DARE, etc.) behind one search. Applies
to `<placeName>`. No auth.

### Getty AAT

![Getty AAT](img/logos/getty-aat.png)
*Logo placeholder — `getty-aat.png`.*

Art & Architecture Thesaurus — controlled vocabulary for art,
architecture, material culture. Applies to `<term>`. No auth; the
plugin uses the Getty SPARQL endpoint.

### OpenAlex

![OpenAlex](img/logos/openalex.png)
*Logo placeholder — `openalex.png`.*

Bibliographic database — successor to Microsoft Academic Graph.
Inserts a TEI `<biblStruct>` fragment at the cursor from any
paper / book record. Uses a polite-pool contact email
(`openalex_contact_email` setting) for faster responses.

### Trismegistos

![Trismegistos](img/logos/trismegistos.png)
*Logo placeholder — `trismegistos.png`.*

Registry of pre-800 AD documentary texts from Egypt and the
Mediterranean (papyri, ostraca, inscriptions). **ID resolver**
(not a free-text search — Trismegistos doesn't publish one):
paste a TM ID or a partner-project ID (DDBDP, HGV, PHI, …) with
the right source selector, and the plugin returns the canonical
TM URL plus cross-references.

### CrossRef DOI resolver

![CrossRef](img/logos/crossref.png)
*Logo placeholder — `crossref.png`.*

Paste a DOI → get a TEI `<biblStruct>` fragment auto-filled from
CrossRef's public record. Uses a polite-pool contact email
(`crossref_contact_email` setting). No auth.

---

## Content import

### Zotero import

![Zotero](img/logos/zotero.png)
*Logo placeholder — `zotero.png`.*

Pull a **Zotero** group library into a collection's bibliography
in one operation. Maps Zotero items → TEI `<bibl>` / `<biblStruct>`
entries. Preview-then-commit flow: the editor sees what will be
imported and can still cancel.

- **Where the UI appears**: "Import from Zotero" button on the
  collection detail page (EiC+).
- **Configuration**: Admin → `/admin/plugins/zotero_import/config`.
  Zotero read-only API key + group ID (Fernet-encrypted key).

---

## Viewer & utility

### EVT viewer

![EVT](img/logos/evt.png)
*Logo placeholder — `evt.png`.*

Feeds the external **EVT 2** viewer with collection config + raw
XML via two public endpoints. The viewer UI itself is a separate
nginx container activated via the `evt` Docker Compose profile.

- **Where the UI appears**: a "Read in EVT" button on published,
  single-document, public collections (when the plugin is active
  **and** the global EVT toggle is on **and** the per-collection
  `evt_enabled` flag is on).
- **Configuration**: Admin → `/admin/plugins/evt/config`. Global
  toggle only — per-collection opt-in lives on the collection edit
  form.

### Help

![Help](img/logos/help.png)
*Logo placeholder — `help.png`.*

The very plugin you're reading from. Renders every markdown file
under `backend/help_docs/` as sanitised HTML and exposes a
full-text search across the tree.

- **Where the UI appears**: the `/help` drawer (left-hand nav).
- **Configuration**: none — the plugin has no tunables.
- **Adding pages**: drop markdown files under
  `backend/help_docs/<section>/<file>.md`; the plugin picks them
  up on the next cache refresh (Admin → `Refresh` button at the
  top of the Help page).

---

## Activating / deactivating a plugin

1. Navigate to `/admin/plugins` (Admin only).
2. Switch to the **Estensioni** tab to see non-native plugins.
3. Click **Attiva** on the plugin you want. The row becomes
   "Attivo".
4. If the plugin exposes routes or hooks (most do), restart the
   backend so the routes mount:
   `docker compose restart backend`.
5. Click **Configura** on the now-active plugin and paste the
   credentials it needs. Save.
6. The plugin's UI appears wherever documented above.

To deactivate: same page, **Disattiva** button. The plugin's UI
disappears but the plugin's data (settings, stored tokens,
per-collection state) stays intact — re-activation picks up where
you left off.

## Adding logo images

The logo placeholders above refer to files under
`backend/help_docs/img/logos/`. To add real logos:

1. Obtain the official service logo (most services publish brand
   assets on a press / brand / identity page).
2. Save it as `<slug>.png` under `backend/help_docs/img/logos/`
   — the slug should match the one used in the markdown
   placeholders (e.g. `wikidata.png`, `zenodo.png`).
3. Reload this help page (or click the Admin **Refresh** button
   to clear the help cache).

The help plugin serves static assets automatically through
`/api/v1/plugins/help/assets/…` — no code change needed.
