import { useEffect, useMemo, useState } from "react";
import { ChevronDown, FileCog, Play, Settings2, StopCircle } from "lucide-react";
import { api, Benchmark, MlperfConfig, RunResult } from "../api";
import { Card, Empty, ProgressBar, SectionTitle, StatusBadge } from "../components/ui";
import ParamControl from "../components/ParamControl";
import { SeriesLineChart } from "../components/charts";

const CATEGORY_COLORS: Record<string, string> = {
  Compute: "bg-brand-500/20 text-brand-200",
  LLM: "bg-emerald-500/20 text-emerald-200",
  Memory: "bg-amber-500/20 text-amber-200",
  MLPerf: "bg-purple-500/20 text-purple-200",
};

export default function Tests({
  benchmarks,
  runs,
  onRunsChanged,
}: {
  benchmarks: Benchmark[];
  runs: RunResult[];
  onRunsChanged: () => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [label, setLabel] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [starting, setStarting] = useState(false);

  const selected = useMemo(
    () => benchmarks.find((b) => b.id === selectedId) ?? null,
    [benchmarks, selectedId]
  );

  useEffect(() => {
    if (!selectedId && benchmarks.length) setSelectedId(benchmarks[0].id);
  }, [benchmarks, selectedId]);

  useEffect(() => {
    if (selected) {
      const defaults: Record<string, unknown> = {};
      selected.params.forEach((p) => (defaults[p.key] = p.default));
      setParams(defaults);
      setLabel(selected.name);
    }
  }, [selected]);

  const activeRun = runs.find((r) => r.status === "running" || r.status === "queued");

  const start = async () => {
    if (!selected) return;
    setStarting(true);
    try {
      await api.createRun({ benchmark_id: selected.id, label, params });
      onRunsChanged();
    } finally {
      setStarting(false);
    }
  };

  // For MLPerf the dedicated config picker owns `config_path`, so hide the raw
  // string field to avoid two controls editing the same value.
  const hideKeys = selected?.engine === "mlperf" ? new Set(["config_path"]) : new Set<string>();
  const advancedParams = (selected?.params ?? []).filter((p) => p.advanced && !hideKeys.has(p.key));
  const basicParams = (selected?.params ?? []).filter((p) => !p.advanced && !hideKeys.has(p.key));

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Benchmarks"
        subtitle="Select a test, tune it with the controls, and run it — no files or commands needed"
      />

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        {/* Catalog */}
        <div className="space-y-3">
          {benchmarks.map((b) => (
            <button
              key={b.id}
              onClick={() => setSelectedId(b.id)}
              className={`w-full rounded-2xl border p-4 text-left transition ${
                selectedId === b.id
                  ? "border-brand-500/60 bg-brand-600/10"
                  : "border-white/10 bg-white/[0.02] hover:border-white/20"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className={`badge ${CATEGORY_COLORS[b.category] ?? "bg-white/10"}`}>
                  {b.category}
                </span>
                {!b.available && <span className="badge bg-rose-500/20 text-rose-300">needs binary</span>}
              </div>
              <div className="mt-2 font-medium text-white">{b.name}</div>
              <p className="mt-1 line-clamp-2 text-xs text-slate-400">{b.description}</p>
            </button>
          ))}
        </div>

        {/* Config + run */}
        <div className="space-y-4">
          {selected && (
            <Card>
              <div className="mb-4 flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-base font-semibold text-white">{selected.name}</h3>
                  <p className="mt-1 text-sm text-slate-400">{selected.description}</p>
                </div>
                <Settings2 size={18} className="shrink-0 text-slate-500" />
              </div>

              {!selected.available && selected.unavailable_reason && (
                <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
                  {selected.unavailable_reason}
                </div>
              )}

              <div className="mb-4">
                <label className="label">Run label</label>
                <input className="input mt-1" value={label} onChange={(e) => setLabel(e.target.value)} />
              </div>

              {selected.engine === "mlperf" && (
                <MlperfConfigPicker
                  value={(params.config_path as string) || ""}
                  onChange={(path) => setParams((prev) => ({ ...prev, config_path: path }))}
                />
              )}

              <div className="grid gap-4 sm:grid-cols-2">
                {basicParams.map((p) => (
                  <ParamControl
                    key={p.key}
                    spec={p}
                    value={params[p.key]}
                    onChange={(v) => setParams((prev) => ({ ...prev, [p.key]: v }))}
                  />
                ))}
              </div>

              {advancedParams.length > 0 && (
                <div className="mt-4">
                  <button
                    className="flex items-center gap-1 text-xs font-medium text-slate-400 hover:text-slate-200"
                    onClick={() => setShowAdvanced((s) => !s)}
                  >
                    <ChevronDown size={14} className={showAdvanced ? "rotate-180 transition" : "transition"} />
                    Advanced settings
                  </button>
                  {showAdvanced && (
                    <div className="mt-3 grid gap-4 sm:grid-cols-2">
                      {advancedParams.map((p) => (
                        <ParamControl
                          key={p.key}
                          spec={p}
                          value={params[p.key]}
                          onChange={(v) => setParams((prev) => ({ ...prev, [p.key]: v }))}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )}

              <div className="mt-5 flex items-center gap-3">
                <button className="btn-primary" onClick={start} disabled={starting || !!activeRun}>
                  <Play size={16} />
                  {activeRun ? "A run is in progress…" : "Run benchmark"}
                </button>
              </div>
            </Card>
          )}

          {activeRun ? (
            <LiveMonitor run={activeRun} />
          ) : (
            <Empty>Configure a benchmark above and click “Run benchmark” to see live progress here.</Empty>
          )}
        </div>
      </div>
    </div>
  );
}

function configLabel(c: MlperfConfig): string {
  const scenario = c.scenario || c.name;
  const parts = [scenario, c.ep, c.device].filter(Boolean);
  return parts.join(" · ") || c.name;
}

function MlperfConfigPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (path: string) => void;
}) {
  const [configs, setConfigs] = useState<MlperfConfig[] | null>(null);
  const [home, setHome] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .mlperfConfigs()
      .then((r) => {
        if (!alive) return;
        setConfigs(r.configs);
        setHome(r.home);
      })
      .catch(() => alive && setConfigs([]));
    return () => {
      alive = false;
    };
  }, []);

  // Group discovered configs by their top-level category for readable optgroups.
  const groups = useMemo(() => {
    const g: Record<string, MlperfConfig[]> = {};
    (configs ?? []).forEach((c) => {
      const key = c.category || "other";
      (g[key] ||= []).push(c);
    });
    return g;
  }, [configs]);

  return (
    <div className="mb-4 rounded-xl border border-white/10 bg-slate-900/40 p-3">
      <div className="mb-1 flex items-center gap-2">
        <FileCog size={15} className="text-brand-400" />
        <label className="label !normal-case !tracking-normal text-slate-200">
          MLPerf scenario config
        </label>
      </div>
      {configs === null ? (
        <p className="text-xs text-slate-500">Loading bundled configs…</p>
      ) : configs.length === 0 ? (
        <p className="text-xs text-slate-500">
          No bundled configs found. The runner will auto-generate one, or install the MLPerf
          Client via the AI-Bench installer to use its stock configs.
        </p>
      ) : (
        <>
          <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
            <option value="">Auto — match execution provider &amp; device below</option>
            {Object.entries(groups).map(([cat, items]) => (
              <optgroup key={cat} label={cat}>
                {items.map((c) => (
                  <option key={c.path} value={c.path}>
                    {configLabel(c)}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
          <p className="mt-1 text-xs text-slate-500">
            {value
              ? "Using the selected stock config."
              : `${configs.length} stock configs available${home ? ` in ${home}` : ""}.`}
          </p>
        </>
      )}
    </div>
  );
}

function LiveMonitor({ run }: { run: RunResult }) {
  const cancel = () => api.cancelRun(run.id);
  const tokenSeries = run.series.find((s) => s.name === "Token generation");
  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <StatusBadge status={run.status} />
          <span className="text-sm font-medium text-slate-200">{run.label}</span>
        </div>
        <button className="btn-ghost" onClick={cancel}>
          <StopCircle size={16} />
          Stop
        </button>
      </div>
      <div className="mb-1 flex items-center justify-between text-xs text-slate-400">
        <span>{run.phase ?? "Starting"}</span>
        <span>{run.progress.toFixed(0)}%</span>
      </div>
      <ProgressBar value={run.progress} />

      {tokenSeries && tokenSeries.points.length > 1 && (
        <div className="mt-4">
          <div className="label mb-1">Live throughput ({tokenSeries.unit})</div>
          <SeriesLineChart series={tokenSeries} />
        </div>
      )}

      <div className="mt-4 max-h-40 overflow-y-auto rounded-lg border border-white/10 bg-black/40 p-3 font-mono text-xs text-slate-400">
        {run.logs.slice(-40).map((l, i) => (
          <div key={i} className="whitespace-pre-wrap">
            {l}
          </div>
        ))}
      </div>
    </Card>
  );
}
