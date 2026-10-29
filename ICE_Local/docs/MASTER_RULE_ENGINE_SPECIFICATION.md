# Deterministic Citation Extractor and ANI XML Generator
# Rule Engine Specification v1.0

Prepared 29 September 2026, Asia/Colombo. Derived from the attached 46-section build brief, three complete source packages and twenty output XML examples. This is a development specification, not a finished application or an assurance of official Elsevier schema compliance.

## 1. Required outcome and boundary

AI may help write the application during development. Production citation processing must use **zero LLM/generative-AI calls, zero AI API credits and no cloud AI OCR**. The supplied brief explicitly permits local OCR when needed. A fixed local OCR recognizer is part of this allowed document-reading layer; it must not become a generative extraction fallback or an online service.

The processing path is: immutable PDF/support files → coordinate-aware native extraction or local OCR → evidence snapshot → deterministic rules and cross-document checks → canonical metadata → XML DOM builder → layered validation → human edit/review/export.

The original PDF is the visual authority. `extraction.json` is the reusable evidence bridge. Markdown/text is a searchable derivative with source mappings, not the authority for superscripts, columns, footnotes or authorship relationships. Processing a saved extraction snapshot through updated rules must not require repeated OCR.

**HOLD never permanently blocks generation.** Generate a full document preview from all successfully recovered metadata even while fields need review. Users can edit structured metadata, edit the entire XML, override individual HOLDs and deliberately export with unresolved HOLDs. Preserve all warnings and technical validation results. Do not claim a malformed draft or an acknowledged mismatch is a validated match.

“Full preview” means the complete document structure containing available data. It does not mean inventing missing values. Unsupported required fields have side-panel issues and selectable insertion locations; optional absent elements are omitted. Unrecoverable source regions remain visible in the review workspace.

## 2. Evidence and specification precedence

1. Explicit instructions in the attached brief establish required behavior.
2. Matching PDFs and support files establish source facts under the field-specific authority matrix.
3. The twenty output XMLs establish the observed output structure, subject to recorded contradictions with the brief/source.
4. Proposed implementation choices in this specification are labeled as such. They must not be disguised as client rules or formal XSD requirements.

The original detailed tagging guide mentioned in the brief is not included as a separate document in this upload. This specification derives from the supplied build brief and the actual samples, and records its unresolved dependencies. Do not invent additional rules from an absent rulebook.

The source packages are 2408.09673v1, 2408.09700v1 and 2408.09763v2. Their XML reference counts are 58, 89 and 45 and were independently counted in the PDFs. The other 17 XMLs have no matching source packages in this upload. All twenty XMLs parse, their refcounts match their reference nodes, and their reference sequences are contiguous. There are 974 reference elements total, all with empty `ref-info`. This is structural evidence, not proof that every sample field is correct.

## 3. Input adapters and exact observed selectors

| Source | Observed content and selector | Adapter requirement |
|---|---|---|
| PDF | First-page rotated arXiv stamp, multi-column text, positioned markers and linked notes | Preserve rotation, page/region identity, text direction and local coordinates. |
| API XML | `/record/metadata/arXiv/id`; `/record/metadata/arXiv/authors/author/forenames` and `keyname` | The supplied API XML elements are unqualified, despite an `xsi:schemaLocation` attribute. Do not assume a default arXiv namespace from that attribute. Preserve author document order. |
| Scrapping XML | `/ARXIV/item/@id`; `/ARXIV/version/@number` values `[v1]` or `[v2]` | Normalize brackets only as syntax. Record `submit_date` separately; it is not proven to represent the current version date. |
| HTML | `meta[name="citation_title"]/@content`; `meta[name="citation_arxiv_id"]/@content`; current-version `span.arxivid`, `td.arxividv` and dateline text | Parse the saved HTML locally. Submission history can contain several versions; choose the explicitly viewed/current version, not the maximum number indiscriminately. |
| Expected output XML | Default ANI namespace and ce common namespace | Development/test input only. Never an extraction source during production. |

Support future XML dialects using explicitly versioned adapters selected by root/namespace. A broad local-name query over an unrecognized document must not accidentally accept unrelated fields. Disable external XML resolution. Render HTML in a sandbox with scripts and remote resources disabled while preserving its raw source view.

Package matching uses both filename and content identity. Folders such as `2408.09673n` use an incidental suffix; `n` is not part of the article ID. Missing support files produce visible review issues and NOT_RUN dependent checks. Missing PDF prevents PDF extraction but does not destroy an existing saved draft. Do not silently choose between two PDFs or two versions.

## 4. Field authority matrix

| Field | Primary authority | Allowed verification/derivation | Mismatch or missing evidence |
|---|---|---|---|
| Base ID and version | PDF stamp | Scrapping ID/version and HTML current ID/version; API base ID for package consistency only | HOLD; preserve candidates; missing version is never assumed v1. |
| Title | PDF | HTML textual comparison with approved presentation normalization | HOLD for actual textual difference; dash policy C02 remains explicit. |
| Abstract | PDF only | Layout reconstruction and approved rich-text serialization | HOLD for unclear text/math; do not repair from API/HTML. |
| Keywords | PDF only | Label and delimiter rules | Leave genuinely absent keywords absent; ambiguous boundary HOLD. |
| Author occurrence/order | PDF | Ordered API identity verification | HOLD on missing/extra/reordered authors. |
| Given name / surname | Matched API author components | Identity linked to original PDF name; deterministic initials | Preserve source abbreviations if no permitted expansion; ambiguity HOLD. |
| Normal affiliation and mapping | PDF only | Marker graph, explicit layout relationships and permitted component composition | No API/HTML completion; ambiguous edges HOLD. |
| City/state/postal/country | PDF wording | Versioned country/state dictionaries under explicit project rules | Never invent missing geographic information. |
| Email, ORCID | PDF text or PDF links only | Source-based reconstruction; syntax validation | One selected email per author; ambiguous association HOLD. |
| Correspondence | PDF only | Exact single-/multi-author decision rules | Symbols without resolved author-level meaning do not set correspondence. |
| References | PDF main/supplement/eligible footnotes only | Segmentation, explicit exclusions and evidenced splits | Keep incomplete citations; no external enrichment or hidden truncation. |
| Envelope IDs/constants | Delivery profile | Configured values separate from article metadata | Observed placeholders require profile resolution/acceptance; preview stays available. |
| Timestamp | Frozen export/run event | Explicit UTC event input | Do not copy sample timestamps or confuse them with publication dates. |

## 5. Data architecture

Persist original input bytes and hashes; `extraction.json`; searchable `normalized.md`; `metadata.json`; versioned issue/decision records; XML revisions; and export/audit events. A local relational database stores package state and revisions; source bytes and extraction artifacts use an article-scoped filesystem directory. Author/affiliation/reference stable IDs must survive edits; sequence numbers are derived display/output fields.

The full model is in `model/data_contract.json`. The important separation is:

- Source evidence: raw spans and original values, immutable.
- Normalized candidates: transformations with explicit rule and evidence IDs.
- Accepted metadata: current selected values plus human edits.
- XML revision: generated or directly edited, linked to a specific metadata revision.
- Validation snapshot: applies only to an exact XML hash/revision.
- Audit: append-only history of actions, decisions, overrides and exports.

Coordinates use page points with a top-left origin in the normalized extraction view. Retain crop-box/rotation matrices for original PDF coordinates. Internal page index is zero-based; displayed page number is one-based. A multi-page field has a list of evidence regions, not one misleading bounding box. A PDF link retains its annotation region and literal URI. HTML/XML evidence records a document ID and selector/XPath instead of a PDF box.

`extraction.json` must record document hash, extractor versions, OCR model hash, per-page dimensions, text direction, blocks, lines, spans/words, font flags, scripts, links, column regions, raw text, native/OCR origin, and normalization trace. Cache invalidation depends on input hash and extraction settings. Rule or template changes invalidate decisions/XML, not necessarily extraction.

