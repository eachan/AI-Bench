"""Parser tests using output shapes taken from the reference repos."""

import json
from pathlib import Path

from aibench.runners.llama_bench import (
    LlamaBenchRunner,
    parse_llama_bench_json,
    parse_llama_devices,
    rows_to_metrics,
)
from aibench.runners.mlperf import (
    build_mlperf_config,
    discover_stock_configs,
    parse_mlperf_csv,
    select_stock_config,
)

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


def test_llama_bench_omits_zero_threads():
    from aibench.runners.llama_bench import LlamaBenchRunner

    runner = LlamaBenchRunner(binary="/fake/llama-bench")
    # threads=0 means auto — must NOT emit "-t 0" (llama-bench aborts on it).
    cmd = runner._build_command({"hf_repo": "x/y", "n_prompt": 32, "n_gen": 16, "threads": 0})
    assert "-t" not in cmd
    # a positive thread count is passed through
    cmd2 = runner._build_command({"hf_repo": "x/y", "threads": 4})
    assert cmd2[cmd2.index("-t") + 1] == "4"


def test_parse_llama_bench_json_handles_garbage():
    assert parse_llama_bench_json("not json at all") == []
    assert parse_llama_bench_json("") == []


def test_mlperf_config_generation_includes_required_fields():
    cfg = build_mlperf_config(
        {"model_name": "Llama 3.1 8B", "backend": "llama-cpp", "iterations": 5}
    )
    sc = cfg["Scenarios"][0]
    assert sc["Iterations"] == 5
    assert sc["ExecutionProviders"][0]["Name"] == "llama-cpp"
    # The real MLPerf Client schema requires InputFilePath — must be present.
    assert "InputFilePath" in sc


def test_mlperf_stock_config_discovery_and_selection(tmp_path: Path):
    # Mirror the real bundle layout: llm/<scenario>/<EP>.json
    cfg_dir = tmp_path / "llm" / "Llama3.1"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "Intel_NativeOpenVINO_GPU_Default.json").write_text(
        json.dumps(
            {
                "SystemConfig": {"Comment": "stock"},
                "Scenarios": [
                    {
                        "Name": "Llama3",
                        "Models": [{"ModelName": "Llama 3.1 8B Instruct"}],
                        "InputFilePath": {"base": ["x"], "extended": []},
                        "ExecutionProviders": [
                            {"Name": "NativeOpenVINO", "Config": {"device_type": "GPU"}}
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    # Something that must be ignored.
    (tmp_path / "Logs").mkdir()
    (tmp_path / "Logs" / "results.json").write_text("{}", encoding="utf-8")

    configs = discover_stock_configs(str(tmp_path))
    assert len(configs) == 1
    assert configs[0]["ep"] == "NativeOpenVINO"
    assert configs[0]["device"] == "GPU"

    chosen = select_stock_config(configs, {"scenario": "Llama3", "backend": "OpenVINO", "device_type": "GPU"})
    assert chosen and chosen.endswith("Intel_NativeOpenVINO_GPU_Default.json")

    assert discover_stock_configs(None) == []


def test_parse_llama_devices_reads_available_devices_block():
    text = (
        "ggml_cuda_init: found 2 CUDA devices:\n"
        "Available devices:\n"
        "  CUDA0: NVIDIA GeForce RTX 5090 (32607 MiB, 31800 MiB free)\n"
        "  CUDA1: NVIDIA GeForce RTX 3090 (24576 MiB, 24000 MiB free)\n"
        "\n"
        "load time ...\n"
    )
    devices = parse_llama_devices(text)
    assert [d["id"] for d in devices] == ["CUDA0", "CUDA1"]
    assert devices[0]["name"] == "NVIDIA GeForce RTX 5090"
    assert "32607 MiB" in devices[0]["description"]
    # A CPU-only build lists no devices.
    assert parse_llama_devices("Available devices:\n") == []
    assert parse_llama_devices("") == []


def test_build_command_honours_device_selection():
    runner = LlamaBenchRunner(binary="/fake/llama-bench")
    base = {"hf_repo": "ggml-org/x", "n_gpu_layers": 999}

    # A specific GPU is pinned with -dev and still offloads layers.
    cmd = runner._build_command({**base, "device": "CUDA1"})
    assert "-dev" in cmd and cmd[cmd.index("-dev") + 1] == "CUDA1"
    assert "-ngl" in cmd and cmd[cmd.index("-ngl") + 1] == "999"

    # CPU only forces -ngl 0 and never pins a device.
    cmd = runner._build_command({**base, "device": "cpu"})
    assert "-dev" not in cmd
    assert cmd[cmd.index("-ngl") + 1] == "0"

    # Auto / empty uses no -dev (llama.cpp uses all GPUs).
    for dev in ("", "auto"):
        cmd = runner._build_command({**base, "device": dev})
        assert "-dev" not in cmd
        assert cmd[cmd.index("-ngl") + 1] == "999"


def test_select_stock_config_is_hardware_aware():
    from aibench.runners.mlperf import vendor_fit

    configs = [
        {"path": "/x/NVIDIA_llamacpp-CUDA_GPU.json", "name": "NVIDIA_llamacpp-CUDA_GPU",
         "category": "llm", "scenario": "Llama3", "ep": "llama-cpp", "device": "GPU"},
        {"path": "/x/Intel_NativeOpenVINO_GPU.json", "name": "Intel_NativeOpenVINO_GPU",
         "category": "llm", "scenario": "Llama3", "ep": "NativeOpenVINO", "device": "GPU"},
    ]
    params = {"scenario": "Llama3", "backend": "llama-cpp", "device_type": "GPU"}
    # On an NVIDIA machine, the CUDA config wins and OpenVINO is not auto-picked.
    chosen = select_stock_config(configs, params, vendors={"nvidia"})
    assert chosen.endswith("NVIDIA_llamacpp-CUDA_GPU.json")
    # vendor_fit flags the OpenVINO GPU config as incompatible on NVIDIA.
    assert vendor_fit("NativeOpenVINO", "Intel_NativeOpenVINO_GPU", {"nvidia"}) < 0
    assert vendor_fit("llama-cpp", "NVIDIA_llamacpp-CUDA_GPU", {"nvidia"}) > 0
    # If only an incompatible config exists, Auto declines to pick it.
    only_openvino = [configs[1]]
    assert select_stock_config(only_openvino, params, vendors={"nvidia"}) is None


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
