(:~
 : Idempotent bootstrap: creates the Aracne2 runtime user and recursively
 : transfers ownership of /db/aracne2 and all its contents to that user.
 :
 : Must be executed under eXist-db admin credentials.
 : Safe to call on every startup — guards prevent duplicate account creation
 : and chown/chmod are safe to re-apply on already-owned resources.
 :
 : External variables (passed by the Python caller):
 :   $username  — the runtime account name (e.g. 'aracne')
 :   $password  — the runtime account password
 :)
declare variable $username as xs:string external;
declare variable $password as xs:string external;

(:~
 : Recursively transfer ownership of a collection and all its contents
 : (documents and subcollections) to $username.
 : Collections get rwx------; documents get rw-------.
 :)
declare function local:chown-recursive(
    $path     as xs:string,
    $username as xs:string
) as empty-sequence() {
  (
    sm:chown(xs:anyURI($path), $username),
    sm:chgrp(xs:anyURI($path), $username),
    sm:chmod(xs:anyURI($path), 'rwx------'),

    for $doc in xmldb:get-child-resources($path)
    let $doc-uri := xs:anyURI($path || '/' || $doc)
    return (
      sm:chown($doc-uri, $username),
      sm:chgrp($doc-uri, $username),
      sm:chmod($doc-uri, 'rw-------')
    ),

    for $child in xmldb:get-child-collections($path)
    let $child-path := $path || '/' || $child
    return local:chown-recursive($child-path, $username)
  )
};

(: Create the account only if it does not already exist :)
let $_ :=
  if (not(sm:user-exists($username)))
  then sm:create-account($username, $password, 'guest', ())
  else ()

return
  if (xmldb:collection-available('/db/aracne2'))
  then local:chown-recursive('/db/aracne2', $username)
  else ()
