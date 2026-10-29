"""Runtime installer for benchmark engines (llama.cpp's llama-bench, MLPerf Client).

Lets the app download and install the external binaries a benchmark needs, on
demand, into the app data dir (``BIN_DIR``) — so "needs binary" tests become
runnable without reinstalling the whole app. Platform-aware and resilient to the
upstream release layout (llama.cpp ships binaries on rolling ``b#####``
prereleases, not ``releases/latest``).
"""

from __future__ import annotations

import platform
import shutil
import tarfile
import threading
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import httpx

from . import config

_LLAMA_REPO = "ggml-org/llama.cpp"
_MLPERF_REPO = "mlcommons/mlperf_client"
_MLPERF_TAG = "v2.0.1"
_UA = {"User-Agent": "AI-Bench-ToolInstaller", "Accept": "application/vnd.github+json"}


def _os() -> str:
    s = platform.system()
    return {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(s, "linux")


def resolve_variant(requested: str) -> str:
    """Resolve 'auto' to a concrete llama.cpp build based on detected GPUs.

    A discrete GPU → the Vulkan build (GPU-accelerated, uses the driver's Vulkan
    runtime, works for NVIDIA/AMD/Intel without a CUDA toolkit). Otherwise CPU.
    macOS uses the universal build (Metal) so variant is irrelevant there.
    """

    if requested and requested != "auto":
        return requested
    if _os() == "macos":
        return "cpu"
    try:
        from .hardware import detect_gpus

        if detect_gpus():
            return "vulkan"
    except Exception:  # noqa: BLE001
        pass
    return "cpu"


# --------------------------------------------------------------------------- #
# Asset selection (pure, testable)
# --------------------------------------------------------------------------- #
def select_llama_asset(assets: list[dict], os_name: str, variant: str = "cpu") -> Optional[dict]:
    """Pick the llama.cpp binary archive for this OS/variant.

    Matches the real naming, e.g. ``llama-b11982-bin-win-cpu-x64.zip`` /
    ``llama-b11982-bin-ubuntu-x64.tar.gz`` / ``llama-b11982-bin-macos-x64.tar.gz``.
    Excludes the ``cudart-*`` runtime-only archives.
    """

    if os_name == "windows":
        if variant == "cpu":
            needles = ["bin-win-cpu-x64.zip"]
        else:
            needles = [f"bin-win-{variant}-x64.zip", f"bin-win-{variant}-"]
    elif os_name == "macos":
        needles = ["bin-macos-arm64.tar.gz" if platform.machine().lower() in ("arm64", "aarch64")
                   else "bin-macos-x64.tar.gz", "bin-macos-x64.tar.gz"]
    else:  # linux
        if variant == "cpu":
            needles = ["bin-ubuntu-x64.tar.gz"]
        else:
            needles = [f"bin-ubuntu-{variant}-x64.tar.gz", f"bin-ubuntu-{variant}-"]

    for needle in needles:
        for a in assets:
            name = (a.get("name") or "")
            if name.startswith("llama-") and needle in name:
                return a
    return None


def select_mlperf_asset(assets: list[dict], os_name: str) -> Optional[dict]:
    if os_name == "windows":
        pred = lambda n: n.endswith("windows-x64.zip") and "gui" not in n  # noqa: E731
    elif os_name == "macos":
        pred = lambda n: "macos" in n and n.endswith(".zip") and "gui" not in n  # noqa: E731
    else:
        pred = lambda n: "ubuntu" in n and n.endswith(".zip") and "gui" not in n  # noqa: E731
    return next((a for a in assets if pred((a.get("name") or "").lower())), None)


# --------------------------------------------------------------------------- #
# Install state
# --------------------------------------------------------------------------- #
@dataclass
class InstallState:
    kind: str = ""
    status: str = "idle"  # idle|resolving|downloading|extracting|done|error
    percent: float = 0.0
    message: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


_state = InstallState()
_lock = threading.Lock()


def get_state() -> InstallState:
    return _state


def _latest_release_with_asset(repo: str, pick) -> tuple[Optional[dict], Optional[dict]]:
    """Return (release, asset) for the most recent release whose assets match."""
    resp = httpx.get(
        f"https://api.github.com/repos/{repo}/releases?per_page=15",
        headers=_UA, timeout=30, follow_redirects=True,
    )
    resp.raise_for_status()
    for rel in resp.json():
        asset = pick(rel.get("assets") or [])
        if asset:
            return rel, asset
    return None, None


def _release_by_tag(repo: str, tag: str, pick) -> tuple[Optional[dict], Optional[dict]]:
    resp = httpx.get(
        f"https://api.github.com/repos/{repo}/releases/tags/{tag}",
        headers=_UA, timeout=30, follow_redirects=True,
    )
    if resp.status_code == 404:
        return None, None
    resp.raise_for_status()
    rel = resp.json()
    return rel, pick(rel.get("assets") or [])


def _download(url: str, dest: Path, state: InstallState) -> None:
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


def _extract(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip" or archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest)
    else:
        with tarfile.open(archive) as t:
            t.extractall(dest)


def _copy_tree_contents(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def _install_llama(state: InstallState, variant: str) -> None:
    os_name = _os()
    variant = resolve_variant(variant)
    state.status = "resolving"
    state.message = f"Finding llama.cpp {variant} build for {os_name}…"
    rel, asset = _latest_release_with_asset(
        _LLAMA_REPO, lambda assets: select_llama_asset(assets, os_name, variant)
    )
    if not asset:
        state.status = "error"
        state.message = f"No llama.cpp {variant} build found for {os_name}."
        return

    config.ensure_dirs()
    tmp = config.BIN_DIR / "_tmp_llama"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    archive = tmp / asset["name"]

    state.status = "downloading"
    state.percent = 0.0
    state.message = f"Downloading {asset['name']} ({rel.get('tag_name')})…"
    _download(asset["browser_download_url"], archive, state)

    state.status = "extracting"
    state.message = "Extracting…"
    extract_dir = tmp / "x"
    _extract(archive, extract_dir)

    exe_name = "llama-bench.exe" if os_name == "windows" else "llama-bench"
    found = next((p for p in extract_dir.rglob(exe_name) if p.is_file()), None)
    if not found:
        state.status = "error"
        state.message = "llama-bench not found inside the downloaded archive."
        return
    # Copy the whole directory holding llama-bench (it needs its sibling shared
    # libraries) into BIN_DIR.
    _copy_tree_contents(found.parent, config.BIN_DIR)
    installed = config.BIN_DIR / exe_name
    try:
        installed.chmod(0o755)
    except OSError:
        pass
    shutil.rmtree(tmp, ignore_errors=True)
    state.status = "done"
    state.percent = 100.0
    state.message = f"Installed llama-bench ({rel.get('tag_name')}, {variant})."


def _install_mlperf(state: InstallState) -> None:
    os_name = _os()
    state.status = "resolving"
    state.message = f"Finding MLPerf Client for {os_name}…"
    rel, asset = _release_by_tag(_MLPERF_REPO, _MLPERF_TAG, lambda a: select_mlperf_asset(a, os_name))
    if not asset:
        rel, asset = _latest_release_with_asset(_MLPERF_REPO, lambda a: select_mlperf_asset(a, os_name))
    if not asset:
        state.status = "error"
        state.message = f"No MLPerf Client build found for {os_name}."
        return

    config.ensure_dirs()
    mlperf_dir = config.BIN_DIR / "mlperf"
    shutil.rmtree(mlperf_dir, ignore_errors=True)
    archive = config.BIN_DIR / asset["name"]

    state.status = "downloading"
    state.percent = 0.0
    state.message = f"Downloading {asset['name']}…"
    _download(asset["browser_download_url"], archive, state)

    state.status = "extracting"
    state.message = "Extracting…"
    _extract(archive, mlperf_dir)
    archive.unlink(missing_ok=True)

    exe = next((p for p in mlperf_dir.rglob("mlperf-*") if p.is_file() and p.suffix in ("", ".exe")), None)
    if exe:
        try:
            exe.chmod(0o755)
        except OSError:
            pass
    state.status = "done"
    state.percent = 100.0
    state.message = "Installed MLPerf Client."


def _worker(state: InstallState, kind: str, variant: str) -> None:
    try:
        if kind == "llama-bench":
            _install_llama(state, variant)
        elif kind == "mlperf":
            _install_mlperf(state)
        else:
            state.status = "error"
            state.message = f"Unknown tool: {kind}"
    except Exception as exc:  # noqa: BLE001
        state.status = "error"
        state.message = f"Install failed: {exc}"


def start_install(kind: str, variant: str = "auto") -> InstallState:
    global _state
    with _lock:
        if _state.status in {"resolving", "downloading", "extracting"}:
            return _state
        _state = InstallState(kind=kind, status="resolving", percent=0.0, message="Starting…")
    threading.Thread(target=_worker, args=(_state, kind, variant), name=f"install-{kind}", daemon=True).start()
    return _state
