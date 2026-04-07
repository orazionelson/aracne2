# cmschemas

Place your TEI P5 CodeMirror schema XML file here as:

    tei-p5.xml

The editor loads it from `/cmschemas/tei-p5.xml` at runtime.
If the file is missing, the editor works normally without autocomplete.

The schema XML must have the structure expected by `cm-tei-schema.js`
(original by Alfredo Cosco), i.e. a root `<cm_tei_schema>` element with
`<top>`, element entries with `<children>` and `<attrs>` subelements.
