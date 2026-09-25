"""Tests for hardware detection, the synthetic runner, storage and catalog."""

import os
import tempfile

# Route all app data to a temp dir before importing modules that read config.
os.environ["AIBENCH_DATA_DIR"] = tempfile.mkdtemp(prefix="aibench-test-")

from aibench import store  # noqa: E402
from aibench.catalog import get_catalog, get_definition  # noqa: E402
from aibench.hardware import detect_hardware  # noqa: E402
from aibench.runners.base import RunHandle  # noqa: E402
from aibench.runners.synthetic import SyntheticRunner  # noqa: E402
from aibench.schemas import RunResult, RunStatus  # noqa: E402


def test_hardware_detection_populates_core_fields():
    hw = detect_hardware()
    assert hw.cpu.logical_cores and hw.cpu.logical_cores >= 1
    assert hw.memory_gb > 0
    assert hw.os in {"Linux", "Windows", "Darwin"}
    assert isinstance(hw.gpus, list)


def test_synthetic_runner_produces_metrics_and_series():
    events = []
    runner = SyntheticRunner()
    handle = RunHandle(
        run_id="t1",
        params={"matrix_size": 256, "gemm_iters": 3, "gen_tokens": 30, "hidden_size": 512},
    )
    out = runner.run(handle, lambda phase, pct, msg: events.append((phase, pct, msg)))
    metric_names = {m.name for m in out.metrics}
    assert "GEMM throughput" in metric_names
    assert "Memory bandwidth" in metric_names
    assert "Token generation" in metric_names
    assert any(s.name == "Token generation" and s.points for s in out.series)
    assert events and events[-1][1] == 100.0


def test_synthetic_runner_is_cancellable():
    runner = SyntheticRunner()
    handle = RunHandle(run_id="t2", params={"matrix_size": 256, "gemm_iters": 100})
    handle.cancel()
    try:
        runner.run(handle, lambda *a: None)
        assert False, "expected cancellation"
    except Exception as exc:  # CancelledError
        assert exc.__class__.__name__ == "CancelledError"


def test_catalog_has_expected_engines():
    ids = {d.id for d in get_catalog()}
    assert {"synthetic-compute", "llamacpp-bench", "mlperf-client"} <= ids
    synth = get_definition("synthetic-compute")
    assert synth.available is True  # never requires a binary


def test_store_roundtrip_and_profile_export():
    store.init_db()
    run = RunResult(
        id="run-test-1",
        benchmark_id="synthetic-compute",
        benchmark_name="Synthetic",
        engine="synthetic",
        category="Compute",
        label="unit test",
        status=RunStatus.COMPLETED,
    )
    store.save_run(run)
    fetched = store.get_run("run-test-1")
    assert fetched and fetched.label == "unit test"

    profile = store.export_profile(include_results=True)
    assert any(r.id == "run-test-1" for r in profile.results)

    # Import round-trips through validation and persists results.
    payload = profile.model_dump()
    imported = store.import_profile(payload)
    assert len(imported.results) >= 1
