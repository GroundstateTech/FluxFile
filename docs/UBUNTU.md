# Ubuntu support

FluxFile is supported as a desktop application on Ubuntu 22.04 LTS and Ubuntu 24.04 LTS.

## Install system prerequisites

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip python3-tk pandoc libreoffice
```

Pandoc and LibreOffice are optional conversion engines, but installing both gives FluxFile the widest document/office coverage.

## Run

```bash
chmod +x run_fluxfile.sh
./run_fluxfile.sh
```

The launcher creates `.venv`, installs Python dependencies, and starts the GUI.

## Verify the environment

```bash
. .venv/bin/activate
python scripts/doctor.py
python -m unittest discover -s tests -v
```

## Notes

- FluxFile does not require Wine.
- PDF → DOCX uses the optional `pdf2docx` Python package.
- Office conversion quality depends on LibreOffice's support for the source format.
- Pandoc is used only for conversions it natively supports.
- Some proprietary or malformed files cannot be converted reliably; FluxFile reports those jobs as failed rather than silently producing misleading output.
