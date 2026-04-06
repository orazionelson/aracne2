(:~
 : Case-insensitive full-text search across all XML documents in a collection.
 : Uses contains() — no Lucene index required.
 :
 : External variables:
 :   $collection_path  xs:string  — full eXist-db collection path,
 :                                  e.g. /db/aracne2/collections/dante
 :   $query            xs:string  — search term (plain string, case-insensitive)
 :   $max_results      xs:string  — maximum number of hits to return (cast to integer)
 :
 : Returns a <results> element containing zero or more <hit> elements:
 :   @filename  — document name inside the collection
 :   @snippet   — up to 150 chars of context around the first match
 :                (XML attribute escaping applied automatically by the serializer)
 :)
xquery version "3.1";

declare variable $collection_path as xs:string external;
declare variable $query           as xs:string external;
declare variable $max_results     as xs:string external;

declare function local:snippet($text as xs:string, $q as xs:string) as xs:string {
  let $lc-pos := string-length(substring-before(lower-case($text), lower-case($q)))
  let $start  := max((1, $lc-pos - 60))
  return normalize-space(substring($text, $start, string-length($q) + 150))
};

let $hits :=
  for $doc in collection($collection_path)
  let $text := string($doc)
  where contains(lower-case($text), lower-case($query))
  return
    <hit filename="{ util:document-name($doc) }"
         snippet="{ local:snippet($text, $query) }"/>

return
  <results>{ subsequence($hits, 1, xs:integer($max_results)) }</results>
