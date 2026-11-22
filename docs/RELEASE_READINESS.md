# Release verification without hosted artifact storage

FluxFile verification runs without uploading packages. The workflow records resolved Python dependencies in each job log and rejects incompatible installed dependencies with `pip check`. Dependency compatibility is not a vulnerability audit or proof of conversion fidelity.

## Local verification

Run from a clean checkout using the project's activated virtual environment:

```sh
python -m pip install -r requirements.txt
python -m pip check
python scripts/doctor.py --strict
python -m unittest discover -s tests -v
python fluxfile_cli.py --engines
python -m pip freeze > release-dependencies.txt
git rev-parse HEAD > release-commit.txt
```

The requirements describe supported ranges. `release-dependencies.txt` records one actual environment, including transitive dependencies; it is not a universal cross-platform lockfile. Keep this record with the Python/OS versions and any candidate package on your own machine. Do not commit local file paths or private conversion reports.

## Runtime compatibility gate (2026-11-20)

Core `requirements.txt` requires `Pillow>=13.0.0,<14`, whose declared interpreter requirement is **Python >=3.11**. The earlier 3.10 CI jobs and launchers could therefore fail during dependency installation, before FluxFile tests began. Keep the Windows/Ubuntu CI floor, `scripts/doctor.py`, `scripts/bootstrap.py` and launchers aligned at Python 3.11+; do not work around it by downgrading to a vulnerable older Pillow series. If support for Python 3.10 becomes essential, resolve compatible patched dependencies and their security status first, and document that as a separate reviewed decision.

## Required before a public product release

- Record the chosen source commit, version, Python/OS versions, dependency inventory, and external converter versions.
- On Windows and Linux, launch the desktop UI and exercise intake, conversion, cancellation, queue save/load, recovery, retries, relinking, and output conflicts.
- Convert representative real files for each advertised route with the required external engines installed. Inspect the output and preserve source files; a successful process exit does not establish fidelity.
- Check install/start instructions from a clean user environment. Confirm missing external engines produce actionable messages.
- Verify runtime dependency advisories for the resolved release environment.
- Confirm redistribution permissions and the intended project license. This repository currently has no root license file; do not infer a license from public visibility.
- Record known limitations and checksums for any distributed package.

These gates do not require a public server or paid artifact storage. A CI pass is validation evidence, not a published or retained release binary.

## Desktop packaging draft

The PyInstaller spec in `packaging/FluxFile.spec` prepares a one-folder desktop build. Its build dependencies live in `packaging/requirements-build.txt`. The runtime uses `requirements.txt`; FFmpeg, LibreOffice, Pandoc, and the optional Cairo SVG stack are installed separately. Portable engine binaries can go under `engines/` beside the packaged executable.

Wait for the source desktop app to pass on the Windows workstation and on muchateta before making a package. Build separately on each target OS. On the Windows workstation, the future build commands from the FluxFile checkout are:

```powershell
.\.venv\Scripts\python.exe -m pip install -r packaging\requirements-build.txt
.\.venv\Scripts\python.exe -m PyInstaller --clean packaging\FluxFile.spec
```

Test the entire `dist/FluxFile` folder on a clean Windows account before distribution. Include both appearance modes, queue recovery, PNG → QOI, XLSM → XLSX, and MP4 → MP3 with an installed FFmpeg. Confirm that external tools launch without opening console windows and that startup errors remain diagnosable. Generate the checksum from the final archive after those checks.
