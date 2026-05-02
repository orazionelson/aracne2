(:~
 : Copy a collection's working tree to its published snapshot path.
 :
 : Source:      /db/aracne2/collections/{slug}
 : Destination: /db/aracne2/published/{slug}
 :
 : The destination is removed first if it exists. eXist-db's
 : ``xmldb:copy-collection`` does not overwrite existing same-named documents,
 : so a clean slate is required to guarantee that documents removed from the
 : working tree since the previous publish do not survive as stale residuals
 : in the snapshot.
 :
 : ``xmldb:copy-collection($source, $target-parent)`` copies the source
 : collection (with its name) into the target parent. Passing
 : '/db/aracne2/published' as the target parent yields
 : '/db/aracne2/published/{slug}' as the resulting destination.
 :)
declare variable $slug external;

let $source := concat('/db/aracne2/collections/', $slug)
let $dest := concat('/db/aracne2/published/', $slug)
let $_ :=
  if (xmldb:collection-available($dest))
  then xmldb:remove($dest)
  else ()
return
  xmldb:copy-collection($source, '/db/aracne2/published')
