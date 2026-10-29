# Infinity ACE — Project Overview

This document is a guided overview of the full repository: the local application, its processing pipeline, project structure, setup, operational workflow, development notes, and the detailed references maintained with the code.

## What this project is

Infinity ACE contains **ICE Local (Infinity Citation Engine)**, a local application for extracting and reviewing article metadata and references from research article packages. It reads a PDF together with supplied API XML, Scrapping XML and HTML documents, then produces editable metadata and ANI-style XML.

The application is a bundled Python HTTP server with a plain HTML/CSS/JavaScript browser interface. It runs on the user's computer and binds to `127.0.0.1`. Article processing is deterministic and makes no AI/LLM or cloud OCR calls. The PDF and its page-coordinate extraction are the primary evidence; support documents are used only for defined cross-checks.

**Version documented by the application docs:** 1.3.0.

## Main capabilities

- Import individual PDFs and support documents, folders, or up to 50 ZIP packages at a time. Nested ZIP files are supported.
- Identify source roles and associate documents with article packages; report ambiguous or skipped files so an operator can correct source selection.
- Extract PDF text, lines, spans, words, page numbers, bounding boxes and links. Optional locally installed Tesseract can OCR scanned or unreliable pages.
- Parse supplied XML and HTML into structured support-source records and searchable text.
- Derive candidate article IDs, titles, abstracts, keywords, authors, affiliations, correspondence details and references, retaining evidence and uncertainty for review.
- Keep additional affiliation candidates from page footers, marked blocks beyond the author area, and blocks after the references; operators can inspect the PDF evidence, link the affiliation to authors, or mark it as not original.
- Reconcile author initials and expanded names, surface conflicting middle names as identity candidates, and let operators choose the more complete name or add a separate PDF author and reorder the sequence.
- Capture numbered bottom-of-page footnote references when no main bibliography is detected; preserve incomplete references and flag possible multi-work or stealth references for review.
- Generate editable ANI-style XML, validate it against the available sample profile, and preserve manual XML revisions.
- Keep every file in the **General** queue and show explainable matching checks and review findings alongside it.
- Keep all files in General and retain validation, identity, extraction and matching findings as review notes. Findings never block metadata saves, XML generation or export.
- Track export status, audit events and revision history; the app has no blocking Hold workflow.
- Compare source documents with metadata and XML; edit article data and export XML, audit bundles, batch ZIPs, CSV reports, or selected-folder output where the browser supports it.

## Repository map

```text
infinity-ACE/
├── README.md                    # Top-level setup and product summary
├── READ_ME_FIRST.txt            # Short Windows quick start
├── START_ICE.cmd                # Windows launcher for ICE_Local
├── PROJECT_OVERVIEW.md          # This project-wide guide
├── LATEST_RULES.txt             # Latest user-provided field and XML-tagging rules
└── ICE_Local/
    ├── app.py                   # Local HTTP server, API, persistence, imports/exports
    ├── documents.py             # File classification, ZIP expansion and package association
    ├── engine.py                # PDF/source extraction, metadata, XML and validation
    ├── triage.py                # General queue and matching findings: rulebook + safety checks
    ├── rulebook.py              # The routing rule checks
    ├── static/                  # Browser UI and standalone reports page
    ├── config/                  # Routing rulebook, rule catalogue and XML profile
    ├── docs/                    # Product brief, specifications and operator/developer guides
    ├── samples/                 # Research examples and synthetic General-queue demo
    ├── tests/                   # Import, application, queue and affiliation regressions
    ├── tools/                   # Release and sample-generation utilities
    ├── runtime/                 # Bundled Windows Python 3.12 runtime and dependencies
    ├── requirements.txt         # PyMuPDF and lxml pins for non-bundled installs
    ├── START_WINDOWS.cmd        # Windows launcher when already inside ICE_Local
    └── START_MAC_LINUX.sh       # macOS/Linux launcher
```

`ICE_Local/data/` is created at runtime to hold local jobs and user files. It is git-ignored and should be backed up before moving or replacing the application.

## How processing works

1. **Import and package recognition.** `documents.py` examines uploaded files, ZIP contents and folders; recognizes PDFs and support documents; groups them by package/article identity; and records ambiguous or skipped inputs.
2. **Evidence extraction.** `engine.py` reads PDF layout with PyMuPDF. It records coordinate-aware evidence in `extraction.json`. If configured, local Tesseract is used when native text is insufficient or corrupted. Original documents are retained.
3. **Support parsing.** XML/HTML values and text are parsed into a source feeder. These sources verify permitted values; they do not fill missing original affiliations or complete incomplete PDF references.
4. **Metadata candidates.** The engine proposes metadata using the PDF as primary evidence, plus allowed support comparisons. It retains uncertain candidates and findings for human review instead of silently guessing.
5. **XML and routing.** Initial XML is generated automatically when extraction finishes. The validator checks well-formedness and the observed sample profile. `triage.py` applies the matching rulebook (`config/rulebook.toml`) and records findings; every article stays in General.
6. **Human review and delivery.** Operators compare sources, correct metadata, inspect informational findings and history/audit, then export XML. Findings do not block export.

