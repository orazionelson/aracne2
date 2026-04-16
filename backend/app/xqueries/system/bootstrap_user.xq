(:~
 : Idempotent bootstrap: creates the Aracne2 runtime user and transfers ownership
 : of all Aracne2 root collections to that user.
 :
 : Must be executed under eXist-db admin credentials.
 : Safe to call on every startup — guards prevent duplicate account creation.
 :
 : External variables (passed by the Python caller):
 :   $username  — the runtime account name (e.g. 'aracne')
 :   $password  — the runtime account password
 :)
declare variable $username as xs:string external;
declare variable $password as xs:string external;

(: Create the account only if it does not already exist :)
let $_ :=
  if (not(sm:user-exists($username)))
  then sm:create-account($username, $password, 'guest', ())
  else ()

(: Set ownership and restrict permissions on all Aracne2 collections :)
let $paths := ('/db/aracne2', '/db/aracne2/collections')
for $path in $paths
where xmldb:collection-available($path)
return (
  sm:chown(xs:anyURI($path), $username),
  sm:chgrp(xs:anyURI($path), $username),
  sm:chmod(xs:anyURI($path), 'rwx------')
)
