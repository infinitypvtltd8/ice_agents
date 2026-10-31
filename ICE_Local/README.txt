ICE LOCAL 1.4.6 - FULL CITATION EXTRACTION APP

START ON WINDOWS
1. Extract the whole ZIP to a normal folder such as C:\ICE-Local.
2. Double-click START_ICE.cmd in the outer extracted folder. It opens the
   bundled app inside ICE_Local. In PowerShell, run .\START_ICE.cmd.
   If you are already inside ICE_Local, run .\START_WINDOWS.cmd.
3. The app opens at http://127.0.0.1:8765 in your browser.
4. Keep the command window open while using the app.

This is a bundled Python application. Do not use npm install or npm start;
there is no package.json or Node installation step.

APP_PREVIEW.png and REPORTS_PREVIEW.png are included beside this README in
the extracted ICE_Local folder. Open them to see the workspace and analytics
screen before launching.

The Windows 64-bit ZIP includes Python 3.12.10 and the required libraries.
No Python installation or dependency download is needed for the included
Windows runtime. Citation processing is local and works without internet.
No login or internet connection is needed to use the local workspace. No LLM calls are used. START_WINDOWS.cmd launches the bundled
Python application. Tesseract OCR is optional and is not bundled.

FULL PROJECT DOCUMENTATION
See docs/PROJECT_INSTRUCTIONS.md, docs/CODING_GUIDE.md, docs/USER_GUIDE.md,
docs/RULES_IMPLEMENTATION.md, docs/QUEUE_DEFINITIONS_AND_VERIFICATION.md,
and docs/FOLLOWER_HANDOFF.md. The full supplied
requirements and numbered master rule specification are included in docs/.
The latest user-provided field and XML tagging rules are in
docs/LATEST_RULES.txt; correspondence cues are applied by the deterministic
metadata engine and remain reviewable without blocking XML export.
AGENTS.md gives short instructions to later coding agents. The supplied
Infinity Group logo is in static/logo.gif and displayed in the workspace.

NEW REVIEW CONTROLS
Import up to 50 ZIP packages per selection. The compact Dashboard includes a
numbered file selector, metadata count and author/reference counts. The dashboard folds away to give the PDF and editor more room; its cards are black with orange text. A fully separate Reports & Analytics screen tracks
all files, matching findings, package totals and exports. Findings do not block export. Select articles to download one ZIP with optional original
sources, or export XML/audit into a browser-selected folder (repeat for other
destinations). Clear one, selected or all finished articles after confirmation.
The three support widgets open inline, center or large, with source comparisons,
metadata highlighting and full-screen controls. The author-group editor,
reference source/full-text editor, rich inline tags, PDF right-click assignments
and XML tag tools are included. Review all generated content visually.

QUICK TEST
Click Try sample files. Three research packages and one explicitly synthetic
General example are included. Expected research reference totals:
2408.09673 = 58; 2408.09700 = 89; 2408.09763 = 45. The synthetic example has
three references. These are tests, not limits or hard-coded extraction totals.

YOUR FILES
Use Import multiple ZIPs to upload several ZIP packages at once. Each ZIP
gets its own heading and articles, even if another ZIP has the same article ID.
You can also import a folder or PDF/HTML/API XML/Scrapping XML files.
Files are matched by article IDs, document identity fields, or their article
folder. ZIP names are case-insensitive and nested ZIPs are supported. Folders
can also be dragged into the workspace. Each PDF is processed independently.
Support documents are optional for extraction; missing checks are saved as informational findings.
Duplicate or unfamiliar XML candidates can be assigned before processing.
Unique recognized files are already selected. Last import report shows every
file and explains skipped files. Keep each article package in its own folder
when filenames and document IDs do not identify the article.

AUTOMATIC QUEUES
Every imported article stays in the General queue. The matching rules in
config/rulebook.toml compare its metadata with source documents and show
findings for review; they do not move files between queues. Edit the rulebook
in a text editor; docs/RULEBOOK.md explains each check. Matching rules shows
the rules in force. Match & regenerate XML reapplies them to existing articles,
regenerates generated XML and retries failed imports. The Validation tab shows
each rule and the reason an article needs review. General is not final editorial
approval:
use informational findings (including address parsing, reference completeness and
delivery placeholders) to guide editing. Findings do not block export.
Import starts extraction automatically; the initial XML is created when the
job becomes READY. Pending jobs remain visibly marked as processing until
their evidence can be assessed. The matching checks and tested examples
are in docs/QUEUE_DEFINITIONS_AND_VERIFICATION.md.

