"""Adapter for the MLPerf Client benchmark binary.

The MLPerf Client tool is driven by a JSON configuration file describing
scenarios, models and execution providers, and can export results to CSV
(``-x``). This adapter can either use a user-selected stock config from the
MLPerf repo's ``data/configs`` tree or synthesize a minimal config from UI
parameters, run the binary, and parse the exported CSV into AI-Bench metrics.

CSV parsing is intentionally schema-tolerant: MLPerf Client's exact columns vary
by version/scenario, so we detect throughput / latency style columns by name.
"""

from __future__ import annotations

import csv
import io
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

from .. import config
from ..schemas import Metric
from .base import BenchmarkRunner, CancelledError, ProgressCallback, RunHandle, RunOutput

_FLOAT_RE = re.compile(r"[-+]?\d*\.?\d+")


def build_mlperf_config(params: dict[str, Any]) -> dict[str, Any]:
    """Synthesize a minimal MLPerf Client config from UI parameters."""

    model_name = params.get("model_name", "Llama 3.1 8B")
    model_url = params.get("model_url", "")
    tokenizer_url = params.get("tokenizer_url", "")
    backend = params.get("backend", "llama-cpp")
    device_type = params.get("device_type", "GPU")
    iterations = int(params.get("iterations", 3))

    model_entry: dict[str, Any] = {"ModelName": model_name}
    if model_url:
        model_entry["FilePath"] = model_url
    if tokenizer_url:
        model_entry["TokenizerPath"] = tokenizer_url

    ep_config: dict[str, Any] = {"device_type": device_type}
    if backend == "llama-cpp":
        ep_config.update({"backend": params.get("llama_backend", "CUDA"), "gpu_layers": 999})

    return {
        "SystemConfig": {"Comment": f"AI-Bench generated ({backend})", "TempPath": ""},
        "Scenarios": [
            {
                "Name": params.get("scenario", "Llama3"),
                "Models": [model_entry],
                "Iterations": iterations,
                "WarmUp": int(params.get("warmup", 1)),
                "ExecutionProviders": [{"Name": backend, "Config": ep_config}],
            }
        ],
    }


def parse_mlperf_csv(text: str) -> tuple[list[Metric], list[str]]:
    """Parse an MLPerf Client results CSV into metrics (schema-tolerant)."""

    metrics: list[Metric] = []
    notes: list[str] = []
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return metrics, notes

    def _num(v: Any) -> Optional[float]:
        if v is None:
            return None
        m = _FLOAT_RE.search(str(v))
        return float(m.group()) if m else None

    for row in reader:
        scenario = (
            row.get("Scenario")
            or row.get("scenario")
            or row.get("Model")
            or row.get("model")
            or "MLPerf"
        )
        for col, val in row.items():
            if col is None:
                continue
            low = col.lower()
            num = _num(val)
            if num is None:
                continue
            if "tok" in low and ("/s" in low or "per" in low or "throughput" in low):
                metrics.append(
                    Metric(name=f"{scenario}: {col}", value=num, unit="tok/s", group="Throughput")
                )
            elif "ttft" in low or "time to first" in low:
                metrics.append(
                    Metric(
                        name=f"{scenario}: TTFT",
                        value=num,
                        unit="ms",
                        higher_is_better=False,
                        group="Latency",
                    )
                )
            elif "latency" in low or "duration" in low or "time" in low:
                metrics.append(
                    Metric(
                        name=f"{scenario}: {col}",
                        value=num,
                        unit="ms",
                        higher_is_better=False,
                        group="Latency",
                    )
                )
    if not metrics:
        notes.append("No recognizable metric columns found in MLPerf CSV output.")
    return metrics, notes


class MLPerfRunner(BenchmarkRunner):
    engine = "mlperf"

    def __init__(self, binary: Optional[str] = None) -> None:
        self.binary = binary or config.MLPERF_CLIENT_PATH

    def run(self, handle: RunHandle, progress: ProgressCallback) -> RunOutput:
        if not self.binary or not Path(self.binary).exists():
            raise RuntimeError(
                "MLPerf Client binary not found. Install it via the AI-Bench installer "
                "or set AIBENCH_MLPERF_CLIENT."
            )
        p = handle.params
        config.ensure_dirs()
        out = RunOutput()

        # Resolve a config file: an explicit path wins, otherwise synthesize one.
        cfg_path = p.get("config_path")
        if not cfg_path:
            cfg = build_mlperf_config(p)
            cfg_path = str(config.CONFIGS_DIR / f"mlperf_{handle.run_id}.json")
            Path(cfg_path).write_text(json.dumps(cfg, indent=2), encoding="utf-8")
            out.logs.append(f"Generated MLPerf config at {cfg_path}")

        results_csv = config.RUNS_DIR / f"mlperf_{handle.run_id}.csv"
        cmd = [self.binary, "-c", str(cfg_path), "-x", str(results_csv), "-p", "false"]
        out.logs.append("$ " + " ".join(cmd))
        progress("Starting", 0.0, "Launching MLPerf Client")

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                if handle.cancelled:
                    proc.terminate()
                    raise CancelledError()
                line = line.rstrip()
                if line:
                    out.logs.append(line)
                    progress("Benchmarking", None, line)
            proc.wait(timeout=10)
        finally:
            if proc.poll() is None:
                proc.kill()

        if proc.returncode not in (0, None):
            raise RuntimeError(f"MLPerf Client exited with code {proc.returncode}")

        if not results_csv.exists():
            raise RuntimeError("MLPerf Client did not produce a results CSV")
        metrics, notes = parse_mlperf_csv(results_csv.read_text(encoding="utf-8", errors="ignore"))
        out.metrics.extend(metrics)
        out.logs.extend(notes)
        progress("Done", 100.0, "Completed")
        return out
