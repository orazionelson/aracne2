# Aracne2 — User Manual

> This manual is written for users who are not developers. It explains what
> Aracne2 does, who can do what, and how to accomplish the most common tasks.
> Technical implementation details are deliberately omitted.

---

## Table of contents

1. [What is Aracne2?](#1-what-is-aracne2)
2. [Who you are — Roles](#2-who-you-are--roles)
3. [Logging in and your profile](#3-logging-in-and-your-profile)
4. [Collections — the main organizing unit](#4-collections--the-main-organizing-unit)
5. [Documents — your XML files](#5-documents--your-xml-files)
6. [The TEI editor](#6-the-tei-editor)
7. [The editorial workflow](#7-the-editorial-workflow)
8. [Validating documents](#8-validating-documents)
9. [Facsimile images and page links](#9-facsimile-images-and-page-links)
10. [Zone editor — linking text to image regions](#10-zone-editor--linking-text-to-image-regions)
11. [Notes](#11-notes)
12. [Named entities](#12-named-entities)
13. [Bibliography (Bibliobuilder)](#13-bibliography-bibliobuilder)
14. [AI assistance](#14-ai-assistance)
15. [Websites — publishing to the web](#15-websites--publishing-to-the-web)
16. [EVT viewer](#16-evt-viewer)
17. [Notifications](#17-notifications)
18. [Search](#18-search)
19. [Search Engines — standalone search portals](#19-search-engines--standalone-search-portals)
20. [OAI-PMH — making your data harvestable](#20-oai-pmh--making-your-data-harvestable)
21. [Webhooks — connecting to external tools](#21-webhooks--connecting-to-external-tools)
22. [External repositories — depositing collections and websites](#22-external-repositories--depositing-collections-and-websites)
23. [Document version history](#23-document-version-history)
24. [Email notifications and password reset](#24-email-notifications-and-password-reset)
25. [Personal API tokens and the `aracne` CLI](#25-personal-api-tokens-and-the-aracne-cli)
26. [Natural-language search](#26-natural-language-search)
27. [Plugin links on the public site](#27-plugin-links-on-the-public-site)
28. [Audit log dashboard](#28-audit-log-dashboard)
29. [Fixity dashboard](#29-fixity-dashboard)
30. [Policy pages and the PolicyManager role](#30-policy-pages-and-the-policymanager-role)
31. [Your data — privacy and GDPR rights](#31-your-data--privacy-and-gdpr-rights)
32. [Admin reference](#32-admin-reference)

---

## 1. What is Aracne2?

Aracne2 is a web-based content management system designed for **scholarly digital
editions**: projects that produce, edit, and publish documents encoded in TEI XML
(Text Encoding Initiative, the academic standard for encoding historical and
literary texts).

Think of it as a specialized word processor + publishing platform built for
philologists, archivists, and digital humanities researchers. It handles:

- **Organizing** documents into collections (one collection per edition or corpus)
- **Editing** TEI XML directly in the browser, with intelligent assistance
- **Managing** the full editorial workflow from draft to publication
- **Publishing** collections as navigable websites, complete with search, indices,
  and bibliography
- **Exposing** metadata to external aggregators (OAI-PMH for library catalogs)

Everything happens in the browser. There is nothing to install on your computer.

---

## 2. Who you are — Roles

Aracne2 has five roles. Your role determines what you can see and do.

```
          Admin
            │
      EditorInChief
       ╱          ╲
  Editor         Designer
       ╲          ╱
           User
```

### User
Read-only access to **published** collections. Can browse and search published
documents. Cannot edit anything.

### Editor
Creates and edits TEI documents within collections that have been assigned to them.
Can upload documents, use the editor, validate their work, and submit a collection
for review when ready.

### Designer
Manages the visual presentation layer of public websites: writes and edits XSLT
stylesheets that transform TEI XML into HTML, configures page templates, builds
indices, and publishes the final site. Has no access to the documents themselves.

An Editor and a Designer are **independent roles at the same level** — the same
person can hold both simultaneously.

### EditorInChief
Sees all collections regardless of status. Creates collections, assigns them to
Editors, reviews submitted work, publishes or requests revisions, and manages
bibliographies and permissions. The central coordinating role.

### Admin
Full access to everything, including user management, system configuration, plugin
activation, and the ability to unpublish a collection. The only role that can
delete collections or create new user accounts (when public registration is off).

---

## 3. Logging in and your profile

### Logging in

Navigate to the Aracne2 URL provided by your system administrator. Enter your
email and password on the login page. Your session is maintained automatically —
you do not need to log in again until the session expires (typically 60 minutes
of inactivity, extended automatically when you are active).

### Your profile

Click your name or avatar in the top-right corner to access your profile. From
there you can:

- Change your display name
- Change your password
- Switch the interface language (Italian or English)
- Set your **ORCID iD**

Your language preference is saved and applied automatically every time you log in.

#### ORCID iD

ORCID ([orcid.org](https://orcid.org/)) is an international registry of
persistent identifiers for researchers. Set yours once in the profile page
and Aracne2 uses it automatically wherever your authorship is declared:

- The public collection and document pages show a clickable ORCID link next
  to your display name.
- RDF / Linked Open Data output (JSON-LD, schema.org, Dublin Core) emits
  `schema:sameAs` / `foaf:account` pointing at your ORCID record.
- If the Zenodo deposit plugin is active, your ORCID is attached to the
  `creators` entry on every record deposited for a collection you edit —
  so Zenodo can disambiguate authorship and cross-link your other works.

Expected format: `0000-0002-1825-0097` (the hyphenated short form). The
form accepts full URLs too (`https://orcid.org/0000-…`) and stores the
short form. Aracne2 validates the ISO 7064 Mod 11-2 checksum before
saving — a typo in the last digit is rejected immediately.

If you do not have an ORCID, leave the field empty: nothing downstream
breaks, the public pages simply show your name without a link.

**Admins** can edit another user's ORCID from the user-detail page
(`/admin/users/:id`) if a member asks to have it corrected.

#### ORCID lookup in the TEI editor

Independent of the profile field above: when the **ORCID lookup plugin** is
activated by an Admin (see §32 Plugins), the TEI editor gains an "ORCID"
button in its toolbar that searches the public ORCID registry by name and
writes the resulting `@ref="https://orcid.org/…"` onto the enclosing
`<persName>`. That flow is described in §6 (The TEI editor → External
reference lookups).

---

## 4. Collections — the main organizing unit

A **collection** is the top-level container for a scholarly edition or corpus.
It groups related TEI documents together with shared metadata: title, publisher,
author, license, validation schema, and publication settings.

Every document belongs to exactly one collection.

### The collections list

The main screen after login shows all collections you have access to. You can:

- Filter by status (draft, assigned, review, published)
- Search by title

### Creating a collection (EditorInChief+)

Click **New collection**. Fill in:

| Field | What it is |
|-------|-----------|
| **Title** | The human-readable name of the edition |
| **Description** | A short summary (optional) |
| **Schema** | The TEI validation schema to use (your Admin must have uploaded one) |
| **Body template** | A starting XML snippet for new documents (simplifies encoding) |
| **Author** | Main author; autocompleted from the VIAF authority database as you type |
| **Publication place** | Autocompleted from Geonames as you type |
| **Publisher** | The institution or publisher |
| **Publication year** | Year of publication |
| **License** | Copyright/open license |
| **Responsibility statements** | A list of people and their roles (e.g. "edited by — Jane Smith") |
| **Manuscript identifier** | Shelfmark or identifier of the source manuscript |
| **Object type** | Physical form: codex, leaf, roll, etc. |
| **Identifier URL** | DOI, Handle, or URN for the edition |

All metadata fields are optional except the title. You can change them at any
time while the collection is not yet published.

### Collection detail page

Click any collection to open its detail page. This is where all the action
happens: managing documents, running the workflow, viewing validation results,
and managing the bibliography.

The detail page shows:

- Collection title and status badge (draft / assigned / review / published)
- The currently assigned editor (if any)
- The list of documents in the collection
- Actions available to your role

### Permissions — giving an Editor access to a specific collection

EditorInChief+ can grant individual Editors read access to a collection even if
that Editor is not the assigned one. From the collection detail page, use
**Permissions** to add or remove users.

---

## 5. Documents — your XML files

### Document list

The bottom section of the collection detail page lists all documents. Each row
shows the filename, title (extracted from the `<titleStmt>` of the TEI header),
author, and file size. The list is paginated; you can show 10, 25, 50, or 100
documents per page.

### Creating a new document

Click **New document**, enter a filename (`.xml` will be added automatically if
you omit it), and click Create. Aracne2 automatically generates a complete TEI
skeleton populated with all the collection metadata (title statements, publisher,
license, responsibility statements, manuscript description). The editor opens
immediately so you can start working.

### Uploading documents

If you already have TEI XML files on your computer:

- **Single file**: click **Upload**, select one `.xml` file.
- **ZIP archive**: click **Upload ZIP** to upload up to 500 `.xml` files at once
  inside a `.zip` archive. Only root-level files are imported; files inside
  subdirectories in the archive are skipped.

After a ZIP upload, Aracne2 reports how many files were successfully imported,
how many were skipped, and how many failed.

### Downloading a document

Click the download icon next to any document to save a copy of the current XML
to your computer.

### Deleting documents

Click the trash icon to delete a single document. To delete multiple documents
at once, use the checkboxes on the left to select them, then click **Delete selected**.

Published collections are frozen — no documents can be added, edited, or deleted
until an Admin unpublishes the collection.

### Searching within a collection

Use the search bar at the top of the document list. The search performs a
full-text scan across all documents in the collection. Results show the filename
and a context snippet. Clicking a result opens the document in the editor.

---

## 6. The TEI editor

Click any document filename to open the TEI editor. The editor occupies most of
the screen and is divided into two areas:

```
┌─────────────────────────────┬──────────────────────────────┐
│                             │                              │
│   XML editor (main area)    │   Side panel                 │
│                             │   (resizable)                │
│                             │                              │
└─────────────────────────────┴──────────────────────────────┘
```

You can drag the vertical divider left or right to resize the side panel.

### The toolbar

At the top of the editor:

| Button | What it does |
|--------|-------------|
| **Save** | Saves the current content to the database. If a schema is attached, validation runs automatically after saving. |
| **Format** | Re-indents the XML for readability |
| **Fold all** | Collapses all XML elements so only the outermost structure is visible |
| **Fullscreen (F11)** | Expands the editor to fill the entire browser window. Press Esc or F11 again to exit. |
| **Add note (alpha)** | Inserts an alphabetic note (a, b, c…) at the cursor |
| **Add note (numeric)** | Inserts a numeric note (1, 2, 3…) at the cursor |
| **TEI help** | Opens the help panel with element documentation |
| **Media** | Opens the facsimile/media panel |
| **Zones** | Opens the zone editor for text-image alignment |
| **Validate** | Opens the validation panel and runs the schema validator |
| **AI** | Opens the AI assistance panel |

### Autocomplete

If the collection has a TEI schema attached, the editor offers intelligent
autocomplete:

- Type `<` to see a list of elements valid at the current position
- Press space inside an opening tag to see valid attributes
- Press `=` after an attribute name to see valid values for that attribute
- Press `Ctrl+Space` to trigger autocomplete manually at any time

### Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+J` | Jump to the matching closing/opening tag |
| `Ctrl+/` | Toggle XML comment on the selected line(s) |
| `F11` | Toggle fullscreen |
| `Esc` | Exit fullscreen |
| `Ctrl+Space` | Trigger autocomplete |

### TEI Help panel

Open the help panel (right-side panel, "TEI Help" tab) and type an element name
to see a link to its TEI P5 documentation. This works only when a CM5 schema is
loaded.

### External reference lookups

Three optional buttons appear in the toolbar when the matching plugin is
activated by your Admin. Each opens a side-panel that lets you resolve an
external reference and insert the resulting attribute or TEI fragment
directly into the document.

| Button | Plugin | What it does |
|--------|--------|--------------|
| **Wikidata** | `wikidata` (always available) | Searches Wikidata by name or by the selected text; on "Apply" writes `@ref="https://www.wikidata.org/entity/Q…"` on the enclosing `<persName>`, `<placeName>`, or `<orgName>`. |
| **ORCID** | `orcid` (non-native, Admin must activate) | Searches the public ORCID registry by researcher name or affiliation; on "Apply" writes `@ref="https://orcid.org/0000-…"` on the enclosing `<persName>`. Use this for any person with an ORCID, not just Aracne2 users — the profile field in §3 is only for your own identifier. |
| **DOI** | `crossref_lookup` (non-native, Admin must activate) | Paste a DOI (accepts `doi:…`, `https://doi.org/…`, or the bare identifier) and CrossRef returns a ready-to-insert TEI `<biblStruct>` that is appended to the document's `<listBibl>`. |

If a button is missing it is because the plugin is not currently
activated in `/admin/plugins`. Plugin activation takes effect after the
backend is restarted.

The Wikidata and ORCID panels are mutually exclusive on a given element
(one `@ref` per element), so only one can be applied at a time. The DOI
resolver is deterministic — the output is whatever CrossRef has on file,
not an AI guess — making it safer than the AI `tei_bibl_inline` prompt
for citations you need to match a published record exactly.

---

## 7. The editorial workflow

Each collection moves through four states. Each transition is logged and triggers
a notification.

```
Draft  →  Assigned  →  Review  →  Published
              ↑____________|
              (revisions requested, back to assigned)
```

### Draft
The collection has been created but not yet assigned to an editor. Only
EditorInChiefs and Admins can see it or edit its metadata.

### Assigned
An EditorInChief has assigned the collection to a specific Editor (via the
**Assign** button on the collection detail page). The assigned Editor is
notified and gains write access to the documents.

### Review
The assigned Editor, when satisfied with their work, clicks **Submit for review**.
All EditorInChiefs and Admins are notified. The collection is now visible to
EditorInChiefs for review. Document editing is still possible at this stage.

### Published
An EditorInChief clicks **Publish**. The collection becomes publicly accessible
(if marked as public). Documents are frozen — no edits are possible until an
Admin unpublishes the collection.

### Requesting revisions
If the EditorInChief wants the Editor to revise the work before publishing,
they click **Request revisions** and provide a mandatory note explaining what
to change. The collection returns to the **Assigned** state and the Editor is
notified with the revision notes. This is a neutral, constructive action —
part of the normal editorial back-and-forth, not a rejection. The Editor can
address the notes and re-submit for review.

### Direct publish (EditorInChief+)
The **Direct publish** button bypasses the workflow and publishes a collection
immediately regardless of its current state. Useful for bulk imports or projects
that do not need a formal review step.

### Unpublish (Admin only)
An Admin can revert a published collection back to **Draft** using **Unpublish**.
This removes public access immediately. This is the only way to re-enable
document editing on a published collection.

---

## 8. Validating documents

If a collection has a TEI schema attached (RNG, DTD, or XSD), Aracne2 can
check whether your documents are valid according to that schema.

### Per-document validation

In the editor, click **Validate** in the toolbar. The validation panel opens on
the right showing either:
- A green "Valid" indicator
- A list of errors with line number, column, and message

Validation also runs automatically every time you save, if a schema is attached.

**You can validate without saving first.** Click Validate to check the current
state of the editor buffer — errors in unsaved content are caught without writing
to the database.

### Collection-wide validation (EditorInChief+)

From the collection detail page, click **Validate all**. Aracne2 runs the
validator on every document in the collection in the background. You can see:

- A progress indicator while the run is active
- A summary: X of N documents valid
- Per-document rows with error counts
- An expandable list of errors for each invalid document
- An **Explain errors (AI)** button that opens the AI assistant pre-loaded with
  the error list for plain-language explanation

You can also cancel an ongoing validation run.

---

## 9. Facsimile images and page links

Aracne2 lets you attach digital images of the manuscript pages to the document and
link them to specific positions in the transcription. This is the TEI "facsimile"
mechanism.

### Opening the media panel

In the editor, click **Media** in the toolbar. The side panel shows:
- A list of all media files uploaded for this collection
- A list of facsimile surfaces (page images) already registered in the document

### Uploading images

Use the upload area in the media panel to add images from your computer. Supported
formats are common image types (JPEG, PNG, etc.). After upload, the image appears
in the media file list.

### Inserting an image inline in the text

Find the image in the media list, position your cursor in the editor where you
want the image reference, and click **Insert as figure**. This inserts a
`<figure><graphic url="…"/></figure>` element at the cursor position.

### Linking an image to a manuscript page (facsimile)

To create a page-image link (so that a `<pb/>` element in the text points to
the image of that page):

1. Find the image in the media list
2. Click **Insert as card** (instead of "Insert as figure")
3. Aracne2 registers the image as a facsimile surface (a `<surface>` element in
   the `<facsimile>` block) and inserts a `<pb facs="#s1"/>` page-break element
   at the cursor position, linking the transcription break to the image

The facsimile panel shows all registered surfaces in order, with buttons to
move them up/down or delete them. Deleting a surface also removes all `<pb>`
references to it from the transcription.

---

## 10. Zone editor — linking text to image regions

The zone editor takes the facsimile integration one step further: it lets you
draw rectangular regions on a page image and link them to specific words or lines
in the transcription. This is used for detailed text-image alignment.

### Opening the zone editor

In the editor, click **Zones** in the toolbar. The zone editor opens in the side
panel. Select a facsimile surface (page image) from the list at the top.

### Drawing zones

The page image appears with any existing zones highlighted in color. To draw a
new zone:

1. Click and drag on the image to draw a rectangle
2. The system assigns the zone an automatic identifier (e.g. `z1`, `z2`, …)
3. The zone appears in the list below the image

### Linking a zone to the transcription

To link a zone to a word or line in the text:

1. Click on the zone in the zone editor list — it becomes selected
2. Switch to the XML editor and click on the TEI element you want to link
   (`<w>`, `<lb>`, etc.)
3. Click **Associate** — the system adds a `facs="#zone_id"` attribute to
   that element

### Saving zones

Click **Save** in the zone editor. Zones are stored directly in the `<facsimile>`
block of the document. Unsaved edits outside the facsimile block (in the text
body) are preserved.

---

## 11. Notes

The editor supports two types of notes, both inserted at the cursor position:

| Type | Numbering | Use case |
|------|-----------|----------|
| **Alpha** | a, b, c… | Textual / editorial notes |
| **Numeric** | 1, 2, 3… | Source notes / footnotes |

### Inserting a note

1. Place the cursor in the text where the note reference should appear
2. Click **Add note (alpha)** or **Add note (numeric)** in the toolbar
3. A dialog opens — type the note text
4. Click **Confirm**

The editor inserts a `<ref>` element at the cursor and the note content at the
appropriate container. The `<ref>` element appears highlighted in the editor and
is protected from accidental editing.

### Editing a note

Click on any highlighted note reference in the editor. The note dialog opens
pre-populated with the current text. Edit and click **Confirm**.

### Deleting a note

Click on the note reference, then click **Delete** in the dialog. Both the
`<ref>` element and the note content are removed.

---

## 12. Named entities

Aracne2 automatically scans every TEI document in a collection and extracts
named entities — by default: persons (`<persName>`), places (`<placeName>`), and
organisations (`<orgName>`). The extracted entities are stored in a searchable
index.

### What happens automatically

Every time a document is uploaded or saved, the system runs an extraction scan
in the background. No action is required from the Editor. The index is updated
silently.

### Public entity browser

Published collections expose their entity index on the public website. Visitors
can browse and search persons, places, and organisations, and see all the
passages in which each entity appears.

### Admin entity management (Admin)

Administrators can:

- **Normalise canonical forms**: different textual forms of the same name
  (e.g. "Rome" / "Roma" / "Roma, city of") can be merged into one canonical form
- **Link to authority files**: each entity can be assigned a URI from VIAF
  (Virtual International Authority File), GeoNames, or any other authority
- **Merge entities**: two records identified as duplicates can be merged into one,
  combining all their occurrences
- **Re-index a collection**: if the tag configuration changes, trigger a fresh
  scan of all documents

### Configuring which tags to extract (EditorInChief+)

By default the system extracts `persName`, `placeName`, and `orgName`. An
EditorInChief can change this list to include any TEI element — for example
`objectName`, `geogName`, or `measure`. After changing the configuration,
re-index existing collections to apply the new tags.

---

## 13. Bibliography (Bibliobuilder)

A collection can have a bibliography — a structured list of all sources cited in
its documents, formatted as a TEI `<listBibl>`. Aracne2 includes a dedicated tool,
the **Bibliobuilder**, to help create it.

### How the Bibliobuilder works

1. **Extract**: the Bibliobuilder scans all documents in the collection and
   collects every `<bibl>` and `<biblStruct>` element it finds — including
   informal citations scattered throughout the notes or bibliography sections.

2. **Normalize with AI**: the raw, possibly inconsistent citations are sent to
   the configured AI model with a specialized prompt. The AI produces a clean,
   deduplicated, consistently formatted `<listBibl>`.

3. **Review and edit**: the EditorInChief reviews the AI output in a read-only
   viewer and can manually edit it before saving.

4. **Save a version**: each save creates a new numbered version of the
   bibliography. Previous versions are preserved and can be browsed.

5. **Publish**: one version can be marked as **public**. Only one version can be
   public at a time. The public version appears on the collection's public website
   and on the platform home page (if enabled).

### Accessing the Bibliobuilder

From the collection detail page, click **Bibliobuilder** (EditorInChief+).
The button is visible only when the collection has documents.

### Saved bibliographies panel

The collection detail page shows all saved bibliography versions in a collapsible
panel (EditorInChief+). From here you can:
- Expand a version to read its content
- Set a version as public (or unset it)
- Delete a version
- Copy the XML content to the clipboard

---

## 14. AI assistance

Aracne2 integrates AI language models to assist editors. AI features are
**optional and configurable** — they appear only when an Admin has activated
one of the supported providers:

- **OpenAI** (ChatGPT, GPT-4)
- **Anthropic** (Claude)
- **Google Gemini**
- **Ollama** — local inference on a model running on your own server. No API
  key, no data leaves your infrastructure. Slower than remote providers and
  typically weaker on complex tasks, but the only option for privacy-sensitive
  or air-gapped projects.

The available features are the same regardless of which provider the Admin
selected — the quality and speed of the responses change.

### Where AI assistance is available

#### In the TEI editor (Editor+)

Open the **AI** panel from the toolbar. Three modes are available:

**Validate** — explains validation errors in plain language
After you click Validate, the editor checks the current buffer and, if errors
are found, sends them to the AI. The AI responds with a plain-language
explanation of each error and, when possible, suggests how to fix it.
This mode does not insert anything into the document.

**Improve** — suggests XML improvements
Select a portion of text in the editor (or leave nothing selected to use the
whole document), then click Improve. The AI suggests improvements or corrections
to the encoding and shows them in a read-only viewer. Click **Apply** to replace
the selected text with the suggestion, or close the panel to discard it.

**Discuss** — free-form conversation about the document
Click Discuss to open a chat interface. Ask any question about the document,
request encoding advice, or discuss philological interpretation. The AI has
context about the current document. You can continue the conversation with
follow-up messages. This mode never modifies the document automatically.

**TEI-specific actions** (when the Admin has enabled them)
Additional prompts are available in the AI panel when you have a selection
in the editor:

- **Normalize inline bibliography** — converts a free-text citation (e.g.
  "Smith 1998, pp. 45–67") into a `<biblStruct>` element following TEI P5
  conventions.
- **Tag named entities** — wraps every person, place and organization name
  in the selected passage with the appropriate `<persName>`, `<placeName>`
  or `<orgName>` element, preserving the text itself.
- **Scaffold teiHeader** — turns a paragraph of bibliographic metadata
  (title, author, editor, publisher, date, license) into a minimal
  `<teiHeader>` block.

All three replace the current selection with the produced TEI fragment —
review before saving.

### Grounded on the TEI Guidelines (optional)

If your Admin has enabled **RAG** (retrieval-augmented generation) and
indexed the TEI P5 Guidelines, the three TEI-specific actions above
receive relevant reference passages automatically along with your
selection. This helps the model stay faithful to P5 conventions — it
cites structures from the Guidelines rather than relying on what it
"remembers" during training. You do not have to do anything different:
when the feature is active, the AI answers are simply more consistent
with the official Guidelines.

#### In collection-wide validation (EditorInChief+)

An **Explain errors (AI)** button appears next to each invalid document in the
collection validation report. Click it to open the AI panel pre-loaded with
that document's error list.

#### In the Bibliobuilder (EditorInChief+)

The Bibliobuilder uses a specialized AI prompt to normalize and structure
bibliographic citations. See §13.

### Privacy notice

If your Admin has enabled the privacy warning, a notice appears before the
first AI request in each session, reminding you that document content is sent
to an external provider. Consider this when working with unpublished or
confidential material.

### Rate limits

The Admin sets a per-user hourly limit for AI requests (default: 20 per hour).
If you reach the limit, the AI panel will show a "rate limit exceeded" message
and you must wait before making further requests.

---

## 15. Websites — publishing to the web

Aracne2 can transform a published collection into a fully navigable public
website. This is managed by the **Designer** (with the Designer or EditorInChief
or Admin role).

### What a website includes

A website built from a collection provides:

- **Index page**: cover page with collection title, description, and metadata
- **Browse page**: list of all documents with their titles and authors
- **Document pages**: each TEI document rendered as readable HTML (via XSLT)
- **Search**: full-text search across the collection
- **Bibliography page**: the public bibliography (if one is published)
- **Index pages**: per-tag indices (e.g. a persons index, a places index)
- **Custom pages**: free-form Markdown or rich-text pages added by the Designer
  (e.g. an introduction, a methodology page, a credits page)

### Rendering modes

The Designer chooses how the website is generated:

| Mode | How it works | Best for |
|------|-------------|---------|
| **Static** | All HTML pages are generated at once and stored on disk. The Designer triggers the build manually. | Stable collections that change infrequently |
| **Dynamic** | Every page request is rendered in real time from eXist-db. No build step needed. | Frequently updated collections |
| **Hybrid** | Fixed pages (index, browse, bibliography) are pre-built; document pages are rendered on the fly. | Balanced approach |

### XSLT stylesheets — making documents look good

The heart of the website is the XSLT stylesheet that transforms TEI XML into
HTML. Designers can:

- **Use the built-in template**: a standard TEI stylesheet provided by the system
- **Write a custom stylesheet**: edit the XSLT directly in the browser using the
  built-in code editor (with syntax highlighting)
- **Preview instantly**: a live preview panel shows how the current XSLT renders
  any document in the collection. Changes in the editor update the preview.

### Indices

Designers can define custom indices — for example, an index of all persons
mentioned in the collection, or all places, or all dates. For each index:

1. Choose which TEI element and attribute to index
   (e.g. `<persName key="…">` → index by the `key` attribute value)
2. Assign a human-readable label ("Persons", "Places", …)
3. The system builds the index by scanning the collection

### Building and downloading the site

For Static and Hybrid modes, click **Build** to generate the site files. The
build runs asynchronously — a progress indicator shows the status. Once complete,
you can **Download** the entire site as a ZIP archive for offline use or
deployment to a static hosting service.

### Custom homepage CSS

The Admin can upload a custom CSS file that overrides the default homepage styles.
If **Propagate CSS** is enabled, the same CSS is also applied to public document
pages, entity pages, and the bibliography page.

---

## 16. EVT viewer

[EVT (Edition Visualization Technology)](https://github.com/evt-project/evt-viewer)
is an external viewer specifically designed for TEI digital editions. Aracne2
integrates it as an optional alternative way to display a published collection.

### When it appears

A **View in EVT** button appears on the collection detail page when all of the
following are true:

- The **EVT Viewer** plugin is active in `/admin/plugins` (it is now a non-native
  opt-in plugin — earlier installs activated it by default)
- The global EVT toggle is on (configured from the EVT plugin's Configure page,
  not the legacy Settings page)
- The collection has EVT enabled (in the collection edit form)
- The collection is published and public
- The collection contains exactly one document (EVT is designed for
  single-document editions)

When the EVT plugin is **inactive**, opening `/collections/<slug>/read`
shows a friendly "Viewer not enabled on this installation" page with a
back-to-home link, so old bookmarks don't 404.

### What EVT provides

EVT presents the XML document as a side-by-side view of the facsimile images and
the transcription, with support for critical apparatus, diplomatic transcription,
and other TEI features. It is a standalone viewer — the Editor does not configure
it beyond enabling it on the collection.

---

## 17. Notifications

The bell icon in the top navigation bar shows your unread notifications. The
badge updates automatically.

Notifications are generated by the system for the following events:

| Event | Who is notified |
|-------|----------------|
| Collection assigned to you | The assigned Editor |
| Collection reassigned away from you | The previous Editor |
| Collection submitted for review | All EditorInChiefs and Admins |
| Revisions requested on a collection | The assigned Editor |
| Collection published | The assigned Editor |
| New user account created | The new user (welcome notification) |
| ZIP upload completed | The user who triggered the upload |

Click a notification to mark it as read and navigate to the relevant collection.
Click **Mark all as read** to clear the badge without opening each notification.
Notifications can also be deleted individually.

---

## 18. Search

### Within a collection

Use the search bar in the collection detail page. Results come from a full-text
scan of the XML content (not just titles). Each result shows the document name
and the sentence or passage where the term appears.

### Public cross-collection search

The public home page (if enabled by your Admin) includes a search bar that
searches across all published public collections simultaneously. Results show the
collection, document title, and matching context.

Admins and EditorInChiefs can also search the metadata of all collections
(including unpublished ones) from the collections list.

---

## 19. Search Engines — standalone search portals

A **Search Engine** is a configurable search interface that you create once and
then share as a standalone page or embed directly into any external website. It
is different from the simple search bar inside a collection: a Search Engine
works across **multiple collections at once**, has its own URL, and can be
styled independently.

### Who can create Search Engines

**Designers**, **EditorInChiefs**, and **Admins** can create and manage Search
Engines from **Tools → Search Engines** in the navigation menu.

### What a Search Engine can do

| Capability | Description |
|---|---|
| **Multi-collection search** | Covers any number of published collections simultaneously |
| **Full-text search** | Searches inside every XML document, not just titles or metadata |
| **Advanced search** | Filters by TEI element (`persName`, `placeName`, …) or XML attribute |
| **Built page** | A self-contained HTML page hosted by Aracne2, ready to share as a link |
| **Embed widget** | A `<script>` snippet that places the search box on any external site |
| **Query cache** | Server-side result caching to serve frequent queries instantly |

### Creating a Search Engine

1. Go to **Tools → Search Engines** and click **New search engine**
2. Fill in the **title** and **slug** (the slug becomes part of the URL, e.g.
   `search-pages/archivio-manzoni/`)
3. In the **Collections** field, pick the published collections to include
4. Adjust **Appearance** options (background colour, header colour, footer text)
   if you want the page to match your project's visual identity
5. Click **Save**

### Building the search page

After saving, click the **Build** button. Aracne2 generates the HTML page in the
background — the status badge will switch from *Building* to *Done* in a few
seconds. Once done, click **Open** to preview the page in your browser.

The URL of the built page follows the pattern:

```
https://your-aracne2-instance.org/search-pages/{slug}/
```

This URL can be linked from your project website or shared with readers directly.

### Advanced search

If your collections use structured TEI markup, you can enable **Advanced search**
to let users filter by element type and attribute. A "Person" filter backed by
`<persName>`, for example, lets users search exclusively within person names.

To configure it:
1. Enable the **Advanced search** toggle
2. Click **Add tag** to define the display label and the TEI element it maps to
3. Optionally add **attribute filters** (e.g. `role`, `subtype`)
4. Rebuild the page

### Embedding the search box on an external site

If readers use a website outside Aracne2 (your university project page, for
example), you can embed the search box there with a single line of HTML.

1. Open the Search Engine, click the **Embed** button
2. Enable the embed widget and choose a mode:
   - **Simple**: full-text search only
   - **Advanced**: structural search only
   - **Both**: the widget shows tabs for both modes
3. If you want to restrict which sites can use the widget, add those origins
   to the **Allowed origins** list (e.g. `https://project.university.edu`).
   Leave the list empty to allow all sites.
4. Copy the **snippet** shown in the Embed tab and paste it into your website's
   HTML where the search box should appear

The widget loads your Aracne2 instance's search results in real time, so there
is nothing else to maintain.

### Clearing the cache

If you have recently added documents to a collection and want the search page to
reflect the new content immediately, click **Clear cache**. The next search query
will hit the database directly instead of using cached results.

---

## 20. OAI-PMH — making your data harvestable

OAI-PMH (Open Archives Initiative Protocol for Metadata Harvesting) is a standard
protocol used by library catalogs, aggregators (such as Europeana, OpenDOAR, and
national repositories), and academic databases to automatically collect metadata
from digital repositories.

When this feature is enabled, Aracne2 automatically exposes metadata for all
published public collections in Dublin Core format. External harvesting systems
can discover and index your collections without any action on your part.

### What is exposed

Each collection maps to an OAI-PMH "set". Each XML document within the collection
maps to an OAI-PMH "record" with Dublin Core metadata extracted from the TEI header
(`<titleStmt>`, `<publicationStmt>`, `<author>`, etc.).

### What you need to do

Nothing, once the system is configured. The Admin enables OAI-PMH in the system
settings. The endpoint is:

```
GET /api/v1/oai?verb=Identify
```

This URL can be registered with harvesters and aggregators by your institution's
library.

---

## 21. Webhooks — connecting to external tools

Webhooks allow Aracne2 to automatically notify an external system whenever
something significant happens: a collection is published, a document is uploaded,
a user is created, and so on.

This is useful for:
- Triggering a backup job when a collection is published
- Sending a Slack or Teams notification to a team channel
- Starting a CI/CD pipeline (e.g. to deploy a static website automatically)
- Logging events in an external audit system

### Setting up a webhook (Admin)

Go to **Settings → Webhooks** and click **New endpoint**. Fill in:

- **Label**: a human-readable name for this connection
- **URL**: the external URL that will receive the notification
- **Events**: which events should trigger this webhook
- **Secret**: an optional signing secret so the receiving system can verify
  that the notification genuinely came from Aracne2

### Supported events

| Event | When it fires |
|-------|--------------|
| `collection.submitted` | An Editor submits a collection for review |
| `collection.published` | A collection is published |
| `collection.unpublished` | A collection is reverted to draft |
| `document.uploaded` | A document is uploaded to a collection |
| `document.deleted` | A document is deleted |
| `user.created` | A new user account is created |

### Testing a webhook

Each endpoint has a **Test** button that sends a sample payload to the configured
URL, so you can verify the connection is working before relying on it.

### Delivery outcome

For each endpoint, the last delivery result is visible: timestamp, HTTP status
code returned by the external URL, and any error message. Failed deliveries are
automatically retried up to three times.

---

## 22. External repositories — depositing collections and websites

Once an Admin activates the relevant plugins, the editorial flow gains
several "Deposit" / "Push" / "Archive" buttons that send a published
collection or a built website to an external repository or
versioning service. Every integration is **opt-in** at the
deployment level (the Admin activates each plugin under
`/admin/plugins` and pastes the relevant credentials) and **manual
or hook-driven** at the editorial level.

### Where the controls live

- **Collection detail page** (`/collections/:slug`):
  - "Deposito Zenodo" — DOI minting on Zenodo
  - "Archived on Wayback" badge + Archive / Refresh buttons (Internet Archive)
  - "Deposit on Dataverse" — DOI on a Dataverse instance (per-deposit alias override)
  - One section per active git-forge plugin (Codeberg / GitHub / GitLab) with
    Connect / Push / Initialize / Disconnect controls — rendered by a single
    `<ForgeCollectionSection>` component instantiated three times
- **Website edit page → "Deposit" tab**: parallel sections for the
  same plugins, each one targeting the website's rendered output
  rather than the collection's TEI source

### What each plugin does at a glance

| Plugin | What it deposits | Trigger | Identifier returned |
|---|---|---|---|
| **Zenodo Deposit** | Collection's TEI files (one-by-one or zipped) AND/OR the website's rendered tree | Auto on collection publish (toggleable) + manual; manual for websites | DOI on publish; draft URL for unpublished |
| **Internet Archive** | The collection's public URL AND/OR the website's public URL — submitted to Save Page Now 2 | Auto on collection publish (toggleable) + manual + Refresh; manual for websites | Wayback Machine snapshot URL |
| **Dataverse Integration** | Collection's TEI files OR website's rendered tree, on any Dataverse instance (default sandbox at demo.dataverse.org; configurable for institutional Dataverses) | Auto on collection publish (toggleable) + manual; manual for websites | DOI immediately on dataset creation (preallocated; resolves via doi.org only on publish) |
| **Codeberg / GitHub / GitLab Integration** | Push every TEI file (collection) or every rendered file (website) to a git repository in **a single commit per push**. Plus one-shot **Initialize** for empty collections (forge → eXist-db) | Manual | Commit SHA + Wayback link |

### The "Initialize" flow (forge → empty collection)

A safety-asymmetric one-shot operation available on the Codeberg /
GitHub / GitLab sections: import every XML file from a git
repository into an *empty* Aracne2 collection. Once the collection
has any document (imported or hand-created) Initialize is
permanently disabled — the only allowed direction from then on is
push (Aracne2 → forge). Designed for migrating an existing TEI
corpus that already lives on a git forge into Aracne2 without
manual file-by-file upload, with no risk of overwriting live work.

XML is validated with `defusedxml` before a single byte reaches
eXist-db, so a malformed file aborts the whole import.

### Per-link PAT override

Every git-forge link has an optional per-link PAT field that wins
over the plugin's global PAT. Useful when a specific collection
lives under a different organisation or namespace whose token you
don't want to share globally. The override is Fernet-encrypted at
rest just like the global PAT.

### Per-deposit alias override (Dataverse)

Dataverse's "alias" identifies the sub-Dataverse a dataset belongs
to inside an instance (e.g. `tei-editions` for one research group,
`dh-2026` for another). The plugin's config sets a default alias;
each deposit can override it via the "Use a different alias for this
deposit…" link. This makes a single Aracne2 install workable when
one institution hosts multiple research-group Dataverses inside the
same instance.

### Self-hosted forges and Dataverses

All integrations support self-hosted instances via a configurable
`base_url`:

- Codeberg → any Forgejo or Gitea install (set the per-link
  `base_url` to your institutional Forgejo)
- GitHub → GitHub Enterprise Server (the adapter rewrites API calls
  to the `/api/v3/` prefix)
- GitLab → any self-hosted GitLab (uses `/api/v4/` everywhere)
- Dataverse → any institutional Dataverse instance

### Detailed reference

For settings, endpoints, and version history per plugin, see
[`docs/reference/NON_NATIVE_PLUGINS.md`](reference/NON_NATIVE_PLUGINS.md)
and the per-plugin reference docs under `docs/reference/`.

---

## 23. Document version history

Every TEI document has an **append-only timeline** of versions: every
workflow event (creation, submission, revisions requested, publication)
plus every explicit "Save version" or "Roll back" leaves a row that an
editor can browse, compare, and restore.

### Where the panel lives

In the TEI editor, click **History** (right-side toolbar). The panel
lists every version of the current document, newest first, with:

- Version number (`v1`, `v2`, …)
- Origin tag — `creation`, `manual`, `submission`, `revision`,
  `publication`, `rollback`
- Actor display name + timestamp
- A short message (set when an editor saves manually)
- A SHA-256 short hash for fixity (see §29)

### What you can do

| Action | Notes |
|---|---|
| **Open a version** | Loads that version's content into a read-only viewer next to the live editor |
| **Compare** | Side-by-side diff between two versions |
| **Save version** (Editor+) | Captures the current working tree with a message; useful before risky edits |
| **Roll back to vN** (Editor+) | Replaces the working tree with vN's content; recorded as a new `rollback`-origin row |

Rollback never erases history — the previous content is still
visible as the row right before the rollback row.

### The working / published split

Editors keep editing freely on a published collection without taking
the public website offline. The public sees the **last
publication-origin version** for each document; the working tree
lives in parallel until the next publish bumps it.

A `?version=N` URL on a public document page resolves only to a
publication-origin row, so manual saves and rollbacks never leak to
anonymous visitors.

### Reference

[`docs/reference/DOCUMENT_VERSIONING.md`](reference/DOCUMENT_VERSIONING.md)
covers the data model, dedup strategy, and per-origin behaviour
matrix.

---

## 24. Email notifications and password reset

Aracne2 can send transactional email for the workflow events that
already produce in-app notifications (§17), plus a self-service
password-reset flow.

### What gets emailed

| Event | Recipient |
|---|---|
| Collection submitted for review | Every active EditorInChief / Admin (except the actor) |
| Collection sent back for revisions | The assigned Editor, with the reviewer's note |
| Collection published | The assigned Editor |
| Password reset requested | The requesting user |

In-app notifications still fire regardless — email is an
*additional* channel.

### Per-user opt-out

Profile → **Email notifications** toggle. Default `on`. When
`off`, you still see in-app notifications but no email is sent.
The toggle does *not* suppress password-reset email — that flow
is anonymous (you triggered it from the login page) and is the
only way back into your account if you've forgotten the password.

### Forgot password

The login page shows a **Forgot password?** link. It opens
`/forgot-password`, asks for your email, and (regardless of
whether the email matches an account, to avoid leaking
membership) shows a "we've sent you a link if your address
exists" confirmation. Clicking the link in the email lands on
`/reset-password/:token`, where you set a new password. Tokens
are single-use and expire after one hour.

### Admin-side prerequisites

Email is **off by default** at the platform level. An Admin must:

1. Enable `email_enabled` in System settings (§32).
2. Set `email_from_address` (default `noreply@<your-domain>`).
3. Make sure the bundled Postfix container is running and the
   smarthost is reachable. The platform never stores SMTP
   credentials in the database — Postfix owns the queue.

If `email_enabled=false`, the user-facing toggle and the password
reset flow remain visible but no message goes out (a queue line
is logged for the operator).

### Reference

[`docs/reference/EMAIL_CHANNELS.md`](reference/EMAIL_CHANNELS.md)
documents templates, retry/backoff, DKIM, and the operator's
runbook.

---

## 25. Personal API tokens and the `aracne` CLI

Aracne2 ships a headless command-line tool — `aracne` — that runs
on your laptop and talks to the platform over HTTPS using a
**Personal Access Token (PAT)** you issue from your own profile.

### Issuing a token

Profile → **API Tokens** card. Click **Issue token**, give it a
label (e.g. `my-laptop`), and the platform shows the plaintext
*once*. Copy it immediately into a safe place — it is bcrypt-hashed
in the database and cannot be recovered later.

The card also lists every token you've ever issued with `last
used` and a per-row **Revoke** button. A revoked token stops
authenticating on the next request.

PATs inherit the role of the issuing user at request time, so
revoking the user's role or deactivating the user immediately
disarms every PAT they hold without an explicit revoke step.

### What the CLI does today

| Command | Purpose |
|---|---|
| `aracne login` | Capture a PAT and verify it against the host |
| `aracne whoami` | Print the user the saved PAT resolves to |
| `aracne import --collection SLUG --dir PATH` | Bulk-upload `*.xml` files into a collection |
| `aracne export --collection SLUG --output FILE.zip` | Download the collection's working tree as a ZIP |
| `aracne export --collection SLUG --as-of YYYY-MM-DD --output FILE.zip` | Same, but resolves each document to its publication-origin state at that date |

`import` defaults to `--on-conflict=skip`, so re-running an
import never overwrites work; pass `--on-conflict=overwrite` or
`--on-conflict=fail` to change that.

The `--as-of` flag pairs with the document version history (§23):
the CLI walks each document's `publication`-origin rows and picks
the latest at or before the given date.

### Installing

Not on PyPI. The audience is invite-only.

```bash
git clone https://github.com/orazionelson/aracne2.git
cd aracne2/cli
pip install -e .
aracne --help
```

### Reference

[`docs/reference/CLI.md`](reference/CLI.md) covers the config-file
layout (`~/.aracne/config.toml`), profile switching, and the
deferred commands (`validate`, `delete`).

---

## 26. Natural-language search

When the **NL search** plugin is active, your deployment exposes a
chat-style search box at `/search-nl`. Visitors type a question in
natural language; the platform runs an LLM tool-use loop against
its own read-only MCP tools and streams back an answer with
**citations to real TEI documents** (passage URL + filename).

### Visitor experience

- Public route, no login required.
- Streaming answer (the page fills in as the model writes).
- Every claim ends with a citation; clicking it opens the source
  document at the right passage.
- An on-page disclaimer explains the answer is generated and
  should be checked against the citations.

### Admin setup

Off by default. To turn it on:

1. Activate the plugin from `/admin/plugins`.
2. Configure provider, model, corpus to search, and the optional
   API key from **Settings → NL search**.
3. Decide whether to surface the home-page tile from
   **Public Pages → Pagine → Plugin links** (see §27). The
   `/search-nl` route works regardless of that toggle — the
   toggle only controls the visible link.

### Why citations are mandatory

The orchestrator refuses to emit an answer that doesn't cite at
least one document. This is by design — without citations, the
output would be indistinguishable from an open-domain LLM and
would damage the platform's scientific posture.

### Reference

[`docs/reference/NL_SEARCH.md`](reference/NL_SEARCH.md) covers the
tool-use loop, rate limits, prompt-injection mitigations, and the
admin Settings surface.

---

## 27. Plugin links on the public site

Some plugins ship a public-facing page (e.g. NL search §26, the
policy pages §30). Aracne2's public layout — header, home tiles,
footer — automatically iterates the active plugins and surfaces a
link to that page **only when the matching admin toggle is on**.

### Where the toggles live

**Public Pages → Pagine → Plugin links** (Admin or PolicyManager).
Each public-navigation-capable plugin shows one row with:

- Plugin name + label preview (per locale)
- Section the link will appear in: `header`, home `quick links`,
  or `footer`
- A toggle (default `off`)

Activating a plugin never auto-publishes its public surface — the
Admin must consciously flip the toggle. This guards against
"installed-but-not-yet-configured" surprises on the public site.

### Reference

[`docs/reference/PUBLIC_NAVIGATION.md`](reference/PUBLIC_NAVIGATION.md)
documents the per-plugin descriptor format, locale fallbacks, and
the `system_settings` row format.

---

## 28. Audit log dashboard

Every intentional, user-attributable action is recorded in the
`audit_log` table: auth events, document edits, plugin activations,
settings changes, role grants, GDPR requests, and so on.

### Where the page lives

**Admin → Audit log** (Admin only). The page shows a paginated,
filterable table with:

| Column | What it shows |
|---|---|
| When | Timestamp, locale-formatted |
| Action | e.g. `collection.published`, `user.role_assigned`, `policy_pages.published` |
| Actor | Display name (anonymised entries show a placeholder) |
| Target | Slug / filename / username — never bare UUIDs |
| Details | JSON payload, expandable |

### Filters

- Free-text search across action / actor / target label
- Action prefix (`collection.*`, `user.*`, `auth.*`, …)
- Actor (any user)
- Date range

### Export

Click **Export CSV** to download the current filtered view. The
export honours the platform's privacy posture: IP addresses are
already SHA-256-hashed in production, and anonymised users show
their placeholder identity.

### Retention

Configurable per platform (default 90 days) via the
`audit_log_retention_days` system setting. A nightly job prunes
rows older than that window.

### Reference

[`docs/reference/AUDIT_LOG.md`](reference/AUDIT_LOG.md) covers the
schema, the indexed-column choices, and the per-action payload
shape.

---

## 29. Fixity dashboard

Fixity is the routine integrity check that confirms what's stored
on disk still matches what was written. Aracne2 hashes every
document version with SHA-256 at write time; the fixity layer
re-hashes the **latest publication-origin version per document**
on a schedule and surfaces drift.

### Where the page lives

**Admin → Fixity** (Admin only). The dashboard shows:

- Last full sweep: timestamp + duration
- Per-collection summary: total docs checked, drift count, last
  drift timestamp
- A drift list with the failing filename, the expected vs. the
  observed hash, and the version row affected

### What "drift" means

A drift row means the bytes on disk no longer match the SHA-256
recorded when that version was published. Causes are operational:
storage corruption, an out-of-band edit on the filesystem, a
restore from an older backup. The platform never expects drift
under normal operation.

### Recheck on demand

The **Recheck now** button runs the sweep immediately rather than
waiting for the next scheduled tick. Useful right after a backup
restore or a storage-volume swap.

### What gets re-checked

Only the latest publication-origin version of each document. Older
versions and `manual`-origin rows are not re-hashed on the
schedule (their integrity check happens on read). This keeps the
sweep cheap and meaningful: it covers exactly what the public
site serves.

### Reference

[`docs/reference/FIXITY.md`](reference/FIXITY.md) covers the
scheduler config, the on-write hash strategy, and the drift-row
schema.

---

## 30. Policy pages and the PolicyManager role

Trustworthy-repository assessments (CoreTrustSeal, nestor seal, ISO
16363) ask a deployment to publish institutional declarations:
mission statement, privacy / DPIA, storage policy, continuity plan,
preservation plan, appraisal policy, citation guide, editorial
board, expert directory, and more.

The **policy_pages** plugin turns these into live forms inside
Aracne2 with public rendering, multi-locale support (IT / EN), and
append-only versioning.

### What you get out of the box

Twelve template-driven pages, each with a form, a public URL, and
a version history:

| Slug | Page |
|---|---|
| `mission` | Mission statement |
| `privacy_dpia` | Privacy / DPIA notice |
| `storage_policy` | Storage policy |
| `continuity_plan` | Continuity plan |
| `preservation_plan` | Preservation plan |
| `appraisal_policy` | Appraisal policy |
| `incident_response` | Incident response plan |
| `citation_guide` | Citation guide |
| `editorial_board` | Editorial board |
| `funding_staffing` | Funding & staffing |
| `expert_directory` | Expert directory |
| `cts_self_assessment` | CTS self-assessment |

Every template ships with field-level guidance and an "as filled
by the reference deployment" example, so a new operator can stand
up the page set in an afternoon.

### Where the controls live

**Admin → Policies** (Admin or PolicyManager). For each template
you see:

- The current published version (or "draft" if no version
  published yet)
- A form to edit, with per-locale text fields
- **Save draft**, **Publish**, **History** buttons

### The PolicyManager capability

Editing policy content is **delegated** through a capability role
that is *orthogonal* to the five hierarchical roles — granting it
does not change the holder's main role; it only unlocks the
Policies admin surface.

The role is **singleton**: at most one user holds it at a time. An
Admin can transfer it from the current holder to another user in
one operation; the audit log records it as a single
`role.transferred` row. Granting it to a new user automatically
revokes it from the previous holder.

Why singleton: a single named accountability holder for
institutional policy content matches how organisations actually
assign that responsibility.

### Public exposure

Each published policy page lives at `/policies/<slug>` (the index
page at `/policies` lists all of them). The link to that index can
be surfaced via the §27 footer-iterator toggle.

### Reference

- [`docs/reference/POLICY_PAGES.md`](reference/POLICY_PAGES.md) — schema, template format, public URL slug rules
- [`docs/reference/CAPABILITY_ROLES.md`](reference/CAPABILITY_ROLES.md) — singleton semantics, `require_capability` middleware, audit-log shape
- [`docs/reference/CTS_COMPLIANCE.md`](reference/CTS_COMPLIANCE.md) — which CTS requirement each template addresses

---

## 31. Your data — privacy and GDPR rights

Aracne2 hosts published scientific work. Once an EditorInChief
approves a TEI document at a public URL, that contribution becomes
part of an institutional record-of-work — citable, indexable, and
referenced downstream. The platform's GDPR posture reflects that:
contributors retain every personal-data right under articles 15,
16, 18, and 20, but **erasure is mediated** rather than
self-service.

### What you can do from your profile

Profile → **Privacy** card.

| Right | What the button does |
|---|---|
| **Export my data** (art. 15 / 20) | Downloads a JSON dump of every personal-metadata row across the platform: profile, role grants, sessions, audit_log rows where you're actor or target, notifications, PAT metadata, GDPR-request history. Document bodies are *not* included — they are editorial content, not personal data. |
| **Edit my profile** (art. 16) | The profile form itself: bio, ORCID, email, language, avatar |
| **Pause email notifications** (art. 18, partial) | The §24 toggle |
| **Request anonymisation** (art. 17) | Opens a confirmation dialog; on submit, files a request for review. See below. |

The export endpoint excludes by design: `password_hash`, the
SHA-256-hashed IP address (privacy-cost without investigative
value), bcrypt digests of any kind, document bodies.

### Why account deletion isn't self-service

A self-service "delete my account → unpublish all my
contributions" flow would either:

- silently break foreign keys to `audit_log`,
  `document_versions`, `policy_page_versions` (auditability
  lost), or
- leave the editorial record intact while wiping the personal
  metadata — which is what we ship, but it is an
  *anonymisation*, not a *delete*, and it should be reviewed
  before it happens.

GDPR art. 17.3.d permits this: erasure does not apply when
processing is necessary "for archiving purposes in the public
interest, scientific or historical research purposes". Edited
scientific corpora fall squarely inside that exception, the same
foundation every serious scientific publisher uses.

### The anonymisation request flow

You file a request from the Privacy card; the request lands in
**Admin → GDPR queue** for review. After institutional sign-off,
an Admin executes the anonymisation, which:

- replaces your user fields with a placeholder identity,
- rewrites `audit_log.actor_username` to the placeholder,
- revokes every active session and PAT,
- deactivates the account,
- emits a `user.anonymised` audit row.

Your editorial contributions remain in the record, but no longer
carry your name — only the placeholder. The flow is mediated, not
denied: the platform commits to processing the request through
its review queue, and the audit log captures the outcome.

### Reference

[`docs/reference/GDPR_POSTURE.md`](reference/GDPR_POSTURE.md)
covers the legal foundation, the per-table anonymisation script,
the Admin queue surface, and the rationale for what's in and
out of the export.

---

## 32. Admin reference

This section is a quick reference for Admins. Most of these features are found
under **Settings** in the navigation.

### User management

Create, edit, and deactivate user accounts. Admins can set any role. Only Admins
can create accounts when public registration is disabled (the default).

### System settings

| Setting | What it controls |
|---------|-----------------|
| **Platform name** | The name shown in the navbar and browser tab |
| **Logo** | Upload a PNG/JPG/SVG logo for the navbar |
| **Navbar colour** | CSS colour for the navigation bar background |
| **Default language** | Interface language shown before login |
| **Public home** | Whether the platform is accessible without login |
| **Show collections on home** | Show published collection list on the home page |
| **Show search on home** | Show a search bar on the home page |
| **Show login button** | Show a login link for non-authenticated visitors |
| **Custom homepage CSS** | Upload a CSS file to override the home page styles |
| **Propagate CSS** | Apply the custom CSS to all public pages (not just the home) |
| **EVT viewer** | Enable/disable the EVT integration globally |
| **AI provider** | Choose: disabled / OpenAI / Anthropic / Gemini |
| **AI model** | The specific model to use for AI features |
| **AI API key** | The API key for the selected provider (stored encrypted) |
| **AI requests per hour** | Per-user rate limit for AI features (default: 20) |
| **AI privacy warning** | Show a privacy notice before the first AI request per session |
| **Max upload size** | Maximum size for a single XML file upload (MB) |
| **ZIP max archive size** | Maximum size of a ZIP file for batch uploads (MB) |
| **ZIP max extracted size** | Maximum total size of all files extracted from a ZIP (MB) |
| **ZIP max files** | Maximum number of files in a single ZIP batch |
| **Audit log retention** | How many days to keep audit records (default: 90 days) |
| **Session retention** | How many days to keep expired session records (default: 30 days) |
| **Email enabled** | Master switch for the transactional email channel (§24) |
| **Email from address** | The `From:` header used by every outgoing message |
| **Fixity sweep schedule** | Cron expression for the routine integrity check (§29) |
| **Public link toggles** | One per public-navigation-capable plugin (§27) |

### Plugins

Aracne2 has a plugin system. Some features are built-in and always active
(audit logging, notifications, collections, named entities, OAI-PMH, webhooks,
EVT viewer, AI). Others can be installed as optional add-ons and activated or
deactivated by the Admin without restarting the system.

A plugin can declare one or more **capabilities** that the platform's
generic surfaces auto-cable to: `inline_authority` (TEI editor toolbar
buttons), `collection_deposit` and `website_deposit` (per-plugin section
on the collection / website edit pages), and `public_navigation` (§27).
Activating a plugin never auto-publishes its public surface — see §27.

### Named entity tag configuration

By default the entity indexer extracts `persName`, `placeName`, and `orgName`.
The Admin (or EditorInChief) can change this list to include any TEI element
name. After changing, re-index existing collections to apply the change.

### Admin-only surfaces shipped post-M0

| Page | Purpose |
|---|---|
| `/admin/audit-log` | Browse/filter/export the audit log (§28) |
| `/admin/fixity` | Per-collection fixity dashboard + recheck (§29) |
| `/admin/policies` | Edit / publish institutional declarations (§30) |
| `/admin/gdpr` | Review queue for anonymisation requests (§31) |
| Profile → API Tokens | Self-service PAT management (§25) |
| Profile → Privacy | Personal-data export and anonymisation request (§31) |

### Audit log

Every significant action (user creation, collection state changes, document
operations, settings changes, role grants, GDPR requests) is recorded in the
audit log. The log is retained for a configurable number of days. It is visible
to Admins only at `/admin/audit-log` and is never exposed in API responses.

### Capability roles

Beyond the five hierarchical roles, the platform supports
**capability roles** — granted explicitly per user, orthogonal to the
hierarchy. The first one is `PolicyManager` (§30). See
[`docs/reference/CAPABILITY_ROLES.md`](reference/CAPABILITY_ROLES.md).

---

*Last updated: 2026-05-02*
