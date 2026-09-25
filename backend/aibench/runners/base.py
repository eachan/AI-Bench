"""Runner abstraction shared by all benchmark engines.

A runner takes a resolved set of parameters and executes a benchmark, reporting
progress through a callback and returning summary metrics plus optional time
series. Runners run in a worker thread (see :mod:`aibench.engine`) and must
periodically check ``handle.cancelled`` so runs can be stopped from the UI.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..schemas import Metric, MetricSeries


@dataclass
class RunHandle:
    """Mutable state passed to a runner for a single execution."""

    run_id: str
    params: dict[str, Any]
    _cancel: threading.Event = field(default_factory=threading.Event)

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()


@dataclass
class RunOutput:
    metrics: list[Metric] = field(default_factory=list)
    series: list[MetricSeries] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)


# progress(phase, percent 0-100, message)
ProgressCallback = Callable[[str, Optional[float], Optional[str]], None]


class BenchmarkRunner:
    """Base class for benchmark engines."""

    engine: str = "base"

    def run(self, handle: RunHandle, progress: ProgressCallback) -> RunOutput:
        raise NotImplementedError

    # Helper so subclasses can bail out promptly on cancellation.
    @staticmethod
    def _check_cancel(handle: RunHandle) -> None:
        if handle.cancelled:
            raise CancelledError()


class CancelledError(Exception):
    """Raised inside a runner when the run has been cancelled."""
