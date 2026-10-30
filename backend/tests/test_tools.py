"""Tests for the runtime tool installer's asset selection (pure, no network)."""

from aibench import tools
from aibench.tools import select_cudart_asset, select_llama_asset, select_mlperf_asset

# Real-world llama.cpp release asset names (rolling b##### builds), including the
# arm64 and multi-version CUDA archives that the selector must not mis-match.
_LLAMA = [
    {"name": "cudart-llama-bin-win-cuda-12.4-x64.zip"},
    {"name": "cudart-llama-bin-win-cuda-13.4-x64.zip"},
    {"name": "cudart-llama-bin-win-cuda-13.4-arm64.zip"},
    {"name": "llama-b11982-bin-win-cpu-x64.zip"},
    {"name": "llama-b11982-bin-win-cpu-arm64.zip"},
    {"name": "llama-b11982-bin-win-cuda-12.4-x64.zip"},
    {"name": "llama-b11982-bin-win-cuda-13.4-x64.zip"},
    {"name": "llama-b11982-bin-win-cuda-13.4-arm64.zip"},
    {"name": "llama-b11982-bin-win-vulkan-x64.zip"},
    {"name": "llama-b11982-bin-win-vulkan-arm64.zip"},
    {"name": "llama-b11982-bin-ubuntu-x64.tar.gz"},
    {"name": "llama-b11982-bin-ubuntu-vulkan-x64.tar.gz"},
    {"name": "llama-b11982-bin-macos-x64.tar.gz"},
    {"name": "llama-b11982-bin-macos-arm64.tar.gz"},
]


def test_llama_windows_cpu_excludes_cudart():
    a = select_llama_asset(_LLAMA, "windows", "cpu")
    assert a["name"] == "llama-b11982-bin-win-cpu-x64.zip"


def test_llama_windows_vulkan():
    a = select_llama_asset(_LLAMA, "windows", "vulkan")
    assert a["name"] == "llama-b11982-bin-win-vulkan-x64.zip"


def test_llama_windows_cuda_picks_newest_x64_not_arm64():
    a = select_llama_asset(_LLAMA, "windows", "cuda")
    # Must be x64 (not arm64) and the newest toolkit (13.4 over 12.4).
    assert a["name"] == "llama-b11982-bin-win-cuda-13.4-x64.zip"


def test_cudart_matches_build_version_and_x64():
    # cudart picked for a 12.4 build is the 12.4 x64 runtime, never arm64.
    a = select_cudart_asset(_LLAMA, "windows", "12.4")
    assert a["name"] == "cudart-llama-bin-win-cuda-12.4-x64.zip"
    # With no version hint it falls back to the newest x64 cudart.
    b = select_cudart_asset(_LLAMA, "windows", "")
    assert b["name"] == "cudart-llama-bin-win-cuda-13.4-x64.zip"


def test_llama_linux_cpu():
    a = select_llama_asset(_LLAMA, "linux", "cpu")
    assert a["name"] == "llama-b11982-bin-ubuntu-x64.tar.gz"


def test_llama_macos():
    a = select_llama_asset(_LLAMA, "macos", "cpu")
    assert a["name"].startswith("llama-b11982-bin-macos-")


def test_llama_no_match_returns_none():
    assert select_llama_asset([{"name": "nightly-tag.txt"}], "windows", "cpu") is None


def test_resolve_variant(monkeypatch):
    # Explicit variant is respected.
    assert tools.resolve_variant("cuda") == "cuda"
    # 'auto' → vulkan when a GPU is present, cpu otherwise.
    monkeypatch.setattr(tools, "_os", lambda: "windows")
    monkeypatch.setattr("aibench.hardware.detect_gpus", lambda: [object()])
    assert tools.resolve_variant("auto") == "vulkan"
    monkeypatch.setattr("aibench.hardware.detect_gpus", lambda: [])
    assert tools.resolve_variant("auto") == "cpu"


def test_mlperf_selection_prefers_cli_over_gui():
    assets = [
        {"name": "mlperf-client-2.0.1-f0dbab3-windows-x64-gui.zip"},
        {"name": "mlperf-client-2.0.1-f0dbab3-windows-x64.zip"},
        {"name": "mlperf-client-2.0.1-f0dbab3-ubuntu-24.04.zip"},
    ]
    assert select_mlperf_asset(assets, "windows")["name"].endswith("windows-x64.zip")
    assert "gui" not in select_mlperf_asset(assets, "windows")["name"]
    assert "ubuntu" in select_mlperf_asset(assets, "linux")["name"]
