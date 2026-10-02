# FluxFile

FluxFile is Groundstate Technology LLC's local-first bulk file conversion workstation.

Version **0.8.0** expands FluxFile into a multi-family conversion workstation: documents, ebooks, spreadsheets, images, audio, video, subtitles, PDF exports, and archives. Conversion stays on your computer.

## New in 0.8.0

| Family | New routes | Engine |
| --- | --- | --- |
| Audio | MP3, WAV, FLAC, OGG, OPUS, M4A, AAC, AIFF output | FFmpeg |
| Video | MP4, MKV, MOV, AVI, WebM, animated GIF; extract audio | FFmpeg |
| Images | ICO, ICNS, PPM, TGA, AVIF output; additional image inputs | Pillow; codec availability varies |
| Vector graphics | SVG → PNG / PDF | optional CairoSVG + Cairo |
| PDF | HTML; single-page PNG/JPG; all pages as TIFF | PyMuPDF |
| Data | JSONL ↔ existing table formats | pandas |
| Subtitles | SRT ↔ VTT | built in |
| Archives | ZIP / TAR / TGZ / TBZ2 / TXZ repacking | built in |

Animated image export preserves frames in GIF, WebP, PNG, TIFF and PDF; targets that would silently discard frames are refused. Multi-page PDF → PNG/JPG is refused; choose TIFF to preserve pages. Failed conversions retain existing destination files.

Use **Format guide** inside the app for engine requirements and conversion boundaries. A headless CLI uses the same engine:

```bash
python fluxfile_cli.py --engines
python fluxfile_cli.py recording.mp4 --to mp3 --output-dir converted
python fluxfile_cli.py bundle.zip --to tgz
```

### Install the additional engines

Ubuntu:

```bash
sudo apt install ffmpeg libcairo2
python -m pip install -r requirements-optional.txt
```

Windows: install FFmpeg and add its `bin` directory to PATH. SVG rendering additionally requires CairoSVG and a working Cairo runtime; it remains optional. Run `python -m pip install -r requirements-optional.txt` in FluxFile's virtual environment after installing Cairo. Use **Rescan engines** after installing an engine. Ordinary images, tables, archives and subtitles need no FFmpeg/Cairo setup.

### Conversion boundaries

FluxFile supports useful conversions within compatible families; no converter can turn every arbitrary file into every other format. Proprietary CAD, raw camera formats, encrypted files, DRM-protected ebooks and OCR are not included in this release.

Media output uses the first video/audio stream. Audio extraction uses the first audio stream. Extra tracks and embedded subtitles are omitted; lossy targets re-encode. GIF video output is limited to 640 pixels wide at 12 fps. Installed FFmpeg encoders determine actual media availability, and missing codecs produce a visible error.

Table conversion preserves cell values and sheet names, not workbook formulas, macros or formatting. Subtitle conversion preserves timing and cue text; WebVTT styling, regions, cue identifiers and positioning are omitted. PDF text/HTML export does not OCR scanned pages. PDF image rendering is capped at approximately 512 MiB of raster data.

Archive repacking preserves regular-file contents, paths and empty directories, not original permissions or metadata. It refuses links, special files, duplicate/unsafe paths, more than 10,000 entries, and expanded contents over 512 MiB. It never extracts archive members onto the filesystem. SVG rendering rejects external resource references and stylesheet imports.

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
