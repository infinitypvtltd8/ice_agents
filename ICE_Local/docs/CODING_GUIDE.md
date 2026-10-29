# Coding guide for maintainers

## Principles

- Runtime extraction is deterministic. Do not add LLM SDKs, agents, embeddings or cloud OCR to article processing. AI may help develop code, but generated code must still pass deterministic tests.
- The visual PDF and coordinate-aware extraction record are evidence. Never promote normalized Markdown, API XML, scraped data, HTML, or outside bibliographic services above the PDF without an explicit numbered rule and a review trail.
- Preserve incomplete references as printed. Split multiple works only when their boundaries are evidenced. Do not enrich a partial reference from the internet.
- Preserve original author global sequence numbers across repeated author groups. Current/former affiliations ordinarily do not replace original affiliations. Correspondence addresses must not fill missing ordinary-affiliation details.
- Retain source files, extracted evidence, issue state, audit history and snapshots. Changes to accepted metadata must be traceable.

## Local development

Use Python 3.12 with PyMuPDF and lxml. The static UI is plain HTML, CSS and JavaScript; it has no build step. `static/index.html` uses `app.js` for the citation workspace. The standalone `static/reports.html` uses `reports.css` and `reports.js`; it reads the same local API and does not load the editor shell. Keep the API summary and both views aligned. The dashboard fold state is stored in browser session storage. Run `python app.py --port 8765 --no-browser`, then open the loopback URL. Set `ICE_DATA_DIR` to a disposable directory for development tests. Do not put sample or user data in a release ZIP's `data/` folder.

`app.summary` calculates the metadata entry count from populated scalar fields and individual keywords, authors, affiliations, references, email and ORCID values. It is separate from the eight verification checks. `app.Handler` exposes the local API for session bootstrap, jobs, source evidence, history, upload, processing, clear, export, metadata, XML, validation, review and workflow. The app has no login; the server binds to loopback, validates write origins and requires its in-memory request token for state-changing requests. Audit every state-changing action and retain revision conflict checks.

`engine.build_xml` maps metadata to observed ANI/CE tags. It allows simple `<sup>`/`<inf>` in title, abstract and reference full text only when concatenated text exactly equals the plain field. Reference `source_text` preserves PDF transcription; `full_text` is editable XML display text. The XML editor also permits direct tags but marks the result manual and requires review. Unsupported profile tags need a sample, rule mapping, and validation before automatic generation.

`author_groups` may be omitted for affiliation-derived grouping or explicitly list `{author_ids:[...],affiliation_id:"..."}`. An author may occur in multiple groups; their `global_seq` is unchanged. Unlinked authors are still emitted. Changing groups or markup records source differences for review; the article remains in General.

## Rules and tests

`config/rulebook.toml` contains the matching rules and `rulebook.py` holds its checks; `docs/RULEBOOK.md` explains both and how to add a check. `triage.assess` records the findings from enabled checks and keeps the file in General. Keep every check deterministic, give it evidence, and add a firing and a clean case to `tests/test_rulebook.py`.

`config/specification_rules.json` is the design-level contract catalogue for extraction rules. Do not interpret `SPECIFIED_NOT_IMPLEMENTED` as a working rule. To implement a rule, add the handler in the appropriate stage, evidence capture, issue/review behavior, XML mapping where relevant, a meaningful test, and update its status and `RULES_IMPLEMENTATION.md`. Keep IDs stable. Favor tests involving actual extracted files and cross-source disagreements over tests that simply copy implementation logic.

The import worker writes `source_feeder.json`/`.md`, `candidate_metadata.json`, `metadata.json`, `routing.json` and `current.xml` beside the original sources and coordinate-aware PDF extraction. Keep these synchronized on edits, restores and regeneration; queue qualification occurs only after initial XML creation/validation. Use `QUEUE_DEFINITIONS_AND_VERIFICATION.md` as the routing contract.

Run:

```sh
python -m unittest discover -s tests -v
node --check static/app.js
```

The sample test expects 58, 89 and 45 references. An 82-reference synthetic boundary test detects truncation. Import tests cover 50 separate ZIP packages, nested/case-insensitive ZIPs, ambiguous XML, duplicate article IDs in distinct packages, traversal and Windows text encoding. Backend tests cover repeated author groups, inline markup, workflow states, multi-file export and clear.

## Known limits and work to do

- Official Elsevier/client XSD is not included. The XML validator checks an observed sample profile, not contractual schema compliance. Obtain the official XSD and representative final XML before claiming certification.
- Many rules in the supplied 123-rule catalogue remain design contracts. Unusual author/affiliation diagrams, math, formula reconstruction, OCR layouts, multi-work references and incomplete boundaries require operator review.
- Local Tesseract OCR is optional and is not bundled. No cloud fallback exists.
- The rule engine is a combination of deterministic handlers plus declarative catalogue, not a general interpreter for arbitrary JSON predicates.
- Batch export labels unresolved/held records REVIEW and malformed XML INVALID_DRAFT. A bulk download is a review artifact, not automatic client delivery approval.
- The Windows runtime is bundled; this development environment tested the archive and browser/API flows on Linux. Verify `runtime/python312.zip` as a nested ZIP and confirm `encodings/__init__.pyc` is present in each release. Run launcher smoke tests on Windows before a production rollout.

## Security and persistence

`documents.py` rejects ZIP traversal and unsafe symbolic links and caps expanded volume. `engine.secure_xml` disables dangerous XML parser features. HTML is sanitized and sandboxed. The app binds to `127.0.0.1`, checks write origins, and blocks Python socket egress while running. Browser fetching of remote resources is constrained by local CSP. This app has no login, so anyone using the same computer can access it; do not serve it publicly. Clear is destructive; the UI confirms it and the API skips running jobs. Back up `data/` before changes.
