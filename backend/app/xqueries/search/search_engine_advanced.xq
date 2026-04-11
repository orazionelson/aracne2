(:~
 : Advanced search across multiple eXist-db collections for a search engine.
 :
 : Supports four modes (any combination of the optional filters is valid):
 :
 :   1. Tag search         — text inside a specific element (e.g. persName)
 :   2. Attribute search   — elements whose attribute matches a value
 :                           (e.g. @role = 'Conte')
 :   3. Combined           — both element and attribute constraints + optional text
 :   4. Plain text fallback — when element_name is empty, searches //p like the
 :                            regular search endpoint
 :
 : Primary path: eXist-db Lucene FT index; fallback: contains() scan.
 : Per-document snippet cap ($max_snippets_per_doc) prevents flooding.
 :
 : External variables:
 :   $collection_paths_csv  xs:string  — comma-separated eXist-db paths
 :   $query                 xs:string  — search term (empty = no text filter)
 :   $element_name          xs:string  — element local-name to target (empty = //p)
 :   $attr_name             xs:string  — attribute local-name to filter (empty = none)
 :   $attr_value            xs:string  — attribute value to match (empty = any)
 :   $max_results           xs:string  — maximum total hits (cast to integer)
 :
 : Returns <results count="N"> with <hit> children carrying attributes:
 :   @collection_path, @filename, @title, @element, @score, @mode
 :   and a <kwic> child with the text snippet.
 :)
xquery version "3.1";
import module namespace kwic = "http://exist-db.org/xquery/kwic";

declare variable $collection_paths_csv as xs:string external;
declare variable $query                as xs:string external;
declare variable $element_name         as xs:string external;
declare variable $attr_name            as xs:string external;
declare variable $attr_value           as xs:string external;
declare variable $max_results          as xs:string external;

(:~ Extract a plain-text snippet centred on the first occurrence of $q. :)
declare function local:snippet($text as xs:string, $q as xs:string) as xs:string {
  if ($q = "") then normalize-space(substring($text, 1, 200))
  else
    let $lc-pos := string-length(substring-before(lower-case($text), lower-case($q)))
    let $start  := max((1, $lc-pos - 60))
    return normalize-space(substring($text, $start, string-length($q) + 200))
};

(:~ Extract the document title (namespace-agnostic). :)
declare function local:doc-title($root as node()) as xs:string {
  normalize-space(
    string(($root//*[local-name() = 'titleStmt']/*[local-name() = 'title'])[1])
  )
};

(:~ True when $node passes the attribute filter. :)
declare function local:passes-attr(
  $node     as node(),
  $a-name   as xs:string,
  $a-val    as xs:string
) as xs:boolean {
  if ($a-name = "") then true()
  else if ($a-val = "") then exists($node/@*[local-name() = $a-name])
  else string($node/@*[local-name() = $a-name]) = $a-val
};

(: ── Main FLWOR ───────────────────────────────────────────────────────────── :)

let $max_snippets_per_doc := 5
let $paths      := tokenize(normalize-space($collection_paths_csv), "\s*,\s*")
let $has-query  := normalize-space($query) != ""
let $has-elem   := normalize-space($element_name) != ""
let $has-attr   := normalize-space($attr_name) != ""

let $ft-options :=
  <options>
    <default-operator>and</default-operator>
    <phrase-slop>0</phrase-slop>
    <leading-wildcard>no</leading-wildcard>
  </options>

let $all-hits :=
  for $path in $paths

  (: Target element set: specific element, or //p as default. :)
  let $targets :=
    if ($has-elem) then
      collection($path)//*[local-name() = $element_name]
    else
      collection($path)//*[local-name() = 'p']

  (: ── Lucene path (only when a text query is present) ─────────────────── :)
  let $raw-lucene :=
    if ($has-query) then
      try {
        for $m in ft:query($targets, $query, $ft-options)
        where local:passes-attr($m, $attr_name, $attr_value)
        let $root    := root($m)
        let $score   := ft:score($m)
        let $summary := kwic:summarize($m, <config width="60" table="no"/>)
        order by $score descending
        return
          <hit collection_path="{ $path }"
               filename="{ util:document-name($root) }"
               title="{ local:doc-title($root) }"
               element="{ local-name($m) }"
               score="{ $score }"
               mode="advanced-lucene">
            <kwic>{ normalize-space(string-join($summary/descendant-or-self::text(), "")) }</kwic>
          </hit>
      } catch * { () }
    else ()

  (: ── contains() / structural path ───────────────────────────────────── :)
  (: Used when: no Lucene index available, or no text query (attr-only search). :)
  let $raw-fallback :=
    if (exists($raw-lucene)) then ()
    else
      for $m in $targets
      let $text := string($m)
      where
        local:passes-attr($m, $attr_name, $attr_value)
        and (not($has-query) or contains(lower-case($text), lower-case($query)))
      let $root := root($m)
      return
        <hit collection_path="{ $path }"
             filename="{ util:document-name($root) }"
             title="{ local:doc-title($root) }"
             element="{ local-name($m) }"
             score="0"
             mode="{ if ($has-query) then 'advanced-contains' else 'advanced-structural' }">
          <kwic>{ local:snippet($text, $query) }</kwic>
        </hit>

  let $raw := ($raw-lucene, $raw-fallback)

  (: Per-document cap. :)
  let $capped :=
    if (exists($raw)) then
      let $filenames := distinct-values($raw/@filename/string())
      return
        for $fname in $filenames
        return subsequence($raw[@filename = $fname], 1, $max_snippets_per_doc)
    else ()

  return $capped

let $sorted :=
  for $hit in $all-hits
  order by xs:decimal($hit/@score) descending
  return $hit

return
  <results count="{ count($sorted) }">
    { subsequence($sorted, 1, xs:integer($max_results)) }
  </results>
