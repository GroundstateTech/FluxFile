#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

MIN_PYTHON = (3, 10)


def digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Install/update FluxFile Python dependencies only when needed")
    parser.add_argument("--force", action="store_true", help="force dependency installation")
    args = parser.parse_args()

    if sys.version_info < MIN_PYTHON:
        print(
            f"FluxFile requires Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+; "
            f"found {sys.version.split()[0]}",
            file=sys.stderr,
        )
        return 2

    root = Path(__file__).resolve().parents[1]
    requirements = root / "requirements.txt"
    venv = Path(sys.prefix)
    stamp = venv / ".fluxfile-requirements.sha256"
    wanted = digest_file(requirements)

    if not args.force and stamp.exists() and stamp.read_text(encoding="utf-8").strip() == wanted:
        print("FluxFile dependencies are already current.")
        return 0

    print("FluxFile: installing/updating Python dependencies...")
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run([sys.executable, "-m", "pip", "install", "-r", str(requirements)])
    stamp.write_text(wanted + "\n", encoding="utf-8")
    print("FluxFile dependencies are current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
