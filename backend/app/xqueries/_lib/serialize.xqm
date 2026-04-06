(:~
 : Common serialization helpers.
 : Imported by other XQuery modules via: import module namespace ser="http://aracne2/serialize" at "_lib/serialize.xqm";
 :)
module namespace ser = "http://aracne2/serialize";

(:~ Serialize a sequence of items as a JSON array of strings. :)
declare function ser:strings-to-json-array($items as xs:string*) as xs:string {
    concat("[", string-join(for $i in $items return concat('"', $i, '"'), ","), "]")
};
