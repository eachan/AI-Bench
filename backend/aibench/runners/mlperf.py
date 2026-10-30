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


def discover_stock_configs(home: Optional[str]) -> list[dict[str, Any]]:
    """Enumerate the MLPerf Client's bundled stock scenario configs.

    These ship next to the binary under ``llm/``, ``agentic/`` and
    ``image-gen/`` and already contain valid model/data download URLs and all
    required fields, so they are the reliable way to drive a real benchmark
    (synthesized configs are rejected by the tool's schema validation).
    """

    if not home:
        return []
    root = Path(home)
    if not root.exists():
        return []
    configs: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.json")):
        parts = {p.lower() for p in path.parts}
        if "logs" in parts or path.name.lower() in {"results.json"}:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except (json.JSONDecodeError, OSError):
            continue
        scenarios = data.get("Scenarios")
        if not isinstance(scenarios, list) or not scenarios:
            continue
        sc = scenarios[0]
        eps = sc.get("ExecutionProviders") or [{}]
        ep = eps[0] if isinstance(eps, list) and eps else {}
        rel_top = path.relative_to(root).parts[0] if path.relative_to(root).parts else ""
        configs.append(
            {
                "path": str(path),
                "name": path.stem,
                "category": rel_top,
                "scenario": sc.get("Name", ""),
                "ep": ep.get("Name", ""),
                "device": (ep.get("Config") or {}).get("device_type", ""),
            }
        )
    return configs


def vendor_fit(ep: str, name: str, vendors: set[str]) -> int:
    """Score how well a config's execution provider fits the detected GPU vendor(s).

    Positive = a good match (e.g. CUDA/TensorRT on NVIDIA); strongly negative =
    incompatible (e.g. an Intel OpenVINO GPU config on an NVIDIA-only machine,
    which can't run and produces no results).
    """

    s = (ep + " " + name).lower()
    score = 0
    if "nvidia" in vendors:
        if any(k in s for k in ("nvidia", "cuda", "tensorrt")):
            score += 3
        if "openvino" in s:
            score -= 5
    if "amd" in vendors:
        if any(k in s for k in ("amd", "rocm", "ryzenai")):
            score += 3
        if "openvino" in s:
            score -= 3
    if "intel" in vendors:
        if any(k in s for k in ("intel", "openvino")):
            score += 3
    # llama.cpp and DirectML (WindowsML-DML) run broadly across vendors.
    if any(k in s for k in ("llama-cpp", "llamacpp")) or "dml" in s:
        score += 1
    return score


def select_stock_config(
    configs: list[dict[str, Any]],
    params: dict[str, Any],
    vendors: Optional[set[str]] = None,
) -> Optional[str]:
    """Pick the stock config that best matches the requested scenario/EP/device
    and the detected GPU vendor(s)."""

    if not configs:
        return None
    scenario = str(params.get("scenario", "")).lower()
    backend = str(params.get("backend", "")).lower()
    device = str(params.get("device_type", "")).lower()
    vendors = vendors or set()

    def score(c: dict[str, Any]) -> int:
        s = 0
        if scenario and scenario in (c["scenario"].lower() + " " + c["name"].lower()):
            s += 2
        if backend and backend.replace("-", "") in c["ep"].lower().replace("-", ""):
            s += 4
        if device and device == c["device"].lower():
            s += 3
        s += vendor_fit(c["ep"], c["name"], vendors)
        return s

    ranked = sorted(configs, key=score, reverse=True)
    best = ranked[0]
    # Don't auto-pick a config that's incompatible with the hardware.
    if vendors and vendor_fit(best["ep"], best["name"], vendors) < 0:
        return None
    return best["path"]


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

    # NOTE: the MLPerf Client schema requires InputFilePath (and typically
    # AssetsPath); include them so a synthesized config validates. Real runs
    # should prefer a bundled stock config, which carries valid download URLs.
    input_files = params.get("input_files") or {"base": [], "extended": []}
    return {
        "SystemConfig": {"Comment": f"AI-Bench generated ({backend})", "TempPath": ""},
        "Scenarios": [
            {
                "Name": params.get("scenario", "Llama3"),
                "Models": [model_entry],
                "InputFilePath": input_files,
                "AssetsPath": params.get("assets") or [],
                "Iterations": iterations,
                "WarmUp": int(params.get("warmup", 1)),
                "ExecutionProviders": [{"Name": backend, "Config": ep_config}],
            }
        ],
    }


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    m = _FLOAT_RE.search(str(v))
    return float(m.group()) if m else None


