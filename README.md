# FluxFile

FluxFile is Groundstate Technology LLC's local-first bulk file conversion workstation.

Version **0.11.0** is the portable-session recovery release. It keeps the 0.10 bulk workflow, upgrades queue sessions to a move-aware v2 schema, preserves v1 compatibility, and adds explicit recovery tools for sources that were moved or mounted somewhere else.

## New in 0.11.0

### Portable sessions and recovery

- Queue session schema **v2** stores a safe relative reference when a source/output lives inside the folder containing the `.fluxqueue.json` file.
- Move that whole workspace folder to another drive or machine and FluxFile resolves those relative references from the new session location.
- External files remain absolute references instead of being rewritten deceptively.
- Existing queue session **v1** files continue to load.
- **Relink missing** chooses a new source root and repairs missing jobs from their saved relative folder + filename.
- Right-click **Relink selected source…** repairs an individual queue item.
- **Ctrl+Shift+R** opens the bulk relink workflow.
- Relinked jobs are re-detected, re-sized, and either queued or explicitly marked Unsupported for the currently installed engines.
- Session files still contain no source-file contents.

### Bulk workflow

- **Folder layout** selector: `flat` preserves the established behavior; `preserve` recreates each queued folder-relative subdirectory under the output directory.
- **Save queue / Load queue** stores conversion plans as `.fluxqueue.json` session files.
- Completed session jobs stay completed only when their recorded output still exists.
- Failed/cancelled/skipped session jobs resume as queued work.
- Missing source files load as **Missing** instead of failing in the middle of a batch.
- Recursive folder entries display their relative path in the queue so same-named files are easy to distinguish.
- CLI directory collection now deduplicates a file even if it is supplied both directly and through a folder.
- JSON/CSV reports include each job's `relative_dir` and the batch output layout.

### Desktop workflow

- Cleaner **Plan → Intake → Queue → Progress → Actions** layout.
- Queue columns are reduced to Source, Route, Engine, Status, and Result.
- Full paths/errors move to a selected-item detail line instead of crowding the table.
- Queue rows update incrementally instead of deleting/rebuilding the entire Treeview after every status change.
- Determinate batch progress, item counts, Cancel, Retry, and selected-output opening.
- Context menu and keyboard shortcuts:
  - **Ctrl+O** add files
  - **Ctrl+Shift+O** add folder
  - **Ctrl+Enter** convert queued items
  - **Delete** remove selected
  - **Ctrl+A** select all
  - **Ctrl+Shift+S** save queue session
  - **Ctrl+Shift+L** load queue session
  - **Ctrl+Shift+R** relink missing sources
  - **F5** rescan engines
  - **Esc** cancel
- Format guide is now a readable resizable window instead of a dense message box.

### Backend organization

```text
fluxfile_core.py     format registry, routing, conversion engines, intake/path safety
fluxfile_batch.py    bounded concurrency, cancellation, output reservation, folder layout, reports
fluxfile_session.py  portable queue serialization, safe resume rules, missing-source relinking
extended_formats.py  FFmpeg/media, subtitle, archive and SVG helpers
fluxfile.py          desktop UI only; re-exports legacy core imports for compatibility
fluxfile_cli.py      headless batch client using the same scheduler/core
```

See `docs/ARCHITECTURE.md` for the ownership rules between these modules.

### Performance and reliability

- Bounded parallel batch execution; default worker count is automatically selected up to four.
- Set `FLUXFILE_WORKERS=1..8` to override the default, or use `--workers` in the CLI.
- FFmpeg is limited to two simultaneous jobs to avoid resource thrashing.
- LibreOffice and PDF→DOCX are serialized because those engines are heavier and less concurrency-friendly.
- Conversion-route decisions are cached per Engine instance.
- Pillow output capability discovery is cached instead of re-probing on every queue row.
- Recursive folder discovery now **prunes** `.git`, `.venv`, `node_modules`, cache directories, hidden trees, and the active output directory before walking them.
- Parallel jobs reserve destinations before conversion, preventing equal basenames from racing for the same output file.
- Compound archive names stay clean: `bundle.tar.gz → bundle.zip`, not `bundle.tar.zip`.
- External converter cancellation terminates the active subprocess instead of waiting for its normal timeout.
- Reports now include per-job duration, input bytes, output bytes, worker count, and aggregate status counts.
- JSON/CSV reports themselves are written atomically.

A synthetic 16-job scheduler benchmark during development measured about **4× throughput with four workers versus one**. Real conversion speedups depend on file type, codec, storage, CPU and the engine-specific concurrency limits above.

## Conversion families

| Family | Routes | Engine |
| --- | --- | --- |
| Audio | MP3, WAV, FLAC, OGG, OPUS, M4A, AAC, AIFF | FFmpeg |
| Video | MP4, MKV, MOV, AVI, WebM, animated GIF; audio extraction | FFmpeg |
| Images | PNG/JPG/BMP/GIF/TIFF/WebP plus ICO, ICNS, PPM, TGA, AVIF where supported | Pillow |
| Vector | SVG → PNG / PDF | optional CairoSVG + Cairo |
| PDF | DOCX, TXT, HTML; single-page PNG/JPG; all pages as TIFF | pdf2docx / PyMuPDF |
| Data | CSV, TSV, JSON, JSONL, XLS/XLSX, ODS | pandas / spreadsheet engines |
| Documents | Markdown, HTML, DOCX, ODT, RTF, EPUB, TXT | Pandoc / LibreOffice |
| Presentations | PPT/PPTX/ODP → supported office targets / PDF | LibreOffice |
| Subtitles | SRT ↔ VTT | built in |
| Archives | ZIP / TAR / TGZ / TBZ2 / TXZ repacking | built in |

