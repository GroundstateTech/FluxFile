# Ubuntu support

FluxFile is supported as a desktop application on Ubuntu 22.04 LTS and Ubuntu 24.04 LTS, with Python 3.10 or newer.

## Install system prerequisites

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip python3-tk pandoc libreoffice
```

Pandoc and LibreOffice are optional conversion engines, but installing both gives FluxFile the widest document/office coverage.

## Run

```bash
chmod +x fluxfile.sh
./fluxfile.sh
```

`run_fluxfile.sh` remains as a compatibility wrapper.

The launcher verifies Python, repairs an incomplete `.venv`, creates the virtual environment when needed, and runs `scripts/bootstrap.py`. Python packages are reinstalled only when `requirements.txt` changes, so normal launches do not require a fresh network install every time.

## Verify the environment

```bash
.venv/bin/python scripts/doctor.py --strict
.venv/bin/python -m unittest discover -s tests -v
```

`doctor.py --strict` treats the Python version, Tkinter, and Python conversion dependencies as required. Pandoc and LibreOffice remain optional and are reported separately.

## Recursive folder behavior

When **Include subfolders** is enabled, FluxFile deliberately ignores:

- hidden directories such as `.git`
- `.venv` / `venv`
- `__pycache__`
- `node_modules`
- the currently selected output directory

This prevents repository metadata, installed packages, and FluxFile's own prior outputs from being accidentally re-queued.

## LibreOffice behavior

Headless LibreOffice conversion uses a temporary isolated user profile for each job. This reduces conflicts with an already-running LibreOffice desktop process. Temporary profiles are removed after the job.

## Notes

- FluxFile does not require Wine.
- PDF → DOCX uses `pdf2docx`.
- PDF → TXT uses PyMuPDF.
- Office conversion quality depends on LibreOffice's support for the source document.
- Pandoc is used only for routes FluxFile explicitly recognizes.
- External conversion processes time out after five minutes instead of hanging indefinitely.
- Conversion output is staged to a temporary sibling file and atomically moved into place after success.
- Some proprietary, encrypted, or malformed files cannot be converted reliably; FluxFile records those jobs as failed instead of silently producing misleading output.
