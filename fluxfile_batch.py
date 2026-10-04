#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import threading
import time
from concurrent.futures import CancelledError as FutureCancelledError, Future, ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from fluxfile_core import ConversionCancelled, Engine, Job, VERSION, normalize_format, resolve_output, safe_relative_dir


@dataclass
class BatchEvent:
    kind: str
    job: Job | None = None
    completed: int = 0
    total: int = 0
    message: str = ""


@dataclass
class BatchSummary:
    started_unix: float
    finished_unix: float
    workers: int
    json_report: str
    csv_report: str
    counts: dict[str, int]

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.finished_unix - self.started_unix)


def recommended_workers() -> int:
    raw = os.getenv("FLUXFILE_WORKERS", "").strip()
    if raw:
        try:
            return max(1, min(8, int(raw)))
        except ValueError:
            pass
    return max(1, min(4, os.cpu_count() or 2))


class BatchRunner:
    """Bounded parallel batch execution with output reservation and cancellation."""

    def __init__(self, engine: Engine | None = None, workers: int | None = None):
        self.engine = engine or Engine()
        self.workers = max(1, min(8, workers or recommended_workers()))
        self.cancel_event = threading.Event()
        self._exclusive_gate = threading.Semaphore(1)
        self._ffmpeg_gate = threading.Semaphore(min(2, self.workers))

    def cancel(self) -> None:
        self.cancel_event.set()

    def _emit(self, callback: Callable[[BatchEvent], None] | None, event: BatchEvent) -> None:
        if callback is None:
            return
        try:
            callback(event)
        except Exception:
            pass

    def _gate_for(self, engine_name: str):
        if engine_name in {"libreoffice", "pdf2docx"}:
            return self._exclusive_gate
        if engine_name == "ffmpeg":
            return self._ffmpeg_gate
        return nullcontext()

    def _run_one(self, job: Job, output: Path, callback: Callable[[BatchEvent], None] | None, total: int) -> Job:
        if self.cancel_event.is_set():
            job.status = "Cancelled"
            job.error = "Cancelled before start"
            self._emit(callback, BatchEvent("job", job=job, total=total))
            return job

        source = Path(job.source)
        started = time.monotonic()
        job.status = "Converting"
        job.error = ""
        job.output = str(output)
        self._emit(callback, BatchEvent("job", job=job, total=total))

        try:
            job.input_bytes = source.stat().st_size if source.exists() else 0
            with self._gate_for(job.engine):
                used = self.engine.convert(source, output, self.cancel_event)
            job.engine = used
            job.status = "Done"
            job.output_bytes = output.stat().st_size if output.exists() else 0
        except ConversionCancelled as exc:
            job.status = "Cancelled"
            job.error = str(exc)
            job.output_bytes = 0
            job.output = ""
        except Exception as exc:
            job.status = "Failed"
            job.error = str(exc)
            job.output_bytes = 0
            job.output = ""
        finally:
            job.duration_seconds = round(time.monotonic() - started, 4)
        self._emit(callback, BatchEvent("job", job=job, total=total))
        return job

    def run(
        self,
        jobs: list[Job],
        out_dir: Path,
        conflict: str = "suffix",
        callback: Callable[[BatchEvent], None] | None = None,
        layout: str = "flat",
    ) -> BatchSummary:
        if layout not in {"flat", "preserve"}:
            raise ValueError("layout must be 'flat' or 'preserve'")
        self.cancel_event.clear()
        started_unix = time.time()
        out_dir = out_dir.expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        total = len(jobs)
        completed = 0
        reserved: set[Path] = set()
        planned: list[tuple[Job, Path]] = []

        self._emit(callback, BatchEvent("start", completed=0, total=total, message=f"Using {self.workers} worker(s)"))

        for job in jobs:
            job.duration_seconds = 0.0
            job.output_bytes = 0
            job.error = ""
            engine_name = self.engine.engine_for(job.source_format, job.target_format)
            job.engine = engine_name or "unavailable"
            if not engine_name:
                job.status = "Unsupported"
                job.output = ""
                job.error = f"No installed engine supports .{job.source_format} → .{job.target_format}"
                completed += 1
                self._emit(callback, BatchEvent("job", job=job, completed=completed, total=total))
                continue

            job_out_dir = out_dir
            relative_dir = safe_relative_dir(job.relative_dir)
            if layout == "preserve" and relative_dir:
                job_out_dir = out_dir / Path(relative_dir)
            output = resolve_output(Path(job.source), job_out_dir, normalize_format(job.target_format), conflict, reserved)
            if output is None:
                job.status = "Skipped"
                job.output = ""
                job.error = "Output exists"
                completed += 1
                self._emit(callback, BatchEvent("job", job=job, completed=completed, total=total))
                continue
            job.output = str(output)
            job.status = "Queued"
            planned.append((job, output))

        futures: dict[Future[Job], Job] = {}
        with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="fluxfile") as pool:
            for job, output in planned:
                if self.cancel_event.is_set():
                    job.status = "Cancelled"
                    job.output = ""
                    job.error = "Cancelled before start"
                    completed += 1
                    self._emit(callback, BatchEvent("job", job=job, completed=completed, total=total))
                    continue
                future = pool.submit(self._run_one, job, output, callback, total)
                futures[future] = job

            for future in as_completed(futures):
                job = futures[future]
                try:
                    future.result()
                except FutureCancelledError:
                    job.status = "Cancelled"
                    job.error = "Cancelled before start"
                    job.output = ""
                except Exception as exc:
                    job.status = "Failed"
                    job.error = f"Batch worker error: {exc}"
                    job.output = ""
                completed += 1
                self._emit(callback, BatchEvent("progress", job=job, completed=completed, total=total))
                if self.cancel_event.is_set():
                    for pending in futures:
                        pending.cancel()

        for job in jobs:
            if job.status in {"Queued", "Converting"}:
                job.status = "Cancelled" if self.cancel_event.is_set() else "Failed"
                job.error = "Cancelled" if self.cancel_event.is_set() else "Worker did not complete"
                job.output = ""

        finished_unix = time.time()
        counts: dict[str, int] = {}
        for job in jobs:
            counts[job.status] = counts.get(job.status, 0) + 1

        json_report, csv_report = self._write_reports(
            jobs=jobs,
            out_dir=out_dir,
            started_unix=started_unix,
            finished_unix=finished_unix,
            counts=counts,
            layout=layout,
        )
        summary = BatchSummary(
            started_unix=started_unix,
            finished_unix=finished_unix,
            workers=self.workers,
            json_report=str(json_report),
            csv_report=str(csv_report),
            counts=counts,
        )
        self._emit(callback, BatchEvent("complete", completed=total, total=total, message=json.dumps(asdict(summary))))
        return summary

    def _write_reports(
        self,
        jobs: list[Job],
        out_dir: Path,
        started_unix: float,
        finished_unix: float,
        counts: dict[str, int],
        layout: str,
    ) -> tuple[Path, Path]:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        json_report = out_dir / f"fluxfile-report-{stamp}.json"
        csv_report = out_dir / f"fluxfile-report-{stamp}.csv"
        payload = {
            "fluxfile_version": VERSION,
            "started_unix": started_unix,
            "finished_unix": finished_unix,
            "duration_seconds": round(max(0.0, finished_unix - started_unix), 4),
            "workers": self.workers,
            "layout": layout,
            "platform": os.sys.platform,
            "engines": self.engine.capabilities(),
            "counts": counts,
            "jobs": [asdict(job) for job in jobs],
        }
        json_tmp = json_report.with_suffix(json_report.suffix + ".tmp")
        json_tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(json_tmp, json_report)

        csv_tmp = csv_report.with_suffix(csv_report.suffix + ".tmp")
        with csv_tmp.open("w", newline="", encoding="utf-8") as fh:
            fields = [
                "source", "source_format", "target_format", "engine", "status", "output", "error",
                "duration_seconds", "input_bytes", "output_bytes", "relative_dir",
            ]
            writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(asdict(job) for job in jobs)
        os.replace(csv_tmp, csv_report)
        return json_report, csv_report
