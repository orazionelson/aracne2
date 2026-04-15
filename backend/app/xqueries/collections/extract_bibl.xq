xquery version "3.1";

(:
  extract_bibl.xq — Collect all <bibl> and <biblStruct> elements from a
  collection, stripping the TEI namespace so the AI receives clean XML.

  Each entry is wrapped in a name-space-free element carrying two attributes:
    @source  — the originating document filename (util:document-name)
    @n       — 1-based sequence number within that document

  External variables
    $collection_path  — full eXist-db path to the collection
                        (e.g. /db/aracne2/collections/dante)
:)

declare namespace tei = "http://www.tei-c.org/ns/1.0";

declare variable $collection_path external;

let $col := collection($collection_path)
return
<entries>{
  for $doc in $col
  let $id := util:document-name($doc)
  for $entry at $n in ($doc//tei:bibl | $doc//tei:biblStruct)
  return
    element { local-name($entry) } {
      attribute source { $id },
      attribute n { $n },
      $entry/node() ! (
        if (. instance of element()) then
          element { local-name(.) } { ./(@* except @xmlns), ./node() }
        else .
      )
    }
}</entries>
