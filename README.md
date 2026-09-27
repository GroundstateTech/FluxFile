# FluxFile

FluxFile is Groundstate Technology LLC's local-first bulk file conversion workstation.

Version **0.5.0** establishes a clean cross-platform baseline for Windows and Ubuntu. It keeps conversion jobs local, previews the queue before running it, detects available conversion engines, handles filename conflicts, and writes a conversion report after each batch.

## Current conversion paths

FluxFile uses the best available local engine for each job:

- **Images:** PNG, JPG/JPEG, BMP, GIF, TIFF, WEBP through Pillow
- **Tables/data:** CSV, TSV, JSON, XLSX and ODS through pandas/openpyxl/odfpy
- **Documents:** Markdown, HTML, DOCX, ODT, RTF, EPUB and related Pandoc-supported formats when Pandoc is installed
- **Office formats/PDF output:** LibreOffice headless conversion when LibreOffice is installed
- **PDF → DOCX:** optional `pdf2docx` path when that dependency is installed

The application deliberately reports unsupported conversions instead of pretending a conversion succeeded.

## Ubuntu quick start

Ubuntu 22.04/24.04:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-tk pandoc libreoffice
git clone https://github.com/GroundstateTech/FluxFile.git
cd FluxFile
chmod +x run_fluxfile.sh
./run_fluxfile.sh
```

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

## Verify

```bash
python -m unittest discover -s tests -v
python scripts/doctor.py
```

## Design rules

- Conversion happens locally.
- Source files are never modified in place unless the user explicitly chooses the same output directory and overwrite mode.
- Filename conflicts default to suffixing rather than destructive replacement.
- External engines are detected at runtime.
- Failed jobs remain visible in the report.
- FluxFile does not upload files to Groundstate or a cloud conversion service.

## Repository layout

```text
fluxfile.py             desktop application + conversion engine
requirements.txt        Python dependencies
run_fluxfile.sh         Ubuntu/Linux launcher
run_fluxfile.bat        Windows launcher
scripts/doctor.py       engine/environment diagnostics
tests/                  conversion-core regression tests
docs/UBUNTU.md          Ubuntu setup and troubleshooting
```

Copyright © 2026 Groundstate Technology LLC.
