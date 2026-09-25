"""Built-in synthetic benchmarks.

These run everywhere (no external binaries or model downloads required) and are
used both as an always-available smoke test and as a baseline estimate of a
machine's compute/memory capability for local models. They use NumPy so the
numbers reflect the machine's real BLAS/CPU throughput.

Workloads:
  * GEMM (matrix multiply) throughput in GFLOP/s.
  * Memory bandwidth in GB/s (large array copy).
  * Simulated autoregressive token generation in tokens/s, emitting a live
    per-step throughput series so the UI can chart progress in real time.
"""

from __future__ import annotations

import time

import numpy as np

from ..schemas import Metric, MetricSeries, SeriesPoint
from .base import BenchmarkRunner, ProgressCallback, RunHandle, RunOutput


class SyntheticRunner(BenchmarkRunner):
    engine = "synthetic"

    def run(self, handle: RunHandle, progress: ProgressCallback) -> RunOutput:
        p = handle.params
        matrix_size = int(p.get("matrix_size", 1024))
        gemm_iters = int(p.get("gemm_iters", 20))
        mem_mb = int(p.get("mem_mb", 256))
        gen_tokens = int(p.get("gen_tokens", 200))
        hidden = int(p.get("hidden_size", 2048))
        dtype = np.float32 if p.get("precision", "fp32") == "fp32" else np.float64

        out = RunOutput()

        # ---- Phase 1: GEMM throughput (GFLOP/s) -------------------------- #
        progress("GEMM", 0.0, f"Matrix multiply {matrix_size}x{matrix_size}")
        a = np.random.rand(matrix_size, matrix_size).astype(dtype)
        b = np.random.rand(matrix_size, matrix_size).astype(dtype)
        # Warm up (BLAS init / caches).
        _ = a @ b
        flops_per_iter = 2.0 * (matrix_size**3)
        gflops_samples = []
        gemm_series = MetricSeries(name="GEMM throughput", unit="GFLOP/s")
        for i in range(gemm_iters):
            self._check_cancel(handle)
            t0 = time.perf_counter()
            c = a @ b
            # Touch result so the multiply isn't optimized away.
            _ = float(c[0, 0])
            dt = time.perf_counter() - t0
            gflops = (flops_per_iter / dt) / 1e9 if dt > 0 else 0.0
            gflops_samples.append(gflops)
            gemm_series.points.append(SeriesPoint(step=i + 1, value=round(gflops, 2)))
            progress(
                "GEMM",
                (i + 1) / gemm_iters * 40.0,
                f"GEMM iter {i + 1}/{gemm_iters}: {gflops:.1f} GFLOP/s",
            )
        out.series.append(gemm_series)
        best_gflops = max(gflops_samples) if gflops_samples else 0.0
        out.metrics.append(
            Metric(name="GEMM throughput", value=round(best_gflops, 2), unit="GFLOP/s", group="Compute")
        )

        # ---- Phase 2: memory bandwidth (GB/s) ---------------------------- #
        progress("Memory", 40.0, f"Memory bandwidth ({mem_mb} MB buffers)")
        n = (mem_mb * 1024 * 1024) // 8
        src = np.ones(n, dtype=np.float64)
        bw_samples = []
        for i in range(5):
            self._check_cancel(handle)
            t0 = time.perf_counter()
            dst = src.copy()
            dst += 1.0
            dt = time.perf_counter() - t0
            # read + write + write ~ 3x traffic
            gbps = (src.nbytes * 3 / dt) / 1e9 if dt > 0 else 0.0
            bw_samples.append(gbps)
            progress("Memory", 40.0 + (i + 1) / 5 * 20.0, f"Memory copy {gbps:.1f} GB/s")
        best_bw = max(bw_samples) if bw_samples else 0.0
        out.metrics.append(
            Metric(name="Memory bandwidth", value=round(best_bw, 2), unit="GB/s", group="Memory")
        )

        # ---- Phase 3: simulated token generation (tokens/s) -------------- #
        progress("Generation", 60.0, "Simulated autoregressive decode")
        # A tiny decode loop: each token does a couple of matrix-vector ops
        # against a hidden-state-sized weight matrix, similar in shape to a
        # transformer decode step. Throughput scales with the machine.
        w1 = np.random.rand(hidden, hidden).astype(dtype)
        x = np.random.rand(hidden).astype(dtype)
        tps_series = MetricSeries(name="Token generation", unit="tok/s")
        token_times = []
        window = max(1, gen_tokens // 50)
        t_phase = time.perf_counter()
        for tok in range(gen_tokens):
            self._check_cancel(handle)
            t0 = time.perf_counter()
            x = np.tanh(w1 @ x)
            x = x / (np.linalg.norm(x) + 1e-6)
            token_times.append(time.perf_counter() - t0)
            if (tok + 1) % window == 0 or tok == gen_tokens - 1:
                recent = token_times[-window:]
                tps = window / sum(recent) if sum(recent) > 0 else 0.0
                tps_series.points.append(SeriesPoint(step=tok + 1, value=round(tps, 1)))
                progress(
                    "Generation",
                    60.0 + (tok + 1) / gen_tokens * 40.0,
                    f"Generated {tok + 1}/{gen_tokens} tokens @ {tps:.1f} tok/s",
                )
        total_gen = time.perf_counter() - t_phase
        avg_tps = gen_tokens / total_gen if total_gen > 0 else 0.0
        out.series.append(tps_series)
        out.metrics.append(
            Metric(name="Token generation", value=round(avg_tps, 1), unit="tok/s", group="LLM")
        )
        out.metrics.append(
            Metric(
                name="First-token latency",
                value=round(token_times[0] * 1000, 2) if token_times else 0.0,
                unit="ms",
                higher_is_better=False,
                group="LLM",
            )
        )
        progress("Generation", 100.0, "Done")
        out.logs.append(
            f"Synthetic benchmark complete: {best_gflops:.1f} GFLOP/s, "
            f"{best_bw:.1f} GB/s, {avg_tps:.1f} tok/s"
        )
        return out
