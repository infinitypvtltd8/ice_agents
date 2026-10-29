# General queue and matching checks

All imported files are stored in the General queue (`REGULAR`). The former Irregular queue routing has been removed. Rulebook checks and source safety findings still run and are shown for review. Informational findings remain visible but do not have a hold or review-later workflow.

## Automatic sequence after import

1. Recognize each PDF, API XML, Scrapping XML and HTML, and associate files within their uploaded ZIP/folder. An uncertain choice stays in General with a source-selection prompt. A missing PDF cannot be parsed.
2. Schedule every unambiguous article immediately. Two local workers process independent articles; remaining jobs stay visibly queued. Extract native PDF lines, spans, words, coordinates and links to `extraction.json`. Use free local Tesseract OCR only if a page has too little usable native text or many replacement characters. A missing OCR program or weak OCR produces an explicit matching/review finding; no network or AI service is called.
3. Parse XML/HTML as structured text, including attribute values, into `source_feeder.json` and `source_feeder.md`. Write `normalized.md` from the PDF as a secondary search aid. The original files remain unchanged and the visual PDF remains authoritative.
4. Build `candidate_metadata.json` from the PDF and allowed support checks. Create author-to-original-affiliation links and author groups in PDF affiliation order; repeat a person in multiple groups without changing their global `seq`. Save the XML immediately as `current.xml`, then run matching checks on the same job. No operator click is needed to create the initial XML.
5. Save the current editable `metadata.json`, the field checks and reasons in `routing.json`, the XML and the audit in `job.json`. Saving metadata regenerates XML immediately unless the XML editor has a direct manual revision; in that case the old XML is preserved and marked stale until the operator explicitly regenerates it.

`READY` means initial extraction/XML/matching finished. An article in `QUEUED`, `PROCESSING` or `NEEDS_SOURCES` remains in General and displays its progress. A corrupt PDF may produce a processing error instead of XML; correct the source choice or input and retry.

## Matching checks and review findings

The rulebook (`config/rulebook.toml`) and safety checks produce findings but do not change queue placement. `docs/RULEBOOK.md` explains the checks. Findings can include:

| Check | Finding is shown when |
| --- | --- |
| Sources | The PDF, API, Scrapping or HTML file is missing, or a support file can't be read (`PKG-002`) |
| XML | The generated XML fails the sample-profile validation |
| Manual XML | The XML was edited by hand and not reconciled with the sources (`EDIT-008`) |
| Rulebook | `rulebook.toml` has an error (unknown rule or setting, wrong value type, broken syntax) |

The rulebook's rules follow the client's rule text: ID and version, title, abstract, authors, references, correspondence, affiliations and ORCID. Each finished article stores one card per rule that is on in `routing.json`, with evidence and the rulebook SHA-256. **Match & regenerate XML** reapplies checks, regenerates generated XML and retries failed imports.

Other extraction findings (OCR pages, mathematical layout, affiliation components that couldn't be separated, a keyword list that couldn't be split, and so on) stay on the article as informational issues. They do not affect queue placement or block export. There is no manual queue transfer. General is a storage queue and does not mean the rulebook found nothing, the XML is certified or the client XSD passed.

Support documents verify only their permitted fields. They never supply a missing normal affiliation or complete an incomplete PDF reference. A street number must remain an address part; an explicitly printed city/state/postcode is parsed separately. State codes are country-specific: `NSW` and `ACT` are Australian states, while `Kerala` in the supplied Indian sample stays an address part. Where this cannot be established from printed PDF wording, the matching findings explain the concern and the editor remains usable.

## Verified cases in this release

| Input | Queue | Rules that fire (checked against each PDF) |
| --- | --- | --- |
| `samples/regular_demo.zip` (explicitly synthetic) | General | None; 1 author, 1 affiliation, 3 references, all rules clear |
| `toolsamples/2408.09673` | General | `author_mismatch` (the PDF prints "Jasvith R." and "Sri K." where the API has full given names); `reference_hyperlinks` (reference 39 prints a GitHub address) |
| `toolsamples/2408.09700` | General | `reference_hyperlinks` (DOI and ADS links on all 89 references); `affiliation_non_english` ("Sorbonne Université, … Institut d’Astrophysique de Paris") |
| `toolsamples/2408.09763` | General | `reference_hyperlinks` (clickable DOI links on two references) |

The regression suite covers matching behavior (`tests/test_app.py`), tests each rule with a firing and a clean PDF (`tests/test_rulebook.py`), and asserts the samples' affiliation components, group relationships, support feeder and automatic XML generation. It cannot prove perfect extraction of every future layout. Review real PDFs visually; obtain representative correct final XML and the client XSD before claiming production accuracy or schema certification.

## Inspect or correct a job

On the Audit tab download PDF extraction JSON/MD, support feeder JSON/MD, current metadata and routing JSON. The original PDFs and support files are available in the source widgets. On Metadata, correct affiliation organization/address components and author links; inspect the generated author groups, references and XML. Save metadata to rebuild XML; informational findings are included in the audit and never block export. Back up `ICE_Local/data/` before installing a new folder so the prior jobs remain available.
