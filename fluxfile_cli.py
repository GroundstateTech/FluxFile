#!/usr/bin/env python3
"""Headless batch conversion using the same FluxFile core and scheduler as the GUI."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from fluxfile_batch import BatchEvent, BatchRunner, recommended_workers
from fluxfile_core import Engine, create_job, discover_folder_files, normalize_format


def main() -> int:
    parser = argparse.ArgumentParser(description="FluxFile local batch converter")
    parser.add_argument("sources", nargs="*", type=Path, help="Files or folders to convert")
    parser.add_argument("--to", help="Target format, or 'auto' for the per-file recommended target")
    parser.add_argument("--output-dir", type=Path, default=Path("converted"))
    parser.add_argument("--conflict", choices=["suffix", "skip", "overwrite"], default="suffix")
    parser.add_argument("--recursive", action="store_true", help="Include subfolders for directory sources")
    parser.add_argument("--workers", type=int, default=recommended_workers(), help="Parallel workers (1-8)")
    parser.add_argument("--engines", action="store_true", help="Print installed engine availability")
    parser.add_argument("--json", action="store_true", help="Print the final summary as JSON")
    args = parser.parse_args()

    engine = Engine()
    if args.engines:
        print(json.dumps(engine.capabilities(), indent=2))
        return 0
    if not args.sources or not args.to:
        parser.error("at least one source and --to are required unless --engines is used")
    if not 1 <= args.workers <= 8:
        parser.error("--workers must be between 1 and 8")

    paths: list[Path] = []
    for source in args.sources:
        if source.is_file():
            paths.append(source)
        elif source.is_dir():
            paths.extend(discover_folder_files(source, args.recursive, args.output_dir))
        else:
            parser.error(f"source does not exist: {source}")
    if not paths:
        parser.error("no files found")

    target = normalize_format(args.to)
    jobs = [create_job(path, target, engine) for path in paths]
    runner = BatchRunner(engine, workers=args.workers)

    def on_event(event: BatchEvent):
        if args.json:
            return
        if event.kind == "progress" and event.job is not None:
            print(f"[{event.completed}/{event.total}] {event.job.status:11} {Path(event.job.source).name}")

    summary = runner.run(jobs, args.output_dir, args.conflict, callback=on_event)
    if args.json:
        print(json.dumps({
            "counts": summary.counts,
            "duration_seconds": summary.duration_seconds,
            "workers": summary.workers,
            "json_report": summary.json_report,
            "csv_report": summary.csv_report,
        }, indent=2))
    else:
        print(f"Finished in {summary.duration_seconds:.2f}s with {summary.workers} worker(s): {summary.counts}")
        print(f"Report: {summary.json_report}")
    return 1 if any(summary.counts.get(name, 0) for name in ("Failed", "Unsupported", "Cancelled")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
