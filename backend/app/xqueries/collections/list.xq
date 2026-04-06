(:~
 : List all XML document names in a collection.
 : Returns one name per line as plain text.
 :
 : External variables:
 :   $path  xs:string  — full eXist-db path, e.g. /db/aracne2/collections/dante
 :)
declare variable $path as xs:string external;

string-join(xmldb:get-child-resources($path), "&#10;")
