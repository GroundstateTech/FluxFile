#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any

from fluxfile_core import Engine, Job, VERSION, safe_relative_dir, source_format

SESSION_SCHEMA = "fluxfile-queue-session"
SESSION_VERSION = 2
SUPPORTED_SESSION_VERSIONS = {1, 2}
SAFE_STATUSES = {"Queued", "Done", "Failed", "Unsupported", "Skipped", "Cancelled", "Missing"}


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _path_reference(value: str | Path, base_dir: Path) -> dict[str, str]:
    raw = str(value or "").strip()
    if not raw:
        return {"kind": "empty", "path": ""}
    candidate = Path(raw).expanduser()
    try:
        resolved = candidate.resolve(strict=False)
        relative = resolved.relative_to(base_dir.resolve(strict=False))
        safe = safe_relative_dir(relative.as_posix())
        if safe:
            return {"kind": "relative", "path": safe}
    except (OSError, ValueError):
        pass
    return {"kind": "absolute", "path": raw}


def _resolve_reference(reference: Any, base_dir: Path, fallback: str = "") -> str:
    if not isinstance(reference, dict):
        return fallback
    kind = str(reference.get("kind", "")).strip().lower()
    raw = str(reference.get("path", "")).strip()
    if kind == "empty":
        return ""
    if kind == "relative":
        safe = safe_relative_dir(raw)
        if not safe:
            return fallback
        return str((base_dir / Path(safe)).resolve(strict=False))
    if kind == "absolute":
        return raw
    return fallback


def _portable_source_name(value: str | Path) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    windows_name = PureWindowsPath(raw).name
    native_name = Path(raw).name
    return windows_name if ("\\" in raw or PureWindowsPath(raw).drive) else native_name


def _serialize_job(job: Job, base_dir: Path) -> dict[str, Any]:
    raw = asdict(job)
    raw["source_ref"] = _path_reference(job.source, base_dir)
    raw["output_ref"] = _path_reference(job.output, base_dir)
    return raw


def save_session(path: Path, jobs: list[Job], settings: dict[str, Any]) -> Path:
    path = path.expanduser().resolve(strict=False)
    base_dir = path.parent
    payload = {
        "schema": SESSION_SCHEMA,
        "version": SESSION_VERSION,
        "fluxfile_version": VERSION,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "settings": {
            "output_dir": str(settings.get("output_dir", "")),
            "output_dir_ref": _path_reference(str(settings.get("output_dir", "")), base_dir),
            "source_choice": str(settings.get("source_choice", "any")),
            "target_choice": str(settings.get("target_choice", "auto")),
            "conflict": str(settings.get("conflict", "suffix")),
            "recursive": bool(settings.get("recursive", False)),
            "layout": str(settings.get("layout", "flat")),
        },
        "jobs": [_serialize_job(job, base_dir) for job in jobs],
    }
    _atomic_json(path, payload)
    return path


def _load_job(raw: dict[str, Any], base_dir: Path, version: int) -> Job | None:
    fallback_source = str(raw.get("source", "")).strip()
    fallback_output = str(raw.get("output", "")).strip()
    source = (
        _resolve_reference(raw.get("source_ref"), base_dir, fallback_source)
        if version >= 2 else fallback_source
    )
    output = (
        _resolve_reference(raw.get("output_ref"), base_dir, fallback_output)
        if version >= 2 else fallback_output
    )
    if not source:
        return None

    source_exists = Path(source).is_file()
    status = str(raw.get("status", "Queued"))
    if status not in SAFE_STATUSES:
        status = "Queued"
    if not source_exists:
        status = "Missing"
        output = ""
    elif status == "Done" and (not output or not Path(output).is_file()):
        status = "Queued"
        output = ""
    elif status in {"Converting", "Cancelled", "Failed", "Skipped", "Unsupported", "Missing"}:
        status = "Queued"
        output = ""

    try:
        duration = float(raw.get("duration_seconds", 0.0) or 0.0)
        input_bytes = int(raw.get("input_bytes", 0) or 0)
        output_bytes = int(raw.get("output_bytes", 0) or 0)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("Queue session contains invalid job metrics.") from exc
    if not math.isfinite(duration) or min(duration, input_bytes, output_bytes) < 0:
        raise ValueError("Queue session job metrics must be finite and nonnegative.")
    return Job(
        id=str(raw.get("id") or os.urandom(8).hex()),
        source=source,
        source_format=str(raw.get("source_format", "")),
        target_format=str(raw.get("target_format", "")),
        status=status,
        engine=str(raw.get("engine", "")),
        output=output,
        error="" if status in {"Queued", "Done"} else str(raw.get("error", "")),
        duration_seconds=duration,
        input_bytes=input_bytes,
        output_bytes=output_bytes,
        relative_dir=safe_relative_dir(raw.get("relative_dir", "")),
    )


