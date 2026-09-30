# FluxFile

FluxFile is Groundstate Technology LLC's local-first bulk file conversion workstation.

Version **0.7.0** is a reliability and bug-hunt release. It keeps the existing cross-platform conversion planner while hardening recursive intake, conversion routing, overwrite safety, LibreOffice isolation, launchers, worker/UI coordination, diagnostics, and CI.

## What changed in 0.7.0

- **Atomic output writes.** Conversions are written to a temporary sibling file and moved into place only after the engine succeeds. A failed conversion no longer destroys an existing destination file.
- **Recursive folder safety.** Folder intake ignores hidden/internal trees such as `.git`, `.venv`, `__pycache__`, and `node_modules`, and it skips the active output directory.
- **Truthful conversion matrix.** The planner no longer advertises spreadsheet/presentation targets for document types that the engine layer cannot reliably produce.
- **Partial-batch execution.** Unsupported jobs are recorded and skipped while supported jobs continue instead of one bad route blocking the entire queue.
- **LibreOffice isolation.** Headless conversions use a dedicated temporary user profile so an already-running desktop LibreOffice session is much less likely to lock or stall FluxFile.
- **Conversion timeout.** External engine calls are capped at five minutes instead of hanging forever.
- **Safer image conversion.** EXIF orientation is applied before image export.
- **Thread-safe UI updates.** The worker reports through a queue polled by Tk's main thread rather than directly driving Tk from the worker thread.
- **Run-state protection.** Queue-mutating controls are disabled while a conversion pass is active.
- **Unique reports.** Report names now include microseconds to avoid same-second collisions.
- **Faster launchers.** Python dependencies are only reinstalled when `requirements.txt` changes.
- **Stricter diagnostics and CI.** The doctor can fail on a broken core environment, and CI now tests Python 3.10–3.13 on Ubuntu and Windows plus real conversion smoke tests.

## Conversion planning

Choose the input family first, then choose a compatible output format.

Representative routes:

- CSV / TSV / XLS / XLSX / ODS → XLSX / ODS / CSV / TSV / JSON
- CSV / TSV / XLS / XLSX / ODS → PDF when LibreOffice is installed
- JSON → XLSX / ODS / CSV / TSV / JSON
- DOC / DOCX / ODT / RTF → common document formats; PDF through LibreOffice
- Markdown / HTML / TXT / EPUB → DOCX / ODT / RTF / HTML / Markdown / TXT / EPUB through Pandoc
- PPT / PPTX / ODP → PDF / PPTX / ODP through LibreOffice
- PDF → DOCX / TXT
- PNG / JPG / TIFF / WEBP / BMP / GIF → other image formats or PDF

Mixed-folder mode remains available with **From = any**.

## Current engines

FluxFile uses the best available local engine for each job:

- **Images:** Pillow
- **Tables/data:** pandas + openpyxl / odfpy / xlrd
- **Documents:** Pandoc when installed
- **Office/PDF output:** LibreOffice headless when installed
- **PDF → DOCX:** pdf2docx
- **PDF → TXT:** PyMuPDF

Pandoc and LibreOffice are optional external engines. FluxFile detects them at runtime.

## Ubuntu quick start

Ubuntu 22.04/24.04 or newer:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip python3-tk pandoc libreoffice
git clone https://github.com/GroundstateTech/FluxFile.git
cd FluxFile
chmod +x fluxfile.sh
./fluxfile.sh
```

The older `run_fluxfile.sh` command remains as a compatibility wrapper.

The launcher verifies Python 3.10+, repairs a broken `.venv`, creates the environment if needed, installs dependencies only when `requirements.txt` changes, and starts FluxFile.

## Windows quick start

Install Python 3.10+ and optionally Pandoc + LibreOffice, then run:

```bat
run_fluxfile.bat
```

The Windows launcher accepts either the `py` launcher or `python.exe`, rebuilds an incomplete `.venv`, and uses the same dependency-stamp logic as Linux.

## Queue workflow

1. Choose **From**.
2. Choose **To**.
3. Add files or a folder.
4. Optionally enable **Include subfolders**.
5. Review detected format, target, and engine.
6. Use **Apply plan to queue** if you change the conversion plan.
7. Choose conflict handling: `suffix`, `skip`, or `overwrite`.
8. Choose the output folder.
9. Run the conversion.

Unsupported jobs are marked **Unsupported** and written to the report; supported jobs continue.

Each pass writes JSON and CSV reports into the output folder.

## Verify

Inside the virtual environment:

```bash
python scripts/doctor.py --strict
python -m unittest discover -s tests -v
```

The test suite includes real smoke conversions for tables, images, and PDF text extraction in addition to planner and safety regression tests.

## Design rules

- Conversion happens locally.
- Windows and Ubuntu use the same application logic.
- Filename conflicts default to suffixing instead of destructive replacement.
- Existing outputs are protected from partial/failed conversion writes.
- Hidden/internal dependency and repository folders are ignored during recursive intake.
- External engines are detected at runtime.
- Unsupported routes do not block otherwise valid jobs.
- Failed and unsupported jobs remain visible in the reports.
- FluxFile does not upload files to Groundstate or a cloud conversion service.

## Repository layout

```text
fluxfile.py                    shared Windows/Ubuntu application + conversion engine
requirements.txt               Python dependencies
fluxfile.sh                    canonical Ubuntu/Linux launcher
run_fluxfile.sh                legacy Linux compatibility launcher
run_fluxfile.bat               Windows launcher
scripts/bootstrap.py           dependency-stamp/bootstrap helper
scripts/doctor.py              engine/environment diagnostics
tests/test_core.py             planner/safety regression tests
tests/test_conversion_smoke.py real conversion smoke tests
docs/UBUNTU.md                 Ubuntu setup and troubleshooting
```

Copyright © 2026 Groundstate Technology LLC.
