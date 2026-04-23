# Facsimile images and zone editor

TEI supports linking transcriptions to the original manuscript images
at three levels of granularity: the whole page, a region on the page
(a zone), or even an individual word.

## Uploading images

In the TEI editor, open the **Media** panel (toolbar) and drag images
into the upload area. Supported formats: JPEG, PNG, and WebP. Images
are stored per-document; you do not need to re-upload the same image
across documents that reference it.

## Inserting an image inline

Place the cursor where you want the figure, click **Insert figure** in
the media panel, and pick the uploaded image. The editor inserts a
`<figure>` / `<graphic url="…"/>` pair pointing at the correct URL.

## Linking an image to a manuscript page

For a page-break facsimile, place the cursor where the page starts and
click **Insert page break** in the media panel. The editor inserts:

```xml
<pb facs="#f1" n="1"/>
```

plus a matching `<surface xml:id="f1">` with `<graphic url="…"/>` in the
document's `<facsimile>` section. The TEI renderers used by the public
website know how to display this as a clickable thumbnail next to the
transcription.

## Zone editor — linking text to image regions

The **Zones** button opens a full-screen editor where you can draw
rectangles on the image and link each rectangle to a word or a line in
the transcription.

Workflow:

1. Open the zone editor for a page that has a `<pb facs="#fN">` link.
2. Draw rectangles on the image by click-dragging.
3. Click an existing rectangle to select it.
4. In the transcription pane on the right, select the text that belongs
   to that zone.
5. Click **Link** — the editor inserts `<w facs="#zN">…</w>` (for word-level)
   or `<lb facs="#zN"/>` (for line-level) into the transcription.

Zones are saved as `<zone xml:id="zN" ulx="…" uly="…" lrx="…" lry="…"/>`
inside the matching `<surface>`. The public website renders zones as
hoverable highlight boxes in one-to-one viewing mode.
