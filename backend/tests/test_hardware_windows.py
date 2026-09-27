"""Windows hardware-detection parser tests.

These exercise the pure parsers with command output shaped like a real Windows
11 25H2 machine (multi-GPU: RTX 5090 / RTX 3090 / AMD Radeon), so the logic is
validated even though it can't run on the Linux CI host.
"""

from aibench.hardware import (
    build_windows_gpus,
    parse_csv_rows,
    parse_nvidia_smi_csv,
    parse_registry_vram_csv,
    windows_cpu_name_from_cim,
)

# nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits
NVIDIA_SMI = """NVIDIA GeForce RTX 5090, 32607, 581.42
NVIDIA GeForce RTX 3090, 24576, 581.29
"""

# Get-CimInstance Win32_VideoController | Select Name,AdapterRAM,DriverVersion | ConvertTo-Csv
# AdapterRAM is a 32-bit field: it saturates (~4 GB) or overflows negative for
# large-VRAM cards, so it must NOT be trusted for VRAM.
CIM_GPUS = (
    '"Name","AdapterRAM","DriverVersion"\r\n'
    '"NVIDIA GeForce RTX 5090","4293918720","32.0.15.8142"\r\n'
    '"NVIDIA GeForce RTX 3090","-1073741824","32.0.15.7042"\r\n'
    '"AMD Radeon(TM) Graphics","4293918720","31.0.24027.1012"\r\n'
)

# Driver registry HardwareInformation.qwMemorySize (bytes) — accurate for all vendors.
REG_VRAM = (
    '#TYPE Selected.Microsoft.Win32.RegistryKey\r\n'
    '"Name","Mem"\r\n'
    '"NVIDIA GeForce RTX 5090","34084302848"\r\n'
    '"NVIDIA GeForce RTX 3090","25769803776"\r\n'
    '"AMD Radeon(TM) Graphics","8589934592"\r\n'
)

CIM_CPU = '"Name"\r\n"AMD Ryzen 9 9950X3D 16-Core Processor"\r\n'


def test_cpu_name_from_cim():
    assert windows_cpu_name_from_cim(CIM_CPU) == "AMD Ryzen 9 9950X3D 16-Core Processor"
    assert windows_cpu_name_from_cim("") is None


def test_parse_nvidia_smi():
    rows = parse_nvidia_smi_csv(NVIDIA_SMI)
    assert [r["name"] for r in rows] == ["NVIDIA GeForce RTX 5090", "NVIDIA GeForce RTX 3090"]
    assert rows[0]["memory_mb"] == 32607
    assert rows[1]["driver"] == "581.29"


def test_parse_registry_vram_skips_type_line():
    vram = parse_registry_vram_csv(REG_VRAM)
    assert vram["amd radeon(tm) graphics"] == 8589934592
    assert vram["nvidia geforce rtx 5090"] == 34084302848


def test_build_windows_gpus_multi_gpu_accurate_vram():
    cim = [
        {"name": r["Name"], "driver": r["DriverVersion"],
         "adapter_ram": int(r["AdapterRAM"])}
        for r in parse_csv_rows(CIM_GPUS)
    ]
    nvidia = parse_nvidia_smi_csv(NVIDIA_SMI)
    vram = parse_registry_vram_csv(REG_VRAM)

    gpus = build_windows_gpus(cim, nvidia, vram)
    assert len(gpus) == 3

    by_name = {g.name: g for g in gpus}
    g5090 = by_name["NVIDIA GeForce RTX 5090"]
    g3090 = by_name["NVIDIA GeForce RTX 3090"]
    amd = by_name["AMD Radeon(TM) Graphics"]

    # NVIDIA VRAM comes from nvidia-smi (accurate), not the garbage AdapterRAM.
    assert g5090.memory_mb == 32607 and g5090.vendor == "NVIDIA" and g5090.backend == "CUDA"
    assert g3090.memory_mb == 24576 and g3090.vendor == "NVIDIA"
    # AMD VRAM comes from the driver registry: 8 GiB, not the ~4 GB AdapterRAM cap.
    assert amd.memory_mb == 8192 and amd.vendor == "AMD"
    assert amd.memory_mb != 4095  # would be the wrong AdapterRAM-derived value


def test_build_windows_gpus_adapterram_only_when_sane():
    # No nvidia-smi, no registry: a small (<4 GB) AdapterRAM is trusted; a
    # saturated 4 GB value is treated as unknown.
    cim = [
        {"name": "Intel Arc A380", "driver": "31.0.0", "adapter_ram": 6 * 1024**3},  # too big → untrusted
        {"name": "Intel HD Graphics", "driver": "31.0.0", "adapter_ram": 2 * 1024**3},  # sane
    ]
    gpus = build_windows_gpus(cim, [], {})
    mems = {g.name: g.memory_mb for g in gpus}
    assert mems["Intel HD Graphics"] == 2048
    assert mems["Intel Arc A380"] is None


def test_build_windows_gpus_handles_missing_cim():
    # CIM empty but nvidia-smi present → still list the NVIDIA cards.
    gpus = build_windows_gpus([], parse_nvidia_smi_csv(NVIDIA_SMI), {})
    assert [g.name for g in gpus] == ["NVIDIA GeForce RTX 5090", "NVIDIA GeForce RTX 3090"]