# MLPerf Client's pivoted-CSV metadata rows (label in col 0, values from col 3).
_MLPERF_HEADER_ROWS = {
    "ep",
    "device",
    "scenario",
    "date",
    "tested by mlcommons",
    "config category",
    "system info",
}
# Descriptive (non-performance) rows we skip when parsing metric sections.
_MLPERF_SKIP_LABELS = {"image size", "inference steps"}


def _classify_mlperf_metric(label: str) -> tuple[str, str, bool, str]:
    """Map an MLPerf metric-row label to (clean name, unit, higher_is_better, group)."""

    low = label.lower()
    clean = re.sub(r"\s*\((seconds|s)\)\s*$", "", label).strip() or label
    if "ttft" in low:
        return "TTFT", "s", False, "Latency"
    if low == "tps" or "token generation" in low or "tokens/s" in low or "tps" in low:
        return "TPS", "tok/s", True, "Throughput"
    if "images/min" in low:
        return "Images/Min", "img/min", True, "Throughput"
    if "steps/sec" in low or "steps/s" in low:
        return "Steps/Sec", "steps/s", True, "Throughput"
    if any(k in low for k in ("duration", "e2e", "seconds", "first-step", "setup", "warmup", "load")):
        return clean, "s", False, "Latency"
    return clean, "", True, "Other"


def _header_values(rows: list[list[str]], name: str) -> list[str]:
    """Return the per-result values (columns 3+) of a pivoted metadata row."""

    for r in rows:
        if r and r[0].strip().lower() == name:
            return [c.strip() for c in r[3:]]
    return []


def _parse_mlperf_pivoted(rows: list[list[str]]) -> tuple[list[Metric], list[str]]:
    """Parse MLPerf Client's real (pivoted) results CSV.

    Layout: seven metadata rows (``EP``/``Device``/``Scenario``/...), each with
    one column per result from index 3; then per-category sections where a
    single-cell row names the category and following rows carry a metric label
    in column 2 and one value per result from column 3 (e.g. ``TTFT (seconds)``,
    ``TPS``, image-gen ``Images/Min`` ...).
    """

    eps = _header_values(rows, "ep")
    devices = _header_values(rows, "device")
    multi = len(eps) > 1

    metrics: list[Metric] = []
    category = ""
    for r in rows:
        if not r:
            continue
        c0 = r[0].strip()
        if c0.lower() in _MLPERF_HEADER_ROWS:
            continue
        label = r[2].strip() if len(r) > 2 else ""
        values = r[3:] if len(r) > 3 else []
        if c0 and not label and not any(c.strip() for c in values):
            category = c0  # single-cell category marker
            continue
        if not label or label.lower() in _MLPERF_SKIP_LABELS:
            continue
        name, unit, hib, group = _classify_mlperf_metric(label)
        for i, raw in enumerate(values):
            num = _num(raw)
            if num is None:
                continue
            ep = eps[i] if i < len(eps) else ""
            dev = devices[i] if i < len(devices) else ""
            # Keep names concise for the common single-result case; disambiguate
            # by execution provider only when a run has multiple results.
            suffix = f" ({ep}{'/' + dev if dev else ''})" if multi and (ep or dev) else ""
            metrics.append(
                Metric(
                    name=f"{name}{suffix}",
                    value=num,
                    unit=unit,
                    higher_is_better=hib,
                    group=group,
                )
            )
    return metrics, []


def _parse_mlperf_flat(text: str) -> tuple[list[Metric], list[str]]:
    """Fallback parser for a flat (header-row) CSV shape."""

    metrics: list[Metric] = []
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return metrics, []
    for row in reader:
        scenario = (
            row.get("Scenario") or row.get("scenario") or row.get("Model") or row.get("model") or "MLPerf"
        )
        for col, val in row.items():
            if col is None:
                continue
            low = col.lower()
            num = _num(val)
            if num is None:
                continue
            if "tok" in low and ("/s" in low or "per" in low or "throughput" in low):
                metrics.append(Metric(name=f"{scenario}: {col}", value=num, unit="tok/s", group="Throughput"))
            elif "ttft" in low or "time to first" in low:
                metrics.append(Metric(name=f"{scenario}: TTFT", value=num, unit="ms",
                                      higher_is_better=False, group="Latency"))
            elif "latency" in low or "duration" in low or "time" in low:
                metrics.append(Metric(name=f"{scenario}: {col}", value=num, unit="ms",
                                      higher_is_better=False, group="Latency"))
    return metrics, []


