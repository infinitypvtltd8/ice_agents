# Rule implementation and verification map

The latest user-provided extraction and XML tagging guide is `LATEST_RULES.txt`; consult it alongside `SOURCE_REQUIREMENTS.txt` and `MASTER_RULE_ENGINE_SPECIFICATION.md`. The JSON catalogue contains 123 numbered contracts. The program implements selected deterministic checks, but **does not implement all 123 contracts**, and prose files are not dynamically interpreted by the runtime. Runtime findings are review notes: ICE has no HOLD state, and findings do not block XML generation, metadata saving or export.

| Area | Current behavior | Evidence and review |
| --- | --- | --- |
| Import / identity | PDF required; ZIP/folder boundaries retained; file content, names and role fields associate documents; ambiguous XML needs explicit source selection | Import report, selected files, SHA-256 hashes and audit |
| PDF / OCR | Native PyMuPDF layout with page/line/span/word coordinates; optional local Tesseract replaces unreliable page text | Original PDF, `extraction.json`, normalized Markdown, OCR origin/word confidence and matching findings |
| ID, version, title | Parse PDF, cross-check Scrapping/API/HTML values as available; flag raised/lowered title spans for rich-text review | `source_values`, title span evidence, Validation reasons, issues |
| Authors and groups | PDF candidate parsing with API name/order checks; editable global sequence, repeatable group membership, correspondence links | author and email evidence, manual assignment audit and matching findings on edits |
| Correspondence | Apply the latest guide's single-author email/affiliation rule and multi-author author-side asterisk/envelope cues; ignore matching symbols explicitly used for equal contribution, fellowship or address history. Email/affiliation symbols alone do not assign a multi-author correspondence author. | `correspondence_basis` and PDF evidence on the author; generated `<correspondence>` entry. This deterministic pass does not infer from a marked email alone. |
| Affiliations | Detect numbered, lettered, and single unmarked original first-page address blocks by markers, organization terms and geometry; capture explicit author-named “is/are with” affiliations and end-matter address blocks placed beside named authors; retain wrapped lines; parse country-specific US/Canadian/Australian state patterns, streets, city and postal code; derive groups from printed markers or explicit author names; flag special/current-address and uncertain candidates | PDF lines and boxes, source text and AFF issues; support XML/HTML does not supply missing normal affiliations; ambiguous or unlinked source evidence remains visible for review |
| Abstract / keywords | PDF boundaries with support checks where present; capture a short keyword list on the line after its heading; editable rich content | PDF evidence; visible keyword headings without a safe list and math/layout flags route to review |
| References | Numbered candidate inventory, contiguous count, source/full text, split/edit, incomplete-entry review | Candidate count, excluded list, labels, first/last PDF boxes, REF issues |
| XML | Observed ANI/CE builder, author groups with stable global seq, `sup`/`inf`, direct XML editor | Deterministic build, preserved manual revisions, sample-profile validator; official XSD NOT_RUN |
| Routing | The rules in `config/rulebook.toml` (checks in `rulebook.py`) plus review notes for missing/unreadable sources, invalid XML, manual XML and rulebook errors. All files remain in General | One card per rule in `routing.json` with evidence and the rulebook hash; findings never block XML generation or export |
| Workflow / reports | CSV ledger, batch ZIP/folder export, single/bulk clear; no Hold, Review Later or Resume workflow | Audit event, package/file ledger, validation recorded as a note |

Keep reference source transcriptions faithful to the PDF. Do not enrich outside the supplied package. A green check means the rule found nothing, not that every visual nuance was understood. Review notes can coexist with XML output and export.

The initial XML is generated in the same automatic job that assigns the queue. Support XML/HTML text and attribute values are persisted in JSON/Markdown feeders; current metadata and XML have inspectable mirrors in each job directory. The demo now includes an explicitly synthetic General case alongside three complex research examples.

## Numbered rule lifecycle

1. Locate the ID in `config/specification_rules.json` and the full contract in `MASTER_RULE_ENGINE_SPECIFICATION.md`.
2. Define primary and secondary sources, precedence, exact failure severity, issue text, and coordinate evidence.
3. Implement a deterministic handler in the correct stage; keep unresolved cases in review, not guessed output.
4. Add a representative test with a positive and discrepancy case, ideally including source files and XML mapping.
5. Update the rule's implementation status only after end-to-end evidence is available. Record limits here.

No external schema was provided. Official XSD validation remains a separate integration task. The sample-profile checker must not be relabeled as an official pass.
