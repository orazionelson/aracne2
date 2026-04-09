(:~
 : Full-text search across all XML documents in a collection.
 :
 : Primary path: eXist-db Lucene FT index via ft:query() with KWIC snippets.
 : Fallback path: case-insensitive contains() scan, used when no Lucene index
 : is configured or when ft:query() raises an error.
 :
 : External variables:
 :   $collection_path  xs:string  — full eXist-db collection path,
 :                                  e.g. /db/aracne2/collections/dante
 :   $query            xs:string  — search term (plain string or Lucene syntax)
 :   $max_results      xs:string  — maximum number of hits to return (cast to integer)
 :
 : Returns a <results> element containing zero or more <hit> elements:
 :   @filename  — document name inside the collection
 :   @score     — relevance score (0 for contains() fallback)
 :   @mode      — "lucene" | "contains" (indicates which path was used)
 :   <kwic>     — text snippet showing the match in context
 :)
xquery version "3.1";
import module namespace kwic = "http://exist-db.org/xquery/kwic";

declare variable $collection_path as xs:string external;
declare variable $query           as xs:string external;
declare variable $max_results     as xs:string external;

(:~ Extract a plain-text snippet of ~200 chars centred on the first occurrence of $q. :)
declare function local:snippet($text as xs:string, $q as xs:string) as xs:string {
  let $lc-pos := string-length(substring-before(lower-case($text), lower-case($q)))
  let $start  := max((1, $lc-pos - 60))
  return normalize-space(substring($text, $start, string-length($q) + 200))
};

(:
 : Try the Lucene FT path first.  If ft:query() raises an error (e.g. no index
 : is configured on the collection), the catch block returns the empty sequence
 : and the code falls through to the contains() scan.
 :)
let $lucene-hits :=
  try {
    let $ft-options :=
      <options>
        <default-operator>and</default-operator>
        <phrase-slop>0</phrase-slop>
        <leading-wildcard>no</leading-wildcard>
      </options>
    for $match in ft:query(collection($collection_path), $query, $ft-options)
    let $score   := ft:score($match)
    let $summary := kwic:summarize($match, <config width="60" table="no"/>)
    order by $score descending
    return
      <hit filename="{ util:document-name(root($match)) }"
           score="{ $score }"
           mode="lucene">
        <kwic>{ normalize-space(string-join($summary/descendant-or-self::text(), "")) }</kwic>
      </hit>
  } catch * {
    ()  (: no index configured — fall through to contains() scan :)
  }

(:
 : contains() fallback: used when Lucene returned nothing (empty result means
 : either no index or genuinely no hits).  We distinguish by checking whether
 : ft:query() succeeded at all via the mode attribute; here we produce results
 : only when the Lucene sequence was empty.
 :)
let $hits :=
  if (exists($lucene-hits)) then
    $lucene-hits
  else
    for $doc in collection($collection_path)
    let $text := string($doc)
    where contains(lower-case($text), lower-case($query))
    return
      <hit filename="{ util:document-name($doc) }"
           score="0"
           mode="contains">
        <kwic>{ local:snippet($text, $query) }</kwic>
      </hit>

return
  <results count="{ count($hits) }">
    { subsequence($hits, 1, xs:integer($max_results)) }
  </results>
