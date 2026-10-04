#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from fluxfile_core import Engine, Job, source_format

PROBLEM_STATUSES = {"Failed", "Unsupported", "Skipped", "Cancelled", "Missing"}


def job_matches(job: Job, query: str = "", status_filter: str = "all") -> bool:
    status_filter = str(status_filter or "all").strip().lower()
    if status_filter == "queued" and job.status != "Queued":
        return False
    if status_filter == "done" and job.status != "Done":
        return False
    if status_filter == "problems" and job.status not in PROBLEM_STATUSES:
        return False
    if status_filter == "missing" and job.status != "Missing":
        return False
    if status_filter == "unsupported" and job.status != "Unsupported":
        return False

    needle = str(query or "").strip().lower()
    if not needle:
        return True
    haystack = " ".join(
        str(value or "")
        for value in (
            job.source,
            job.relative_dir,
            job.source_format,
            job.target_format,
            job.engine,
            job.status,
            job.output,
            job.error,
        )
    ).lower()
    return needle in haystack


def filter_jobs(jobs: list[Job], query: str = "", status_filter: str = "all") -> list[Job]:
    return [job for job in jobs if job_matches(job, query, status_filter)]


def requeue_job(job: Job, engine: Engine) -> Job:
    source = Path(job.source)
    job.output = ""
    job.output_bytes = 0
    job.duration_seconds = 0.0
    job.error = ""
    if not source.is_file():
        job.status = "Missing"
        job.engine = "unavailable"
        job.error = "Source file is missing"
        return job

    job.source_format = source_format(source)
    job.input_bytes = source.stat().st_size
    job.engine = engine.engine_for(job.source_format, job.target_format) or "unavailable"
    if job.engine == "unavailable":
        job.status = "Unsupported"
        job.error = f"No installed engine supports .{job.source_format} → .{job.target_format}"
    else:
        job.status = "Queued"
    return job


def requeue_problems(jobs: list[Job], engine: Engine) -> tuple[int, int]:
    queued = 0
    unresolved = 0
    for job in jobs:
        if job.status not in PROBLEM_STATUSES:
            continue
        requeue_job(job, engine)
        if job.status == "Queued":
            queued += 1
        else:
            unresolved += 1
    return queued, unresolved


def remove_completed(jobs: list[Job]) -> tuple[list[Job], int]:
    kept = [job for job in jobs if job.status != "Done"]
    return kept, len(jobs) - len(kept)
