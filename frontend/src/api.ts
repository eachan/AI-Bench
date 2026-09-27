// Typed API client and live-progress WebSocket hook for the AI-Bench backend.
import { useEffect, useRef, useState } from "react";

export type ParamOption = { label: string; value: unknown };
export type ParamSpec = {
  key: string;
  label: string;
  type: "int" | "float" | "bool" | "select" | "string";
  default: unknown;
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
  options?: ParamOption[];
  help?: string;
  advanced: boolean;
};

export type Benchmark = {
  id: string;
  name: string;
  category: string;
  engine: string;
  description: string;
  metrics: string[];
  params: ParamSpec[];
  requires_binary: boolean;
  available: boolean;
  unavailable_reason?: string | null;
};

export type GpuInfo = {
  name: string;
  memory_mb?: number | null;
  driver?: string | null;
  vendor?: string | null;
  backend?: string | null;
};

export type Hardware = {
  hostname: string;
  os: string;
  os_version: string;
  python_version: string;
  cpu: {
    name: string;
    arch?: string;
    physical_cores?: number;
    logical_cores?: number;
    max_freq_mhz?: number;
  };
  memory_gb: number;
  gpus: GpuInfo[];
  captured_at: string;
};

export type Metric = {
  name: string;
  value: number;
  unit: string;
  higher_is_better: boolean;
  group?: string | null;
};
export type SeriesPoint = { step: number; value: number };
export type MetricSeries = { name: string; unit: string; points: SeriesPoint[] };

export type RunResult = {
  id: string;
  benchmark_id: string;
  benchmark_name: string;
  engine: string;
  category: string;
  label: string;
  status: "queued" | "downloading" | "running" | "completed" | "failed" | "cancelled";
  params: Record<string, unknown>;
  hardware?: Hardware | null;
  metrics: Metric[];
  series: MetricSeries[];
  logs: string[];
  error?: string | null;
  progress: number;
  phase?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
};

export type MlperfConfig = {
  path: string;
  name: string;
  category: string;
  scenario: string;
  ep: string;
  device: string;
};

export type ProgressEvent = {
  type: "progress" | "log" | "status" | "metric";
  run_id: string;
  ts: string;
  phase?: string | null;
  percent?: number | null;
  message?: string | null;
  status?: RunResult["status"] | null;
};

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => fetch("/api/health").then((r) => j<{ status: string; version: string }>(r)),
  hardware: () => fetch("/api/hardware").then((r) => j<Hardware>(r)),
  refreshHardware: () =>
    fetch("/api/hardware/refresh", { method: "POST" }).then((r) => j<Hardware>(r)),
  benchmarks: () => fetch("/api/benchmarks").then((r) => j<Benchmark[]>(r)),
  mlperfConfigs: () =>
    fetch("/api/mlperf/configs").then((r) =>
      j<{ home: string | null; configs: MlperfConfig[] }>(r)
    ),
  runs: () => fetch("/api/runs").then((r) => j<RunResult[]>(r)),
  run: (id: string) => fetch(`/api/runs/${id}`).then((r) => j<RunResult>(r)),
  createRun: (body: { benchmark_id: string; label?: string; params: Record<string, unknown> }) =>
    fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => j<RunResult>(r)),
  cancelRun: (id: string) =>
    fetch(`/api/runs/${id}/cancel`, { method: "POST" }).then((r) => j<{ cancelled: boolean }>(r)),
  deleteRun: (id: string) =>
    fetch(`/api/runs/${id}`, { method: "DELETE" }).then((r) => j<{ deleted: boolean }>(r)),
  exportProfileUrl: "/api/profile/export",
  importProfile: (payload: unknown) =>
    fetch("/api/profile/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((r) => j<{ imported_results: number; configs: number }>(r)),
};

// Subscribe to the live progress WebSocket. Reconnects automatically.
export function useProgressSocket(onEvent: (e: ProgressEvent) => void) {
  const cb = useRef(onEvent);
  cb.current = onEvent;
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let retry: ReturnType<typeof setTimeout>;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, 1500);
      };
      ws.onmessage = (m) => {
        try {
          cb.current(JSON.parse(m.data) as ProgressEvent);
        } catch {
          /* ignore malformed frames */
        }
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      ws?.close();
    };
  }, []);

  return connected;
}
