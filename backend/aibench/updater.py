"""Self-update: check GitHub Releases and upgrade the installed app.

The packaged Windows app is a self-contained bundle (frozen Python runtime +
packages, web UI, and the llama.cpp/MLPerf binaries), so updating means
downloading the newer release's installer and letting it upgrade in place and
restart. That single step updates the app *and* every bundled dependency /
framework as one consistent, tested unit — avoiding partial/incompatible
piecemeal updates.

Design notes:
- The update feed is the repo's GitHub "latest release" (overridable via
  ``AIBENCH_UPDATE_API_URL`` for testing/self-hosting).
- The running version is ``__version__`` (overridable via ``AIBENCH_VERSION``).
- Parsing / version comparison / command building are pure functions so the
  logic is unit-tested even though the Windows install+restart can only run on
  Windows.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import httpx

from . import __version__, config

DEFAULT_API_URL = "https://api.github.com/repos/eachan/AI-Bench/releases/latest"
_KEY_PACKAGES = ["fastapi", "uvicorn", "pydantic", "numpy", "httpx", "psutil"]


def current_version() -> str:
    return os.environ.get("AIBENCH_VERSION") or __version__


def api_url() -> str:
    return os.environ.get("AIBENCH_UPDATE_API_URL") or DEFAULT_API_URL


def is_packaged() -> bool:
    return bool(getattr(sys, "frozen", False))


# --------------------------------------------------------------------------- #
# Pure helpers (unit-tested)
# --------------------------------------------------------------------------- #
def _ver_tuple(v: str) -> tuple[int, ...]:
    v = re.sub(r"^[vV]", "", (v or "").strip())
    nums: list[int] = []
    for part in re.split(r"[.\-+]", v):
        m = re.match(r"\d+", part)
        if not m:
            break
        nums.append(int(m.group()))
    return tuple(nums) or (0,)


def compare_versions(a: str, b: str) -> int:
    """Return -1 if a<b, 0 if equal, 1 if a>b (semver-ish, tolerant)."""

    ta, tb = _ver_tuple(a), _ver_tuple(b)
    n = max(len(ta), len(tb))
    ta += (0,) * (n - len(ta))
    tb += (0,) * (n - len(tb))
    return (ta > tb) - (ta < tb)


def parse_release(data: dict) -> dict:
    """Extract the fields we need from a GitHub release object."""

    tag = data.get("tag_name") or data.get("name") or ""
    version = re.sub(r"^[vV]", "", tag.strip())
    assets = data.get("assets") or []

    def _first(pred) -> Optional[dict]:
        return next((a for a in assets if pred((a.get("name") or "").lower())), None)

    exe = _first(lambda n: n.endswith(".exe"))
    zip_ = _first(lambda n: n.endswith(".zip"))
    return {
        "version": version,
        "tag": tag,
        "notes": data.get("body") or "",
        "url": data.get("html_url"),
        "published_at": data.get("published_at"),
        "installer_url": (exe or {}).get("browser_download_url"),
        "installer_name": (exe or {}).get("name"),
        "installer_size": (exe or {}).get("size"),
        "zip_url": (zip_ or {}).get("browser_download_url"),
    }


def bundled_components() -> list[dict]:
    """List the frameworks/binaries that update together with the app."""

    import importlib.metadata as md

    comps: list[dict] = [{"name": "AI-Bench", "version": current_version()}]
    for pkg in _KEY_PACKAGES:
        try:
            comps.append({"name": pkg, "version": md.version(pkg)})
        except Exception:  # noqa: BLE001
            pass
    comps.append(
        {"name": "llama.cpp (llama-bench)", "version": "bundled" if config.LLAMA_BENCH_PATH else "not installed"}
    )
    comps.append(
        {"name": "MLPerf Client", "version": "bundled" if config.MLPERF_CLIENT_PATH else "not installed"}
    )
    return comps


def build_windows_installer_cmd(exe_path: str) -> list[str]:
    """Silent upgrade that closes and restarts the running app.

    ``/CLOSEAPPLICATIONS`` + ``/RESTARTAPPLICATIONS`` use the Windows Restart
    Manager (the installer declares ``CloseApplications``/``RestartApplications``)
    so the running AI-Bench is closed for the file swap and relaunched after.
    """

    return [
        str(exe_path),
        "/SILENT",
        "/SUPPRESSMSGBOXES",
        "/NOCANCEL",
        "/CLOSEAPPLICATIONS",
        "/RESTARTAPPLICATIONS",
    ]


# --------------------------------------------------------------------------- #
# Check
# --------------------------------------------------------------------------- #
def check_for_update(timeout: float = 10.0) -> dict:
    cur = current_version()
    base = {"current_version": cur, "components": bundled_components(), "packaged": is_packaged()}
    try:
        resp = httpx.get(
            api_url(),
            headers={"Accept": "application/vnd.github+json", "User-Agent": "AI-Bench-Updater"},
            timeout=timeout,
            follow_redirects=True,
        )
        if resp.status_code == 404:
            return {**base, "update_available": False, "status": "no_releases",
                    "message": "No releases have been published yet."}
        resp.raise_for_status()
        rel = parse_release(resp.json())
        available = bool(rel["version"]) and compare_versions(cur, rel["version"]) < 0
        return {
            **base,
            "latest_version": rel["version"],
            "release": rel,
            "update_available": available,
            "status": "update_available" if available else "up_to_date",
        }
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        return {**base, "update_available": False, "status": "error", "message": str(exc)}


# --------------------------------------------------------------------------- #
# Apply (download installer, then upgrade+restart on Windows)
# --------------------------------------------------------------------------- #
@dataclass
class UpdateState:
    status: str = "idle"  # idle|checking|downloading|installing|unsupported|error|done
    percent: float = 0.0
    message: Optional[str] = None
    version: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


_state = UpdateState()
_lock = threading.Lock()


def get_state() -> UpdateState:
    return _state


def _download(url: str, dest: Path, state: UpdateState) -> None:
    with httpx.stream("GET", url, follow_redirects=True, timeout=None) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0) or 0)
        got = 0
        with open(dest, "wb") as fh:
            for chunk in resp.iter_bytes(chunk_size=1024 * 256):
                fh.write(chunk)
                got += len(chunk)
                if total:
                    state.percent = round(got / total * 100.0, 1)


def _apply_worker(state: UpdateState) -> None:
    info = check_for_update()
    if not info.get("update_available"):
        state.status = "error"
        state.message = "No update available."
        return
    rel = info["release"]
    state.version = rel["version"]
    url = rel.get("installer_url") or rel.get("zip_url")
    if not url:
        state.status = "error"
        state.message = "Release has no downloadable installer asset."
        return

    config.ensure_dirs()
    suffix = ".exe" if (rel.get("installer_url") and url == rel["installer_url"]) else ".zip"
    dest = config.DATA_DIR / f"AI-Bench-Update-{rel['version']}{suffix}"
    state.status = "downloading"
    state.percent = 0.0
    try:
        _download(url, dest, state)
    except Exception as exc:  # noqa: BLE001
        state.status = "error"
        state.message = f"Download failed: {exc}"
        return

    # Only the packaged Windows app can self-install & restart.
    if is_packaged() and os.name == "nt" and suffix == ".exe":
        state.status = "installing"
        state.message = "Installing update — the app will close and restart automatically."
        cmd = build_windows_installer_cmd(str(dest))
        try:
            subprocess.Popen(cmd, close_fds=True)
        except Exception as exc:  # noqa: BLE001
            state.status = "error"
            state.message = f"Failed to launch installer: {exc}"
            return
        # Exit shortly so the installer can replace files; Restart Manager
        # relaunches the app afterwards.
        threading.Timer(3.0, lambda: os._exit(0)).start()
    else:
        state.status = "unsupported"
        state.message = (
            f"Downloaded {dest.name}. Automatic in-place install & restart runs in the "
            "packaged Windows app. In development, update via git and reinstall dependencies."
        )


def start_apply() -> UpdateState:
    global _state
    with _lock:
        if _state.status in {"downloading", "installing"}:
            return _state
        _state = UpdateState(status="downloading", percent=0.0, message="Starting…")
    threading.Thread(target=_apply_worker, args=(_state,), name="aibench-update", daemon=True).start()
    return _state
