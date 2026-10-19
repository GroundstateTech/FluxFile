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

## Required before a public product release

- Record the chosen source commit, version, Python/OS versions, dependency inventory, and external converter versions.
- On Windows and Linux, launch the desktop UI and exercise intake, conversion, cancellation, queue save/load, recovery, retries, relinking, and output conflicts.
- Convert representative real files for each advertised route with the required external engines installed. Inspect the output and preserve source files; a successful process exit does not establish fidelity.
- Check install/start instructions from a clean user environment. Confirm missing external engines produce actionable messages.
- Verify runtime dependency advisories for the resolved release environment.
- Confirm redistribution permissions and the intended project license. This repository currently has no root license file; do not infer a license from public visibility.
- Record known limitations and checksums for any distributed package.

These gates do not require a public server or paid artifact storage. A CI pass is validation evidence, not a published or retained release binary.
