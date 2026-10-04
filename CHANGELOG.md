# Changelog

## 0.11.0 — 2026-10-03

Portable session and missing-source recovery release.

### Added

- Queue session schema v2 with relative source/output references when paths live under the session directory.
- Move-aware output-directory references.
- Backward-compatible loading of v1 queue sessions.
- Bulk **Relink missing** workflow using saved relative folders and original filenames.
- Per-item **Relink selected source…** context action.
- `Ctrl+Shift+R` shortcut for missing-source recovery.
- Cross-platform Windows-path basename recovery for sessions moved between operating systems.
- Regression tests for workspace moves, v1 compatibility, bulk relinking, and Windows-style missing paths.

### Fixed

- A queue described as portable no longer depends exclusively on stale absolute paths when the session and workspace are moved together.
- Missing source recovery no longer requires deleting and rebuilding the affected queue entries.


## 0.10.0 — 2026-10-03

Bulk workflow and resumability release.

### Added

- Flat vs preserved recursive output-folder layout in the desktop app and CLI.
- Safe relative-directory metadata on queue jobs.
- `.fluxqueue.json` queue session save/load with atomic writes.
- Resume rules that keep valid completed outputs, requeue incomplete work, and flag missing sources.
- Save/load keyboard shortcuts and queue-path display for recursive jobs.
- CLI source deduplication when the same file arrives through overlapping arguments.
- Relative folder metadata and layout mode in conversion reports.
- Cross-platform tests for preserved folder layout, session round trips, missing-file recovery, and CLI deduplication.

### Fixed

- Applying a new plan can no longer turn a missing source into runnable work.
- Recursive bulk jobs no longer have to flatten same-named files into suffixed filenames when preserved layout is selected.


## 0.9.0 — 2026-10-03

Workstation architecture, UI cleanup and batch-performance release.

### Architecture

- Split the monolithic desktop module into `fluxfile_core.py`, `fluxfile_batch.py`, and the thinner `fluxfile.py` desktop shell.
- Kept legacy imports such as `from fluxfile import Engine` working through explicit re-exports.
- Upgraded the CLI to use the same core and scheduler as the GUI.
- Added `docs/ARCHITECTURE.md` to define module ownership and prevent future UI/backend entanglement.
- Doctor now validates FluxFile's internal module graph in addition to dependencies.

### UI / workflow

- Reorganized the window into Plan, Intake, Queue, Progress, and Actions.
- Reduced queue-table clutter and moved full paths/errors to a selected-item detail line.
- Added determinate progress, Cancel, Retry, selected-output opening, context actions, and keyboard shortcuts.
- Replaced repeated full Treeview rebuilds with incremental row updates.
- Replaced the small format-guide message box with a resizable guide window.
- Finished jobs no longer rerun implicitly; Retry explicitly requeues them.

### Performance / backend

- Added bounded parallel batch execution with automatic worker selection (up to four by default, configurable to 1–8).
- Limited FFmpeg to two concurrent conversions and serialized LibreOffice/PDF→DOCX heavy paths.
- Cached route selection and Pillow save-capability discovery.
- Replaced recursive `rglob()` intake with pruned `os.walk()` traversal so ignored trees are never walked.
- Added destination reservation so parallel equal-basename jobs cannot race or overwrite each other.
- Added active subprocess cancellation for external converters.
- Added per-job duration/input/output metrics and richer aggregate reports.
- Made report writes atomic.
- Fixed compound archive destination names such as `bundle.tar.gz → bundle.zip`.
- Development scheduler benchmark: 16 synthetic jobs measured ~4× throughput at four workers versus one.

### Tests / CI

- Added scheduler concurrency, cancellation, output-reservation, recursive-pruning and compound-archive tests.
- Added CLI integration tests covering multi-source same-name batches.
- CI now compiles the split modules and smoke-tests `fluxfile_cli.py --engines` before running tests.
- Existing Windows/Ubuntu Python 3.10–3.14 coverage and the extended FFmpeg/Cairo job remain in place.

## 0.8.0 — 2026-10-02

- Added FFmpeg audio/video conversion, audio extraction and video GIF output.
- Added local SVG rendering, image/icon formats, JSONL, subtitles and archive repacking.
- Added PDF HTML/page-image export, with all-page TIFF output.
- Preserve image frames or refuse destructive flattening; retain atomic output protection.
- Added Format guide and headless CLI, optional-engine setup and explicit conversion boundaries.
- Added real round-trip, media, SVG, PDF/frame integrity and archive safety tests.

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
