(:~
 : Extract Dublin Core-compatible metadata from a TEI XML document.
 :
 : Uses local-name() matching so the query is namespace-agnostic and works
 : whether or not the document declares the TEI namespace.
 :
 : External variables:
 :   $doc_path  xs:string  — full eXist-db document path,
 :                           e.g. /db/aracne2/collections/dante/inferno.xml
 :
 : Returns a <dc> element whose children are named after the DC fields they
 : represent (title, creator, publisher, date, language, description).
 : Elements with empty values are omitted.
 :)
xquery version "3.1";

declare variable $doc_path as xs:string external;

let $doc             := doc($doc_path)
let $header          := ($doc//*[local-name() = 'teiHeader'])[1]
let $fileDesc        := ($header/*[local-name() = 'fileDesc'])[1]
let $titleStmt       := ($fileDesc/*[local-name() = 'titleStmt'])[1]
let $publicationStmt := ($fileDesc/*[local-name() = 'publicationStmt'])[1]
let $profileDesc     := ($header/*[local-name() = 'profileDesc'])[1]

let $title     := normalize-space(string(($titleStmt/*[local-name() = 'title'])[1]))
let $authors   := $titleStmt/*[local-name() = 'author']
let $publisher := normalize-space(string(($publicationStmt/*[local-name() = 'publisher'])[1]))

(: Prefer @when attribute for machine-readable dates; fall back to element text :)
let $date-when := string(($publicationStmt/*[local-name() = 'date']/@when)[1])
let $date-text := normalize-space(string(($publicationStmt/*[local-name() = 'date'])[1]))
let $date      := if ($date-when != '') then $date-when else $date-text

let $lang    := string(($profileDesc/*[local-name() = 'langUsage']/*[local-name() = 'language']/@ident)[1])
let $abstract := normalize-space(string(($profileDesc/*[local-name() = 'abstract'])[1]))

return
  <dc>
    { if ($title != '') then <title>{ $title }</title> else () }
    { for $a in $authors
      let $atext := normalize-space(string($a))
      where $atext != ''
      return <creator>{ $atext }</creator>
    }
    { if ($publisher != '') then <publisher>{ $publisher }</publisher> else () }
    { if ($date != '')      then <date>{ $date }</date>           else () }
    { if ($lang != '')      then <language>{ $lang }</language>   else () }
    { if ($abstract != '')  then <description>{ $abstract }</description> else () }
  </dc>
