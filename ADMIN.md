# FluxFile administrator and operator guide

[Project README](README.md) · [Repository](https://github.com/GroundstateTech/FluxFile)

## Start

Windows: `run_fluxfile.bat`; Ubuntu: `bash fluxfile.sh`. `run_fluxfile.sh` remains a compatibility alias. Launchers bootstrap the local environment.

## Frontend to backend

`fluxfile.py` GUI and `fluxfile_cli.py` CLI → `fluxfile_batch.py` scheduler → `fluxfile_core.py` / `extended_formats.py` engines. Queue filtering and retry live in `fluxfile_queue.py`; portable sessions in `fluxfile_session.py`; recovery in `fluxfile_recovery.py`.

## Find the controls

No web backend or admin login is required. `python fluxfile_cli.py --engines` lists installed engines. `python scripts/doctor.py --strict` checks setup. Add FFmpeg, LibreOffice or optional SVG support only for the routes you need.

## Connection and configuration

Example: `python fluxfile_cli.py input.txt --to txt --output-dir converted --json`. GUI and CLI use the same engines. Failed, missing or unsupported queue items can be retried/relinked; output conflict rules are explicit.

## Data and recovery

Export `.fluxqueue.json` for portable queues. Automatic recovery is per-user: Windows LocalAppData/FluxFile; Linux XDG_STATE_HOME/fluxfile or `~/.local/state/fluxfile`. A queue contains paths and metadata, not copies of input/output files.

## Validation

`python -m unittest discover -s tests -v`; `python scripts/doctor.py --strict`; `python fluxfile_cli.py --engines`. Invalid session metrics and duplicate IDs are rejected before import.

## Remaining release work

Verify representative conversions with installed external engines and desktop UI. Preserve inputs and inspect fidelity; format availability alone does not prove a lossless conversion.

