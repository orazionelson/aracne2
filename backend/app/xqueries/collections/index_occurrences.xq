(:~
 : Collect all occurrences of a tag from a collection for index building.
 :
 : Returns one record per occurrence as a newline-separated list of
 : pipe-triple-separated fields:   key ||| subkey ||| text ||| filename
 :
 :   key      = value of $key_attr on the element, or its text content when
 :              $key_attr is empty
 :   subkey   = value of $subkey_attr on the element, or empty string when
 :              $subkey_attr is empty
 :   text     = normalized text content of the element
 :   filename = base filename of the source document (e.g. "doc001.xml")
 :
 : External variables:
 :   $path        xs:string  — full eXist-db path
 :   $tag         xs:string  — element local-name to index (e.g. "persName")
 :   $key_attr    xs:string  — attribute name for the key (empty = use text content)
 :   $subkey_attr xs:string  — attribute name for the sub-key (empty = no sub-grouping)
 :)
declare variable $path as xs:string external;
declare variable $tag as xs:string external;
declare variable $key_attr as xs:string external;
declare variable $subkey_attr as xs:string external;

let $sep := "|||"
let $lines :=
  for $doc in collection($path)
  let $filename := tokenize(base-uri($doc), "/")[last()]
  for $el in $doc//*[local-name() = $tag]
  let $key-val :=
    if ($key_attr != "")
    then normalize-space(string($el/@*[local-name() = $key_attr][1]))
    else normalize-space(string($el))
  let $subkey-val :=
    if ($subkey_attr != "")
    then normalize-space(string($el/@*[local-name() = $subkey_attr][1]))
    else ""
  let $text-val := normalize-space(string($el))
  return string-join(($key-val, $subkey-val, $text-val, $filename), $sep)
return string-join($lines, "&#10;")