def parse_mlperf_csv(text: str) -> tuple[list[Metric], list[str]]:
    """Parse an MLPerf Client results CSV into metrics.

    Handles the tool's real pivoted layout (metrics as rows, results as columns)
    and falls back to a flat header-row shape for other inputs.
    """

    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return [], []
    if rows[0] and rows[0][0].strip().lower() == "ep":
        metrics, notes = _parse_mlperf_pivoted(rows)
    else:
        metrics, notes = _parse_mlperf_flat(text)
    if not metrics:
        notes = notes + ["No recognizable metric columns found in MLPerf CSV output."]
    return metrics, notes


class MLPerfRunner(BenchmarkRunner):
    engine = "mlperf"

    def __init__(self, binary: Optional[str] = None) -> None:
        self.binary = binary or config.mlperf_client_path()

    def run(self, handle: RunHandle, progress: ProgressCallback) -> RunOutput:
        if not self.binary or not Path(self.binary).exists():
            raise RuntimeError(
                "MLPerf Client binary not found. Install it via the AI-Bench installer "
                "or set AIBENCH_MLPERF_CLIENT."
            )
        p = handle.params
        config.ensure_dirs()
        out = RunOutput()

        # Resolve a config file. Priority: explicit path -> a bundled stock
        # config matching the requested scenario/EP/device -> synthesized (last
        # resort). Stock configs are strongly preferred because the tool's
        # schema validation rejects incomplete configs.
        cfg_path = p.get("config_path")
        if not cfg_path:
            from ..hardware import detect_gpus

            vendors = {(g.vendor or "").lower() for g in detect_gpus() if g.vendor}
            stock = discover_stock_configs(config.mlperf_home())
            cfg_path = select_stock_config(stock, p, vendors)
            if cfg_path:
                out.logs.append(f"Using stock MLPerf config: {cfg_path}")
        if not cfg_path:
            cfg = build_mlperf_config(p)
            cfg_path = str(config.CONFIGS_DIR / f"mlperf_{handle.run_id}.json")
            Path(cfg_path).write_text(json.dumps(cfg, indent=2), encoding="utf-8")
            out.logs.append(
                f"No stock config found; generated {cfg_path}. If MLPerf rejects it, "
                "select a bundled config via the Custom config file setting."
            )

        results_csv = config.RUNS_DIR / f"mlperf_{handle.run_id}.csv"
        data_dir = config.DATASETS_DIR / "mlperf"
        data_dir.mkdir(parents=True, exist_ok=True)
        # -p false disables the tool's end-of-run "Press any key" pause (which
        # would otherwise hang a headless subprocess).
        cmd = [
            self.binary,
            "-c", str(cfg_path),
            "-x", str(results_csv),
            "-o", str(config.RUNS_DIR),
            "-d", str(data_dir),
            "-p", "false",
        ]
        out.logs.append("$ " + " ".join(cmd))
        progress("Starting", 0.0, "Launching MLPerf Client")

        # Run from the MLPerf home dir so its execution-provider plugins resolve.
        mlperf_root = config.mlperf_home()
        cwd = mlperf_root if mlperf_root else None
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, cwd=cwd
        )
        proc_output: list[str] = []
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                if handle.cancelled:
                    proc.terminate()
                    raise CancelledError()
                line = line.rstrip()
                if line:
                    out.logs.append(line)
                    proc_output.append(line)
                    progress("Benchmarking", None, line)
            proc.wait(timeout=10)
        finally:
            if proc.poll() is None:
                proc.kill()

        def _tail(n: int = 12) -> str:
            tail = [ln for ln in proc_output if ln.strip()][-n:]
            return ("\n  " + "\n  ".join(tail)) if tail else " (no output captured)"

        if proc.returncode not in (0, None):
            raise RuntimeError(f"MLPerf Client exited with code {proc.returncode}. Output:{_tail()}")

        if not results_csv.exists():
            raise RuntimeError(
                "MLPerf Client finished without producing results. This usually means the "
                "chosen config's execution provider isn't available on this hardware (e.g. an "
                "Intel OpenVINO config on an NVIDIA GPU) or required model files couldn't be "
                f"downloaded. MLPerf output:{_tail()}"
            )
        metrics, notes = parse_mlperf_csv(results_csv.read_text(encoding="utf-8", errors="ignore"))
        out.metrics.extend(metrics)
        out.logs.extend(notes)
        progress("Done", 100.0, "Completed")
        return out