WORKFLOW
Select an article. Three support document widgets are to the left of the PDF.
The editable metadata and Validation tab are to its right. The import area and
both source/metadata side panels slide closed; panel grips resize on desktop.
Review and edit metadata, affiliations, corresponding authors and references.
Right-click a PDF text line or a selected phrase to assign ID, title, abstract,
keyword, author, affiliation/address, email, corresponding author, corresponding
address link or reference. Assignments are recorded with PDF evidence in Metadata and regenerated into XML when saved. You can also edit and link authors/affiliations in the
Metadata panel.
Click PDF evidence links to jump to the source region. The PDF viewer supports
page navigation, zoom, search, a selectable text overlay and a readable Capture document mode. The original PDF
also opens directly using Open PDF. Use View PNG for a full-size image of the
current PDF page or Save PNG to download that page as a .png file.

Save metadata to regenerate XML. In XML editor you can edit the entire document,
save, find/replace, format and validate. Standard Ctrl+Z / Ctrl+Y work in the
editor. Saving direct XML creates a protected manual revision. Later metadata
changes do not overwrite it. Regenerate explicitly replaces direct edits after
confirmation. History offers restoration of saved revisions.

ISSUES AND EXPORT
Informational findings preserve source evidence and do not block export. Export XML or an XML + audit ZIP at any time. Malformed XML remains marked in the output manifest; delivery placeholders can still be edited in Metadata.

OCR
Native PDF text is used first. Image-only pages can use locally installed
Tesseract OCR. Set the tesseract.exe path in Settings if it is not detected.
Without Tesseract, scanned pages are held for manual review; there is no AI or
cloud fallback. This ZIP does not bundle Tesseract. Mixed-layout OCR and unusual
PDFs may need manual extraction/correction.
PDF line/span/word coordinates are saved in extraction.json, with normalized.md
as secondary text. Structured support fields and text are saved in
source_feeder.json and source_feeder.md. Metadata, queue checks and current XML
are mirrored to metadata.json, routing.json and current.xml in each job folder.

WHAT TO REVIEW
This first functional release uses conservative deterministic layout heuristics.
Review automatically separated affiliation/address components, mathematical
notation, unnumbered or heading-free reference boundaries and completeness.
Unknown author structures without API name components remain editable instead
of being guessed. Multi-work references can be split at the text cursor. There
is no external reference enrichment. The 123-rule specification catalogue is
design guidance; the routing rules in force are the ones in rulebook.toml.
Mathematical scripts are initially plain text and flagged for visual correction.
Rich title, abstract and reference full-text editors can generate supported sup/inf tags and formula placeholders when visually confirmed. The XML editor preserves direct manual changes.

SAVING AND PRIVACY
All jobs, original files, extraction snapshots, XML revisions and audits are
stored in the data folder beside the app. Keep that folder when moving/updating
the app, and back it up. The server listens only on your own computer.
The app opens directly without login and listens only on this computer. A local request token protects writes; cross-origin writes and external Python network connections are blocked. Saved HTML is sanitized and sandboxed. No telemetry or LLM service is included. The fallback setup script uses internet only if the bundled runtime is missing.

IF IT DOES NOT OPEN
Open http://127.0.0.1:8765 manually. Keep the command window open. If the port is
already in use, close the old ICE command window, or run:
  runtime\python.exe -X utf8 app.py --port 8766
Do not run the app from inside the ZIP; extract it first.

TESTING
Developer regression tests:
  python tests/test_app.py
  python tests/test_import.py
19 HTTP/extraction/import/queue regressions passed, including multiple ZIPs
with the same article ID, source-match routing, nested uppercase ZIPs,
renamed support documents and simulated Windows cp1252 default encoding.
Windows launcher is supplied; testing in this release was performed on Linux,
including real HTTP upload/processing/edit/export. The complete release ZIP
was extracted and tested in Chromium: browser ZIP upload, all three sample
reference totals, PDF rendering, metadata edits, reference review, XML
validation and XML download passed with no browser console/page errors. The
new source version was also browser tested with two ZIPs, distinct package
headings, sliders, validation and PDF right-click assignment.
The bundled Windows executable was not executed on Windows here.

DEPENDENCIES
PyMuPDF/MuPDF and lxml retain their own licenses. PyMuPDF is offered under AGPL
or commercial licensing; assess the applicable terms before redistributing
this app commercially. License text links and dependency metadata are included
in DEPENDENCIES.txt.
