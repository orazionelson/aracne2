(:~
 : Full-text search across multiple eXist-db collections for a search engine.
 :
 : Primary path: eXist-db Lucene FT index via ft:query() with KWIC snippets.
 : Fallback path: case-insensitive contains() scan used when no Lucene index
 : is configured or when ft:query() raises an error.
 :
 : External variables:
 :   $collection_paths_csv  xs:string  — comma-separated list of eXist-db collection
 :                                       paths, e.g. "/db/aracne2/collections/dante,
 :                                                    /db/aracne2/collections/petrarca"
 :   $query                 xs:string  — search term (plain string or Lucene syntax)
 :   $max_results           xs:string  — maximum total hits to return (cast to integer)
 :
 : Returns a <results> element with a @count attribute and zero or more <hit> elements:
 :   @collection_path  — the eXist-db collection path where the hit was found
 :   @filename         — document name inside the collection
 :   @score            — relevance score (0 for contains() fallback)
 :   @mode             — "lucene" | "contains"
 :   <kwic>            — text snippet showing the match in context
 :)
xquery version "3.1";
import module namespace kwic = "http://exist-db.org/xquery/kwic";

declare variable $collection_paths_csv as xs:string external;
declare variable $query                as xs:string external;
declare variable $max_results          as xs:string external;

(:~ Extract a plain-text snippet of ~200 chars centred on the first occurrence of $q. :)
declare function local:snippet($text as xs:string, $q as xs:string) as xs:string {
  let $lc-pos := string-length(substring-before(lower-case($text), lower-case($q)))
  let $start  := max((1, $lc-pos - 60))
  return normalize-space(substring($text, $start, string-length($q) + 200))
};

let $paths := tokenize(normalize-space($collection_paths_csv), "\s*,\s*")

let $ft-options :=
  <options>
    <default-operator>and</default-operator>
    <phrase-slop>0</phrase-slop>
    <leading-wildcard>no</leading-wildcard>
  </options>

let $all-hits :=
  for $path in $paths
  let $lucene-hits :=
    try {
      for $match in ft:query(collection($path), $query, $ft-options)
      let $score   := ft:score($match)
      let $summary := kwic:summarize($match, <config width="60" table="no"/>)
      order by $score descending
      return
        <hit collection_path="{ $path }"
             filename="{ util:document-name(root($match)) }"
             score="{ $score }"
             mode="lucene">
          <kwic>{ normalize-space(string-join($summary/descendant-or-self::text(), "")) }</kwic>
        </hit>
    } catch * {
      ()  (: no Lucene index on this collection — fall through :)
    }
  return
    if (exists($lucene-hits)) then
      $lucene-hits
    else
      for $doc in collection($path)
      let $text := string($doc)
      where contains(lower-case($text), lower-case($query))
      return
        <hit collection_path="{ $path }"
             filename="{ util:document-name($doc) }"
             score="0"
             mode="contains">
          <kwic>{ local:snippet($text, $query) }</kwic>
        </hit>

let $sorted :=
  for $hit in $all-hits
  order by xs:decimal($hit/@score) descending
  return $hit

return
  <results count="{ count($sorted) }">
    { subsequence($sorted, 1, xs:integer($max_results)) }
  </results>
