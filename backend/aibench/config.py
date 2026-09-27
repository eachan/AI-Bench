"""Runtime configuration and filesystem layout for AI-Bench.

All user data (results database, downloaded models/datasets, generated benchmark
configs and logs) lives under a single application data directory so the app is
easy to install, back up, and fully uninstall. Locations can be overridden with
environment variables, which the Windows installer/launcher sets.
"""

from __future__ import annotations

import os
import sys
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

def _bundled_binary(name: str) -> str | None:
    """Locate a benchmark binary bundled next to a packaged (PyInstaller) app.

    Checks, in order: a ``bin/`` dir next to the executable (PyInstaller
    onedir), the PyInstaller ``_internal`` dir, and the ``_MEIPASS`` temp dir.
    Returns ``None`` when nothing is found (dev / not packaged).
    """

    candidates = []
    exe_dir = Path(sys.executable).resolve().parent
    candidates += [exe_dir / "bin" / name, exe_dir / "_internal" / "bin" / name]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "bin" / name)
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def _resolve_binary(env_var: str, exe_name: str) -> str | None:
    override = os.environ.get(env_var)
    if override:
        return override
    only_when_frozen = getattr(sys, "frozen", False)
    return _bundled_binary(exe_name) if only_when_frozen else None


_EXE_SUFFIX = ".exe" if os.name == "nt" else ""

# Optional paths to external benchmark binaries. The Windows installer bundles
# these; when unset the app falls back to the built-in synthetic benchmarks so
# it is always usable out of the box.
LLAMA_BENCH_PATH = _resolve_binary("AIBENCH_LLAMA_BENCH", f"llama-bench{_EXE_SUFFIX}")
MLPERF_CLIENT_PATH = _resolve_binary("AIBENCH_MLPERF_CLIENT", f"mlperf{_EXE_SUFFIX}")


def ensure_dirs() -> None:
    for d in (DATA_DIR, MODELS_DIR, DATASETS_DIR, RUNS_DIR, CONFIGS_DIR, BIN_DIR):
        d.mkdir(parents=True, exist_ok=True)
