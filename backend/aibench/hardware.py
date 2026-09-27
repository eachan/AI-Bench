"""Cross-platform hardware detection.

Detects CPU, memory and GPUs on Windows, Linux and macOS.

Windows note: modern Windows 11 (24H2/25H2) removes ``wmic`` by default, so we
use PowerShell CIM (``Get-CimInstance``) as the primary source, with ``wmic``
only as a legacy fallback. GPU VRAM is resolved from reliable sources rather
than ``Win32_VideoController.AdapterRAM`` (a 32-bit field that cannot represent
>4 GB): ``nvidia-smi`` for NVIDIA cards and the display-driver registry
(``HardwareInformation.qwMemorySize``) for every adapter, so multi-GPU rigs and
large-VRAM / non-NVIDIA cards report correctly.

Parsing is split into pure functions (``parse_*`` / ``build_windows_gpus``) so
the platform-specific logic can be unit-tested with captured command output.
"""

from __future__ import annotations

import csv
import io
import os
import platform
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from typing import Optional

import psutil

from .schemas import CpuInfo, GpuInfo, HardwareInfo

_GPU_CLASS_GUID = "{4d36e968-e325-11ce-bfc1-08002be10318}"


def _run(cmd: list[str], timeout: float = 15.0) -> str:
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


def _powershell(script: str) -> str:
    exe = shutil.which("powershell") or shutil.which("pwsh")
    if not exe:
        return ""
    return _run([exe, "-NoProfile", "-NonInteractive", "-Command", script])


# --------------------------------------------------------------------------- #
# Pure parsers (unit-tested)
# --------------------------------------------------------------------------- #
def parse_csv_rows(text: str) -> list[dict[str, str]]:
    """Parse PowerShell ``ConvertTo-Csv -NoTypeInformation`` output into rows."""

    text = (text or "").strip()
    if not text:
        return []
    # ConvertTo-Csv may emit a leading "#TYPE ..." line on some hosts.
    lines = [ln for ln in text.splitlines() if not ln.startswith("#TYPE")]
    if not lines:
        return []
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    return [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in reader]


def parse_nvidia_smi_csv(text: str) -> list[dict]:
    """Parse ``nvidia-smi --query-gpu=name,memory.total,driver_version`` output."""

    gpus: list[dict] = []
    for line in (text or "").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if not parts or not parts[0]:
            continue
        name = parts[0]
        mem = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else None
        driver = parts[2] if len(parts) >= 3 and parts[2] else None
        gpus.append({"name": name, "memory_mb": mem, "driver": driver})
    return gpus


def parse_registry_vram_csv(text: str) -> dict[str, int]:
    """Map adapter name (lowercased) -> VRAM bytes from the driver registry CSV."""

    out: dict[str, int] = {}
    for row in parse_csv_rows(text):
        name = (row.get("Name") or "").strip()
        mem = (row.get("Mem") or "").strip()
        if name and mem.lstrip("-").isdigit():
            val = int(mem)
            if val > 0:
                out[name.lower()] = val
    return out


def windows_cpu_name_from_cim(text: str) -> Optional[str]:
    rows = parse_csv_rows(text)
    if rows:
        name = (rows[0].get("Name") or "").strip()
        return name or None
    return None


def _vendor_from_name(name: str) -> str:
    low = name.lower()
    if "nvidia" in low or "geforce" in low or "rtx" in low or "gtx" in low or "quadro" in low:
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


