# ICE Local — project instructions

Version: 1.3.0. This folder is the complete local citation extraction application, including the bundled 64-bit Windows Python runtime in `runtime/`. Read `QUEUE_DEFINITIONS_AND_VERIFICATION.md` for the matching checks and observed fixtures.

## Goal and boundary

Process an article package through deterministic PDF extraction, local OCR fallback where necessary, rule-based metadata parsing, support-document comparison, ANI-style XML generation, validation, and human review. Production processing must make **zero AI or LLM calls**. The PDF is the main source; API XML, Scrapping XML, and HTML supply specified verification values and exceptions. Keep the PDF and the coordinate-aware `extraction.json` as evidence. `normalized.md` is a secondary search representation.

The included `SOURCE_REQUIREMENTS.txt` is the supplied product brief. `docs/LATEST_RULES.txt` is the latest user-provided extraction and XML tagging guide and should be consulted as the current field-level rules supplement. `MASTER_RULE_ENGINE_SPECIFICATION.md` is the detailed numbered design catalogue. `config/specification_rules.json` is a machine-readable contract catalogue, **not a claim that every rule has an executable handler**. `RULES_IMPLEMENTATION.md` explains implemented checks and gaps. The runtime does not dynamically read prose documents; a rule is executable only where the implementation map says it is implemented.

All validation, identity mismatches, incomplete fields, and uncertain matches remain informational review notes. They never block metadata saves or XML generation/export.

## Start and inspect

- Windows: extract the entire ZIP, then double-click the outer `START_ICE.cmd` (or run `.\START_ICE.cmd` from PowerShell). It launches `ICE_Local\START_WINDOWS.cmd`. If you are already inside `ICE_Local`, run `.\START_WINDOWS.cmd`. The embedded Python runtime is included; keep the command window open. Do not run `npm install` or `npm start`: this is a bundled Python app, not a Node project.
- macOS/Linux development: install Python 3.12, `PyMuPDF` and `lxml`, then run `python app.py --port 8765` from the application folder. `START_MAC_LINUX.sh` provides a fallback launcher.
- Open `http://127.0.0.1:8765` in a browser. The workspace opens without login. The service binds only to loopback; other users on this computer can access it. Never serve it publicly without a separate security design.
- Click **Try sample files** for three research examples with 58, 89 and 45 references, plus one clearly labeled synthetic General example with 3 references. Import your own PDF and support documents or up to 50 ZIP packages in one browser selection.

The application writes `data/jobs/<id>/job.json`, original sources, `extraction.json` (PDF lines, spans and words with boxes), `normalized.md`, `source_feeder.json`/`.md` (structured XML/HTML values and text), `candidate_metadata.json`, current `metadata.json`, `routing.json`, `current.xml`, and revision snapshots. Back up `data/` before replacing or moving the application. The ZIP intentionally does not include user data.

## Processing order

1. `documents.py` recognizes content, expands nested ZIPs safely, associates each source to one package/article, and reports skipped or ambiguous files.
2. `engine.py` extracts PDF pages, lines, spans, words and bounding boxes; local Tesseract can be configured for scanned/garbled text. Native text is not duplicated when OCR replaces an unreliable layer. XML/HTML supports are parsed structurally into a feeder. The original PDF remains authoritative.
3. `engine.py` derives candidate metadata, affiliation components and author groups from original PDF evidence, including printed markers, explicit author-named affiliation statements, and clearly adjacent end-matter author/address blocks. It preserves uncertain candidates and issues instead of using correspondence/support data to manufacture missing original affiliations.
4. `engine.build_xml` creates XML automatically before a job becomes READY. `engine.validate_xml` checks well-formedness and sample-profile invariants. `triage.py` always keeps the file in **General** and records matching and safety findings for review. Official client XSD validation is **not run**, because no client XSD was supplied.
5. `app.py` persists edits, audit events, revisions, exports, and clear actions. The browser UI in `static/` shows PDF/source evidence and editable metadata.

## Review and delivery

Use the three support widgets beside the PDF; expand each inline, open it in the center, or use Large view. Compare pairs or all sources. The PDF viewer includes a readable capture-document mode; select text and assign it into metadata fields, including structured author and affiliation components. Highlighted matches show accepted metadata occurrences, but visual interpretation is still useful for superscripts, math, footnotes, authors and correspondence. Validation explains each matching check. Informational issues preserve findings and PDF evidence, but they do not block XML export. The top Dashboard can collapse to free vertical workspace; its black cards use orange counts. The file selector shows a numbered article and its metadata entry count.

Download selected articles as one ZIP with optional originals; each article is grouped by package with XML and audit. Reports & Analytics is a standalone `/reports.html` page, with independent `reports.css` and `reports.js`, General queue totals, package totals, metadata totals, filters and a file ledger. It contains no citation editor or import workspace. It exports CSV. “Export to folder” uses the browser's user-selected folder permission and can repeat for another destination; where unsupported, download the ZIP and extract it. Clear actions permanently remove selected/all finished job records and sources from the local data directory. Processing jobs are skipped until they finish.

## Project tree

| Path | Purpose |
| --- | --- |
| `app.py` | local HTTP API, state, imports, exports, audit, workflow |
| `documents.py` | ZIP/folder recognition and association |
| `engine.py` | PDF layout, parsing, evidence, XML, validation |
| `triage.py` | General queue placement and matching results: rulebook plus safety checks |
| `rulebook.py` | the routing rule checks |
| `config/rulebook.toml` | the matching rulebook, edited as text (see `docs/RULEBOOK.md`) |
| `static/` | citation workspace, standalone Reports page with its own CSS/JS, and supplied logo |
| `config/specification_rules.json` | design-level numbered rule contracts |
| `samples/toolsamples.zip` | three bundled regression examples |
| `samples/regular_demo.zip` | synthetic General-queue example; rebuild script alongside it |
| `docs/QUEUE_DEFINITIONS_AND_VERIFICATION.md` | routing contract, workflow and observed fixture results |
| `docs/RULEBOOK.md` | how to edit the routing rulebook and what each rule checks |
| `tests/` | integration and routing checks |
| `runtime/` | bundled Windows Python and dependencies |
| `data/` | local operator state, created on launch |
| `docs/` | source brief, specification, coding/user/handoff guides |

## Release checklist

Run `python -m unittest discover -s tests -v` and `node --check static/app.js`. Verify the actual ZIP extracts, its archive CRC (`ZipFile.testzip()`), the embedded Windows `lxml/etree` binary is intact, and the browser flow imports multiple ZIPs, shows a PDF page, edits metadata and downloads XML. Do not claim Windows execution testing until run on Windows. Update the preview image and release notes from a tested build. The review website is a **sample preview**, while this ZIP is the operational local app.

The metadata entry count sums populated article ID/version/title/abstract fields, individual keyword/author/affiliation/reference records, and populated author email/ORCID values. It measures captured items, not editorial correctness. The verified check count is displayed separately.