The stored job files typically include `job.json`, original sources, `extraction.json`, `normalized.md`, `source_feeder.json` / `source_feeder.md`, `candidate_metadata.json`, `metadata.json`, `routing.json`, `current.xml`, audit records and revision snapshots.

### Queue meaning

General is the storage queue, not final editorial approval or proof of client-schema certification. Matching findings are informational review notes and never block XML generation or export. There are no Hold or Review Later workflow states.

The latest field and XML-tagging guide is [`LATEST_RULES.txt`](LATEST_RULES.txt), also copied to `ICE_Local/docs/LATEST_RULES.txt`. The deterministic matching rules are in `ICE_Local/config/rulebook.toml`; [`ICE_Local/docs/RULEBOOK.md`](ICE_Local/docs/RULEBOOK.md) explains them. The runtime implements selected deterministic rules; prose guides are not dynamically interpreted. Findings never block XML generation, saving or export.

## Start the application

### Windows

Use 64-bit Windows 10/11. The repository includes a portable Python 3.12 runtime, so Python installation is not normally needed.

1. Extract or clone the complete repository to a local folder.
2. From the repository root, double-click `START_ICE.cmd`, or run:

   ```powershell
   .\START_ICE.cmd
   ```

3. Keep the command window open while using the app. It opens at <http://127.0.0.1:8765>.
4. Choose **Try sample files** to explore the workflow, or import your article package.

If already in `ICE_Local`, run `.\START_WINDOWS.cmd`.

### macOS / Linux

Install Python 3.12 or newer. From `ICE_Local`, run:

```sh
./START_MAC_LINUX.sh
```

The fallback environment uses the pinned packages in `requirements.txt` (`PyMuPDF` and `lxml`) and may need internet access for first-time package installation. For direct development startup:

```sh
python app.py --port 8765 --no-browser
```

Open <http://127.0.0.1:8765> yourself. Do not run `npm install` or `npm start`; this project has no Node build or package step.

### OCR setup

Tesseract is optional and not included. Install it locally only if image-only or scanned PDFs need OCR, then point the application Settings to `tesseract.exe` if it is not detected. Without Tesseract, scanned pages remain available for review and are not sent to a cloud service.

## Using the app

1. Import a PDF and, when available, its API XML, Scrapping XML and HTML. Packages can be imported as ZIPs or folders; support files can also be selected directly.
2. Check the import report and assign any ambiguous source documents.
3. Select an article from the General queue and inspect the PDF alongside its support documents.
4. Compare extracted metadata with the visual PDF and permitted support evidence. Review author order, affiliation markers and groups, correspondence, mathematical notation, abstract boundaries, and reference completeness.
5. Resolve affiliation and author identity candidates, link them to the relevant authors, and adjust author order when needed. Queue transfers can be made from the open article and are recorded in History.
6. Edit metadata and save to regenerate XML. Direct edits in the XML editor are preserved as manual revisions and require review.
7. Inspect Validation and the Audit tab; use each issue's file number and PDF evidence link to review it, then approve the resolved item or document an override. Export valid XML or an explicitly acknowledged draft when appropriate.
8. Use Reports & Analytics for queue/workflow summaries, filters, per-file actions and CSV export.

The app saves its data locally under `ICE_Local/data/` by default. `ICE_DATA_DIR` can point it to a different data folder. Back up that folder before replacing the application.

## Application structure

| File or folder | Responsibility |
| --- | --- |
| `ICE_Local/app.py` | Local HTTP API, origin checks, job persistence, audit, workflow and exports |
| `ICE_Local/documents.py` | File classification, safe ZIP expansion, source role and package association |
| `ICE_Local/engine.py` | PDF/OCR layout extraction, support parsing, metadata candidates, XML generation and validation |
| `ICE_Local/triage.py` | Queue routing from the rulebook and safety checks, with human-readable reasons |
| `ICE_Local/rulebook.py` | One deterministic check per routing rule; loads and validates the rulebook |
| `ICE_Local/config/rulebook.toml` | The matching rulebook, edited as text |
| `ICE_Local/static/index.html`, `app.js`, `style.css` | Main import and citation-editing workspace |
| `ICE_Local/static/reports.html`, `reports.js`, `reports.css` | Standalone reports and analytics interface |
| `ICE_Local/config/specification_rules.json` | Machine-readable catalogue of numbered rule contracts and implementation status |
| `ICE_Local/config/xml_profile.json` | Observed XML profile used for generation/validation |
| `ICE_Local/samples/` | Bundled example packages; `regular_demo.zip` is explicitly synthetic |
| `ICE_Local/tests/` | Regression coverage for application behavior, imports, affiliations and routing |
| `ICE_Local/runtime/` | Bundled Windows Python runtime and packages |

