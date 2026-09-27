# FluxFile

FluxFile is Groundstate Technology LLC's local-first bulk file conversion workstation.

Version **0.6.0** brings the Windows and Ubuntu builds back onto the same feature path. The application now uses one shared cross-platform codebase with an explicit **From → To** conversion planner, compatibility-aware target selection, queue previews, engine detection, conflict handling, recursive folder intake, and JSON/CSV conversion reports.

## Conversion planning

Choose the input family first, then choose a compatible output format.

Examples:

- CSV → ODS / XLSX / JSON / TSV
- ODS → CSV / XLSX / JSON
- JSON → XLSX / ODS / CSV
- DOCX → PDF / ODT / HTML / TXT
- Markdown → DOCX / HTML / ODT / RTF / EPUB
- PDF → DOCX / TXT
- PNG / JPG / TIFF / WEBP → other image formats or PDF

Mixed-folder mode remains available with **From = any**.

The queue displays:

- source file
- detected source format
- selected target format
- conversion engine
- current status
- output/error

Use **Apply plan to queue** to retarget compatible queued files before conversion.

## Current engines

FluxFile uses the best available local engine for each job:

- **Images:** PNG, JPG/JPEG, BMP, GIF, TIFF, WEBP and PDF output through Pillow
- **Tables/data:** CSV, TSV, JSON, XLS/XLSX and ODS through pandas/openpyxl/odfpy/xlrd
- **Documents:** Markdown, HTML, DOCX, ODT, RTF, EPUB and text through Pandoc when installed
- **Office formats/PDF output:** LibreOffice headless conversion when LibreOffice is installed
- **PDF → DOCX:** pdf2docx
- **PDF → TXT:** PyMuPDF

FluxFile reports unsupported conversions before starting instead of silently producing misleading output.

## Ubuntu quick start

Ubuntu 22.04/24.04:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-tk pandoc libreoffice
git clone https://github.com/GroundstateTech/FluxFile.git
cd FluxFile
chmod +x fluxfile.sh
./fluxfile.sh
```

The older `run_fluxfile.sh` command remains as a compatibility wrapper.

If FluxFile finds a broken or partially-created `.venv`, the launcher rebuilds it automatically.

## Windows quick start

Install Python 3.10+ and optionally Pandoc + LibreOffice, then run:

```bat
run_fluxfile.bat
```

or:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python fluxfile.py
```

Windows and Ubuntu launch the same `fluxfile.py` application and therefore share the same conversion-planning interface and feature set.

## Queue workflow

1. Choose **From**.
2. Choose **To**.
3. Add files or a folder.
4. Optionally enable **Include subfolders**.
5. Review the detected format, target and engine in the queue.
6. Use **Apply plan to queue** if you change the conversion plan.
7. Choose conflict handling:
   - suffix
   - skip
   - overwrite
8. Choose the output folder.
9. Run the conversion.

Each conversion pass writes both JSON and CSV reports into the output folder.

## Verify

```bash
. .venv/bin/activate
python scripts/doctor.py
python -m unittest discover -s tests -v
```

## Design rules

- Conversion happens locally.
- Windows and Ubuntu use the same application logic.
- Source files are not modified unless overwrite behavior is explicitly chosen.
- Filename conflicts default to suffixing instead of destructive replacement.
- External engines are detected at runtime.
- Unsupported conversion plans are identified before the batch starts.
- Failed jobs remain visible in the report.
- FluxFile does not upload files to Groundstate or a cloud conversion service.

## Repository layout

```text
fluxfile.py             shared Windows/Ubuntu application + conversion engine
requirements.txt        Python dependencies
fluxfile.sh             canonical Ubuntu/Linux launcher
run_fluxfile.sh         legacy compatibility launcher
run_fluxfile.bat        Windows launcher
scripts/doctor.py       engine/environment diagnostics
tests/                  conversion-core regression tests
docs/UBUNTU.md          Ubuntu setup and troubleshooting
```

Copyright © 2026 Groundstate Technology LLC.
