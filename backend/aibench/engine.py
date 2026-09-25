"""Run orchestration: schedules benchmark runs and broadcasts live progress.

Benchmarks run in a background thread (they are subprocess/CPU heavy). Progress
callbacks from the worker thread are marshalled onto the asyncio loop and pushed
to all connected WebSocket subscribers, and also persisted on the run so REST
polling works as a fallback. Results are saved to SQLite when a run finishes.
"""

from __future__ import annotations

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from . import store
from .catalog import get_definition
from .hardware import detect_hardware
from .runners.base import BenchmarkRunner, CancelledError, RunHandle
from .runners.llama_bench import LlamaBenchRunner
from .runners.mlperf import MLPerfRunner
from .runners.synthetic import SyntheticRunner
from .schemas import ProgressEvent, RunConfig, RunResult, RunStatus, utcnow_iso


def _make_runner(engine: str) -> BenchmarkRunner:
    if engine == "synthetic":
        return SyntheticRunner()
    if engine == "llama-bench":
        return LlamaBenchRunner()
    if engine == "mlperf":
        return MLPerfRunner()
    raise ValueError(f"Unknown engine: {engine}")


class RunManager:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="bench")
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._subscribers: set[asyncio.Queue] = set()
        self._handles: dict[str, RunHandle] = {}
        self._active: dict[str, RunResult] = {}

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # ---- pub/sub ----------------------------------------------------------- #
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def _broadcast(self, event: ProgressEvent) -> None:
        for q in list(self._subscribers):
            q.put_nowait(event)

    def _emit_threadsafe(self, event: ProgressEvent) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._broadcast, event)

    # ---- run lifecycle ----------------------------------------------------- #
    def start_run(self, cfg: RunConfig) -> RunResult:
        defn = get_definition(cfg.benchmark_id)
        if defn is None:
            raise ValueError(f"Unknown benchmark: {cfg.benchmark_id}")

        # Merge defaults with provided params.
        params = {p.key: p.default for p in defn.params}
        params.update(cfg.params or {})

        run_id = f"run-{uuid.uuid4().hex[:12]}"
        result = RunResult(
            id=run_id,
            benchmark_id=defn.id,
            benchmark_name=defn.name,
            engine=defn.engine,
            category=defn.category,
            label=cfg.label or defn.name,
            status=RunStatus.QUEUED,
            params=params,
            hardware=detect_hardware(),
        )
        self._active[run_id] = result
        store.save_run(result)

        handle = RunHandle(run_id=run_id, params=params)
        self._handles[run_id] = handle
        self._executor.submit(self._execute, defn.engine, handle, result)
        return result

    def cancel_run(self, run_id: str) -> bool:
        handle = self._handles.get(run_id)
        if handle:
            handle.cancel()
            return True
        return False

    def _execute(self, engine: str, handle: RunHandle, result: RunResult) -> None:
        run_id = result.id

        def progress(phase, percent, message) -> None:
            if phase is not None:
                result.phase = phase
            if percent is not None:
                result.progress = round(float(percent), 1)
            if message:
                result.logs.append(message)
            self._emit_threadsafe(
                ProgressEvent(
                    type="progress",
                    run_id=run_id,
                    phase=result.phase,
                    percent=result.progress,
                    message=message,
                    status=result.status,
                )
            )

        result.status = RunStatus.RUNNING
        result.started_at = utcnow_iso()
        self._emit_threadsafe(
            ProgressEvent(type="status", run_id=run_id, status=result.status, phase="Starting")
        )
        try:
            runner = _make_runner(engine)
            output = runner.run(handle, progress)
            result.metrics = output.metrics
            result.series = output.series
            result.logs.extend(output.logs)
            result.status = RunStatus.COMPLETED
            result.progress = 100.0
        except CancelledError:
            result.status = RunStatus.CANCELLED
            result.error = "Run cancelled by user"
        except Exception as exc:  # noqa: BLE001 - report failures to the UI
            result.status = RunStatus.FAILED
            result.error = str(exc)
            result.logs.append(f"ERROR: {exc}")
        finally:
            result.finished_at = utcnow_iso()
            store.save_run(result)
            self._handles.pop(run_id, None)
            self._emit_threadsafe(
                ProgressEvent(
                    type="status",
                    run_id=run_id,
                    status=result.status,
                    percent=result.progress,
                    phase=result.phase,
                    message=result.error or "Completed",
                )
            )

    def get_active(self, run_id: str) -> Optional[RunResult]:
        return self._active.get(run_id)


manager = RunManager()
