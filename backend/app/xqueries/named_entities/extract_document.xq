(:~
 : Extract named entities (persName, placeName, orgName) from a single TEI document.
 :
 : Uses local-name() matching so the query is namespace-agnostic — works whether
 : or not the document declares the TEI namespace.
 :
 : External variables:
 :   $doc_path  xs:string  — full eXist-db document path,
 :                           e.g. /db/aracne2/collections/dante/inferno.xml
 :
 : Returns an <entities> root with zero or more <entity> children.
 : Each <entity> carries:
 :   @type  — local tag name: persName | placeName | orgName
 :   @ref   — value of @ref attribute if present (authority URI or internal ref), else ""
 :   <raw>  — normalised text content of the element (the name as it appears)
 :   <context> — up to 250 chars of the parent element's text (surrounding sentence)
 :)
xquery version "3.1";

declare variable $doc_path as xs:string external;

let $doc := doc($doc_path)
return
  <entities>{
    for $e in $doc//(
        *[local-name() = 'persName'] |
        *[local-name() = 'placeName'] |
        *[local-name() = 'orgName']
      )
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
