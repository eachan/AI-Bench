import { useRef, useState } from "react";
import { Download, Trash2, Upload } from "lucide-react";
import { api, RunResult } from "../api";
import { Card, Empty, SectionTitle, StatusBadge, Stat } from "../components/ui";
import { MetricBarChart, SeriesLineChart } from "../components/charts";

export default function Results({
  runs,
  onRunsChanged,
}: {
  runs: RunResult[];
  onRunsChanged: () => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const selected = runs.find((r) => r.id === selectedId) ?? runs[0] ?? null;

  const doImport = async (file: File) => {
    try {
      const payload = JSON.parse(await file.text());
      const res = await api.importProfile(payload);
      setImportMsg(`Imported ${res.imported_results} result(s).`);
      onRunsChanged();
    } catch (e) {
      setImportMsg(`Import failed: ${(e as Error).message}`);
    }
  };

  const remove = async (id: string) => {
    await api.deleteRun(id);
    if (selectedId === id) setSelectedId(null);
    onRunsChanged();
  };

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Results"
        subtitle="Review, visualize, and share benchmark results"
        right={
          <div className="flex gap-2">
            <a className="btn-ghost" href={api.exportProfileUrl} download>
              <Download size={16} />
              Export
            </a>
            <button className="btn-ghost" onClick={() => fileRef.current?.click()}>
              <Upload size={16} />
              Import
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="application/json"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && doImport(e.target.files[0])}
            />
          </div>
        }
      />

      {importMsg && (
        <div className="rounded-lg border border-brand-500/30 bg-brand-600/10 p-3 text-sm text-brand-200">
          {importMsg}
        </div>
      )}

      {runs.length === 0 ? (
        <Empty>No results yet. Run a benchmark from the Tests tab.</Empty>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
          <div className="space-y-2">
            {runs.map((r) => (
              <button
                key={r.id}
                onClick={() => setSelectedId(r.id)}
                className={`w-full rounded-xl border p-3 text-left transition ${
                  selected?.id === r.id
                    ? "border-brand-500/60 bg-brand-600/10"
                    : "border-white/10 bg-white/[0.02] hover:border-white/20"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="truncate font-medium text-slate-100">{r.label}</span>
                  <StatusBadge status={r.status} />
                </div>
                <div className="mt-1 flex items-center justify-between text-xs text-slate-500">
                  <span>{new Date(r.created_at).toLocaleString()}</span>
                  <span>{r.category}</span>
                </div>
              </button>
            ))}
          </div>

          {selected && <ResultDetail run={selected} onDelete={() => remove(selected.id)} />}
        </div>
      )}
    </div>
  );
}

function ResultDetail({ run, onDelete }: { run: RunResult; onDelete: () => void }) {
  return (
    <div className="space-y-4">
      <Card>
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-lg font-semibold text-white">{run.label}</h3>
            <p className="text-sm text-slate-400">
              {run.benchmark_name} · {run.engine}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge status={run.status} />
            <button className="btn-ghost !px-2" onClick={onDelete} title="Delete result">
              <Trash2 size={16} />
            </button>
          </div>
        </div>

        {run.error && (
          <div className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">
            {run.error}
          </div>
        )}

        {run.metrics.length > 0 && (
          <>
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {run.metrics.map((m) => (
                <Stat key={m.name} label={m.name} value={m.value} unit={m.unit} />
              ))}
            </div>
            <div className="mt-5">
              <div className="label mb-2">Metric overview</div>
              <MetricBarChart metrics={run.metrics} />
            </div>
          </>
        )}
      </Card>

      {run.series
        .filter((s) => s.points.length > 1)
        .map((s) => (
          <Card key={s.name}>
            <div className="label mb-2">
              {s.name} ({s.unit})
            </div>
            <SeriesLineChart series={s} />
          </Card>
        ))}

      {run.hardware && (
        <Card>
          <div className="label mb-2">Hardware</div>
          <div className="grid grid-cols-2 gap-2 text-sm text-slate-300 sm:grid-cols-3">
            <div>{run.hardware.cpu.name}</div>
            <div>{run.hardware.memory_gb} GB RAM</div>
            <div>{run.hardware.gpus[0]?.name ?? "No discrete GPU"}</div>
          </div>
        </Card>
      )}

      <Card>
        <div className="label mb-2">Parameters</div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
          {Object.entries(run.params).map(([k, v]) => (
            <div key={k} className="flex justify-between gap-2 border-b border-white/5 py-1">
              <span className="text-slate-500">{k}</span>
              <span className="text-slate-200">{String(v)}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
