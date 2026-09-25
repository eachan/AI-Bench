"""Runtime configuration and filesystem layout for AI-Bench.

All user data (results database, downloaded models/datasets, generated benchmark
configs and logs) lives under a single application data directory so the app is
easy to install, back up, and fully uninstall. Locations can be overridden with
environment variables, which the Windows installer/launcher sets.
"""

from __future__ import annotations

import os
from pathlib import Path


def _default_data_dir() -> Path:
    override = os.environ.get("AIBENCH_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(base) / "AI-Bench"
    # macOS / Linux
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "ai-bench"


DATA_DIR = _default_data_dir()
MODELS_DIR = DATA_DIR / "models"
DATASETS_DIR = DATA_DIR / "datasets"
RUNS_DIR = DATA_DIR / "runs"
CONFIGS_DIR = DATA_DIR / "configs"
BIN_DIR = DATA_DIR / "bin"
DB_PATH = DATA_DIR / "aibench.db"

# Optional paths to external benchmark binaries. The Windows installer downloads
# these; when unset the app falls back to the built-in synthetic benchmarks so it
# is always usable out of the box.
LLAMA_BENCH_PATH = os.environ.get("AIBENCH_LLAMA_BENCH")
MLPERF_CLIENT_PATH = os.environ.get("AIBENCH_MLPERF_CLIENT")


def ensure_dirs() -> None:
    for d in (DATA_DIR, MODELS_DIR, DATASETS_DIR, RUNS_DIR, CONFIGS_DIR, BIN_DIR):
        d.mkdir(parents=True, exist_ok=True)
