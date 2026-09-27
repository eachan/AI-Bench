"""Desktop launcher for AI-Bench.

Starts the FastAPI backend (which also serves the built frontend) on a local
port and opens it in a native desktop window using pywebview. This is what the
Windows Start Menu shortcut / ``run.ps1`` invokes so the user gets a real app
window rather than a browser tab. Falls back to opening the default browser if
pywebview is not installed.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

# Ensure the backend package is importable whether run from source or a bundle.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "backend"))

import uvicorn  # noqa: E402

HOST = os.environ.get("AIBENCH_HOST", "127.0.0.1")
PORT = int(os.environ.get("AIBENCH_PORT", "8760"))


def _serve() -> None:
    uvicorn.run("aibench.main:app", host=HOST, port=PORT, log_level="info")


def _wait_until_up(url: str, timeout: float = 20.0) -> bool:
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return True
        except Exception:
            time.sleep(0.3)
    return False


def main() -> None:
    # Headless / server-only mode: run just the API+UI server (used for testing
    # the packaged bundle and for advanced/remote usage).
    if os.environ.get("AIBENCH_SERVER_ONLY") == "1":
        _serve()
        return

    server = threading.Thread(target=_serve, name="aibench-server", daemon=True)
    server.start()

    url = f"http://{HOST}:{PORT}/"
    _wait_until_up(f"http://{HOST}:{PORT}/api/health")

    try:
        import webview  # type: ignore

        webview.create_window("AI-Bench — Local ML/LLM Profiler", url, width=1280, height=860)
        webview.start()
    except Exception:
        # No pywebview available: open the default browser and keep serving.
        import webbrowser

        webbrowser.open(url)
        print(f"AI-Bench running at {url} (press Ctrl+C to stop)")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