def _norm_gpu(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _names_match(a: str, b: str) -> bool:
    na, nb = _norm_gpu(a), _norm_gpu(b)
    if not na or not nb:
        return False
    if na in nb or nb in na:
        return True
    # Match on a shared 3-5 digit model number (e.g. 5090, 3090).
    ma = set(re.findall(r"\d{3,5}", a))
    mb = set(re.findall(r"\d{3,5}", b))
    return bool(ma & mb)


def build_windows_gpus(
    cim_gpus: list[dict],
    nvidia: list[dict],
    vram_by_name: dict[str, int],
) -> list[GpuInfo]:
    """Combine CIM adapter enumeration with accurate VRAM sources.

    * Adapter names/drivers come from CIM (reliable for all vendors).
    * VRAM comes from nvidia-smi (NVIDIA) or the driver registry (any vendor);
      the unreliable CIM ``AdapterRAM`` is used only as a last resort and only
      when it is a sane sub-4 GB value.
    """

    result: list[GpuInfo] = []
    nvidia_used = [False] * len(nvidia)

    def _vram_from_registry(name: str) -> Optional[int]:
        key = name.lower()
        if key in vram_by_name:
            return vram_by_name[key] // (1024 * 1024)
        for reg_name, b in vram_by_name.items():
            if _names_match(reg_name, name):
                return b // (1024 * 1024)
        return None

    for g in cim_gpus:
        name = (g.get("name") or "").strip()
        if not name:
            continue
        vendor = _vendor_from_name(name)
        driver = g.get("driver") or None
        mem: Optional[int] = None

        if vendor == "NVIDIA":
            for i, n in enumerate(nvidia):
                if not nvidia_used[i] and _names_match(n["name"], name):
                    mem = n.get("memory_mb")
                    driver = n.get("driver") or driver
                    nvidia_used[i] = True
                    break
        if mem is None:
            mem = _vram_from_registry(name)
        if mem is None:
            ram = g.get("adapter_ram")
            if isinstance(ram, int) and 0 < ram < 4 * 1024**3:
                mem = ram // (1024 * 1024)

        result.append(
            GpuInfo(
                name=name,
                memory_mb=mem,
                driver=driver,
                vendor=vendor,
                backend=_backend_for_vendor(vendor),
            )
        )

    # Any NVIDIA GPUs that CIM missed (rare) — add from nvidia-smi directly.
    for i, n in enumerate(nvidia):
        if not nvidia_used[i]:
            result.append(
                GpuInfo(
                    name=n["name"],
                    memory_mb=n.get("memory_mb"),
                    driver=n.get("driver"),
                    vendor="NVIDIA",
                    backend="CUDA",
                )
            )
    return result


# --------------------------------------------------------------------------- #
# CPU
# --------------------------------------------------------------------------- #
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
        # Primary: PowerShell CIM (works on Win11 24H2/25H2 where wmic is gone).
        name = windows_cpu_name_from_cim(
            _powershell("Get-CimInstance Win32_Processor | Select-Object Name | ConvertTo-Csv -NoTypeInformation")
        )
        if name:
            return name
        # Legacy fallback: wmic (older Windows).
        wmic = _run(["wmic", "cpu", "get", "name"])
        lines = [l.strip() for l in wmic.splitlines() if l.strip() and "Name" not in l]
        if lines:
            return lines[0]
        env = os.environ.get("PROCESSOR_IDENTIFIER")
        if env:
            return env
    return platform.processor() or platform.machine() or "Unknown CPU"


def _windows_cpu_mhz() -> Optional[float]:
    rows = parse_csv_rows(
        _powershell("Get-CimInstance Win32_Processor | Select-Object MaxClockSpeed | ConvertTo-Csv -NoTypeInformation")
    )
    if rows:
        v = (rows[0].get("MaxClockSpeed") or "").strip()
        if v.isdigit():
            return float(v)
    return None


# --------------------------------------------------------------------------- #
# GPUs
# --------------------------------------------------------------------------- #
def _detect_nvidia_gpus() -> list[dict]:
    if not shutil.which("nvidia-smi"):
        return []
    return parse_nvidia_smi_csv(
        _run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ]
        )
    )


def _detect_windows_gpus() -> list[GpuInfo]:
    # 1) Enumerate all adapters (names + drivers) via CIM.
    cim_rows: list[dict] = []
    for row in parse_csv_rows(
        _powershell(
            "Get-CimInstance Win32_VideoController | "
            "Select-Object Name,AdapterRAM,DriverVersion | ConvertTo-Csv -NoTypeInformation"
        )
    ):
        ram = row.get("AdapterRAM", "")
        cim_rows.append(
            {
                "name": row.get("Name", ""),
                "driver": row.get("DriverVersion") or None,
                "adapter_ram": int(ram) if ram.lstrip("-").isdigit() else None,
            }
        )

    # 2) Accurate VRAM for every adapter from the display-driver registry.
    vram = parse_registry_vram_csv(
        _powershell(
            "Get-ItemProperty "
            f"'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\{_GPU_CLASS_GUID}\\*' "
            "-ErrorAction SilentlyContinue | "
            "Where-Object { $_.'HardwareInformation.qwMemorySize' } | "
            "Select-Object @{N='Name';E={$_.DriverDesc}},"
            "@{N='Mem';E={$_.'HardwareInformation.qwMemorySize'}} | "
            "ConvertTo-Csv -NoTypeInformation"
        )
    )

    # 3) Accurate NVIDIA VRAM/driver from nvidia-smi.
    nvidia = _detect_nvidia_gpus()

    gpus = build_windows_gpus(cim_rows, nvidia, vram)
    if gpus:
        return gpus
    # Legacy fallback if CIM/registry were unavailable: nvidia-smi only.
    return [
        GpuInfo(name=n["name"], memory_mb=n.get("memory_mb"), driver=n.get("driver"),
                vendor="NVIDIA", backend="CUDA")
        for n in nvidia
    ]


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


def detect_gpus() -> list[GpuInfo]:
    system = platform.system()
    if system == "Windows":
        return _detect_windows_gpus()
    if system == "Darwin":
        gpus = [
            GpuInfo(name=n["name"], memory_mb=n.get("memory_mb"), driver=n.get("driver"),
                    vendor="NVIDIA", backend="CUDA")
            for n in _detect_nvidia_gpus()
        ]
        return gpus or _detect_macos_gpus()
    # Linux (and others): nvidia-smi if present.
    return [
        GpuInfo(name=n["name"], memory_mb=n.get("memory_mb"), driver=n.get("driver"),
                vendor="NVIDIA", backend="CUDA")
        for n in _detect_nvidia_gpus()
    ]


@lru_cache(maxsize=1)
def detect_hardware() -> HardwareInfo:
    freq = None
    try:
        cf = psutil.cpu_freq()
        if cf:
            freq = cf.max or cf.current
    except Exception:  # pragma: no cover - platform dependent
        freq = None
    if (not freq) and platform.system() == "Windows":
        freq = _windows_cpu_mhz()

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
