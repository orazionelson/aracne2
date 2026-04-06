(:~
 : Return document count and total size (bytes) for a collection.
 : Output format: "count={n} size={bytes}"
 :
 : External variables:
 :   $path  xs:string  — full eXist-db path, e.g. /db/aracne2/collections/dante
 :)
declare variable $path as xs:string external;

let $resources := xmldb:get-child-resources($path)
let $count     := count($resources)
let $size      := sum(
    for $r in $resources
    return xmldb:size($path, $r)
)
return concat("count=", $count, " size=", $size)
