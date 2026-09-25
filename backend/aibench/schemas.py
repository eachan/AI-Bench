"""Pydantic schemas shared across the API, engine, and storage layers."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Hardware
# --------------------------------------------------------------------------- #
class GpuInfo(BaseModel):
    name: str
    memory_mb: Optional[int] = None
    driver: Optional[str] = None
    vendor: Optional[str] = None
    backend: Optional[str] = None  # CUDA / ROCm / Metal / DirectML / CPU


class CpuInfo(BaseModel):
    name: str
    arch: Optional[str] = None
    physical_cores: Optional[int] = None
    logical_cores: Optional[int] = None
    max_freq_mhz: Optional[float] = None


class HardwareInfo(BaseModel):
    hostname: str
    os: str
    os_version: str
    python_version: str
    cpu: CpuInfo
    memory_gb: float
    gpus: list[GpuInfo] = Field(default_factory=list)
    captured_at: str = Field(default_factory=utcnow_iso)


# --------------------------------------------------------------------------- #
# Benchmark catalog
# --------------------------------------------------------------------------- #
ParamType = Literal["int", "float", "bool", "select", "string"]


class ParamOption(BaseModel):
    label: str
    value: Any


class ParamSpec(BaseModel):
    key: str
    label: str
    type: ParamType
    default: Any = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    unit: Optional[str] = None
    options: Optional[list[ParamOption]] = None
    help: Optional[str] = None
    advanced: bool = False


class BenchmarkDefinition(BaseModel):
    id: str
    name: str
    category: str  # LLM | Compute | Memory | MLPerf
    engine: str  # synthetic | llama-bench | mlperf
    description: str
    metrics: list[str] = Field(default_factory=list)
    params: list[ParamSpec] = Field(default_factory=list)
    requires_binary: bool = False
    available: bool = True
    unavailable_reason: Optional[str] = None


# --------------------------------------------------------------------------- #
# Runs & results
# --------------------------------------------------------------------------- #
class RunStatus(str, Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Metric(BaseModel):
    name: str
    value: float
    unit: str = ""
    higher_is_better: bool = True
    group: Optional[str] = None


class SeriesPoint(BaseModel):
    step: float
    value: float


class MetricSeries(BaseModel):
    name: str
    unit: str = ""
    points: list[SeriesPoint] = Field(default_factory=list)


class ProgressEvent(BaseModel):
    type: Literal["progress", "log", "status", "metric"] = "progress"
    run_id: str
    ts: str = Field(default_factory=utcnow_iso)
    phase: Optional[str] = None
    percent: Optional[float] = None
    message: Optional[str] = None
    status: Optional[RunStatus] = None


class RunConfig(BaseModel):
    benchmark_id: str
    label: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)


class RunResult(BaseModel):
    id: str
    benchmark_id: str
    benchmark_name: str
    engine: str
    category: str
    label: str
    status: RunStatus
    params: dict[str, Any] = Field(default_factory=dict)
    hardware: Optional[HardwareInfo] = None
    metrics: list[Metric] = Field(default_factory=list)
    series: list[MetricSeries] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    progress: float = 0.0
    phase: Optional[str] = None
    created_at: str = Field(default_factory=utcnow_iso)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class TestProfile(BaseModel):
    """Shareable export bundle: test parameter settings and (optionally) results."""

    app: str = "AI-Bench"
    version: str = "1"
    exported_at: str = Field(default_factory=utcnow_iso)
    hardware: Optional[HardwareInfo] = None
    configs: list[RunConfig] = Field(default_factory=list)
    results: list[RunResult] = Field(default_factory=list)