FluxFile supports useful conversions within compatible families; it does not pretend every arbitrary file can become every other arbitrary format.

## Integrity boundaries

- Failed conversions do not replace an existing destination; output is staged and atomically published after success.
- Animated images preserve frames only in multi-frame-capable targets; destructive flattening is refused.
- Multi-page PDF → PNG/JPG is refused; use TIFF to preserve all pages.
- Multi-sheet workbooks preserve sheets when targeting XLSX/ODS; flattening to CSV/TSV/JSON is refused rather than silently discarding sheets.
- Table conversion preserves cell values and sheet names, not formulas, macros, workbook formatting, or embedded objects.
- PDF TXT/HTML export does not OCR scanned pages.
- Media conversion uses the first video/audio stream; extra tracks and embedded subtitles are omitted.
- Archive repacking rejects links, special files, duplicate/unsafe paths, more than 10,000 entries, and expanded content above 512 MiB.
- SVG rendering rejects external resources and stylesheet imports.
- Encrypted files, DRM, proprietary CAD, raw-camera workflows, and OCR remain outside the current scope.

## Desktop quick start

### Ubuntu

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip python3-tk pandoc libreoffice ffmpeg
git clone https://github.com/GroundstateTech/FluxFile.git
cd FluxFile
chmod +x fluxfile.sh
./fluxfile.sh
```

SVG rendering additionally needs Cairo and the optional Python requirements:

```bash
sudo apt install -y libcairo2
.venv/bin/python -m pip install -r requirements-optional.txt
```

### Windows

Install Python 3.10+ and optionally Pandoc, LibreOffice, and FFmpeg, then run:

```bat
run_fluxfile.bat
```

The launchers validate Python, repair an incomplete `.venv`, and only reinstall Python requirements when `requirements.txt` changes.

## CLI

The CLI now accepts multiple files and folders and uses the same batch scheduler as the GUI:

```bash
python fluxfile_cli.py --engines
python fluxfile_cli.py recording.mp4 --to mp3 --output-dir converted
python fluxfile_cli.py input-a input-b --recursive --to auto --workers 4
python fluxfile_cli.py photos --recursive --layout preserve --to webp --output-dir converted
python fluxfile_cli.py folder --recursive --to png --conflict suffix --json
```

`--workers` accepts 1–8. The default is also available through `FLUXFILE_WORKERS`. `--layout preserve` mirrors recursive source subdirectories; the default `flat` mode remains backward-compatible.

## Queue behavior

1. Choose **From** and **To**.
2. Add files or a folder.
3. Optionally enable **Include subfolders**.
4. Review the detected route and engine.
5. Use **Apply to queue** when changing an existing plan.
6. Choose `flat` or `preserve` folder layout.
7. Choose `suffix`, `skip`, or `overwrite` for existing outputs.
8. Optionally **Save queue** if you want to resume the plan later. Save it beside the source workspace when you want move-aware relative references.
9. If a loaded queue reports missing sources, use **Relink missing** to select the replacement source root, or right-click one row and use **Relink selected source…**.
10. Convert.
11. Cancel if necessary; completed outputs remain valid and unfinished jobs are marked Cancelled.
12. Select failed/cancelled rows and use **Retry** to explicitly requeue them.

Completed jobs are not silently rerun on the next pass.

## Verify

```bash
python scripts/doctor.py --strict
python -m compileall -q fluxfile_core.py fluxfile_batch.py fluxfile_session.py fluxfile.py fluxfile_cli.py extended_formats.py
python fluxfile_cli.py --engines
python -m unittest discover -s tests -v
```

CI executes the core suite on **Windows and Ubuntu with Python 3.10–3.14**, plus an extended Ubuntu job with FFmpeg/Cairo.

## Repository layout

```text
fluxfile_core.py            conversion core and routing
fluxfile_batch.py           parallel scheduler, folder layout, cancellation and reports
fluxfile_session.py         queue session persistence / resume validation
extended_formats.py         media/archive/subtitle/SVG helpers
fluxfile.py                 desktop application
fluxfile_cli.py             headless batch client
requirements.txt            core Python dependencies
requirements-optional.txt   optional SVG dependency
fluxfile.sh                 canonical Ubuntu/Linux launcher
run_fluxfile.sh             Linux compatibility launcher
run_fluxfile.bat            Windows launcher
scripts/bootstrap.py        dependency-stamp/bootstrap helper
scripts/doctor.py           dependency + architecture diagnostics
tests/                      regression, conversion, batch and CLI tests
docs/ARCHITECTURE.md        module ownership and backend design
docs/UBUNTU.md              Ubuntu setup and troubleshooting
```

FluxFile performs conversion locally and does not upload source files to Groundstate or a cloud conversion service.

Copyright © 2026 Groundstate Technology LLC.
