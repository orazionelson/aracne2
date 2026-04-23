# Validating documents

Validation checks a document against the TEI schema attached to its
collection. A valid document is not necessarily a correct document —
validation catches *structural* mistakes (missing required elements,
forbidden nesting, invalid attribute values), not editorial errors.

## Per-document validation

The **Validate** button in the editor toolbar runs the schema validator
on the current document and shows results in the right-hand panel:

- Green: the document is valid.
- Red: each error is listed with line number, element path, and a
  human-readable message.

Click an error to jump the editor cursor to the offending line.

## Collection-wide validation (EditorInChief+)

From the collection page, **Validate all** runs the schema against
every document in the collection and summarises results: how many
valid, how many with errors, and which documents had which errors.

Collection-wide validation is useful as a pre-publication safety check —
running it just before moving the collection to Review saves the
EditorInChief from having to spot-check each document by hand.

## No schema attached?

If the collection has no schema attached, the Validate button still
works but produces no meaningful output. Ask your EditorInChief or
Admin to attach a schema to the collection from its settings page.
