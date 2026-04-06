(:~
 : Create a new eXist-db collection.
 :
 : External variables:
 :   $root  xs:string  — parent collection path, e.g. /db/aracne2/collections
 :   $name  xs:string  — name of the new collection (slug only, no slashes)
 :)
declare variable $root as xs:string external;
declare variable $name as xs:string external;

xmldb:create-collection($root, $name)
