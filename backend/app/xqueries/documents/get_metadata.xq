(:~
 : Return generic metadata for a single XML document.
 :
 : External variables:
 :   $doc_path  xs:string  — full eXist-db document path,
 :                           e.g. /db/aracne2/collections/dante/inferno.xml
 :
 : Returns a <metadata> element with:
 :   root-element  — local name of the document root element
 :   namespace     — namespace URI of the root element (empty string if none)
 :   size          — total character count of the serialized document
 :   child-count   — number of direct child elements of the root
 :)
xquery version "3.1";

declare variable $doc_path as xs:string external;

let $doc   := doc($doc_path)
let $root  := $doc/*[1]
return
  <metadata>
    <root-element>{ local-name($root) }</root-element>
    <namespace>{ namespace-uri($root) }</namespace>
    <size>{ string-length(string($doc)) }</size>
    <child-count>{ count($root/*) }</child-count>
  </metadata>
