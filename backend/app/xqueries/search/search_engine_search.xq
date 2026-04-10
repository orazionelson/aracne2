(:~
 : Full-text search across multiple eXist-db collections for a search engine.
 :
 : Queries at paragraph level (//p) so that multiple occurrences within the same
 : document produce distinct KWIC snippets, each capped at $max_snippets_per_doc
 : per document.  TEI document title is extracted from //titleStmt/title and
 : attached to every hit.
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
 :   $max_results           xs:string  — maximum total snippets to return (cast to integer)
 :
 : Returns a <results> element with a @count attribute and zero or more <hit> elements:
 :   @collection_path  — the eXist-db collection path where the hit was found
 :   @filename         — document name inside the collection
 :   @title            — TEI titleStmt/title text (empty string if absent)
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

(:~ Extract the document title from a TEI root element (namespace-agnostic). :)
declare function local:doc-title($root as node()) as xs:string {
  normalize-space(
    string(($root//*[local-name() = 'titleStmt']/*[local-name() = 'title'])[1])
  )
};

(: ── Main FLWOR ───────────────────────────────────────────────────────────── :)

(: Maximum KWIC snippets returned per document to avoid flooding results. :)
let $max_snippets_per_doc := 5

let $paths := tokenize(normalize-space($collection_paths_csv), "\s*,\s*")

let $ft-options :=
  <options>
    <default-operator>and</default-operator>
    <phrase-slop>0</phrase-slop>
    <leading-wildcard>no</leading-wildcard>
  </options>

let $all-hits :=
  for $path in $paths

  (: ── Lucene path ──────────────────────────────────────────────────────── :)
  let $raw-lucene :=
    try {
      for $match in ft:query(collection($path)//*[local-name() = 'p'], $query, $ft-options)
      let $root    := root($match)
      let $score   := ft:score($match)
      let $summary := kwic:summarize($match, <config width="60" table="no"/>)
      let $title   := local:doc-title($root)
      order by $score descending
      return
        <hit collection_path="{ $path }"
             filename="{ util:document-name($root) }"
             title="{ $title }"
             score="{ $score }"
             mode="lucene">
          <kwic>{ normalize-space(string-join($summary/descendant-or-self::text(), "")) }</kwic>
        </hit>
    } catch * {
      ()  (: no Lucene index on this collection — fall through :)
    }

  (: Cap per document to avoid flooding results from a single large document. :)
  let $lucene-hits :=
    if (exists($raw-lucene)) then
      let $filenames := distinct-values($raw-lucene/@filename/string())
      return
        for $fname in $filenames
        return subsequence($raw-lucene[@filename = $fname], 1, $max_snippets_per_doc)
    else
      ()

  (: ── contains() fallback ─────────────────────────────────────────────── :)
  let $raw-contains :=
    if (exists($lucene-hits)) then
      ()
    else
      for $para in collection($path)//*[local-name() = 'p']
      let $text := string($para)
      where contains(lower-case($text), lower-case($query))
      let $root  := root($para)
      let $title := local:doc-title($root)
      return
        <hit collection_path="{ $path }"
             filename="{ util:document-name($root) }"
             title="{ $title }"
             score="0"
             mode="contains">
          <kwic>{ local:snippet($text, $query) }</kwic>
        </hit>

  let $contains-hits :=
    if (exists($raw-contains)) then
      let $filenames := distinct-values($raw-contains/@filename/string())
      return
        for $fname in $filenames
        return subsequence($raw-contains[@filename = $fname], 1, $max_snippets_per_doc)
    else
      ()

  return ($lucene-hits, $contains-hits)

let $sorted :=
  for $hit in $all-hits
  order by xs:decimal($hit/@score) descending
  return $hit

return
  <results count="{ count($sorted) }">
    { subsequence($sorted, 1, xs:integer($max_results)) }
  </results>
