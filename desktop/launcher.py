"""Desktop launcher for AI-Bench.

Starts the FastAPI backend (which also serves the built frontend) on a local
port and opens it in a native desktop window using pywebview.

Robustness/diagnostics (so a failed launch is never a blank "can't reach this
page"):
  * Any backend startup error is written to ``<data dir>/launch-error.log`` and,
    if the server never comes up, shown inside the window instead of a
    connection-refused page.
  * A free port is chosen dynamically so a port already in use can't block start.
  * The window is only pointed at the server once it answers /api/health.
  * ``AIBENCH_SERVER_ONLY=1`` runs just the server (headless / testing).
"""

from __future__ import annotations

import multiprocessing
import os
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

# Ensure the backend package is importable whether run from source or a bundle.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "backend"))

HOST = os.environ.get("AIBENCH_HOST", "127.0.0.1")


def _data_dir() -> Path:
    try:
        from aibench import config

        config.ensure_dirs()
        return config.DATA_DIR
    except Exception:
        d = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "AI-Bench"
        d.mkdir(parents=True, exist_ok=True)
        return d


def _log_path() -> Path:
    return _data_dir() / "launch-error.log"


def _log(msg: str) -> None:
    try:
        with open(_log_path(), "a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def _pick_port(preferred: int) -> int:
    for candidate in (preferred, 0):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((HOST, candidate))
                return s.getsockname()[1]
        except OSError:
            continue
    return preferred


def _serve(port: int) -> None:
    """Run uvicorn; capture any crash to the launch-error log."""
    try:
        import uvicorn

        # In a windowed (no-console) packaged app sys.stdout/stderr are None;
        # point them at the log file so uvicorn/logging can't crash on write.
        if sys.stdout is None or sys.stderr is None:
            fh = open(_log_path(), "a", encoding="utf-8")
            sys.stdout = sys.stdout or fh
            sys.stderr = sys.stderr or fh

        from aibench.main import app  # import here so import errors are logged

        _log(f"Starting backend on http://{HOST}:{port}")
        uvicorn.run(app, host=HOST, port=port, log_level="info")
    except Exception:
        _log("Backend failed to start:\n" + traceback.format_exc())


def _wait_until_up(url: str, timeout: float = 60.0) -> bool:
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return True
        except Exception:
            time.sleep(0.4)
    return False


def _error_html(port: int) -> str:
    log = _log_path()
    detail = ""
    try:
        detail = log.read_text(encoding="utf-8", errors="ignore")[-4000:]
    except Exception:
        detail = "(no log captured)"
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>body{{font-family:Segoe UI,system-ui,sans-serif;background:#0b1020;color:#e6ebf5;padding:32px;line-height:1.5}}
h1{{color:#f87171}} code,pre{{background:#111827;border:1px solid #334155;border-radius:8px;padding:2px 6px}}
pre{{padding:14px;overflow:auto;max-height:50vh;white-space:pre-wrap}}</style></head><body>
<h1>AI-Bench couldn't start its local service</h1>
<p>The app's background service didn't respond on <code>http://{HOST}:{port}</code>.</p>
<p>Details were written to:<br><code>{log}</code></p>
<p>Please share that file so we can diagnose it. You can also try relaunching;
first launch can be slow while Windows scans the app.</p>
<h3>Recent log</h3><pre>{detail or '(empty)'}</pre>
</body></html>"""


def main() -> None:
    port = int(os.environ.get("AIBENCH_PORT", "8760"))

    if os.environ.get("AIBENCH_SERVER_ONLY") == "1":
        _serve(port)
        return

    port = _pick_port(port)
    threading.Thread(target=_serve, args=(port,), name="aibench-server", daemon=True).start()

    url = f"http://{HOST}:{port}/"
    up = _wait_until_up(f"http://{HOST}:{port}/api/health")
    if not up:
        _log("Backend did not become healthy within the startup timeout.")

    try:
        import webview  # type: ignore

        if up:
            webview.create_window("AI-Bench — Local ML/LLM Profiler", url, width=1280, height=860)
        else:
            webview.create_window(
                "AI-Bench — Local ML/LLM Profiler", html=_error_html(port), width=1000, height=720
            )
        webview.start()
    except Exception:
        # No pywebview available: fall back to the default browser.
        import webbrowser

        if up:
            webbrowser.open(url)
        else:
            err = _data_dir() / "launch-error.html"
            err.write_text(_error_html(port), encoding="utf-8")
            webbrowser.open(err.as_uri())
        print(f"AI-Bench running at {url} (press Ctrl+C to stop)")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
