"""SQLite-backed persistence for run results.

Results are stored as JSON blobs keyed by run id, which keeps the schema simple
while allowing the rich nested result structure (metrics, series, logs,
hardware snapshot) to evolve. Export/import operate on :class:`TestProfile`
bundles so users can share test settings and results between machines.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from typing import Optional

from . import config
from .schemas import RunResult, TestProfile

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock, _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                benchmark_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                data TEXT NOT NULL
            )
            """
        )
        conn.commit()


def save_run(run: RunResult) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO runs (id, benchmark_id, created_at, status, data) "
            "VALUES (?, ?, ?, ?, ?)",
            (run.id, run.benchmark_id, run.created_at, run.status.value, run.model_dump_json()),
        )
        conn.commit()


def get_run(run_id: str) -> Optional[RunResult]:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT data FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        return None
    return RunResult.model_validate_json(row["data"])


def list_runs(limit: int = 200) -> list[RunResult]:
    with _lock, _connect() as conn:
        rows = conn.execute(
            "SELECT data FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [RunResult.model_validate_json(r["data"]) for r in rows]


def delete_run(run_id: str) -> bool:
    with _lock, _connect() as conn:
        cur = conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        conn.commit()
        return cur.rowcount > 0


def export_profile(run_ids: Optional[list[str]] = None, include_results: bool = True) -> TestProfile:
    from .hardware import detect_hardware
    from .schemas import RunConfig

    runs = list_runs()
    if run_ids:
        runs = [r for r in runs if r.id in set(run_ids)]
    configs = [
        RunConfig(benchmark_id=r.benchmark_id, label=r.label, params=r.params) for r in runs
    ]
    return TestProfile(
        hardware=detect_hardware(),
        configs=configs,
        results=runs if include_results else [],
    )


def import_profile(payload: dict) -> TestProfile:
    """Validate an imported profile and persist any results it carries."""

    profile = TestProfile.model_validate(payload)
    for run in profile.results:
        save_run(run)
    return profile
