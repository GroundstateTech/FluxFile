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

## Microsoft Store release path

Target Windows x64 MSIX first. Microsoft signs MSIX submissions for Store distribution.
The Windows SDK tools still require a separate development signature and trusted
certificate to install a local test copy.

| Machine | Release check |
| --- | --- |
| Ubuntu workstation (muchateta) | Launch the source GUI and run the Linux checks above before compiling. |
| Windows workstation | Launch the source GUI, run the checks above, and build the x64 one-folder app with the existing PyInstaller spec. Use a clean virtual environment and dist folder. |
| Windows workstation (Windows SDK developer PowerShell) | Stage the full PyInstaller runtime into MSIX with the command below. |
| Clean Windows x64 VM | Test-sign and install a test copy. Launch from the Start menu, confirm conversion and queue recovery, then test an in-place upgrade and uninstall. Run the Windows App Certification Kit. |

Reserve the listing name and copy the package name, publisher ID, publisher display name,
and reserved app name exactly from Partner Center. Use a four-part Store package
version with a nonzero first part and zero final part. The MSIX package version
can advance independently of the version shown inside FluxFile.

```powershell
$packageName = Read-Host 'Package identity name'
$publisher = Read-Host 'Publisher ID'
$publisherDisplayName = Read-Host 'Publisher display name'
$appName = Read-Host 'Reserved app name'
$packageVersion = Read-Host 'Four-part package version (e.g. 1.0.0.0)'
.\.venv\Scripts\python.exe scripts\make_msix.py --name $packageName --publisher $publisher --publisher-display-name $publisherDisplayName --display-name $appName --version $packageVersion
```

If MakeAppx is outside PATH, add `--makeappx` with its full SDK path. The
command writes an unsigned package to `dist/`. Retain that file for Store
submission and sign a separate copy for VM testing. Packaged conversions
default to `FluxFile\converted` in the user's home folder. The user can
choose another output folder in the app.

### Submission checks

- Decide the project's license and the terms for distributing PyMuPDF/MuPDF
  before uploading any binary. Upstream offers AGPL and commercial licensing.
  Confirm the terms and notices for the resolved Python dependencies, native
  libraries and any external engines selected for distribution.
- FFmpeg, LibreOffice and Pandoc are separate installs under this recipe.
  Verify engine discovery and conversion from the installed MSIX on the VM.
  Include MP4 → MP3 with FFmpeg and check the missing-engine flow on a
  clean VM. State these prerequisites in the Store listing.
- Confirm how the installed app and its engines handle local files, queue
  paths and recovery data. Prepare the listing screenshots, support contact
  and privacy disclosures from the tested package.
- Explain the `runFullTrust` capability during submission. The packaged
  desktop app accesses user-selected files and launches installed converters.
  After certification, use limited distribution before broad release.

[Microsoft Store readiness checklist](https://learn.microsoft.com/en-us/windows/apps/publish/store-readiness-checklist) · [PyMuPDF licensing](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright)
