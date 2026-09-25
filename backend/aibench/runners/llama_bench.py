"""Adapter for llama.cpp's ``llama-bench`` tool.

Builds a ``llama-bench`` command line from UI parameters, streams progress by
watching ``--progress`` output on stderr, and parses the structured ``-o json``
result from stdout into AI-Bench metrics.

The JSON schema mirrors llama.cpp/tools/llama-bench (fields such as ``avg_ts``,
``stddev_ts``, ``n_prompt``, ``n_gen``, ``model_type``, ``gpu_info``). Prompt
processing rows (``n_prompt`` > 0, ``n_gen`` == 0) and text generation rows
(``n_gen`` > 0) are reported as separate metrics.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

from .. import config
from ..schemas import Metric, MetricSeries, SeriesPoint
from .base import BenchmarkRunner, CancelledError, ProgressCallback, RunHandle, RunOutput


def parse_llama_bench_json(text: str) -> list[dict[str, Any]]:
    """Parse ``llama-bench -o json`` stdout into a list of row dicts.

    Tolerant of surrounding log noise: extracts the first top-level JSON array.
    """

    text = text.strip()
    if not text:
        return []
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def rows_to_metrics(rows: list[dict[str, Any]]) -> tuple[list[Metric], list[str]]:
    metrics: list[Metric] = []
    notes: list[str] = []
    for row in rows:
        n_prompt = int(row.get("n_prompt", 0) or 0)
        n_gen = int(row.get("n_gen", 0) or 0)
        avg_ts = row.get("avg_ts")
        stddev_ts = row.get("stddev_ts")
        if avg_ts is None:
            continue
        if n_gen == 0 and n_prompt > 0:
            label = f"Prompt processing (pp{n_prompt})"
            group = "Prompt"
        elif n_gen > 0 and n_prompt == 0:
            label = f"Text generation (tg{n_gen})"
            group = "Generation"
        else:
            label = f"pp{n_prompt}+tg{n_gen}"
            group = "Combined"
        metrics.append(
            Metric(name=label, value=round(float(avg_ts), 2), unit="tok/s", group=group)
        )
        if stddev_ts is not None:
            notes.append(f"{label}: {avg_ts:.2f} ± {stddev_ts:.2f} tok/s")
    return metrics, notes


class LlamaBenchRunner(BenchmarkRunner):
    engine = "llama-bench"

    def __init__(self, binary: Optional[str] = None) -> None:
        self.binary = binary or config.LLAMA_BENCH_PATH

    def _build_command(self, params: dict[str, Any]) -> list[str]:
        cmd: list[str] = [self.binary, "-o", "json", "--progress"]
        model = params.get("model_path")
        hf_repo = params.get("hf_repo")
        if model:
            cmd += ["-m", str(model)]
        elif hf_repo:
            cmd += ["-hf", str(hf_repo)]
        n_prompt = params.get("n_prompt")
        n_gen = params.get("n_gen")
        if n_prompt not in (None, ""):
            cmd += ["-p", str(int(n_prompt))]
        if n_gen not in (None, ""):
            cmd += ["-n", str(int(n_gen))]
        if params.get("n_gpu_layers") not in (None, ""):
            cmd += ["-ngl", str(int(params["n_gpu_layers"]))]
        if params.get("threads") not in (None, ""):
            cmd += ["-t", str(int(params["threads"]))]
        if params.get("batch_size") not in (None, ""):
            cmd += ["-b", str(int(params["batch_size"]))]
        if params.get("repetitions") not in (None, ""):
            cmd += ["-r", str(int(params["repetitions"]))]
        return cmd

    def run(self, handle: RunHandle, progress: ProgressCallback) -> RunOutput:
        if not self.binary or not Path(self.binary).exists():
            raise RuntimeError(
                "llama-bench binary not found. Install it via the AI-Bench installer "
                "or set AIBENCH_LLAMA_BENCH. You can use the built-in synthetic "
                "benchmarks in the meantime."
            )
        cmd = self._build_command(handle.params)
        progress("Starting", 0.0, "Launching llama-bench")
        out = RunOutput()
        out.logs.append("$ " + " ".join(cmd))

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        stdout_lines: list[str] = []
        # llama-bench prints progress like "llama-bench: 3/8" to stderr.
        prog_re = re.compile(r"(\d+)\s*/\s*(\d+)")
        try:
            assert proc.stderr is not None
            for line in proc.stderr:
                if handle.cancelled:
                    proc.terminate()
                    raise CancelledError()
                line = line.rstrip()
                if not line:
                    continue
                out.logs.append(line)
                m = prog_re.search(line)
                if m:
                    done, total = int(m.group(1)), int(m.group(2))
                    pct = (done / total * 100.0) if total else None
                    progress("Benchmarking", pct, line)
                else:
                    progress("Benchmarking", None, line)
            if proc.stdout is not None:
                stdout_lines = proc.stdout.readlines()
            proc.wait(timeout=10)
        finally:
            if proc.poll() is None:
                proc.kill()

        if proc.returncode not in (0, None):
            raise RuntimeError(f"llama-bench exited with code {proc.returncode}")

        rows = parse_llama_bench_json("".join(stdout_lines))
        metrics, notes = rows_to_metrics(rows)
        if not metrics:
            raise RuntimeError("llama-bench produced no parseable results")
        out.metrics.extend(metrics)
        out.logs.extend(notes)
        # Build a simple comparison series across the reported tests.
        series = MetricSeries(name="Throughput by test", unit="tok/s")
        for i, mtr in enumerate(metrics):
            series.points.append(SeriesPoint(step=i + 1, value=mtr.value))
        out.series.append(series)
        progress("Done", 100.0, "Completed")
        return out
