# FluxFile architecture

FluxFile is intentionally split into four layers. Keep new work inside the narrowest layer that owns it.

## 1. `fluxfile_core.py` — conversion core

Owns:

- format normalization and source detection
- compatible target lists and auto-target selection
- source/output path safety
- folder discovery and internal-directory pruning
- `Job`
- local engine detection
- conversion routing
- atomic output publication
- engine-specific conversion implementations for the original core families

Must **not** own Tkinter widgets, dialogs, queue rendering, or batch-thread policy.

The core may call the helpers in `extended_formats.py`.

## 2. `extended_formats.py` — focused format helpers

Owns the specialized helper implementations introduced with the 0.8 format expansion:

- FFmpeg command construction
- subtitle conversion
- archive repacking
- SVG rendering
- the associated media/archive/image format constants

Keep security/integrity validation close to the format implementation: archive path validation belongs with archive code; SVG external-resource validation belongs with SVG rendering.

Do not put desktop UI code here.

## 3. `fluxfile_batch.py` — scheduling and reporting

Owns:

- bounded parallel execution
- cancellation state
- engine concurrency gates
- parallel destination reservation
- batch progress events
- job timing/byte metrics
- JSON and CSV reports

It accepts `Job` objects and an `Engine`; it does not know about Tkinter.

Concurrency policy currently is:

- general work: up to the configured worker pool
- FFmpeg: at most 2 simultaneously
- LibreOffice: 1
- PDF → DOCX: 1

The default pool is 1–4 workers based on the host CPU. `FLUXFILE_WORKERS` and CLI `--workers` may select 1–8.

Any future engine that is not safely parallel should receive its own gate here rather than embedding scheduler logic inside the conversion implementation.

## 4. `fluxfile_session.py` — queue persistence

Owns:

- atomic `.fluxqueue.json` session serialization
- session schema/version validation and v1 → v2 compatibility
- safe relative path references anchored to the session directory
- restoring saved UI/batch settings
- resume rules for completed, failed, cancelled and missing jobs
- deterministic missing-source relinking

Session files contain paths and queue metadata, not copies of source files. Relative references are used only when the referenced path is inside the session directory tree; external paths remain explicit absolute references.

## 5. `fluxfile_queue.py` — queue operations

Owns:

- queue search and status-filter predicates
- problem-state classification
- safe requeue/revalidation behavior
- completed-row cleanup policy

This module does not know about Tkinter and does not run conversions. Filters affect presentation only; they never decide which queued jobs the batch scheduler receives.

## 6. `fluxfile.py` — desktop shell

Owns:

- Tkinter layout and interaction
- queue presentation
- file/folder and relinking dialogs
- incremental Treeview updates
- keyboard/context-menu actions
- queue search/filter presentation
- progress presentation
- sending batch events across the UI queue

It re-exports the established public core names so existing code/tests importing `Engine`, `compatible_targets`, etc. from `fluxfile` continue to work.

Do not add conversion implementations to this file.

## 7. `fluxfile_cli.py` — headless client

The CLI is a client of `fluxfile_core` and `fluxfile_batch`, just like the desktop UI.

There should not be a separate CLI conversion engine. A behavior difference between GUI and CLI should normally be treated as a bug.

## Data-flow

```text
files/folders
    │
    ▼
fluxfile_core: detect + create Job
    │
    ▼
fluxfile_batch: reserve outputs + apply flat/preserve layout + schedule
    │
    ├──> Engine.convert(...)
    │       └──> extended_formats helpers where needed
    │
    ▼
BatchEvent / BatchSummary
    │
    ├──> desktop UI queue + progress
    └──> CLI text/JSON output
```

## Performance rules

1. Never rebuild the full desktop queue for a single job-status change.
2. Prune ignored directories before recursive traversal; do not discover them and discard them afterward.
3. Cache conversion-routing/capability data that is invariant for the life of an Engine instance.
4. Reserve output paths before parallel execution.
5. Publish converted files atomically.
6. Bound concurrency; more workers are not automatically faster for media or office engines.
7. Cancellation must stop external processes where practical and leave staged outputs unpublished.

## Test expectations

A backend change should preserve:

- existing conversion-core tests
- real conversion smoke tests
- extended media/archive/SVG/PDF tests
- batch concurrency/cancellation/reservation tests
- CLI integration tests
- portable session / legacy-session / relinking tests
- queue search/filter/bulk-operation tests

CI compiles every top-level module before executing the tests on Windows and Ubuntu across Python 3.10–3.14.