The app uses Python's local HTTP server. Its browser interface is plain static web code without a frontend framework or compilation stage. It opens without login and is intended for local loopback access, not public hosting.

## Data, safety and project boundaries

- Processing is local and deterministic. There are no production LLM, telemetry, external bibliography enrichment or cloud OCR calls.
- Keep the original PDF and source files alongside extracted evidence. `normalized.md` is a search aid, not an authority over the visual PDF.
- Reference transcription should preserve what was printed, including incomplete references. Do not silently enrich from outside sources.
- Preserve audit events, revisions, source evidence, author global sequence numbers and informational review findings.
- The local server binds to loopback (`127.0.0.1`). Do not expose it publicly without a separate security design.
- The app has no account login. The loopback-only service and local origin checks keep requests on this computer; Python egress is blocked while it runs.
- Clear actions permanently remove local records and original sources for finished jobs. Export or back up needed data before clearing.
- The release does not include the official client/Elsevier XSD. The current XML check is a sample-profile/business check, not official schema certification.
- The 123-rule catalogue is a design specification, not a claim that all rules are implemented. Consult the implementation map before promising coverage.

## Development and verification

Read [`ICE_Local/AGENTS.md`](ICE_Local/AGENTS.md), then [`ICE_Local/docs/FOLLOWER_HANDOFF.md`](ICE_Local/docs/FOLLOWER_HANDOFF.md) and [`ICE_Local/docs/CODING_GUIDE.md`](ICE_Local/docs/CODING_GUIDE.md) before changing application code. Key development constraints:

- Keep runtime behavior deterministic and local; do not add AI SDKs, cloud OCR or reference-enrichment services.
- Capture source evidence and make state-changing actions auditable.
- Implement numbered rules with evidence, review behavior, tests and updated status; do not mark specification-only rules as implemented.
- Preserve manual XML edits, revision conflicts, author sequence and repeatable author/affiliation grouping.

From `ICE_Local`, the documented checks are:

```sh
python -m unittest discover -s tests -v
node --check static/app.js
```

Release verification also calls for checking the built ZIP/CRC, bundled Windows `lxml` binary, and an end-to-end browser flow for import, PDF display, metadata edit and XML download. A successful test suite does not prove perfect extraction on all article layouts or Windows execution unless that environment was actually tested.

## Documentation index

| Document | What it covers |
| --- | --- |
| [`README.md`](README.md) | Top-level purpose and installation quick start |
| [`LATEST_RULES.txt`](LATEST_RULES.txt) | Latest user-provided field, correspondence and XML-tagging rules |
| [`READ_ME_FIRST.txt`](READ_ME_FIRST.txt) | Short Windows quick start |
| [`ICE_Local/README.txt`](ICE_Local/README.txt) | Product features, workflow, privacy and troubleshooting |
| [`ICE_Local/docs/USER_GUIDE.md`](ICE_Local/docs/USER_GUIDE.md) | Operator tasks, source comparison, editing, review and export |
| [`ICE_Local/docs/PROJECT_INSTRUCTIONS.md`](ICE_Local/docs/PROJECT_INSTRUCTIONS.md) | Product boundary, processing sequence, tree and release checklist |
| [`ICE_Local/docs/CODING_GUIDE.md`](ICE_Local/docs/CODING_GUIDE.md) | Maintainer principles, architecture and test guidance |
| [`ICE_Local/docs/FOLLOWER_HANDOFF.md`](ICE_Local/docs/FOLLOWER_HANDOFF.md) | Handoff context for ongoing engineering work |
| [`ICE_Local/docs/MASTER_RULE_ENGINE_SPECIFICATION.md`](ICE_Local/docs/MASTER_RULE_ENGINE_SPECIFICATION.md) | Detailed numbered rule-engine specification |
| [`ICE_Local/docs/RULES_IMPLEMENTATION.md`](ICE_Local/docs/RULES_IMPLEMENTATION.md) | Implemented behavior, gaps and rule lifecycle |
| [`ICE_Local/docs/QUEUE_DEFINITIONS_AND_VERIFICATION.md`](ICE_Local/docs/QUEUE_DEFINITIONS_AND_VERIFICATION.md) | Routing contract and tested fixtures |
| [`ICE_Local/docs/RULEBOOK.md`](ICE_Local/docs/RULEBOOK.md) | How to edit the matching rulebook and what each rule checks |
| `ICE_Local/docs/SOURCE_REQUIREMENTS.txt` | Supplied product brief |
| `ICE_Local/DEPENDENCIES.txt` | Third-party dependency/license information |
