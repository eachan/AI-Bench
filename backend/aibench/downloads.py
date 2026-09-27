"""Model / dataset download manager.

Provides streaming HTTP downloads with progress reporting so the UI can show a
progress bar, plus an index of already-downloaded files. Downloads are resilient
to interruption (written to a ``.part`` file and atomically renamed on success).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

from . import config


@dataclass
class DownloadState:
    id: str
    url: str
    dest: str
    total_bytes: int = 0
    downloaded_bytes: int = 0
    status: str = "pending"  # pending | downloading | completed | failed
    error: Optional[str] = None

    @property
    def percent(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return round(self.downloaded_bytes / self.total_bytes * 100.0, 1)


_downloads: dict[str, DownloadState] = {}
_lock = threading.Lock()


def _filename_from_url(url: str) -> str:
    name = Path(urlparse(url).path).name
    return name or "download.bin"


def list_downloads() -> list[DownloadState]:
    with _lock:
        return list(_downloads.values())


def list_local_models() -> list[dict]:
    config.ensure_dirs()
    files = []
    for base in (config.MODELS_DIR, config.DATASETS_DIR):
        for p in base.rglob("*"):
            if p.is_file() and not p.name.endswith(".part"):
                files.append(
                    {
                        "name": p.name,
                        "path": str(p),
                        "size_mb": round(p.stat().st_size / (1024 * 1024), 2),
                        "kind": "model" if base == config.MODELS_DIR else "dataset",
                    }
                )
    return files


def start_download(url: str, kind: str = "model", filename: Optional[str] = None) -> DownloadState:
    """Begin a background download; returns its state immediately."""

    config.ensure_dirs()
    base = config.MODELS_DIR if kind == "model" else config.DATASETS_DIR
    dest = base / (filename or _filename_from_url(url))
    dl_id = f"dl-{len(_downloads) + 1}-{dest.name}"
    state = DownloadState(id=dl_id, url=url, dest=str(dest))
    with _lock:
        _downloads[dl_id] = state

    def _worker() -> None:
        part = dest.with_suffix(dest.suffix + ".part")
        state.status = "downloading"
        try:
            with httpx.stream("GET", url, follow_redirects=True, timeout=None) as resp:
                resp.raise_for_status()
                state.total_bytes = int(resp.headers.get("content-length", 0) or 0)
                with open(part, "wb") as fh:
                    for chunk in resp.iter_bytes(chunk_size=1024 * 256):
                        fh.write(chunk)
                        state.downloaded_bytes += len(chunk)
            part.replace(dest)
            state.status = "completed"
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            state.status = "failed"
            state.error = str(exc)
            if part.exists():
                part.unlink(missing_ok=True)

    threading.Thread(target=_worker, name=f"download-{dl_id}", daemon=True).start()
    return state
