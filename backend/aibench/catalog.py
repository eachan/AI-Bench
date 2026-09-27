"""Static catalog of available benchmarks and their configurable parameters.

Each definition drives the UI: ``params`` render as native form controls
(sliders, number inputs, selects, switches) so users configure everything
without touching files or the command line. Availability of binary-backed
benchmarks is resolved at runtime from configured binary paths.
"""

from __future__ import annotations

from pathlib import Path

from . import config
from .schemas import BenchmarkDefinition, ParamOption, ParamSpec


def _synthetic() -> BenchmarkDefinition:
    return BenchmarkDefinition(
        id="synthetic-compute",
        name="System Capability (Synthetic)",
        category="Compute",
        engine="synthetic",
        description=(
            "Always-available baseline that measures GEMM throughput, memory "
            "bandwidth and simulated token generation using your CPU/BLAS. Great "
            "for a quick capability estimate with no downloads."
        ),
        metrics=["GEMM throughput", "Memory bandwidth", "Token generation"],
        requires_binary=False,
        params=[
            ParamSpec(key="matrix_size", label="Matrix size", type="int", default=1024,
                      min=128, max=4096, step=128, help="NxN matrix for GEMM throughput."),
            ParamSpec(key="gemm_iters", label="GEMM iterations", type="int", default=20,
                      min=1, max=200, step=1),
            ParamSpec(key="precision", label="Precision", type="select", default="fp32",
                      options=[ParamOption(label="FP32", value="fp32"),
                               ParamOption(label="FP64", value="fp64")]),
            ParamSpec(key="mem_mb", label="Memory buffer", type="int", default=256, unit="MB",
                      min=16, max=4096, step=16, advanced=True),
            ParamSpec(key="hidden_size", label="Hidden size", type="int", default=2048,
                      min=256, max=8192, step=256, advanced=True,
                      help="Width of the simulated decode step."),
            ParamSpec(key="gen_tokens", label="Tokens to generate", type="int", default=200,
                      min=10, max=4000, step=10),
        ],
    )


def _llama_bench() -> BenchmarkDefinition:
    return BenchmarkDefinition(
        id="llamacpp-bench",
        name="llama.cpp Inference (llama-bench)",
        category="LLM",
        engine="llama-bench",
        description=(
            "Runs llama.cpp's llama-bench against a GGUF model to measure real "
            "prompt-processing and text-generation throughput on your CPU/GPU."
        ),
        metrics=["Prompt processing", "Text generation"],
        requires_binary=True,
        params=[
            ParamSpec(key="hf_repo", label="HuggingFace model", type="string",
                      default="ggml-org/gemma-3-1b-it-GGUF",
                      help="Pulled automatically with -hf, e.g. user/model:quant."),
            ParamSpec(key="model_path", label="Local GGUF path", type="string", default="",
                      advanced=True, help="Overrides the HuggingFace model when set."),
            ParamSpec(key="n_prompt", label="Prompt tokens", type="int", default=512,
                      min=0, max=8192, step=64),
            ParamSpec(key="n_gen", label="Generation tokens", type="int", default=128,
                      min=0, max=4096, step=32),
            ParamSpec(key="n_gpu_layers", label="GPU layers", type="int", default=999,
                      min=0, max=999, step=1, help="Layers offloaded to GPU (0 = CPU only)."),
            ParamSpec(key="threads", label="CPU threads", type="int", default=0, min=0, max=256,
                      step=1, advanced=True, help="0 = auto."),
            ParamSpec(key="batch_size", label="Batch size", type="int", default=2048, min=1,
                      max=8192, step=1, advanced=True),
            ParamSpec(key="repetitions", label="Repetitions", type="int", default=5, min=1,
                      max=50, step=1),
        ],
    )


def _mlperf() -> BenchmarkDefinition:
    return BenchmarkDefinition(
        id="mlperf-client",
        name="MLPerf Client",
        category="MLPerf",
        engine="mlperf",
        description=(
            "Runs the MLPerf Client benchmark using a chosen execution provider "
            "(llama.cpp/CUDA, DirectML, OpenVINO, TensorRT-RTX). Measures "
            "standardized client inference performance."
        ),
        metrics=["Throughput", "TTFT"],
        requires_binary=True,
        params=[
            ParamSpec(key="scenario", label="Scenario", type="select", default="Llama3",
                      options=[ParamOption(label="Llama 3.1 8B", value="Llama3"),
                               ParamOption(label="Qwen3", value="Qwen3")]),
            ParamSpec(key="backend", label="Execution provider", type="select", default="llama-cpp",
                      options=[ParamOption(label="llama.cpp", value="llama-cpp"),
                               ParamOption(label="WindowsML (DirectML)", value="WindowsML"),
                               ParamOption(label="OpenVINO", value="OpenVINO"),
                               ParamOption(label="TensorRT-RTX", value="NvTensorRtRtx")]),
            ParamSpec(key="llama_backend", label="llama.cpp backend", type="select", default="CUDA",
                      options=[ParamOption(label="CUDA", value="CUDA"),
                               ParamOption(label="Vulkan", value="Vulkan"),
                               ParamOption(label="CPU", value="CPU")]),
            ParamSpec(key="device_type", label="Device", type="select", default="GPU",
                      options=[ParamOption(label="GPU", value="GPU"),
                               ParamOption(label="NPU", value="NPU"),
                               ParamOption(label="CPU", value="CPU")]),
            ParamSpec(key="iterations", label="Iterations", type="int", default=3, min=1, max=100,
                      step=1),
            ParamSpec(key="warmup", label="Warm-up iterations", type="int", default=1, min=0,
                      max=10, step=1, advanced=True),
            ParamSpec(key="config_path", label="Custom config file", type="string", default="",
                      advanced=True, help="Path to a full MLPerf Client JSON config (optional)."),
        ],
    )


def _resolve_availability(defn: BenchmarkDefinition) -> BenchmarkDefinition:
    if not defn.requires_binary:
        return defn
    binary = config.LLAMA_BENCH_PATH if defn.engine == "llama-bench" else config.MLPERF_CLIENT_PATH
    if binary and Path(binary).exists():
        defn.available = True
    else:
        defn.available = False
        defn.unavailable_reason = (
            f"{defn.name} needs an external binary. Install it from the Settings "
            "page or via the installer; synthetic benchmarks work without it."
        )
    return defn


def get_catalog() -> list[BenchmarkDefinition]:
    return [_resolve_availability(d) for d in (_synthetic(), _llama_bench(), _mlperf())]


def get_definition(benchmark_id: str) -> BenchmarkDefinition | None:
    for d in get_catalog():
        if d.id == benchmark_id:
            return d
    return None