## 6. Deterministic rule orchestration

This pack defines **123 numbered rules** in `rules/rule_catalog.json`. These are implementation contracts, not prebuilt executable parsers. Each names a fixed handler with a documented input/output contract. Implement handlers as deterministic functions; JSON supplies parameters and dictionaries. Do not use eval or let arbitrary rule text execute code.

Stages run in a fixed dependency order: ingestion → extraction → identity and base metadata → authors → affiliation graph → contacts/correspondence → references → XML → validation → review/export. Within a stage use priority and rule ID. Independent articles may process concurrently. Conflicting writes to one field emit an issue; do not rely on last-write-wins ordering.

Every handler returns PASS, FAIL, NOT_APPLICABLE or NOT_RUN; any issue separately has severity WARN, HOLD or ERROR. A field can be EXACT, NORMALIZED_EXACT, RULE_RESOLVED, AMBIGUOUS, MISSING or MANUAL. These are deterministic categories, not invented percentage confidence scores. The UI may show MATCH, MISMATCH and OVERRIDDEN_BY_RULE as derived labels while keeping verification and human approval separate.

Rules include basis references to brief section numbers, observed sample IDs or explicit design choices. Retain `rule_bundle_hash`, dictionary/template hashes and as-of date in each run. Year-dependent logic uses that date so a rerun is explainable. Random IDs and audit clock values are excluded from semantic repeatability; XML timestamp is an explicit frozen input when testing byte repeatability.

## 7. Extraction algorithms

### 7.1 Layout and OCR

Read native text, spans, direction and annotations first. Assess usable text by region: missing glyphs, replacement characters, image coverage and text-layer density are signals, not a single page-character threshold. Images in a normal paper do not automatically mean OCR is needed. OCR only deficient regions with a bundled local engine, preserve OCR confidence as OCR metadata, and retain low-quality regions for review.

Segment spanning title/author/abstract areas separately from columns. Within each column order blocks and lines; handle continuations at column/page boundaries. Detect rotated arXiv stamps separately so they do not contaminate abstracts. Exclude running heads and page numbers from article text only through repeatable positional evidence. Store them in the evidence layer even when excluded from a metadata field.

Recover line-wrap spaces and split accent glyphs using glyph positions. Preserve source hyphens unless clearly introduced by line wrapping. A normalization log stores both forms and the reason. Generic ASCII folding, punctuation deletion, OCR over reliable text, or flattened whole-page sorting can destroy scientific content and must not be used as a blanket fix.

### 7.2 Authors and affiliation graph

1. Segment PDF author spans and author-attached markers in reading order; create canonical authors A1..An.
2. Parse API ordered names. Match using exact components or evidence-compatible initials, with no surname-only automatic merge when ambiguous.
3. Verify identities and order. Expand given names only when the matched API explicitly supplies them; retain displayed PDF form separately.
4. Segment normal and special-address affiliation candidates. Decode markers into edges between author IDs and affiliation IDs; include evidence for both ends.
5. Apply original/current-address and composition rules. Do not merge a correspondence-only address into normal affiliations.
6. For each affiliation in source order, serialize its linked authors sorted by original global sequence, followed by that affiliation. Repeat author identities for multiple affiliations while keeping global seq unchanged.
7. Keep authors without a known affiliation. An affiliation-free group is observed in 2408.14658, but its source is absent; use this as an explicit draft policy with review when the missing relationship is unresolved.

Count canonical authors, not serialized occurrences. For 2408.09673 the correct observed grouping is `[1,3,4,5]`, `[1]`, `[2]`: five people and six occurrences. For 2408.09700, Clayton repeats as seq 3. Prevent duplicated or conflicting author identities inside a group while allowing repetition across distinct groups.

State dictionaries must be country-specific. The brief's two-letter wording cannot be implemented as a global length constraint: the supplied Australian affiliations use NSW and ACT. India/Kerala in 2408.09763 demonstrates an address-part rather than state. `ce` is a namespace prefix in the examples, not a separate affiliation component named ce.

### 7.3 Correspondence decision table

| Situation | Decision |
|---|---|
| One canonical author with email and/or affiliation | Corresponding under the written project rule. |
| One author with neither and no explicit correspondence text | Not corresponding; unexplained marker alone does not change this. |
| Explicit correspondence text linked to an author | Corresponding, including an author without other contact fields. |
| Multiple authors; author-attached marker clearly means correspondence | Corresponding. |
| Marker explicitly means equal contribution/current address/other purpose | Not corresponding on that evidence. |
| Star belongs only to email or affiliation | Not corresponding on that evidence. |
| Marker meaning or identity association unresolved | HOLD, retain evidence, human decision available. |

### 7.4 References and completeness

Reference discovery must use two independently inspectable paths: a segmentation path that emits candidates and a coverage path that inventories section regions, labels/entry starts and unassigned spans. If both counts come from the same truncated output array, they do not protect against missing references.

Find all candidate reference sections, including a heading-free list as in 2408.09763. A references heading halfway down the left column does not mean the right column starts at that same y coordinate: 2408.09700's bibliography continues from the bottom left to the top right. Exclude pre-bibliography prose, running heads and end-of-article typesetting notices by region.

For numbered entries, start only on labels aligned with the reference-start margin, then consume continuation text across pages/columns. For unnumbered entries, combine recurring start indentation, bibliographic author/year form and layout; never treat every physical line as one citation. In 2408.09700 the independent inspection found 39 starts in the left reference column and 50 in the right, yielding 89.

For a multi-work entry, split only with a supported bibliographic boundary. Keep `candidate_id`, `original_label`, split-part index and exact source spans for every part. If splitting is ambiguous but the entry boundary is clear, retain the whole source entry as one provisional draft reference and add HOLD. Never silently delete it or complete it using outside data.

Maintain a disjoint candidate ledger:

- C: discovered source entries.
- A: entries included in the draft/output, including clearly bounded unsplit entries that still carry review issues.
- X: explicitly excluded entries with a rule and reason.
- U: candidates not yet sufficiently bounded/readable to include; their source evidence remains in review.
- R: actual emitted references after splitting.
- S: additional parts created by splits, so S = sum(k - 1) over included entries.

Require **C = A + X + U**, **R = sum(k over A) = A + S**, and **XML refcount = number of actual reference elements = R**. Open HOLDs are a separate issue count and may overlap included entries. A fully reconciled source inventory has U=0, explicit treatment of every source region and no unexplained label gaps. It may legitimately have R different from C after splits or exclusions.

The UI shows source entries, emitted references, extra split parts, excluded entries, unresolved candidates, issue count and unassigned source regions. “82 detected / 31 emitted” is a coverage failure unless every difference is explicitly explained. Numbering can restart, be nonnumeric or skip in the original, so neither maximum label nor DOM count alone is proof of completeness. Preserve duplicates until reviewed.

Incomplete references remain incomplete. A cited work before 1970 remains a valid reference; the article-date applicability rule must not filter individual citation years. Supplementary lists and footnote-only cases are preserved under the stated inclusion rules with HOLD where required.

## 8. Exact observed XML profile

The default output namespace is `http://www.elsevier.com/xml/ani/ani`; `ce` is `http://www.elsevier.com/xml/ani/common`. These are the supplied namespace URIs, not generic JATS. `xml:lang` belongs to `http://www.w3.org/XML/1998/namespace`. Namespace declarations in input schemaLocation are never fetched automatically.

The root hierarchy is `units / unit / unit-content / bibrecord`, with `unit-info` beside `unit-content`. Inside bibrecord, `item-info`, `head` and `tail` are siblings. Bibliography belongs under `tail`. Head child order is citation-info, citation-title, author-group(s), correspondence(s), abstracts, source. The full observed path inventory and child order are in `xml/xml_profile.json`.

