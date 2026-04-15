(:~
 : Extract named entities from a single TEI document.
 :
 : The set of element names to extract is controlled by the $tags external
 : variable — a whitespace-separated list of TEI local element names, e.g.:
 :   "persName placeName orgName objectName measure"
 :
 : Uses local-name() matching so the query is namespace-agnostic — works
 : whether or not the document declares the TEI namespace.
 :
 : External variables:
 :   $doc_path  xs:string  — full eXist-db document path,
 :                           e.g. /db/aracne2/collections/dante/inferno.xml
 :   $tags      xs:string  — whitespace-separated TEI element names to match
 :
 : Returns an <entities> root with zero or more <entity> children.
 : Each <entity> carries:
 :   @type  — local tag name as it appears in $tags (e.g. "persName")
 :   @ref   — value of @ref attribute if present (authority URI or internal ref), else ""
 :   <raw>  — normalised text content of the element (the name as it appears)
 :   <context> — up to 250 chars of the parent element's text (surrounding sentence)
 :)
xquery version "3.1";

declare variable $doc_path as xs:string external;
declare variable $tags     as xs:string external := "persName placeName orgName";

let $tag-seq := tokenize(normalize-space($tags), '\s+')
let $doc     := doc($doc_path)
return
  <entities>{
    for $e in $doc//*[local-name() = $tag-seq]
    let $text    := normalize-space(string($e))
    let $ref     := string($e/@ref)
    let $context := normalize-space(string($e/..))
    where $text != ''
    return
      <entity
        type = "{ local-name($e) }"
        ref  = "{ $ref }">
        <raw>{ $text }</raw>
        <context>{ substring($context, 1, 250) }</context>
      </entity>
  }</entities>
