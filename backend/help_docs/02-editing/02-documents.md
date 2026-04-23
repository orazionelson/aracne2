# Documents

Documents are the individual TEI XML files inside a collection. They
are where the actual editorial work happens.

## Document list

The collection page shows every document with its filename, an optional
title (taken from `<titleStmt>/<title>`), the author, and the date of
last edit. Click any row to open the document in the TEI editor.

## Creating a new document

Click **New document**, give it a filename ending in `.xml`, and pick
one of the collection's body templates as a starting skeleton. The
editor opens immediately with the template pre-populated.

## Uploading documents

Drag and drop one or more `.xml` files into the collection detail page,
or click **Upload** and pick them from a file chooser. Each file is
uploaded, validated against the collection's schema if one is attached,
and added to the document list. Upload of non-XML files is blocked.

## Downloading a document

Any document can be downloaded as XML from the "⋯" menu on its row in
the document list. The downloaded file is exactly what lives in the
eXist-db XML database — no transformation applied.

## Deleting documents

Editors and above can delete a document from the "⋯" menu. A confirmation
dialog warns that the operation cannot be undone (apart from restoring
from a platform backup).

## Searching within a collection

The search box on the collection page runs a full-text search against
every document in the collection. Matches are highlighted with a short
snippet of context. The underlying engine is eXist-db's Lucene index.
