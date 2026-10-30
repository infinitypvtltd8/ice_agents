# infinity-ACE

OCR Tool. **ICE Local 1.3.0** is a local citation extraction app. Files are processed entirely on your own computer: no AI/LLM calls and no internet needed to process them. No login or internet connection is needed for the local workspace.

This is a bundled Python application. There is no `npm install` or `npm start` step.

## Windows setup

The repo includes a portable 64-bit Python 3.12.10 runtime with all required libraries (`ICE_Local/runtime/`). You do not need to install Python.

### Requirements

- Windows 10 or 11, 64-bit
- [Git for Windows](https://git-scm.com/download/win) (only needed to clone)
- A modern browser (Edge, Chrome or Firefox)
- Optional: [Tesseract OCR](https://github.com/tesseract-ocr/tesseract), only for scanned or image-only PDFs

## Replit hosting

The app can also run as a shared Replit Reserved VM deployment. It requires an `ICE_ACCESS_PASSWORD` deployment secret before it will bind to the public network. See [`REPLIT_DEPLOYMENT.md`](REPLIT_DEPLOYMENT.md) for setup, access, and data-retention details. Local Windows/macOS/Linux use remains available as described below.

### 1. Clone the repository

Clone into a short folder path such as `C:\ICE`:

```powershell
cd C:\
git clone https://github.com/PasaniFusion/infinity-ACE.git ICE
cd ICE
```

If you have no Git, use **Code → Download ZIP** on GitHub, then extract the whole ZIP to `C:\ICE`. Don't run the app from inside the compressed folder.

### 2. Start the app



Either double-click `START_ICE.cmd` in the repo folder, or run it from PowerShell:

```powershell
.\START_ICE.cmd
```

If you are already inside the `ICE_Local` folder, run `.\START_WINDOWS.cmd` instead.

### 3. Use the app

The app opens directly to the workspace at <http://127.0.0.1:8765>. It is available only on this computer. **Keep the command window open** while you use it. Closing it stops the app.

To check that it works, click **Try sample files** in the app.

### Changing the routing rules

The latest field-extraction and XML-tagging rules are in [`LATEST_RULES.txt`](LATEST_RULES.txt), also copied to `ICE_Local/docs/LATEST_RULES.txt`. Correspondence rules are applied by `ICE_Local/engine.py`. The matching rulebook in `ICE_Local\config\rulebook.toml` controls source-comparison findings and is separate from the field-level guide. The prose guides also include rules not yet automated by the runtime.

All files stay in **General**. Matching and validation results are informational notes; they do not block metadata saves, XML generation, or export. A typo in the matching rulebook is shown in **Matching rules** until fixed. `ICE_Local\docs\RULEBOOK.md` explains its rules and settings.

### Troubleshooting

| Problem | Fix |
| --- | --- |
| Browser does not open | Open <http://127.0.0.1:8765> manually. |
| Port 8765 is already in use | Close the old ICE command window, or from `ICE_Local` run `runtime\python.exe -X utf8 app.py --port 8766` |
| "The bundled Python runtime is incomplete or damaged" | Clone or download the repo again. Back up `ICE_Local\data` first if you have saved articles. |
| Windows SmartScreen warns about the `.cmd` file | Click **More info → Run anyway**. |
| Scanned page text needs review | Install Tesseract OCR and set the `tesseract.exe` path in the app's **Settings**. Review notes do not block XML export. |

If `ICE_Local\runtime\python.exe` is missing, the launcher falls back to a normal Python install. It needs 64-bit Python 3.12+ on `PATH` and internet for this one-time setup. It then creates `ICE_Local\.venv` and installs `requirements.txt`.

## Your data

Jobs, uploaded files, XML revisions and audits are saved in `ICE_Local\data\`. That folder is created when the app first starts and is excluded from git. **Back it up before you update or re-clone the app.** To store it elsewhere, set the `ICE_DATA_DIR` environment variable.

## macOS / Linux

The bundled runtime is Windows-only. On macOS or Linux you need Python 3.12+ installed. The first run creates `ICE_Local/.venv` and installs the pinned dependencies, so it needs internet. Run:

```bash
cd ICE_Local
./START_MAC_LINUX.sh
```

## Documentation

- `LATEST_RULES.txt`: latest user-provided field-extraction and XML-tagging rules
- `ICE_Local/README.txt`: full feature overview and workflow
- `ICE_Local/docs/USER_GUIDE.md`: user guide
- `ICE_Local/docs/`: project instructions, coding guide, rule specification and queue definitions
- `ICE_Local/AGENTS.md`: guidance for coding agents
- `ICE_Local/DEPENDENCIES.txt`: third-party licenses (PyMuPDF is AGPL/commercial; check the terms before redistributing)
