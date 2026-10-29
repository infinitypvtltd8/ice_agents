# Handoff instructions for the next developer or coding agent

Read `PROJECT_INSTRUCTIONS.md`, `CODING_GUIDE.md`, `RULES_IMPLEMENTATION.md`, `QUEUE_DEFINITIONS_AND_VERIFICATION.md`, `USER_GUIDE.md`, the original `SOURCE_REQUIREMENTS.txt`, and `MASTER_RULE_ENGINE_SPECIFICATION.md` before extending extraction behavior. Treat user-supplied corrected final XML and its PDF/API/Scrapping/HTML package as the next essential ground truth. Do not infer a complete Elsevier schema from current samples.

1. Preserve the zero-AI production boundary. Use AI during development only. The PDF is authoritative; retain exact page/box evidence and original sources. Use local OCR only when the text layer is unreliable.
2. Keep metadata, XML, validation, triage, revisions and audit consistent. An edit cannot silently retain a prior override; the backend reopens review decisions on material changes.
3. Add a numbered rule by implementing its handler, expected source precedence, HOLD/review behavior, XML mapping and an end-to-end test. Do not mark specification-only rules implemented based on a UI card alone.
4. Check reference count against all visible PDF entries, preserve incomplete entries, and split multi-work references only on evidence. Never complete them using another source.
5. Preserve repeated authors across groups with their original global `seq`, original affiliations, and correspondence logic. Explicit groups are operator decisions and should remain reviewable.
6. Run the current regression tests and browser checks before packaging. The actual release ZIP must contain the bundled Windows executable and intact `lxml/etree` extension. Test on Windows before claiming native Windows verification.
7. The private review website uses a static sample API shim and is for visual review; synchronize front-end changes after the downloadable local app is tested. Keep the site clearly labeled as a sample. Never imply a browser preview processes uploaded production documents.

Requested next integration: collect several complete packages with their correct final XML, the client's XSD, exact title/abstract/formula samples, and examples of current/former affiliation, correspondence markers and split references. Build a fixture matrix mapping each numbered rule to observed input regions and expected XML. After implementation, update both this guide and the rule-status catalogue.
