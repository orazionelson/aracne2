# Depositing on external repositories

Once an Admin activates the relevant plugins on `/admin/plugins`,
the editorial flow gains several "Deposit" / "Push" / "Archive"
buttons that send a published collection or a built website to an
external repository or versioning service.

Every integration is **opt-in** at the deployment level — you only
see a section if the corresponding plugin is active and the Admin
has pasted the credentials. Most are **manual** at the editorial
level (you click a button); the Zenodo / Internet Archive / Dataverse
plugins also offer an *auto-deposit on collection publish* toggle
in their config page.

## Where the controls live

### On the collection page (`/collections/<slug>`)

Each active "deposit-style" plugin renders its own section above
the Documents list. You'll see one or more of:

- **Deposito Zenodo** — DOI minting on Zenodo, with a per-collection
  resource-type override and an "Upload as single ZIP" toggle.
- **Archived on Wayback** badge + Archive / Refresh buttons —
  Internet Archive Save Page Now.
- **Deposit on Dataverse** — DOI minting on a Dataverse instance,
  with a "Use a different alias for this deposit" link if you need
  to route this single deposit to a different sub-Dataverse.
- **Codeberg / GitHub / GitLab deposit** — Connect / Push /
  Initialize / Disconnect controls. Each forge is a separate
  section but shares the same UI shape.

### On the website edit page (`/admin/websites/<slug>/edit`)

The new **Deposit** tab (last item in the tab bar) hosts the same
plugins, but each section now targets the *rendered output* of the
website rather than the collection's TEI source files.

The website must be in **STATIC** or **HYBRID** rendering mode and
have `build_status = done` for the buttons to be enabled — DYNAMIC
sites have nothing to deposit (the HTML is rendered live per
request).

## What each plugin does

| Plugin | Targets | Identifier returned |
|---|---|---|
| **Zenodo Deposit** | Collection's TEI files (one-by-one or zipped) AND/OR website's rendered tree | DOI on publish; draft URL until then |
| **Internet Archive** | The collection's public URL AND/OR the website's public URL | Wayback Machine snapshot URL |
| **Dataverse Integration** | Collection's TEI files OR website's rendered tree on any Dataverse instance | DOI immediately on dataset creation (preallocated until publish) |
| **Codeberg / GitHub / GitLab** | One commit per push containing every TEI file (collection) or every rendered file (website) | Commit SHA |

## Common operations

### Push (Aracne2 → external service)

The standard direction. Click the deposit / push / archive button
and the plugin sends the current state of the collection or website
to the external service. Always available once the link / config
exists.

### Initialize (forge → empty Aracne2 collection)

A safety-asymmetric **one-shot** operation available on the
Codeberg / GitHub / GitLab sections only. Imports every XML file
from a git repository into an *empty* Aracne2 collection. Once the
collection has any document (imported or hand-created) Initialize
is permanently disabled — the only allowed direction from then on
is push.

Use this when you have an existing TEI corpus that already lives
on a git forge and you want to migrate it into Aracne2. XML is
validated before a single byte reaches eXist-db, so a malformed
file aborts the whole import — you won't end up with a
half-populated collection.

### Refresh (Internet Archive only)

Save Page Now sometimes takes longer than the 60-second polling
window the plugin allows on submit. When that happens the badge
stays "Pending" and a Refresh button appears next to it — clicking
it re-polls the SPN2 job for the result without resubmitting.

## Per-link PAT override (git forges)

The plugin's global PAT is normally enough — every link uses it by
default. But each link also has an optional per-link PAT field
that wins over the global token. Useful when a specific collection
lives under a different organisation or namespace whose token you
don't want to share globally.

The per-link override is Fernet-encrypted at rest just like the
global PAT.

## Per-deposit alias override (Dataverse)

Dataverse's "alias" identifies the sub-Dataverse a dataset belongs
to inside an instance (e.g. `tei-editions` for one research group,
`dh-2026` for another). The plugin's config sets a default alias;
each deposit can override it via the **Use a different alias for
this deposit…** link. Useful when one institution hosts multiple
research-group Dataverses inside the same instance.

## Self-hosted instances

All the integrations support self-hosted instances via a configurable
base URL on the plugin config page (or per-link for the forges):

- **Codeberg** → any Forgejo or Gitea install (e.g. an institutional
  `git.example.edu`)
- **GitHub** → GitHub Enterprise Server (the adapter rewrites API
  calls to the `/api/v3/` prefix transparently)
- **GitLab** → any self-hosted GitLab instance
- **Dataverse** → any institutional Dataverse (default is the public
  sandbox at `https://demo.dataverse.org`)

## Statuses you'll see

| Status | What it means | What to do |
|---|---|---|
| **Draft** | Deposit reached the external service but is not yet public | Open the dataset on the service's site and publish from there (or enable the plugin's auto-publish toggle for next time) |
| **Pending** | (Internet Archive only) The Wayback job is still processing | Click Refresh; if it stays pending for >5 min, click Archive again |
| **Published** | Deposit is finalised; the DOI / Wayback URL resolves | You're done — quote the DOI or share the URL |
| **Failed** | The external service rejected the request | Check the error message under the badge; usually a token / permission issue |

## A note on Dataverse DOIs

Unlike Zenodo (which only mints a DOI on publish), Dataverse mints
a DOI **immediately** when the dataset is created — even in draft
state. The badge shows the DOI from the start, but until you publish
the dataset on Dataverse the DOI is *preallocated*: the link inside
the badge goes to the Dataverse landing page (which always works),
not to `https://doi.org/...` (which only resolves after publish).
