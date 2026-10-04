#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fluxfile_core import Job, VERSION, safe_relative_dir

SESSION_SCHEMA = "fluxfile-queue-session"
SESSION_VERSION = 1
SAFE_STATUSES = {"Queued", "Done", "Failed", "Unsupported", "Skipped", "Cancelled", "Missing"}


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temp, path)


def save_session(path: Path, jobs: list[Job], settings: dict[str, Any]) -> Path:
    path = path.expanduser()
    payload = {
        "schema": SESSION_SCHEMA,
        "version": SESSION_VERSION,
        "fluxfile_version": VERSION,
        "settings": {
            "output_dir": str(settings.get("output_dir", "")),
            "source_choice": str(settings.get("source_choice", "any")),
            "target_choice": str(settings.get("target_choice", "auto")),
            "conflict": str(settings.get("conflict", "suffix")),
            "recursive": bool(settings.get("recursive", False)),
            "layout": str(settings.get("layout", "flat")),
        },
        "jobs": [asdict(job) for job in jobs],
    }
    _atomic_json(path, payload)
    return path


def load_session(path: Path) -> tuple[list[Job], dict[str, Any]]:
    path = path.expanduser()
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if payload.get("schema") != SESSION_SCHEMA:
        raise ValueError("This is not a FluxFile queue session.")
    if int(payload.get("version", 0)) != SESSION_VERSION:
        raise ValueError(f"Unsupported FluxFile queue session version: {payload.get('version')}")

    settings_raw = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    settings = {
        "output_dir": str(settings_raw.get("output_dir", "")),
        "source_choice": str(settings_raw.get("source_choice", "any")),
        "target_choice": str(settings_raw.get("target_choice", "auto")),
        "conflict": str(settings_raw.get("conflict", "suffix")),
        "recursive": bool(settings_raw.get("recursive", False)),
        "layout": str(settings_raw.get("layout", "flat")) if settings_raw.get("layout") in {"flat", "preserve"} else "flat",
    }

    jobs: list[Job] = []
    raw_jobs = payload.get("jobs")
    if not isinstance(raw_jobs, list):
        raise ValueError("FluxFile session does not contain a valid jobs list.")

    for raw in raw_jobs:
        if not isinstance(raw, dict):
            continue
        source = str(raw.get("source", "")).strip()
        if not source:
            continue
        output = str(raw.get("output", "")).strip()
        source_exists = Path(source).is_file()
        status = str(raw.get("status", "Queued"))
        if status not in SAFE_STATUSES:
            status = "Queued"
        if not source_exists:
            status = "Missing"
        elif status == "Done" and (not output or not Path(output).is_file()):
            status = "Queued"
            output = ""
        elif status in {"Converting", "Cancelled", "Failed", "Skipped", "Unsupported", "Missing"}:
            status = "Queued"
            output = ""

        jobs.append(Job(
            id=str(raw.get("id") or os.urandom(8).hex()),
            source=source,
            source_format=str(raw.get("source_format", "")),
            target_format=str(raw.get("target_format", "")),
            status=status,
            engine=str(raw.get("engine", "")),
            output=output,
            error="" if status in {"Queued", "Done"} else str(raw.get("error", "")),
            duration_seconds=float(raw.get("duration_seconds", 0.0) or 0.0),
            input_bytes=int(raw.get("input_bytes", 0) or 0),
            output_bytes=int(raw.get("output_bytes", 0) or 0),
            relative_dir=safe_relative_dir(raw.get("relative_dir", "")),
        ))
    return jobs, settings
