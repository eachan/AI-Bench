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

def _bin_roots() -> list[Path]:
    """Candidate ``bin/`` roots for benchmark binaries bundled with a packaged
    (PyInstaller) app: next to the executable, its ``_internal`` dir, and the
    ``_MEIPASS`` temp dir."""

    exe_dir = Path(sys.executable).resolve().parent
    roots = [exe_dir / "bin", exe_dir / "_internal" / "bin"]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass) / "bin")
    return roots


def _search_bin(patterns: list[str]) -> str | None:
    for root in _bin_roots():
        if not root.exists():
            continue
        for pat in patterns:
            for match in sorted(root.rglob(pat)):
                if match.is_file():
                    return str(match)
    return None


def _resolve_binary(env_var: str, patterns: list[str]) -> str | None:
    override = os.environ.get(env_var)
    if override:
        return override
    # Only auto-discover bundled binaries in a packaged app.
    if not getattr(sys, "frozen", False):
        return None
    return _search_bin(patterns)


_EXE_SUFFIX = ".exe" if os.name == "nt" else ""

if os.name == "nt":
    _MLPERF_PATTERNS = ["mlperf-windows-x64.exe", "mlperf-windows.exe", "mlperf.exe"]
else:
    _MLPERF_PATTERNS = ["mlperf-linux", "mlperf-macos", "mlperf"]

# Optional paths to external benchmark binaries. The Windows installer bundles
# these; when unset the app falls back to the built-in synthetic benchmarks so
# it is always usable out of the box.
LLAMA_BENCH_PATH = _resolve_binary("AIBENCH_LLAMA_BENCH", [f"llama-bench{_EXE_SUFFIX}"])
MLPERF_CLIENT_PATH = _resolve_binary("AIBENCH_MLPERF_CLIENT", _MLPERF_PATTERNS)

# Directory that holds the MLPerf Client's stock scenario configs (llm/,
# agentic/, image-gen/). These ship next to the binary. Overridable for dev.
MLPERF_HOME = os.environ.get("AIBENCH_MLPERF_HOME") or (
    str(Path(MLPERF_CLIENT_PATH).resolve().parent) if MLPERF_CLIENT_PATH else None
)


def ensure_dirs() -> None:
    for d in (DATA_DIR, MODELS_DIR, DATASETS_DIR, RUNS_DIR, CONFIGS_DIR, BIN_DIR):
        d.mkdir(parents=True, exist_ok=True)
