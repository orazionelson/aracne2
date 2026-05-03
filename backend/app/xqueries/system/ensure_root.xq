(:~
 : Ensure the Aracne2 base collection structure exists in eXist-db.
 :
 : Creates the three top-level collections if absent:
 :   /db/aracne2              — root namespace
 :   /db/aracne2/collections  — working trees (editor-facing, mutable)
 :   /db/aracne2/published    — immutable publish-time snapshots served to the public
 :
 : Safe to run at every startup — all operations are idempotent.
 :)
let $_ :=
  if (not(xmldb:collection-available('/db/aracne2')))
  then xmldb:create-collection('/db', 'aracne2')
  else ()
let $_ :=
  if (not(xmldb:collection-available('/db/aracne2/collections')))
  then xmldb:create-collection('/db/aracne2', 'collections')
  else ()
return
  if (not(xmldb:collection-available('/db/aracne2/published')))
  then xmldb:create-collection('/db/aracne2', 'published')
  else ()
