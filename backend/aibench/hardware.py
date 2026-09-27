"""Cross-platform hardware detection.

Detects CPU, memory and GPUs on Windows, Linux and macOS. GPU detection is
best-effort: it tries ``nvidia-smi`` first, then platform-specific queries
(``wmic`` on Windows, ``system_profiler`` on macOS). Everything degrades
gracefully to an empty GPU list when nothing is found, so the app is fully
functional on machines without a discrete GPU.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
from functools import lru_cache

import psutil

from .schemas import CpuInfo, GpuInfo, HardwareInfo


def _run(cmd: list[str], timeout: float = 6.0) -> str:
    try:
        out = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return out.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _cpu_name() -> str:
    system = platform.system()
    if system == "Linux":
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if line.lower().startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except OSError:
            pass
    elif system == "Darwin":
        name = _run(["sysctl", "-n", "machdep.cpu.brand_string"]).strip()
        if name:
            return name
    elif system == "Windows":
        # PROCESSOR_IDENTIFIER is coarse but always present.
        import os

        env = os.environ.get("PROCESSOR_IDENTIFIER")
        wmic = _run(["wmic", "cpu", "get", "name"])
        lines = [l.strip() for l in wmic.splitlines() if l.strip() and "Name" not in l]
        if lines:
            return lines[0]
        if env:
            return env
    return platform.processor() or platform.machine() or "Unknown CPU"


def _detect_nvidia_gpus() -> list[GpuInfo]:
    if not shutil.which("nvidia-smi"):
        return []
    out = _run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    gpus: list[GpuInfo] = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if not parts or not parts[0]:
            continue
        name = parts[0]
        mem = None
        driver = None
        if len(parts) >= 2 and parts[1].isdigit():
            mem = int(parts[1])
        if len(parts) >= 3:
            driver = parts[2]
        gpus.append(
            GpuInfo(
                name=name,
                memory_mb=mem,
                driver=driver,
                vendor="NVIDIA",
                backend="CUDA",
            )
        )
    return gpus


def _detect_windows_gpus() -> list[GpuInfo]:
    out = _run(
        [
            "wmic",
            "path",
            "win32_VideoController",
            "get",
            "Name,AdapterRAM,DriverVersion",
            "/format:csv",
        ]
    )
    gpus: list[GpuInfo] = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("node") or "," not in line:
            continue
        cols = line.split(",")
        # CSV format: Node,AdapterRAM,DriverVersion,Name
        if len(cols) < 4:
            continue
        ram, driver, name = cols[1].strip(), cols[2].strip(), cols[3].strip()
        if not name:
            continue
        mem = int(ram) // (1024 * 1024) if ram.isdigit() else None
        vendor = _vendor_from_name(name)
        gpus.append(
            GpuInfo(
                name=name,
                memory_mb=mem,
                driver=driver or None,
                vendor=vendor,
                backend=_backend_for_vendor(vendor),
            )
        )
    return gpus


def _detect_macos_gpus() -> list[GpuInfo]:
    out = _run(["system_profiler", "SPDisplaysDataType"])
    gpus: list[GpuInfo] = []
    name = None
    mem = None
    for line in out.splitlines():
        s = line.strip()
        m = re.match(r"Chipset Model:\s*(.+)", s)
        if m:
            if name:
                gpus.append(GpuInfo(name=name, memory_mb=mem, vendor="Apple", backend="Metal"))
            name = m.group(1).strip()
            mem = None
        m = re.match(r"VRAM.*:\s*([0-9]+)\s*GB", s)
        if m:
            mem = int(m.group(1)) * 1024
    if name:
        gpus.append(GpuInfo(name=name, memory_mb=mem, vendor="Apple", backend="Metal"))
    return gpus


def _vendor_from_name(name: str) -> str:
    low = name.lower()
    if "nvidia" in low or "geforce" in low or "rtx" in low or "quadro" in low:
        return "NVIDIA"
    if "amd" in low or "radeon" in low:
        return "AMD"
    if "intel" in low or "arc" in low:
        return "Intel"
    if "apple" in low:
        return "Apple"
    return "Unknown"


def _backend_for_vendor(vendor: str) -> str:
    return {
        "NVIDIA": "CUDA",
        "AMD": "ROCm/DirectML",
        "Intel": "OpenVINO/DirectML",
        "Apple": "Metal",
    }.get(vendor, "CPU")


def detect_gpus() -> list[GpuInfo]:
    gpus = _detect_nvidia_gpus()
    system = platform.system()
    if system == "Windows":
        # Merge in any non-NVIDIA adapters reported by Windows.
        existing = {g.name for g in gpus}
        for g in _detect_windows_gpus():
            if g.name not in existing:
                gpus.append(g)
    elif system == "Darwin" and not gpus:
        gpus = _detect_macos_gpus()
    return gpus


@lru_cache(maxsize=1)
def detect_hardware() -> HardwareInfo:
    freq = None
    try:
        cf = psutil.cpu_freq()
        if cf:
            freq = cf.max or cf.current
    except Exception:  # pragma: no cover - platform dependent
        freq = None

    cpu = CpuInfo(
        name=_cpu_name(),
        arch=platform.machine(),
        physical_cores=psutil.cpu_count(logical=False),
        logical_cores=psutil.cpu_count(logical=True),
        max_freq_mhz=freq,
    )
    mem_gb = round(psutil.virtual_memory().total / (1024**3), 2)
    return HardwareInfo(
        hostname=platform.node() or "localhost",
        os=platform.system(),
        os_version=platform.version(),
        python_version=sys.version.split()[0],
        cpu=cpu,
        memory_gb=mem_gb,
        gpus=detect_gpus(),
    )


def refresh_hardware() -> HardwareInfo:
    detect_hardware.cache_clear()
    return detect_hardware()
