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
19. [OAI-PMH — making your data harvestable](#19-oai-pmh--making-your-data-harvestable)
20. [Webhooks — connecting to external tools](#20-webhooks--connecting-to-external-tools)
21. [Admin reference](#21-admin-reference)

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
Editors, reviews submitted work, publishes or rejects, and manages bibliographies
and permissions. The central coordinating role.

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

Your language preference is saved and applied automatically every time you log in.

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

---

## 7. The editorial workflow

Each collection moves through four states. Each transition is logged and triggers
a notification.

```
Draft  →  Assigned  →  Review  →  Published
              ↑____________|
              (rejected, back to assigned)
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

### Rejection
If the EditorInChief finds the work unsatisfactory, they click **Reject** and
provide a mandatory note explaining what needs to be corrected. The collection
returns to the **Assigned** state and the Editor is notified with the rejection note.

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
**optional and configurable** — they appear only when an Admin has set up an
API key for a supported provider (OpenAI, Anthropic/Claude, or Google Gemini).

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

- The global EVT setting is enabled (Admin → Settings)
- The collection has EVT enabled (in the collection metadata)
- The collection is published and public
- The collection contains exactly one document (EVT is designed for
  single-document editions)

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
| Collection rejected | The assigned Editor |
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

## 19. OAI-PMH — making your data harvestable

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

## 20. Webhooks — connecting to external tools

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

## 21. Admin reference

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

### Plugins

Aracne2 has a plugin system. Some features are built-in and always active
(audit logging, notifications, collections, named entities, OAI-PMH, webhooks,
EVT viewer, AI). Others can be installed as optional add-ons and activated or
deactivated by the Admin without restarting the system.

### Named entity tag configuration

By default the entity indexer extracts `persName`, `placeName`, and `orgName`.
The Admin (or EditorInChief) can change this list to include any TEI element
name. After changing, re-index existing collections to apply the change.

### Audit log

Every significant action (user creation, collection state changes, document
operations, settings changes) is recorded in the audit log. The log is retained
for a configurable number of days. It is visible to Admins only and is never
exposed in API responses.

---

*Last updated: 2026-04-16*
