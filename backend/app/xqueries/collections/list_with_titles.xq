(:~
 : list_with_titles.xq
 :
 : Returns a <docs> element containing one <doc> per XML document in the
 : given collection.  For each document, the title and first author are
 : extracted from the TEI titleStmt using local-name() matching so that the
 : query works regardless of whether a default TEI namespace is declared.
 :
 : External variable:
 :   $collection_path — full eXist-db path, e.g. /db/aracne2/collections/dante
 :)

declare variable $collection_path as xs:string external;

<docs>{
  for $doc in collection($collection_path)
  let $filename  := tokenize(base-uri($doc), '/')[last()]
  let $titleStmt := ($doc//*[local-name() = 'titleStmt'])[1]
  let $title     := normalize-space(
                      string(($titleStmt/*[local-name() = 'title'][1])[1])
                    )
  let $author    := normalize-space(
                      string(($titleStmt/*[local-name() = 'author'][1])[1])
                    )
  where ends-with($filename, '.xml')
  return
    <doc>
      <filename>{ $filename }</filename>
      <title>{ $title }</title>
      <author>{ $author }</author>
    </doc>
}</docs>
