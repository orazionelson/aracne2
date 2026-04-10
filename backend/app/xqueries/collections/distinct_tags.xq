(:~
 : Scan all XML documents in a collection and return a JSON object mapping
 : element local-names to the list of attribute local-names found on them.
 :
 : Output format: {"persName":["key","role"],"placeName":["ref"]}
 :
 : External variables:
 :   $path  xs:string  — full eXist-db path, e.g. /db/aracne2/collections/dante
 :)
declare variable $path as xs:string external;

let $elements := collection($path)//*
let $tag-names :=
  for $n in distinct-values($elements/local-name())
  order by $n
  return $n
let $entries :=
  for $name in $tag-names
  let $matching := $elements[local-name() = $name]
  let $attrs :=
    for $a in distinct-values($matching/@*/local-name())
    order by $a
    return $a
  let $attr-json := string-join(for $a in $attrs return concat('"', $a, '"'), ",")
  return concat('"', $name, '":[', $attr-json, ']')
return concat('{', string-join($entries, ','), '}')