XPath aliases below: `a` is the ANI namespace; `B=/a:units/a:unit/a:unit-content/a:bibrecord`; `H=B/a:head`; `F` is a normal or correspondence affiliation; `R=B/a:tail/a:bibliography/a:reference`. Presence rules describe the sample profile and proposed draft handling, not a supplied XSD.

| XML path | Internal data | Authority or derivation | Presence | Rule |
|---|---|---|---|---|
| `/a:units` | `document wrapper` | template | one per exported file | `XML-001` |
| `/a:units/a:unit/@type` | `profile.unit_type` | configurable constant ARTICLE | one in each sample | `XML-004` |
| `/a:units/a:unit/a:unit-info/a:unit-id` | `delivery.unit_id` | run/delivery profile; samples use 1 | one | `XML-004` |
| `/a:units/a:unit/a:unit-info/a:order-id` | `delivery.order_id` | profile; observed unknown is unconfirmed | one | `XML-005` |
| `/a:units/a:unit/a:unit-info/a:parcel-id` | `delivery.parcel_id` | profile; observed none is unconfirmed | one | `XML-005` |
| `/a:units/a:unit/a:unit-info/a:supplier-id` | `delivery.supplier_id` | profile; observed 4, not a universal constant | one | `XML-004` |
| `/a:units/a:unit/a:unit-info/a:timestamp` | `run_context.export_timestamp_utc` | explicit dynamic run input, frozen per export revision | one | `XML-004` |
| `B/a:item-info/a:status/@state` | `profile.item_state` | configurable constant new | one | `XML-004` |
| `B/a:item-info/a:itemidlist/a:itemid[@idtype="ARXIV"]` | `article.base_id + v + article.version` | PDF, verified by Scrapping and HTML | one | `ID-005` |
| `H/a:citation-info/a:citation-type/@code` | `profile.citation_type` | configurable constant ar | one | `XML-004` |
| `H/a:citation-info/a:citation-language/@xml:lang` | `article.language` | explicit language profile; all samples ENG | one | `XML-004` |
| `H/a:citation-info/a:abstract-language/@xml:lang` | `abstract.language` | explicit language profile; all samples ENG | one in samples | `XML-004` |
| `H/a:citation-info/a:author-keywords/a:author-keyword` | `article.keywords[]` | PDF only; omit container if absent | one per keyword when present | `KEY-001` |
| `H/a:citation-title/a:titletext` | `article.title.rich_text` | PDF, HTML verification; original=y and xml:lang=ENG in samples | one | `TITLE-001` |
| `H/a:author-group/@seq` | `derived group position` | PDF affiliation order; 1-based contiguous | one per group | `AFF-016` |
| `H/a:author-group/a:author/@seq` | `author.global_seq` | global PDF sequence, not group-local position | one per membership occurrence | `AUTHOR-008` |
| `H/a:author-group/a:author/@orcid` | `author.orcid.selected` | PDF visible value or PDF hyperlink | optional attribute | `ORCID-002` |
| `H/a:author-group/a:author/ce:initials` | `author.initials` | deterministic derivation from accepted name | one per author in samples | `AUTHOR-005` |
| `H/a:author-group/a:author/ce:surname` | `author.surname` | matched API keyname; reviewed PDF fallback | one per author in samples | `AUTHOR-004` |
| `H/a:author-group/a:author/ce:given-name` | `author.given_name` | matched API forenames; omit if absent | optional; absent in 6 occurrences | `AUTHOR-004` |
| `H/a:author-group/a:author/ce:e-address` | `author.email.selected` | PDF only | zero or one per occurrence | `EMAIL-001` |
| `F/a:organization` | `affiliation.organizations[]` | ordered PDF components | zero or more | `AFF-007` |
| `F/a:address-part` | `affiliation.address_parts[]` | PDF components including non-state subdivisions | zero or more | `AFF-010` |
| `F/a:city` | `affiliation.city` | PDF only | optional | `AFF-008` |
| `F/a:state` | `affiliation.state` | PDF with country-specific dictionary | optional | `AFF-009` |
| `F/a:postal-code` | `affiliation.postal_code` | PDF; string preserves leading zeros | optional | `AFF-007` |
| `F/a:country/@iso-code` | `affiliation.country_code` | approved mapping of source-supplied wording | optional; sample country elements have no text | `AFF-011` |
| `F/ce:source-text` | `affiliation.source_text` | complete PDF affiliation text, without marker; wording retained | one for every emitted affiliation | `AFF-007` |
| `H/a:correspondence/a:person/ce:initials` | `corresponding_author.initials` | same canonical identity as authors | one per person in samples | `CORR-006` |
| `H/a:correspondence/a:person/ce:surname` | `corresponding_author.surname` | same canonical identity as authors | one per person in samples | `CORR-006` |
| `H/a:correspondence/a:person/ce:given-name` | `corresponding_author.given_name` | same canonical identity as authors | optional | `CORR-006` |
| `H/a:correspondence/a:affiliation` | `correspondence.affiliation` | PDF-evidenced correspondence address or identified normal affiliation | optional by design; one in each supplied correspondence | `CORR-006` |
| `H/a:correspondence/ce:e-address` | `correspondence.email` | selected PDF email for that author | optional by design; one in each supplied correspondence | `CORR-006` |
| `H/a:abstracts/a:abstract` | `article.abstract` | original=y and xml:lang=ENG in samples | one in all samples; omissions require review | `ABS-001` |
| `H/a:abstracts/a:abstract/ce:para` | `article.abstract.rich_text` | PDF only; ordered paragraph content | one in samples; multi-paragraph policy needs profile extension | `ABS-001` |
| `H/a:source/@srcid` | `delivery.source_id` | profile; observed ??? is unconfirmed | one | `XML-005` |
| `B/a:tail/a:bibliography/@refcount` | `count of emitted reference nodes` | derived from final XML DOM | one | `REF-017` |
| `R/@seq` | `reference.output_seq` | contiguous source-order sequence | one per reference | `REF-016` |
| `R/a:ref-info` | `sample-profile empty element` | all 974 examples are empty; no inferred subfields | one per reference | `XML-006` |
| `R/a:ref-fulltext` | `reference.export_rich_text` | PDF source text with detected leading label removed | one per reference | `REF-007` |
| `R/ce:source-text` | `reference.export_plain_text` | same work and source evidence; plain text representation | one per reference | `REF-007` |
| `rich text a:sup / a:inf` | `rich_text script segments` | PDF evidence and approved inline mapping; ANI namespace | observed sup and inf only; not a formula schema | `XML-008` |

Build with a namespace-aware XML DOM and encode once as UTF-8. Preserve mixed text/tail content; pretty printing must not inject spaces into mathematical expressions. `sup` and `inf` inherit ANI in the samples; do not replace inf with sub because a generic HTML library does so. An unresolved mathematical mapping remains a review item instead of an invented structure.

Country elements in the examples are empty with an iso-code attribute; country wording survives in affiliation source-text. ORCID is an unqualified attribute on author. Email is ce:e-address. Keywords sit inside citation-info/author-keywords. No DOI, EGI/IPUI, license, audit or HOLD extension is added by default merely because a support document contains that information.

The supplied references contain empty ref-info plus ref-fulltext and ce:source-text. The application must not claim to extract structured reference authors, journal/volume/pages or DOI into schema elements whose mapping has not been supplied. Such a richer profile is a separately specified extension.

Constants observed across examples include ARTICLE, new, ar, ENG and original=y. Values such as supplier-id 4, order-id unknown, parcel-id none and srcid ??? are observed delivery-profile candidates, not verified universal requirements. Provide a sample compatibility profile and an explicit production profile; unconfirmed values generate review issues. Do not make up missing IDs or use a sample timestamp in production.

## 9. Editing, overrides and export

Keep processing state, review state, XML state, validation state and export state independently. A record may simultaneously be EXTRACTED, ON_HOLD, XML_GENERATED and NOT_EXPORTED. Editing does not trigger a full restart.