def load_session(path: Path) -> tuple[list[Job], dict[str, Any]]:
    path = path.expanduser().resolve(strict=False)
    base_dir = path.parent
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("schema") != SESSION_SCHEMA:
        raise ValueError("This is not a FluxFile queue session.")
    raw_version = payload.get("version", 0)
    if isinstance(raw_version, bool) or not isinstance(raw_version, (int, str)):
        raise ValueError("Queue session version must be an integer.")
    try:
        version = int(raw_version)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("Queue session version must be an integer.") from exc
    if version not in SUPPORTED_SESSION_VERSIONS:
        raise ValueError(f"Unsupported FluxFile queue session version: {payload.get('version')}")

    settings_raw = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    output_fallback = str(settings_raw.get("output_dir", ""))
    output_dir = (
        _resolve_reference(settings_raw.get("output_dir_ref"), base_dir, output_fallback)
        if version >= 2 else output_fallback
    )
    settings = {
        "output_dir": output_dir,
        "source_choice": str(settings_raw.get("source_choice", "any")),
        "target_choice": str(settings_raw.get("target_choice", "auto")),
        "conflict": str(settings_raw.get("conflict", "suffix")),
        "recursive": bool(settings_raw.get("recursive", False)),
        "layout": str(settings_raw.get("layout", "flat")) if settings_raw.get("layout") in ("flat", "preserve") else "flat",
        "session_version": version,
    }

    raw_jobs = payload.get("jobs")
    if not isinstance(raw_jobs, list):
        raise ValueError("FluxFile session does not contain a valid jobs list.")

    jobs: list[Job] = []
    identifiers = set()
    for raw in raw_jobs:
        if not isinstance(raw, dict):
            continue
        job = _load_job(raw, base_dir, version)
        if job is not None:
            if job.id in identifiers:
                raise ValueError("Queue session contains duplicate job IDs.")
            identifiers.add(job.id)
            jobs.append(job)
    return jobs, settings


def relink_job(job: Job, source: Path, engine: Engine) -> Job:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(str(source))
    job.source = str(source)
    job.source_format = source_format(source)
    job.input_bytes = source.stat().st_size
    job.output = ""
    job.output_bytes = 0
    job.duration_seconds = 0.0
    job.error = ""
    job.engine = engine.engine_for(job.source_format, job.target_format) or "unavailable"
    job.status = "Queued" if job.engine != "unavailable" else "Unsupported"
    if job.status == "Unsupported":
        job.error = f"No installed engine supports .{job.source_format} → .{job.target_format}"
    return job


def relink_missing_jobs(jobs: list[Job], source_root: Path, engine: Engine) -> tuple[int, int]:
    source_root = source_root.expanduser().resolve()
    if not source_root.is_dir():
        raise NotADirectoryError(str(source_root))
    relinked = 0
    unresolved = 0
    for job in jobs:
        current_source = Path(job.source)
        if current_source.is_file():
            if job.status == "Missing":
                relink_job(job, current_source, engine)
                relinked += 1
            continue
        relative = safe_relative_dir(job.relative_dir)
        name = _portable_source_name(job.source)
        candidate = source_root / Path(relative) / name if relative else source_root / name
        if name and candidate.is_file():
            relink_job(job, candidate, engine)
            relinked += 1
        else:
            job.status = "Missing"
            job.engine = "unavailable"
            job.output = ""
            job.error = "Source file is missing"
            unresolved += 1
    return relinked, unresolved
