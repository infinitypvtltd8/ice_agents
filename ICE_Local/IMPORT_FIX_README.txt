ICE LOCAL 1.0.1 - DOCUMENT IMPORT FIX

INSTALL THIS SMALL UPDATE
1. Close the ICE command window to stop the app.
2. Extract ICE_Local_Import_Fix.zip into your existing ICE_Local folder,
   the folder containing START_WINDOWS.cmd. Choose Replace files when asked.
3. Double-click START_WINDOWS.cmd and refresh the browser (Ctrl+F5).
4. Re-import the document package if it was previously skipped.

The update contains no data folder, so existing saved articles are preserved.
It uses the Python runtime already included in your original app.

FIXES
- Reads saved article text as UTF-8 on Windows, including mathematical symbols
  and accented names. This fixes articles disappearing after upload.
- Recognizes nested ZIPs and uppercase ZIP/PDF/XML/HTML extensions.
- Matches support files using article IDs, document identity and article folders.
- Accepts wrapped API records and namespaced Scrapping XML.
- Keeps unique source selections; unfamiliar XML roles can be selected manually.
- Adds an import report explaining any skipped file, plus folder drag/drop.
- Serves JavaScript with the correct content type regardless of Windows registry.

TESTS
13 automated HTTP/extraction/import tests passed on Linux. Windows text encoding
was simulated in a regression test. The complete GUI was also checked in Linux Chromium: upload, PDF preview,
editing, XML validation and download passed. The Windows launcher has not
been executed on Windows in this environment.

Citation processing remains local with zero AI/LLM calls.