Each HOLD has Edit data, View evidence, Accept extracted value, Override HOLD and Keep HOLD actions. An authorized operator can also select Generate XML with HOLDs or Export XML with HOLDs. Reasons are optional under the attached brief unless an explicitly chosen workflow makes them mandatory. Record actor, timestamp, original issue/value, accepted value, rule version and evidence fingerprint regardless.

An override changes review disposition; it does not rewrite history or change MISMATCH into MATCH. Changed source bytes, rules or accepted values invalidate dependent overrides. Re-run only affected rules and refresh the issue view. Preserve prior decisions in audit.

Support structured metadata edits and unrestricted full-document XML editing. A directly edited buffer gets its own XML revision and the label MANUALLY MODIFIED. A later form edit marks this XML stale; it must not replace the buffer. Provide Keep manual XML and Regenerate from metadata; regeneration requires the warning that it replaces direct changes, an explicit confirmation and a retained prior revision. Do not promise automatic round-trip import of arbitrary XML into metadata. Unmapped manual nodes remain visible as manual/unmapped.

Validate the exact selected revision before export. Normal delivery export follows the chosen profile's technical gates and resolved/overridden review items. Export with HOLDs shows the unresolved list and records acknowledgement, then preserves EXPORTED_WITH_HOLDS and an audit sidecar. If XML is malformed, the user can still save/download the edit buffer as an invalid draft; it must not carry a validated-delivery label. This preserves human control without falsifying technical correctness.

## 10. Validation layers

| Layer | Required checks | Honest status boundary |
|---|---|---|
| XML parsing | UTF-8 declaration, well-formedness, namespace parsing, valid characters, escaped values | Parser success is not source correctness. |
| Observed sample profile | Qualified paths, ordering, known attributes, required observed structure and mapping | Not equivalent to official XSD validation. |
| Business rules | Unique global authors, graph integrity, one selected email, ORCID format, source text, sequences and coverage ledger | An overridden review issue stays recorded. |
| Cross-source verification | PDF/Scrapping/HTML identity; PDF/HTML title; PDF/API authors and order | Missing source/check is NOT_RUN, not PASS. |
| Client XSD | Local, pinned schema and dependencies when supplied | Currently NOT_RUN because none was supplied; never auto-fetch a remote schema. |

Show line/column navigation from the exact XML buffer revision. After formatting/editing, revalidate before using old positions. Tie known nodes to metadata/evidence where possible. Validate refcount after direct edits and export; never silently change manual XML to hide errors.

## 11. Workspace and screens

| Screen | Required behavior |
|---|---|
| Dashboard | New/previous batches; counts by processing and review/export states; resume saved work. |
| Upload/package review | Individual/multi-file/folder/ZIP upload; file-role and identity matching; missing/ambiguous source visibility. |
| Extraction | Per-article/page progress, native/OCR origin and failures; other batch jobs continue. |
| Document workspace | Left source list; central viewer; right metadata/rules; lower or separate full XML editor. |
| Source viewers | PDF page/zoom/search/select/highlights; HTML rendered and raw; API/Scrapping formatted tree and raw; all supplied files accessible. |
| Compare/review | FIELD, PDF VALUE, API VALUE, SCRAPPING VALUE, HTML VALUE, FINAL VALUE, SOURCE USED, RULE, STATUS, EDIT. Expand authors, graph edges and individual references. |
| Flags | Filter severity/rule/field; jump to evidence; edit, accept, override or keep HOLD. |
| XML | Entire document, syntax coloring, line numbers, find/replace, undo/redo, format, validation, exact error navigation, save and export. |
| Rules/settings | Rule viewer; administrator rule/parameter editor; dictionaries; profile/version selection; measured network diagnostics. |
| Export | Single XML or batch ZIP; audit JSON/CSV; optional extraction JSON/MD; visible unresolved/overridden issues. |

Support side-by-side PDF with HTML/API/Scrapping/generated XML. Clicking any final value or reference navigates to its source region; clicking a known XML node selects the associated field. For a split reference, show one source entry linked to multiple output sequences.

## 12. Implementation architecture and project layout

Use the local-first technologies already permitted in the brief: a TypeScript browser UI, a local Python document-processing service, a local database and article-scoped files. Keep extraction behind interfaces so native PDF/OCR library choices can be pinned and license-reviewed during implementation. No library versions or current pricing are asserted by this specification. A Windows launcher is an implementation deliverable if packaged for the user's local workflow; the same service boundary can later support a managed multi-user deployment.

| Project area | Responsibility |
|---|---|
| apps/ui | Upload, viewers, review table, full XML editor, rules, batch dashboard. |
| services/processor | Queue, revisions, source adapters, extraction and local worker boundary. |
| engine/evidence | Layout/OCR snapshots, coordinate transforms, normalized text and source mapping. |
| engine/rules | Fixed deterministic handlers, dependency graph and decision records. |
| config/rules; config/dictionaries | Versioned parameters, source authority and country/state mappings. |
| config/xml_profiles; engine/xml | Qualified field mapping, builder, observed-profile checks and optional supplied schema. |
| storage | SQLite/local filesystem adapters; future server database adapter without changing evidence semantics. |
| tests/fixtures | Immutable source packages, observed expected XMLs and separately approved corrected expectations. |
| tests/acceptance | Source completeness, edit/override protection, offline enforcement and batch tests. |

Queue articles independently with bounded concurrency and persisted checkpoints. Test 1, 5 and 25 packages. No silent first-N page/reference processing. Resource limits must leave a visible error and saved partial work. Do not guarantee under-one-minute processing for arbitrary scanned PDFs; measure native and OCR workloads on declared hardware and report duration, pages and OCR share.

Build the evidence model and issue engine with the first ingestion stages, not as a late UI patch. Implement in increments: package/viewers and revisions; extraction/cache; identity/metadata verification; author-affiliation graph; contacts; references/coverage; XML/validation; full editing and HOLD export; batch/resume and offline acceptance tests. Every increment has real data and visible unresolved cases rather than mock success states.

## 13. Conflicts, gaps and safe development behavior

| ID | Location | Evidence | Handling |
|---|---|---|---|
| C01 | 2408.09700.xml abstract | After trimming outer whitespace, the entire XML abstract equals the supplied API abstract (1,637 characters), including chemicallypeculiar and raw LaTeX fragments. The PDF has visible word boundaries and typeset formulas. | Written rule ABS-001 requires PDF-only content. Keep the observed XML immutable; quarantine its abstract as an expected-output conflict. Produce a PDF-derived candidate and require explicit fixture approval rather than assume a silent correction. |
| C02 | 2408.09700 title | PDF/output have an em dash; HTML/API use a double hyphen. The instructions exempt formatting but do not define this equivalence. | Keep PDF title. Default to a review difference until the named typography comparator is enabled. Never strip all punctuation to force matches. |
| C03 | 2408.09763.pdf pages 9-10 | A numbered bibliography [1]-[45] is present without a References heading. | Detect and retain all 45 candidates. Add a missing-heading review issue; do not output zero references. |
| C04 | 2408.09673.xml abstract | The sample places the radical sign inside `sup` in `O(1/<sup>√</sup>N)`, while the PDF shows a square-root expression. | Do not generalize this into a math rule. Keep a PDF-rich-text candidate and mark inline-math serialization as unresolved until the target profile is confirmed. |
| C05 | 2408.09763_Scrapping.xml / HTML | Scrapping version number [v2] agrees with PDF and current HTML v2, but its submit_date is 2024-08-19; HTML dates v2 at 2024-08-20. | Do not claim submit_date is the v2 revision date. Preserve the discrepancy separately. No article submission-date output path is established by these examples. |
| G01 | All 20 output XMLs | All contain order-id unknown, parcel-id none, supplier-id 4 and source/@srcid ???. | Keep these as observed sample-profile literals. Delivery profile values remain unconfirmed. Preview and explicit export with HOLDs remain possible. |
| G02 | Attachments | No client XSD, DTD or complete formal schema was supplied. Every ref-info is empty. | Provide observed-profile and business checks; display XSD NOT_RUN. Structured bibliographic children, further reference detail and full client compliance cannot be inferred. |
| G03 | Brief section 12 | A configured non-Latin surname rule is mentioned but not provided. | Use explicit API name components where available; unresolved parsing stays editable and on HOLD. Do not invent a cultural name heuristic. |
| G04 | XML rich text / optional structures | Examples show sup and inf, one abstract paragraph, and some absent given names/affiliations. They do not exhaust all allowed structures. | Keep an explicit mapping boundary for mathematical structures, multi-paragraph abstracts, no-affiliation cases and future schema extensions. |
| G05 | 17 output-only examples | The matching PDF, HTML, API and Scrapping files for 17 IDs are absent from this upload. | Use these XMLs for structural coverage only, not claims of source fidelity or complete extraction accuracy. |

