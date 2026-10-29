"""Tests for the runtime tool installer's asset selection (pure, no network)."""

from aibench.tools import select_llama_asset, select_mlperf_asset

# Real-world llama.cpp release asset names (rolling b##### builds).
_LLAMA = [
    {"name": "cudart-llama-bin-win-cuda-13.4-x64.zip"},
    {"name": "llama-b11982-bin-win-cpu-x64.zip"},
    {"name": "llama-b11982-bin-win-cuda-13.4-x64.zip"},
    {"name": "llama-b11982-bin-win-vulkan-x64.zip"},
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


def test_llama_linux_cpu():
    a = select_llama_asset(_LLAMA, "linux", "cpu")
    assert a["name"] == "llama-b11982-bin-ubuntu-x64.tar.gz"


def test_llama_macos():
    a = select_llama_asset(_LLAMA, "macos", "cpu")
    assert a["name"].startswith("llama-b11982-bin-macos-")


def test_llama_no_match_returns_none():
    assert select_llama_asset([{"name": "nightly-tag.txt"}], "windows", "cpu") is None


def test_mlperf_selection_prefers_cli_over_gui():
    assets = [
        {"name": "mlperf-client-2.0.1-f0dbab3-windows-x64-gui.zip"},
        {"name": "mlperf-client-2.0.1-f0dbab3-windows-x64.zip"},
        {"name": "mlperf-client-2.0.1-f0dbab3-ubuntu-24.04.zip"},
    ]
    assert select_mlperf_asset(assets, "windows")["name"].endswith("windows-x64.zip")
    assert "gui" not in select_mlperf_asset(assets, "windows")["name"]
    assert "ubuntu" in select_mlperf_asset(assets, "linux")["name"]
