#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping

from fluxfile_core import Job
from fluxfile_session import load_session, save_session

RECOVERY_FILENAME = "recovery.fluxqueue.json"


def recovery_path(
    *,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    platform: str | None = None,
) -> Path:
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else Path(home)

    if platform.startswith("win"):
        base = env.get("LOCALAPPDATA")
        if base:
            return Path(base) / "FluxFile" / RECOVERY_FILENAME
        return home / "AppData" / "Local" / "FluxFile" / RECOVERY_FILENAME

    state_home = env.get("XDG_STATE_HOME")
    if state_home:
        return Path(state_home) / "fluxfile" / RECOVERY_FILENAME
    return home / ".local" / "state" / "fluxfile" / RECOVERY_FILENAME


def save_recovery(
    jobs: list[Job],
    settings: dict[str, object],
    path: Path | None = None,
) -> Path | None:
    target = recovery_path() if path is None else Path(path)
    if not jobs:
        clear_recovery(target)
        return None
    return save_session(target, jobs, settings)


def load_recovery(path: Path | None = None) -> tuple[list[Job], dict[str, object]]:
    target = recovery_path() if path is None else Path(path)
    return load_session(target)


def recovery_exists(path: Path | None = None) -> bool:
    target = recovery_path() if path is None else Path(path)
    return target.is_file() and target.stat().st_size > 0


def clear_recovery(path: Path | None = None) -> bool:
    target = recovery_path() if path is None else Path(path)
    try:
        target.unlink()
        return True
    except FileNotFoundError:
        return False
