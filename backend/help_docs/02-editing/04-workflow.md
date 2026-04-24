# Editorial workflow

Each collection moves through four states. Each transition is logged
and triggers a notification to the people involved.

```
Draft  →  Assigned  →  Review  →  Published
              ↑____________|
           (request revisions)
```

## Draft

The initial state. EditorInChief has created the collection but no
Editor has been assigned yet. Only EditorInChief and Admin can see
draft collections.

## Assigned

An Editor has been assigned and is actively working. The collection is
visible to that Editor (and to EiC+); the public cannot see it.

## Review

The Editor has declared their work complete and clicked **Submit for
review**. The EditorInChief receives a notification. They can now
read through, validate, and either publish or request revisions
(with a note explaining what needs fixing).

## Published

EditorInChief has approved the work. The collection becomes publicly
readable at `/browse/<slug>`. Published collections can still be
edited, but changes are visible to the public immediately — treat
published collections with care.

## Request revisions

If EditorInChief is not satisfied, they can click **Request
revisions** and attach a note explaining what needs fixing. The
collection returns to Assigned; the Editor receives a notification
containing the reviewer's note and gets to revise. This is a normal
part of the editorial back-and-forth, not a rejection of the work.

## Direct publish (EditorInChief+)

EditorInChief can skip the review step and publish straight from any
state. Useful for small corrections or for workflows where a single
person acts as both editor and editor-in-chief.

## Unpublish (Admin only)

Admin can take a published collection offline and send it back to
Assigned. Used to pull down something that was published by mistake or
that contains a legal issue. Not a routine operation.
