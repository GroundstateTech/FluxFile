#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import platform
import shutil
import sys
from pathlib import Path

MIN_PYTHON = (3, 10)
REQUIRED_MODULES = ("PIL", "pandas", "openpyxl", "odf", "xlrd", "pymupdf", "pdf2docx")
ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="FluxFile environment diagnostics")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero when Python, Tkinter, internal modules, or a requirements.txt module is unavailable",
    )
    args = parser.parse_args()

    failures: list[str] = []
    print("FluxFile doctor")
    print(f"Python: {sys.version.split()[0]} ({platform.platform()})")
    if sys.version_info[:3] < MIN_PYTHON:
        failures.append(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required")

    print("Tkinter: ", end="")
    try:
        import tkinter  # noqa: F401
        print("OK")
    except Exception as exc:
        print(f"MISSING ({exc})")
        failures.append("Tkinter missing")

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    print("FluxFile architecture: ", end="")
    try:
        from fluxfile_core import VERSION
        from fluxfile_batch import recommended_workers
        from fluxfile_session import SESSION_VERSION
        from fluxfile_queue import PROBLEM_STATUSES
        print(f"OK (v{VERSION}, queue schema={SESSION_VERSION}, problem states={len(PROBLEM_STATUSES)}, default workers={recommended_workers()})")
    except Exception as exc:
        print(f"BROKEN ({exc})")
        failures.append(f"FluxFile internal import failed: {exc}")

    print("\nOptional external engines:")
    for binary in ("pandoc", "libreoffice", "soffice", "ffmpeg"):
        print(f"  {binary}: {shutil.which(binary) or 'not found'}")

    print("\nPython conversion modules:")
    for module in REQUIRED_MODULES:
        installed = importlib.util.find_spec(module) is not None
        print(f"  {module}: {'OK' if installed else 'not installed'}")
        if not installed:
            failures.append(f"{module} not installed")

    if failures:
        print("\nProblems:")
        for failure in failures:
            print(f"  - {failure}")
        return 1 if args.strict else 0

    print("\nCore environment: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
