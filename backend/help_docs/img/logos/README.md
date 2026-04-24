# Extension logos

Drop service logos here to populate the placeholders in
`../../05-reference/02-extensions-catalog.md` and
`../../03-advanced/05-external-reference-lookups.md`.

## Expected filenames (one per plugin)

| File | Plugin | Source |
|---|---|---|
| `zenodo.png` | Zenodo Deposit | https://about.zenodo.org/ |
| `dataverse.png` | Dataverse Integration | https://dataverse.org/brand |
| `internet-archive.png` | Internet Archive | https://archive.org/about/brand |
| `codeberg.png` | Codeberg Integration | https://codeberg.org/Codeberg/logo |
| `github.png` | GitHub Integration | https://github.com/logos |
| `gitlab.png` | GitLab Integration | https://about.gitlab.com/press/press-kit/ |
| `wikidata.png` | Wikidata lookup | https://commons.wikimedia.org/wiki/File:Wikidata-logo-en.svg |
| `orcid.png` | ORCID lookup | https://orcid.org/about/brand |
| `ror.png` | ROR lookup | https://ror.org/about/ |
| `viaf.png` | VIAF lookup | https://viaf.org/ |
| `geonames.png` | GeoNames lookup | https://www.geonames.org/ |
| `gnd.png` | GND lookup | https://www.dnb.de/ |
| `cerl.png` | CERL Thesaurus | https://www.cerl.org/ |
| `peripleo.png` | Peripleo (Pelagios) | https://pelagios.org/ |
| `getty-aat.png` | Getty AAT | https://www.getty.edu/research/tools/vocabularies/ |
| `openalex.png` | OpenAlex | https://openalex.org/ |
| `trismegistos.png` | Trismegistos | https://www.trismegistos.org/ |
| `crossref.png` | CrossRef DOI | https://www.crossref.org/ |
| `zotero.png` | Zotero import | https://www.zotero.org/support/ |
| `evt.png` | EVT viewer | https://evt.labcd.unipi.it/ |
| `help.png` | In-app Help | — (use the Aracne2 mark) |

## Guidelines

- **Format**: PNG with transparent background; SVG also works if
  you prefer vector (the filename extension in the markdown
  placeholders is `.png`; change both sides if you switch).
- **Size**: recommended ~200×80px or similar, displayed inline
  at the natural CSS size inside the help page.
- **Licensing**: every service listed above publishes brand
  guidelines and downloadable logo assets — use those; don't
  screenshot or trace. Respect each service's attribution
  requirements if they apply.
- **Dark mode**: the help renders with the user's theme; use
  logos that have enough contrast on a light background (most
  service logos are designed exactly for this). Dark-mode
  variants are a future enhancement.

## Rendering pipeline

The Help plugin rewrites relative `<img src="img/logos/x.png">`
references to absolute `/api/v1/plugins/help/assets/img/logos/x.png`
URLs. After dropping a logo here, reload the help page
(or click Admin → Refresh at the top of the Help drawer) and the
placeholder is replaced by the real logo.
