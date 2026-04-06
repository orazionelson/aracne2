(:~
 : Recursively remove a collection and all its contents.
 :
 : External variables:
 :   $path  xs:string  — full eXist-db path, e.g. /db/aracne2/collections/dante
 :)
declare variable $path as xs:string external;

xmldb:remove($path)
