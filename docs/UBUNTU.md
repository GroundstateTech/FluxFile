# Ubuntu support

FluxFile is supported as a desktop application on Ubuntu 22.04 LTS and Ubuntu 24.04 LTS with Python 3.10 or newer.

## Install system prerequisites

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip python3-tk pandoc libreoffice ffmpeg
```

Pandoc, LibreOffice, and FFmpeg are optional conversion engines. Install only the engines you need.

SVG rendering additionally requires Cairo plus the optional Python package:

```bash
sudo apt install -y libcairo2
.venv/bin/python -m pip install -r requirements-optional.txt
```

## Run

```bash
chmod +x fluxfile.sh
./fluxfile.sh
```

`run_fluxfile.sh` remains as a compatibility wrapper.

The launcher verifies Python, repairs an incomplete `.venv`, creates the virtual environment when needed, and runs `scripts/bootstrap.py`. Core Python packages are reinstalled only when `requirements.txt` changes.

## 0.9 batch performance

FluxFile 0.9 uses bounded parallel execution. The default is selected automatically up to four workers.

Override the desktop/CLI default with:

```bash
FLUXFILE_WORKERS=2 ./fluxfile.sh
```

or use the CLI:

```bash
.venv/bin/python fluxfile_cli.py input-folder --recursive --to auto --workers 4
```

Worker limits are deliberately conservative:

- FFmpeg: maximum two jobs concurrently
- LibreOffice: one
- PDF → DOCX: one
- lighter built-in/Pillow/pandas work: up to the selected pool

## Verify the environment

```bash
.venv/bin/python scripts/doctor.py --strict
.venv/bin/python -m compileall -q fluxfile_core.py fluxfile_batch.py fluxfile.py fluxfile_cli.py extended_formats.py
.venv/bin/python fluxfile_cli.py --engines
.venv/bin/python -m unittest discover -s tests -v
```

`doctor.py --strict` checks Python, Tkinter, FluxFile's internal module split, and core Python conversion dependencies. External engines remain optional and are reported separately.

## Recursive folder behavior

When **Include subfolders** is enabled, FluxFile prunes ignored trees before descending into them:

- hidden directories such as `.git`
- `.venv` / `venv`
- `__pycache__`
- `node_modules`
- common Python tool caches
- the selected output directory

This avoids wasting time walking dependency trees that can contain tens of thousands of files.

## Cancellation

The desktop **Cancel** action stops scheduling new work and signals active jobs. Running FFmpeg, Pandoc, and LibreOffice subprocesses are terminated rather than waiting for the normal five-minute timeout. Pure-Python conversions stop between jobs; a conversion already executing inside a library may finish its current operation before returning.

Completed files remain valid because conversion output is staged and atomically published only after success.

## Notes

- FluxFile does not require Wine.
- PDF → DOCX uses `pdf2docx`.
- PDF → TXT/HTML/page images use PyMuPDF.
- Office conversion quality depends on LibreOffice's support for the source document.
- Pandoc is used only for routes FluxFile explicitly recognizes.
- Some proprietary, encrypted, malformed, or DRM-protected files cannot be converted reliably; FluxFile records those jobs as failed rather than silently producing misleading output.
