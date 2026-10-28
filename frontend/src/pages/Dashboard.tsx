import { ReactNode, useState } from "react";
import { Cpu, HardDrive, Info, MemoryStick, MonitorCog, RefreshCw, Server } from "lucide-react";
import { api, Hardware, RunResult } from "../api";
import { Card, Empty, SectionTitle, Stat, StatusBadge } from "../components/ui";

export default function Dashboard({
  hardware,
  setHardware,
  runs,
}: {
  hardware: Hardware | null;
  setHardware: (h: Hardware) => void;
  runs: RunResult[];
}) {
  const [refreshing, setRefreshing] = useState(false);

  const refresh = async () => {
    setRefreshing(true);
    try {
      setHardware(await api.refreshHardware());
    } finally {
      setRefreshing(false);
    }
  };

  const recent = runs.slice(0, 5);

  return (
    <div className="space-y-6">
      <SectionTitle
        title="System Dashboard"
        subtitle="Detected hardware and capabilities for local model inference"
        right={
          <button className="btn-ghost" onClick={refresh} disabled={refreshing}>
            <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>
        }
      />

      {hardware && hardware.packaged === false && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-100">
          <Info size={18} className="mt-0.5 shrink-0 text-amber-300" />
          <div>
            <div className="font-medium">This is a preview/dev instance, not your PC.</div>
            <p className="mt-1 text-amber-200/90">
              AI-Bench profiles the machine it runs on. This instance is running on{" "}
              <span className="font-semibold">
                {hardware.os} host “{hardware.hostname}”
              </span>
              , so the specs below describe that host — not your computer. To benchmark your own
              hardware, install AI-Bench on your PC and launch it there; the dashboard will then
              show your CPU, memory and GPU(s).
            </p>
          </div>
        </div>
      )}

      {!hardware ? (
        <Empty>Detecting hardware…</Empty>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <Stat label="CPU cores" value={hardware.cpu.logical_cores ?? "?"} unit="threads" />
            <Stat label="Memory" value={hardware.memory_gb} unit="GB" />
            <Stat label="GPUs" value={hardware.gpus.length} />
            <Stat label="Platform" value={hardware.os} />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <div className="mb-3 flex items-center gap-2 text-slate-200">
                <Cpu size={18} className="text-brand-400" />
                <span className="font-medium">Processor</span>
              </div>
              <div className="space-y-2 text-sm">
                <Row label="Model" value={hardware.cpu.name} />
                <Row label="Architecture" value={hardware.cpu.arch ?? "—"} />
                <Row
                  label="Cores / threads"
                  value={`${hardware.cpu.physical_cores ?? "?"} / ${hardware.cpu.logical_cores ?? "?"}`}
                />
                <Row
                  label="Max frequency"
                  value={hardware.cpu.max_freq_mhz ? `${(hardware.cpu.max_freq_mhz / 1000).toFixed(2)} GHz` : "—"}
                />
              </div>
            </Card>

            <Card>
              <div className="mb-3 flex items-center gap-2 text-slate-200">
                <Server size={18} className="text-brand-400" />
                <span className="font-medium">System</span>
              </div>
              <div className="space-y-2 text-sm">
                <Row label="Hostname" value={hardware.hostname} icon={<MonitorCog size={14} />} />
                <Row label="OS" value={`${hardware.os} ${hardware.os_version}`} />
                <Row label="Python" value={hardware.python_version} />
                <Row label="Memory" value={`${hardware.memory_gb} GB`} icon={<MemoryStick size={14} />} />
              </div>
            </Card>
          </div>

          <Card>
            <div className="mb-3 flex items-center gap-2 text-slate-200">
              <HardDrive size={18} className="text-brand-400" />
              <span className="font-medium">Graphics / Accelerators</span>
            </div>
            {hardware.gpus.length === 0 ? (
              <p className="text-sm text-slate-400">
                No discrete GPU detected. Synthetic and CPU benchmarks are still available; GPU
                acceleration will be used automatically when present.
              </p>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {hardware.gpus.map((g, i) => (
                  <div key={i} className="rounded-xl border border-white/10 bg-slate-900/40 p-4">
                    <div className="font-medium text-white">{g.name}</div>
                    <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-400">
                      {g.vendor && <span className="badge bg-white/5">{g.vendor}</span>}
                      {g.backend && <span className="badge bg-white/5">{g.backend}</span>}
                      {g.memory_mb && <span className="badge bg-white/5">{(g.memory_mb / 1024).toFixed(1)} GB</span>}
                      {g.driver && <span className="badge bg-white/5">driver {g.driver}</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card>
            <SectionTitle title="Recent runs" />
            {recent.length === 0 ? (
              <Empty>No runs yet. Head to the Tests tab to start a benchmark.</Empty>
            ) : (
              <div className="divide-y divide-white/5">
                {recent.map((r) => (
                  <div key={r.id} className="flex items-center justify-between py-2.5 text-sm">
                    <div>
                      <div className="font-medium text-slate-100">{r.label}</div>
                      <div className="text-xs text-slate-500">{r.benchmark_name}</div>
                    </div>
                    <StatusBadge status={r.status} />
                  </div>
                ))}
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

function Row({ label, value, icon }: { label: string; value: string; icon?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="flex items-center gap-1.5 text-slate-400">
        {icon}
        {label}
      </span>
      <span className="text-right font-medium text-slate-100">{value}</span>
    </div>
  );
}
