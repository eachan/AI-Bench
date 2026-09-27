"""FastAPI application: REST API, WebSocket progress stream, static UI serving."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, config, downloads, store
from .catalog import get_catalog, get_definition
from .engine import manager
from .hardware import detect_hardware, refresh_hardware
from .schemas import RunConfig

app = FastAPI(title="AI-Bench", version=__version__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup() -> None:
    store.init_db()
    manager.bind_loop(asyncio.get_running_loop())


# --------------------------------------------------------------------------- #
# System / hardware
# --------------------------------------------------------------------------- #
@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/api/hardware")
async def hardware() -> dict:
    return detect_hardware().model_dump()


@app.post("/api/hardware/refresh")
async def hardware_refresh() -> dict:
    return refresh_hardware().model_dump()


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #
@app.get("/api/benchmarks")
async def benchmarks() -> list[dict]:
    return [d.model_dump() for d in get_catalog()]


@app.get("/api/benchmarks/{benchmark_id}")
async def benchmark(benchmark_id: str) -> dict:
    defn = get_definition(benchmark_id)
    if not defn:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    return defn.model_dump()


@app.get("/api/mlperf/configs")
async def mlperf_configs() -> dict:
    """List the MLPerf Client's bundled stock scenario configs (if installed)."""

    from .runners.mlperf import discover_stock_configs

    return {"home": config.MLPERF_HOME, "configs": discover_stock_configs(config.MLPERF_HOME)}


# --------------------------------------------------------------------------- #
# Runs
# --------------------------------------------------------------------------- #
@app.post("/api/runs")
async def create_run(cfg: RunConfig) -> dict:
    try:
        result = manager.start_run(cfg)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.model_dump()


@app.get("/api/runs")
async def runs() -> list[dict]:
    return [r.model_dump() for r in store.list_runs()]


@app.get("/api/runs/{run_id}")
async def run(run_id: str) -> dict:
    result = manager.get_active(run_id) or store.get_run(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Run not found")
    return result.model_dump()


@app.post("/api/runs/{run_id}/cancel")
async def cancel(run_id: str) -> dict:
    ok = manager.cancel_run(run_id)
    return {"cancelled": ok}


@app.delete("/api/runs/{run_id}")
async def remove(run_id: str) -> dict:
    return {"deleted": store.delete_run(run_id)}


# --------------------------------------------------------------------------- #
# Export / import
# --------------------------------------------------------------------------- #
@app.get("/api/profile/export")
async def export_profile(include_results: bool = True) -> JSONResponse:
    profile = store.export_profile(include_results=include_results)
    return JSONResponse(
        content=profile.model_dump(),
        headers={"Content-Disposition": "attachment; filename=ai-bench-profile.json"},
    )


@app.post("/api/profile/import")
async def import_profile(payload: dict) -> dict:
    try:
        profile = store.import_profile(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid profile: {exc}") from exc
    return {"imported_results": len(profile.results), "configs": len(profile.configs)}


# --------------------------------------------------------------------------- #
# Downloads
# --------------------------------------------------------------------------- #
@app.get("/api/models")
async def models() -> dict:
    return {
        "local": downloads.list_local_models(),
        "downloads": [d.to_dict() for d in downloads.list_downloads()],
    }


@app.get("/api/models/catalog")
async def models_catalog() -> dict:
    return {"models": downloads.SUGGESTED_MODELS}


@app.post("/api/downloads")
async def create_download(payload: dict) -> dict:
    url = payload.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="url is required")
    state = downloads.start_download(url, payload.get("kind", "model"), payload.get("filename"))
    return state.to_dict()


@app.delete("/api/models")
async def delete_model(path: str) -> dict:
    try:
        deleted = downloads.delete_local_model(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"deleted": deleted}


# --------------------------------------------------------------------------- #
# WebSocket progress stream
# --------------------------------------------------------------------------- #
@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = manager.subscribe()
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event.model_dump())
    except WebSocketDisconnect:
        pass
    finally:
        manager.unsubscribe(queue)


# --------------------------------------------------------------------------- #
# Static frontend (served in production / packaged app)
# --------------------------------------------------------------------------- #
def _resolve_frontend_dist() -> Path:
    """Find the built web UI in dev and in a packaged (PyInstaller) app."""

    candidates = []
    override = os.environ.get("AIBENCH_FRONTEND_DIST")
    if override:
        candidates.append(Path(override))
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "frontend" / "dist")
    exe_dir = Path(sys.executable).resolve().parent
    candidates += [
        exe_dir / "frontend" / "dist",
        exe_dir / "_internal" / "frontend" / "dist",
    ]
    # Source checkout layout: backend/aibench/main.py -> repo root.
    candidates.append(Path(__file__).resolve().parent.parent.parent / "frontend" / "dist")
    for c in candidates:
        if c.exists():
            return c
    return candidates[-1]


_FRONTEND_DIST = _resolve_frontend_dist()
if _FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(_FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> FileResponse:
        candidate = _FRONTEND_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")
