import { useMemo, useState } from "react";
import { RunResult } from "../api";
import { Card, Empty, SectionTitle } from "../components/ui";
import { CompareBarChart } from "../components/charts";

export default function Compare({ runs }: { runs: RunResult[] }) {
  const completed = runs.filter((r) => r.status === "completed" && r.metrics.length > 0);
  const [selected, setSelected] = useState<string[]>([]);

  const toggle = (id: string) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  const chosen = completed.filter((r) => selected.includes(r.id));

  // Build grouped data: one row per metric name, one series per selected run.
  const { data, keys } = useMemo(() => {
    const metricNames = new Set<string>();
    chosen.forEach((r) => r.metrics.forEach((m) => metricNames.add(m.name)));
    const keys = chosen.map((r) => r.label || r.id);
    const data = [...metricNames].map((name) => {
      const row: Record<string, string | number> = { metric: name };
      chosen.forEach((r) => {
        const m = r.metrics.find((x) => x.name === name);
        row[r.label || r.id] = m ? m.value : 0;
      });
      return row;
    });
    return { data, keys };
  }, [chosen]);

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Compare Results"
        subtitle="Select two or more completed runs to compare them side by side"
      />

      {completed.length < 2 ? (
        <Empty>Run at least two benchmarks to compare them here.</Empty>
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {completed.map((r) => (
              <button
                key={r.id}
                onClick={() => toggle(r.id)}
                className={`rounded-xl border px-3 py-2 text-sm transition ${
                  selected.includes(r.id)
                    ? "border-brand-500/60 bg-brand-600/20 text-brand-100"
                    : "border-white/10 bg-white/[0.02] text-slate-300 hover:border-white/20"
                }`}
              >
                {r.label}
                <span className="ml-2 text-xs text-slate-500">{new Date(r.created_at).toLocaleDateString()}</span>
              </button>
            ))}
          </div>

          {chosen.length >= 2 ? (
            <>
              <Card>
                <div className="label mb-2">Metric comparison</div>
                <CompareBarChart data={data} keys={keys} />
              </Card>

              <Card>
                <div className="label mb-3">Detailed comparison</div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-white/10 text-left text-slate-400">
                        <th className="py-2 pr-4 font-medium">Metric</th>
                        {chosen.map((r) => (
                          <th key={r.id} className="py-2 pr-4 font-medium text-slate-200">
                            {r.label}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {data.map((row) => (
                        <tr key={String(row.metric)} className="border-b border-white/5">
                          <td className="py-2 pr-4 text-slate-400">{row.metric}</td>
                          {chosen.map((r) => (
                            <td key={r.id} className="py-2 pr-4 font-medium text-slate-100">
                              {row[r.label || r.id]}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </>
          ) : (
            <Empty>Select at least two runs above.</Empty>
          )}
        </>
      )}
    </div>
  );
}
