# Changelog

## 0.7.0 — 2026-09-30

Reliability / bug-hunt release.

### Fixed

- recursive intake could traverse `.git`, `.venv`, `node_modules`, and other hidden/internal directories
- the compatibility picker could advertise cross-family Office routes that the engine layer could not reliably produce
- a single unsupported job could block the entire queue
- existing output files could be partially overwritten when a conversion failed
- LibreOffice headless conversion could conflict with an already-running desktop LibreOffice profile
- external converters had no timeout
- worker-thread UI notifications depended on direct Tk calls
- queue controls remained mutable during an active conversion pass
- report filenames could collide when two runs finished in the same second
- launchers reinstalled Python dependencies on every start
- Linux and Windows launchers did not explicitly reject Python versions older than 3.10

### Added

- atomic conversion staging
- isolated LibreOffice profiles
- dependency-stamp bootstrap helper
- strict doctor mode
- Python 3.10–3.13 Ubuntu/Windows CI matrix
- real CSV/XLSX, JSON/CSV, image, and PDF-text conversion smoke tests
- EXIF orientation correction before image export
- multi-sheet XLS/XLSX/ODS preservation when converting between workbook formats
- explicit refusal to flatten multi-sheet workbooks into CSV/TSV/JSON where sheets would be silently lost
- Python 3.14 CI coverage