Continue implementing all unambiguous behavior. Keep contested fields/profile choices explicitly unresolved with preview/edit/override available. Do not stop all development waiting for every optional detail, silently choose between a written rule and contradictory expected value, or alter supplied fixtures to make tests green. Original expected XML, proposed corrected XML and human-approved expected XML are separate artifacts.

## 14. Acceptance plan

The pack contains 40 acceptance scenarios in `tests/acceptance_cases.json`. They are requirements for the implementation, not executed application tests. Structural XML audit and source inspections already performed are recorded separately in `audit/`.

| Test | Scenario | Required result |
|---|---|---|
| T01 | Offline worker | Processing makes zero external calls and does not require AI credentials; all blocked attempts are reported |
| T02 | Repeatability | Canonical metadata, decisions and XML bytes match; actual audit event IDs/times may differ outside semantic output |
| T03 | Reference completeness 58 | 58 source candidates on pages 13-15 map to 58 reference nodes and refcount 58 |
| T04 | Unnumbered references 89 | 89 entries on page 10; 39 starts in left column and 50 in right; URLs and wrapped lines are not extra references |
| T05 | Heading-free references 45 | 45 entries on pages 9-10, missing-heading issue, full XML preview available |
| T06 | Synthetic truncation regression | 51 unreconciled source entries are identified; no PASS from merely setting refcount to 31; force export preserves HOLD evidence |
| T07 | No hard-coded totals | Generated count follows emitted source-backed entries rather than any sample count |
| T08 | Group repetition | Global author count 5; occurrences 6; group sequences [1,3,4,5], [1], [2] |
| T09 | Repeated seq=3 | Clayton retains global seq 3 in two groups; 6 distinct authors and 7 occurrences are valid |
| T10 | API expansion | Accepted components Jasvith Raj and Sri Krishna with PDF identity evidence; other authors are not reordered |
| T11 | Author order conflict | Sequence HOLD; preserve original PDF order and produce editable XML preview |
| T12 | Title word mismatch | TITLE-001 HOLD; no punctuation or case normalizer erases the extra word ending |
| T13 | Title case and whitespace | NORMALIZED_EXACT with raw source forms retained |
| T14 | Dash policy | Default review issue; explicit typography profile can resolve it and its version is logged |
| T15 | API abstract temptation | Do not reproduce API-only glued words or raw LaTeX merely to match expected output; record conflict C01 |
| T16 | Math uncertainty | No automatic radical-as-superscript rule; unsupported serialization stays on HOLD and editable |
| T17 | Missing support | PDF metadata still extracts; title/HTML verification is NOT_RUN with review issue, not PASS |
| T18 | Same ID wrong version | HOLD on actual mismatch, retain all versions/evidence and do not silently pick latest |
| T19 | First-page rotated stamp | Recover v1, v1, v2 from rotated stamps; no dependence on horizontal text search |
| T20 | Australian states | Serialize NSW and ACT without two-character truncation |
| T21 | No geographic invention | No fabricated city or country; preserve source text |
| T22 | Correspondence symbols | Two explicit correspondents in real sample; no corresponding author from email-only star in multi-author synthetic case |
| T23 | Single author decision table | yes, yes, no, yes respectively; missing optional XML components are not fabricated |
| T24 | Multiple works | Two parts with parent lineage for clear case; retain unsplit raw entry and HOLD for ambiguity |
| T25 | Excluded shorthand | Log ibid exclusion; preserve incomplete citation unchanged |
| T26 | Old citation retained | Reference is retained because date scope applies to article, not cited works |
| T27 | Duplicate source entries | Flag possible duplicate and retain both until reviewer disposition; no silent deletion |
| T28 | Edit under HOLD | Save new revision, re-run dependent rules and regenerate full preview without re-extraction |
| T29 | Protect raw XML | Manual XML remains intact, status becomes stale, regenerate requires explicit confirmation |
| T30 | HOLD export | Export selected current XML and sidecar; status EXPORTED_WITH_HOLDS; issues remain visible |
| T31 | Malformed XML | Parser failure navigates to exact buffer location; draft can be saved, normal validated delivery stays unavailable |
| T32 | Edited reference count | Validation reports mismatch against exact manual buffer; no silent correction or validation reuse |
| T33 | Override invalidation | Original override remains audited but becomes stale; new issue must be reviewed |
| T34 | Batch isolation | Other jobs finish independently; queue/revisions survive service restart; no duplicate exports |
| T35 | XSD missing | Report XSD NOT_RUN; sample-profile validation may pass, never claim official schema validation |
| T36 | Unknown XML nodes | Keep edit; flag unmapped/profile difference; no fabricated provenance |
| T37 | Source security | No viewer script/remote fetch, external entity expansion or writes outside package directory |
| T38 | OCR fallback | Native spans stay native; only unusable regions use local OCR; low-quality results HOLD; no remote calls |
| T39 | Namespace and escaping | DOM serialization round-trips values once; ANI and ce qualified names correct; no unescaped fragments |
| T40 | All sample structures | 974 references, all counts/sequences valid, observed optional ORCID and affiliation-free group covered; semantic conflicts remain quarantined |

For golden comparisons, compare qualified XML names, values, child ordering, occurrence identities and rich-text content. Ignore only explicitly permitted serialization differences such as namespace-prefix spelling, indentation-only whitespace outside mixed content and frozen test timestamp differences. Never globally strip punctuation, reorder arrays or ignore every empty element. Quarantine C01/C02/C04 expected-field conflicts until explicit resolution. Do not derive expected outputs from the same implementation functions under test.

Release evidence must include actual offline/egress results, source-to-output coverage reports, cross-source verification, exact-buffer edit protection, override/export audit, batch/resume results and all known unresolved profile choices. Twenty parseable sample XMLs or a UI counter reading zero does not prove this release works.

## 15. Complete numbered catalogue

Consequence is the default issue severity on failure. These rules do not make HOLD fatal to generation or editing. ERROR applies to the affected technical operation while preserving saved work and the draft editor.

