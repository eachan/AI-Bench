"""Parser tests using output shapes taken from the reference repos."""

from aibench.runners.llama_bench import parse_llama_bench_json, rows_to_metrics
from aibench.runners.mlperf import build_mlperf_config, parse_mlperf_csv

# Two rows mirroring llama.cpp/tools/llama-bench JSON output (pp512 and tg128).
LLAMA_BENCH_JSON = """
some warmup log line that should be ignored
[
  {
    "build_commit": "8cf427ff", "cpu_info": "AMD Ryzen 7 7800X3D",
    "gpu_info": "NVIDIA GeForce RTX 4080", "backends": "CUDA",
    "model_type": "qwen2 7B Q4_K - Medium", "n_prompt": 512, "n_gen": 0,
    "avg_ts": 7263.609157, "stddev_ts": 90.940578
  },
  {
    "build_commit": "8cf427ff", "backends": "CUDA",
    "model_type": "qwen2 7B Q4_K - Medium", "n_prompt": 0, "n_gen": 128,
    "avg_ts": 119.844681, "stddev_ts": 0.699739
  }
]
"""


def test_parse_llama_bench_json_extracts_rows():
    rows = parse_llama_bench_json(LLAMA_BENCH_JSON)
    assert len(rows) == 2
    assert rows[0]["n_prompt"] == 512
    assert rows[1]["n_gen"] == 128


def test_rows_to_metrics_splits_pp_and_tg():
    rows = parse_llama_bench_json(LLAMA_BENCH_JSON)
    metrics, notes = rows_to_metrics(rows)
    names = {m.name for m in metrics}
    assert any("Prompt processing" in n for n in names)
    assert any("Text generation" in n for n in names)
    pp = next(m for m in metrics if "Prompt" in m.name)
    assert pp.unit == "tok/s"
    assert round(pp.value) == 7264


def test_parse_llama_bench_json_handles_garbage():
    assert parse_llama_bench_json("not json at all") == []
    assert parse_llama_bench_json("") == []


def test_mlperf_config_generation():
    cfg = build_mlperf_config(
        {"model_name": "Llama 3.1 8B", "backend": "llama-cpp", "iterations": 5}
    )
    assert cfg["Scenarios"][0]["Iterations"] == 5
    assert cfg["Scenarios"][0]["ExecutionProviders"][0]["Name"] == "llama-cpp"


def test_parse_mlperf_csv_detects_metrics():
    csv_text = (
        "Scenario,Tokens per second,TTFT (ms),Total latency (ms)\n"
        "Llama3,42.5,180.0,3200.0\n"
    )
    metrics, notes = parse_mlperf_csv(csv_text)
    names = {m.name for m in metrics}
    assert any("Tokens per second" in n for n in names)
    assert any("TTFT" in n for n in names)
    ttft = next(m for m in metrics if "TTFT" in m.name)
    assert ttft.higher_is_better is False
    assert ttft.value == 180.0
