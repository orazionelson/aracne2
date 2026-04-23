# Roles

Aracne2 has five roles. Your role determines what you can see and do.

```
          Admin
            │
      EditorInChief
       ╱          ╲
  Editor         Designer
       ╲          ╱
           User
```

## User

Read-only access to **published** collections. Can browse and search
published documents. Cannot edit anything.

## Editor

Creates and edits TEI documents within collections that have been
assigned to them. Can upload documents, use the editor, validate their
work, and submit a collection for review when ready.

## Designer

Manages the visual presentation layer of public websites: writes and
edits XSLT stylesheets that transform TEI XML into HTML, configures
page templates, builds indices, and publishes the final site. Has no
access to the documents themselves.

An Editor and a Designer are **independent roles at the same level** —
the same person can hold both simultaneously.

## EditorInChief

Sees all collections regardless of status. Creates collections, assigns
them to Editors, reviews submitted work, publishes or rejects, and
manages bibliographies and permissions. The central coordinating role.

## Admin

Full access to everything, including user management, system
configuration, plugin activation, and the ability to unpublish a
collection. The only role that can delete collections or create new
user accounts (when public registration is off).
