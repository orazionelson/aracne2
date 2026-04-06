(:~
 : Ensure the Aracne2 base collection structure exists in eXist-db.
 :
 : Creates /db/aracne2 and /db/aracne2/collections if they are absent.
 : Safe to run at every startup — all operations are idempotent.
 :)
let $_ :=
  if (not(xmldb:collection-available('/db/aracne2')))
  then xmldb:create-collection('/db', 'aracne2')
  else ()
return
  if (not(xmldb:collection-available('/db/aracne2/collections')))
  then xmldb:create-collection('/db/aracne2', 'collections')
  else ()
