# Collections

A **collection** is the top-level container for a scholarly edition or
corpus. It groups related TEI documents together with shared metadata:
title, publisher, author, license, validation schema, and publication
settings.

Every document belongs to exactly one collection.

## The collections list

The main screen after login shows all collections you have access to.
Editors see only the collections assigned to them; EditorInChief and
Admin see every collection regardless of status.

You can filter by status (draft, assigned, review, published) and
search by title.

## Creating a collection (EditorInChief+)

Click **New collection** and fill in:

| Field | What it is |
|-------|-----------|
| Title | The human-readable name of the edition |
| Description | A short summary (optional) |
| Schema | The TEI validation schema to use (Admin uploads these) |
| Body template | A starting XML snippet for new documents |
| Author | Main author; autocompleted from the VIAF authority database |
| Publication place | Autocompleted from GeoNames |
| Publisher | The institution or publisher |
| Publication year | A plain integer |
| License | Pick from the seeded Creative Commons list |
| Identifier URL | DOI, Handle, or URN for the edition |

Everything can be edited after creation except the URL slug, which is
derived from the title at creation time.

## Collection detail page

The collection page shows the document list, the status pill, the
assigned editors, the bibliography (if any), and the action buttons
that match your role and the current status (assign, submit, publish,
reject, unpublish, delete).

## Permissions — giving an Editor access

EditorInChief can add individual Editors to a collection's authorized
list on the permissions tab. An Editor without a permission entry
cannot see the collection at all, even if it is published.

This permission is distinct from publication status: "published" makes
the collection readable for the public; "permission" controls who on
the editorial team can edit it.