| Rule | Name | Sources | Deterministic requirement | Consequence | Basis |
|---|---|---|---|---|---|
| SYS-001 | No production LLM calls | runtime | Exclude generative models, LLM SDK calls, agents, embeddings and paid/cloud AI OCR from production processing; no hidden fallback. | ERROR | Brief 1,35,36 |
| SYS-002 | Offline processing boundary | runtime | Deny network egress from processing workers; disable remote content in document viewers; bundle OCR assets locally. | ERROR | Design safeguard |
| SYS-003 | Reproducible decisions | runtime | Pin engine, OCR model, parser, dictionary, rule and template versions; use stable ordering and an explicit as-of date. | ERROR | Brief 31,34 |
| SYS-004 | Measured diagnostics | runtime | Display observed network attempts and enforcement state; never use a hard-coded zero counter as evidence of zero AI calls. | ERROR | Brief 36; design safeguard |
| PKG-001 | Package identity | all files | Match basename ID candidates to IDs parsed from file content; folder suffix n in the samples is not part of the ID. | HOLD | Brief 3 |
| PKG-002 | Required and missing files | all files | PDF is required to extract; absent support files remain visible and their dependent cross-checks are NOT_RUN, not PASS. | HOLD | Brief 2,3 |
| PKG-003 | Ambiguous association | all files | Do not choose between different same-role files, versions or content IDs; allow explicit assignment with audit. | HOLD | Brief 3 |
| PKG-004 | Original preservation | all files | Keep original bytes, SHA-256 and package-relative path immutable; edits are new derived revisions. | ERROR | Brief 7,25 |
| PKG-005 | Archive and parser boundaries | all files | Reject traversal, unsafe links and configured expansion limits; disable XML external entities and network DTD/schema resolution. | ERROR | Design safeguard |
| PKG-006 | Sample isolation | all files | Expected output XMLs are development fixtures; never extract production fields from them, Redcarplus files or a prior final XML. | ERROR | Brief 30,38 |
| PDF-001 | Native layout extraction | PDF | Store page dimensions, rotation, text direction, blocks, lines, spans, glyph/word boxes, font/style, links and annotations. | HOLD | Brief 5 |
| PDF-002 | Local OCR fallback | PDF | OCR only regions with missing or unusable native text; record why, OCR boxes, recognition scores and model/version. | HOLD | Brief 6 |
| PDF-003 | Coordinate contract | PDF | Use zero-based internal page indexes plus one-based display page numbers, points and top-left origin; store crop/rotation transforms. | ERROR | Design contract |
| PDF-004 | Layout reading order | PDF | Segment columns and spanning blocks before sorting; never sort every word on a page only by y then x. | HOLD | Brief 5; all 3 PDFs |
| PDF-005 | Boilerplate separation | PDF | Classify running heads, page numbers, captions and rotated arXiv stamps separately while keeping their evidence. | HOLD | Brief 5; all 3 PDFs |
| PDF-006 | Normalized text is secondary | PDF | Produce searchable MD/text with token-to-source mappings; raw text, coordinates and original PDF remain available. | ERROR | Brief 5,6 |
| PDF-007 | Glyph and line repair | PDF | Join soft wraps and reconstruct accent glyphs only with source layout evidence; preserve real hyphens, punctuation and raw text. | HOLD | Observed accent and line-wrap cases |
| PDF-008 | Mathematics and symbols | PDF | Preserve symbol relationships in rich text; unsupported radicals/scripts or damaged symbols require review, not API substitution. | HOLD | Brief 5; 2408.09673 and 2408.09700 |
| ID-001 | PDF identifier and version | PDF | Read ID and positive integer version from the first-page arXiv stamp, including rotation; a basename is not version evidence. | HOLD | Brief 9,10 |
| ID-002 | Scrapping verification | PDF, SCRAPPING | Compare PDF ID with /ARXIV/item/@id and PDF version with normalized /ARXIV/version/@number such as [v2]. | HOLD | Brief 9; 3 source packages |
| ID-003 | HTML verification | PDF, HTML | Compare citation_arxiv_id and the current version explicitly identified by the page; do not assume the largest history entry is the viewed version. | HOLD | Brief 9; 3 source packages |
| ID-004 | Unexpected stamp location | PDF | Search additional regions if the expected stamp is absent; retain any candidate and emit HOLD for unusual or missing location. | HOLD | Brief 9,10 |
| ID-005 | ID construction | PDF | Store base ID and integer version separately; serialize their validated combination as ARXIV itemid text. | HOLD | Brief 17; all 20 XMLs |
| ID-006 | Conflicting version candidates | all support | Retain all candidates and reject silent latest-version replacement; missing version is not v1. | HOLD | Brief 9,35 |
| TITLE-001 | Title verification | PDF, HTML | Compare normalized PDF title with HTML citation_title; ignore case and presentation markup, not different words or mathematical content. | HOLD | Brief 9 |
| TITLE-002 | Conservative normalization | PDF, HTML | Collapse layout whitespace and use approved typographic equivalences only; dash-to-double-hyphen equivalence is a named configurable rule. | HOLD | Brief 9; 2408.09700 |
| TITLE-003 | Title boundaries | PDF | Join multi-line title regions, excluding running heads, date, authors and journal banners; preserve rich text and evidence. | HOLD | Brief 5,9 |
| ABS-001 | PDF-only abstract | PDF | Extract abstract text only from PDF; API or HTML abstracts can be displayed but cannot populate or repair the output abstract. | HOLD | Brief 9 |
| ABS-002 | Abstract boundaries | PDF | Use heading and layout evidence; support an unheaded abstract and cross-page continuation without including keywords or body sections. | HOLD | Brief 9; 3 source packages |
| ABS-003 | Abstract fidelity | PDF | Check word boundaries, formulas and span coverage; a sample with glued words or raw API LaTeX is not an approved normalization rule. | HOLD | Brief 5,9; conflict C01 |
| KEY-001 | PDF keyword extraction | PDF | Recognize configured keyword labels including Key words; missing keywords are absent, not invented from API categories. | WARN | Brief 9 |
| KEY-002 | Keyword boundaries | PDF | Split on source-specific separators with layout evidence; retain punctuation and internal hyphens such as Four-roll-mill flow. | HOLD | Brief 9; 2408.09700 and 2408.09763 |
| AUTHOR-001 | Global PDF order | PDF | Build one canonical author list in PDF reading order; count distinct canonical authors before creating affiliation groups. | HOLD | Brief 9,12,13 |
| AUTHOR-002 | API identity verification | PDF, API | Compare canonical PDF identities with ordered API authors; allow consistent initial/full-name expansions but not arbitrary fuzzy substitutions. | HOLD | Brief 9 |
| AUTHOR-003 | Sequence verification | PDF, API | Compare API author order to PDF global order; never reorder the PDF list to hide disagreement. | HOLD | Brief 9,10 |
| AUTHOR-004 | Given and family names | API, PDF | For matched identities use API forenames and keyname; keep original displayed PDF name and matching evidence. | HOLD | Brief 12; all 3 API XMLs |
| AUTHOR-005 | Initial generation | API, PDF | Create initials deterministically, preserving existing initials, hyphens and diacritics; do not expand unknown names. | HOLD | Brief 12 |
| AUTHOR-006 | Surname particles | API, PDF | Preserve API surname components and multi-family surnames; configured particles are not a license to move words without evidence. | HOLD | Brief 12 |
| AUTHOR-007 | Unspecified name policy | API, PDF | If unstructured/non-Latin parsing needs a missing project rule, retain the displayed name for review rather than assume a universal last-token surname. | HOLD | Brief 12; gap G03 |
| AUTHOR-008 | One identity, repeated occurrences | canonical metadata | Reuse global_seq and the same canonical name/ORCID/email on all author-group occurrences; repeated seq across groups is legitimate. | ERROR | Brief 13; all 20 XMLs |
| AFF-001 | PDF-only affiliations | PDF | Extract normal affiliations only from PDF; API or HTML organizations cannot fill missing fields. | HOLD | Brief 9,11 |
| AFF-002 | Marker mapping | PDF | Create author-affiliation edges from author-attached markers and matching affiliation markers; store both endpoint evidence. | HOLD | Brief 9,13 |
| AFF-003 | Missing marker ambiguity | PDF | Multiple possible affiliations with no reliable relationship require review; a single clearly shared affiliation may be linked by documented layout evidence. | HOLD | Brief 10 |
| AFF-004 | Original versus present address | PDF | Prefer original/main affiliations; use current, former or work-completed-at information only when the author has no original affiliation. | HOLD | Brief 9 |
| AFF-005 | More complete original evidence | PDF | Prefer demonstrably more complete versions of the same original affiliation; incompatible organizations/addresses are a conflict, not a merge. | HOLD | Brief 9 |
| AFF-006 | No correspondence backfill | PDF | Do not manufacture a normal affiliation by copying extra address details from correspondence-only data. | HOLD | Brief 9 |
| AFF-007 | Organization decomposition | PDF | Store organizations as an ordered array and address components separately; retain exact source wording in source_text. | HOLD | Brief 11 |
| AFF-008 | No geographic invention | PDF | Do not infer city or country from institution reputation or web lookup; missing geographic parts remain missing. | HOLD | Brief 11,35 |
| AFF-009 | State dictionary | PDF | Use state for USA, Canada and Australia under country-specific mappings; NSW and ACT are valid observed values and must not be truncated to two letters. | HOLD | Brief 11; 2408.09700 |
| AFF-010 | Other administrative divisions | PDF | Use address-part for other source-supplied subdivisions unless an explicit rule says otherwise; Kerala remains address-part. | HOLD | Brief 11; 2408.09763 |
| AFF-011 | Country code mapping | PDF, dictionary | Use approved alpha-3 dictionary entries for explicitly supplied country/territory wording; preserve original wording in source_text. | HOLD | Brief 11 |
| AFF-012 | UK constituent wording | PDF, dictionary | Map explicitly supplied Scotland, Wales and Northern Ireland to GBR while preserving the wording; do not rewrite source text. | HOLD | Brief 11 |
| AFF-013 | Territory mappings | PDF, dictionary | Map Hong Kong to HKG, Macau to MAC, and Taiwan or Republic of China to TWN under the project dictionary. | HOLD | Brief 11 |
| AFF-014 | Unspecified country cases | PDF | Crimea or Palestine/Israel-related addresses without a stated country must not acquire an invented country. | HOLD | Brief 11 |
| AFF-015 | Department composition | PDF | Combine shared institution and author-specific department fragments only through explicit PDF relationships; retain component-level provenance. | HOLD | Brief 14 |
| AFF-016 | Group serialization | canonical graph | Order groups by source affiliation order and authors within each group by global_seq; repeat authors for multiple affiliations without renumbering. | ERROR | Brief 13; 3 matching XMLs |
| AFF-017 | Unusual affiliation location | PDF | Keep candidates found outside normal front matter/linked notes, show their location, and request review without blocking XML preview. | HOLD | Brief 10 |
| AFF-018 | Affiliation-free authors | PDF | Retain authors with no known affiliation in an affiliation-free group; distinguish truly absent data from unresolved edges and never omit the author. | HOLD | 2408.14658 output-only; design default |
| EMAIL-001 | PDF-only email | PDF | Store at most one selected email per canonical author; preserve all candidates internally and flag unresolved multiple choices. | HOLD | Brief 9 |
| EMAIL-002 | Shared email notation | PDF | Expand grouped local parts only when the complete common domain and author relationship are explicit on the same PDF. | HOLD | Brief 9 |
| EMAIL-003 | Email completion limits | PDF | Fill incomplete email components only from unambiguous PDF evidence; no guessing from names or external lookup. | HOLD | Brief 9,35 |
| ORCID-001 | PDF ORCID evidence | PDF | Accept visible number or PDF hyperlink attached to the relevant author/logo; a logo with no recoverable link is not an identifier. | HOLD | Brief 9 |
| ORCID-002 | ORCID format | PDF | Normalize the identifier only; validate configured syntax/check-digit rules and identity association; store at author/@orcid, not an invented ce:orcid element. | HOLD | Brief 23; observed XML attribute |
| CORR-001 | Single-author decision | PDF | For one canonical author, email or affiliation is sufficient for correspondence; explicit correspondence is sufficient; neither means no unless explicit text says yes. | HOLD | Brief 15 |
| CORR-002 | Multiple-author evidence | PDF | Require explicit correspondence text or an author-attached correspondence marker with a resolved meaning. | HOLD | Brief 15; 2408.09700 and 2408.09763 |
| CORR-003 | Non-correspondence marker | PDF | Equal contribution, present address and other identified non-correspondence markers do not set correspondence. | HOLD | Brief 15 |
| CORR-004 | Email-only or affiliation-only symbol | PDF | An asterisk on email/affiliation without a matching author indicator does not set correspondence. | HOLD | Brief 9,15 |
| CORR-005 | Unexplained symbol | PDF | An unresolved star/envelope/dagger is evidence to review, not automatic correspondence. | HOLD | Brief 15 |
| CORR-006 | Correspondence serialization | PDF, canonical metadata | Create a separate head/correspondence per selected person, with person, optional evidenced affiliation and selected ce:e-address in the observed order. | HOLD | Brief 17; 12 observed correspondence elements |
| REF-001 | Article applicability | PDF, run config | Apply the 1970-to-as-of-year scope to the article, not to each cited work; retain older citations such as the 1967 reference in 2408.09700. | HOLD | Brief 9 |
| REF-002 | Section discovery | PDF | Discover all main/supplementary bibliography regions using headings plus layout and bibliographic entry patterns. | HOLD | Brief 9,16 |
| REF-003 | Heading-free bibliography | PDF | A missing heading must not yield zero references; retain the detected list and flag missing/unusual section identification. | HOLD | Brief 10; 2408.09763 pages 9-10 |
| REF-004 | Column/page continuation | PDF | Continue an entry across column or page breaks until the next confirmed boundary; never truncate at a page/column limit. | HOLD | Brief 16; all 3 PDFs |
| REF-005 | Numbered boundaries | PDF | Detect source labels only at entry starts in a confirmed reference region; body citations, years and figure labels are not entry starts. | HOLD | Brief 16 |
| REF-006 | Unnumbered boundaries | PDF | Use hanging indentation, recurring author/year starts and block structure; URLs, DOI lines and indented continuations stay with their entry. | HOLD | 2408.09700 page 10 |
| REF-007 | Source-label removal | PDF | Strip only the detected leading source label from exported reference text; retain original_label and its bounding box internally. | HOLD | Brief 9,16 |
| REF-008 | No citation enrichment | PDF | Capture incomplete references as found; do not fetch DOI metadata, search the web or use support abstracts to complete them. | HOLD | Brief 9,35 |
| REF-009 | Shorthand-only entries | PDF | An entry consisting only of ibid, supra, op. cit. or loc. cit. is an explicit excluded candidate with a reason, not a fabricated work. | HOLD | Brief 9 |
| REF-010 | Non-Roman-only entries | PDF | Exclude entirely non-Roman references with a logged reason; mixed-script or unclear cases require review, not automatic deletion. | HOLD | Brief 9 |
| REF-011 | Main versus footnote references | PDF | When normal references exist capture those, excluding footnote citations; if only bibliographic footnotes exist capture them with HOLD. | HOLD | Brief 9 |
| REF-012 | Inline citations | PDF | Do not turn body-only inline citations into bibliography entries; retain exclusion classification for coverage review. | WARN | Brief 9 |
| REF-013 | Multiple works in one entry | PDF | Split only on a supported multi-work boundary with source spans; semicolons alone are insufficient evidence. | HOLD | Brief 9,16 |
| REF-014 | Supplement and multiple regions | PDF | Inventory main and supplemental reference regions in document order; multiple distinct locations trigger review and explicit inclusion decisions. | HOLD | Brief 9,10 |
| REF-015 | Underscore placeholders | PDF | Flag blank/underscore author placeholders; keep source text and do not copy an earlier author name into the reference. | HOLD | Brief 10 |
| REF-016 | Output ordering | canonical references | Use source region order, source entry order and split-part order, then assign contiguous output seq starting at 1. | ERROR | Brief 9,16 |
| REF-017 | DOM-derived refcount | generated XML | Set bibliography/@refcount from the actual serialized reference elements; validate again after any direct XML edit. | ERROR | Brief 16,23 |
| REF-018 | Independent source coverage | PDF, canonical references | Independently inventory labels/start lines and region coverage; reconcile accepted, excluded and pending candidates instead of trusting output count alone. | HOLD | Brief 16 |
| REF-019 | Duplicate handling | PDF, canonical references | Flag identical/similar candidates with evidence; never silently deduplicate separate source entries. | HOLD | Brief 23,35 |
| REF-020 | No extraction caps | runtime | Do not impose hidden limits on pages, references, text length or first-N extraction; configured resource limits stop visibly and preserve partial work. | ERROR | Brief 16,35 |
| REF-021 | Coverage accounting | candidate ledger | Require C=A+X+U and R=sum of emitted parts for accepted candidates; extra split parts are recorded and excluded/pending counts are visible. | HOLD | Brief 16; design contract |
| REF-022 | No fixed target counts | runtime | 58, 89, 45 and 82 are regression expectations, never production extraction constants or values copied from expected XML. | ERROR | Brief 30,35 |
| XML-001 | Namespace profile | template | Use default ANI http://www.elsevier.com/xml/ani/ani and ce http://www.elsevier.com/xml/ani/common; XML lang uses the XML namespace. | ERROR | All 20 XMLs |
| XML-002 | DOM-only serialization | canonical metadata | Build qualified elements/attributes using an XML builder, escape text once, serialize UTF-8 and parse the result; no raw concatenation or injected fragments. | ERROR | Brief 17 |
| XML-003 | Exact observed hierarchy | template | Use units/unit/unit-content/bibrecord with sibling item-info, head, tail, and bibliography under tail; preserve observed child order. | HOLD | All 20 XMLs |
| XML-004 | Static versus dynamic fields | template, metadata | Pin constants in a profile, derive article data from current evidence, and obtain timestamp from an explicit frozen run context. | HOLD | Brief 18; all 20 XMLs |
| XML-005 | Placeholder delivery values | delivery profile | unknown, none and ??? are sample literals, not verified client delivery values; require profile selection or recorded acceptance, while allowing draft/forced export. | HOLD | All 20 XMLs; gap G01 |
| XML-006 | Observed reference shape | template | Default sample profile uses ref-info empty, ref-fulltext and ce:source-text; do not invent structured reference children without an approved extension. | HOLD | All 974 references |
| XML-007 | Optional and missing values | canonical metadata | Omit unsupported optional values rather than invent them; missing required values produce a partial full-document draft plus explicit issues, never fabricated text. | HOLD | Brief 35; observed omissions |
| XML-008 | Mixed content | PDF, template | Treat inline text, tails and script spans as rich content; sup/inf are in the inherited ANI namespace; do not turn radicals into superscripts. | HOLD | Observed sup/inf paths; gap G04 |
| XML-009 | No unapproved output metadata | template | Store audit, confidence, HOLD reasons and evidence outside client XML; do not inject telemetry, internal IDs, EGI/IPUI or DOI elements absent from the selected profile. | HOLD | Brief 17,25; observed profile |
| XML-010 | Schema status | validation config | Without a supplied client XSD report XSD NOT_RUN, not schema-valid; local sample-profile checks are a separately named validation layer. | HOLD | Brief 23; gap G02 |
| XML-011 | Technical failure versus HOLD | XML editor | Malformed XML remains editable/saveable as a draft; a HOLD override does not turn a parser/schema error into a validation pass. | ERROR | Brief 39-46; design contract |
| EDIT-001 | Full preview on HOLD | metadata | Generate the full document preview from all available data after extraction even when HOLDs remain; show absent/affected fields beside the XML. | ERROR | Brief 39,42,46 |
| EDIT-002 | Metadata editing | operator | Allow every specified field, author-affiliation edge and reference to be edited; retain extracted and accepted values as separate revisions. | ERROR | Brief 21,41 |
| EDIT-003 | Full XML editing | operator | Offer the entire XML document with undo, search/replace, validation, line/column navigation, save and download; do not limit users to forms. | ERROR | Brief 40,41 |
| EDIT-004 | Direct edit protection | operator | Mark direct XML edits and retain their revision; later metadata changes make XML stale, never silently replace manual edits. | ERROR | Brief 22,41 |
| EDIT-005 | Regenerate or keep manual XML | operator | Provide explicit regenerate-with-confirmation and keep-manual actions; snapshot the current XML before replacement. | ERROR | Brief 22,41 |
| EDIT-006 | Override controls | operator | Allow edit, evidence view, accept extracted value, override and keep HOLD; record rule, issue, user, old/new values, timestamp and optional reason. | ERROR | Brief 39,43 |
| EDIT-007 | Selective reevaluation | dependency graph | Re-run affected rules after edits; an override applies to a specific evidence/value/rule revision and becomes stale when those inputs change. | ERROR | Brief 42 |
| EDIT-008 | Traceability after raw edits | manual XML | Map recognizable XML nodes back to canonical fields; unmatched manual nodes are explicitly unmapped, not falsely linked to PDF evidence. | HOLD | Brief 44; design contract |
| VAL-001 | Validation layers | all | Report parser, sample-profile, business, source-verification and optional XSD results separately; missing checks are NOT_RUN. | HOLD | Brief 23 |
| VAL-002 | Unique author checks | canonical metadata, XML | Validate distinct global author identities, contiguous global sequence and correct group edges; do not compare API count with raw XML author occurrence count. | HOLD | Brief 13,23 |
| VAL-003 | Final artifact validation | exact export bytes | Validate the selected current XML revision immediately before export; do not reuse results from a previous generated revision. | ERROR | Brief 23,43 |
| VAL-004 | Error navigation | XML editor | Use parser line/column against the exact buffer revision; formatting invalidates old coordinates; map to metadata/evidence when available. | ERROR | Brief 24,40 |
| EXP-001 | Normal export | operator, validation | Normal export requires passed technical gates and resolved/validly overridden review issues under the chosen delivery profile. | HOLD | Brief 23,43 |
| EXP-002 | Export with HOLDs | authorized operator | Permit deliberate export with unresolved HOLDs, show the list, record acknowledgement and export status; never relabel it VERIFIED. | HOLD | Brief 39,43,46 |
| EXP-003 | Technical-error draft download | operator | Allow saving/downloading an invalid edit buffer as an explicitly invalid draft; do not present it as a validated delivery XML. | ERROR | Brief 40,46; design contract |
| EXP-004 | Revision and audit export | exact export bytes | Record selected XML hash, revision, input hashes, profile/rule versions, validation snapshot and unresolved/overridden issue IDs in sidecar audit JSON/CSV. | ERROR | Brief 25,27 |
| BATCH-001 | Independent jobs | queue | Support 1, 5 and 25 packages; a failed article does not stop other articles, and completed work survives restart. | ERROR | Brief 26 |
| BATCH-002 | Multidimensional status | job state | Keep processing, review, XML, validation and export states separate; XML_GENERATED and ON_HOLD may coexist. | ERROR | Brief 45 |
| BATCH-003 | Rule update governance | administrator | Version rule/dictionary changes, validate their schema, run regression fixtures and record activation; manual correction never trains an unpredictable model. | ERROR | Brief 19,31 |
| TEST-001 | Quarantined conflicts | fixtures | Do not bless contradictory sample fields as golden truth; maintain observed and approved expectations separately with issue IDs. | ERROR | Brief 30,38 |
| TEST-002 | No unsupported success claim | test reports | Distinguish specification checks, XML parse checks, PDF inspections and actual application tests; do not infer full client acceptance or accuracy from sample counts. | ERROR | Brief 30; audit scope |

## 16. Package contents

`MASTER_BUILD_PROMPT.txt` supplies the implementation handoff and includes the complete original brief verbatim. `rules/rule_catalog.json` contains numbered contracts; `xml/xml_profile.json` contains the namespace/field/order map and observed inventory; `model/data_contract.json` defines the evidence/revision model; `tests/acceptance_cases.json` contains implementation tests to build; `audit/` records what was actually inspected and unresolved sample issues. All three original attachments are bundled unchanged under `attachments/` with SHA-256 entries in `MANIFEST.json`.

No application has been built, no source/expected XML has been modified, and no runtime performance or official XSD pass is claimed by this deliverable.
