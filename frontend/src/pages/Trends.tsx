import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { RunResult } from "../api";
import { Card, Empty, SectionTitle, Stat } from "../components/ui";

export default function Trends({ runs }: { runs: RunResult[] }) {
  const completed = useMemo(
    () => runs.filter((r) => r.status === "completed" && r.metrics.length > 0),
    [runs]
  );

  const benchmarks = useMemo(() => {
    const m = new Map<string, string>();
    completed.forEach((r) => m.set(r.benchmark_id, r.benchmark_name));
    return [...m.entries()].map(([id, name]) => ({ id, name }));
  }, [completed]);

  const [benchmarkId, setBenchmarkId] = useState<string>("");
  useEffect(() => {
    if (!benchmarkId && benchmarks.length) setBenchmarkId(benchmarks[0].id);
  }, [benchmarks, benchmarkId]);

  const benchRuns = useMemo(
    () =>
      completed
        .filter((r) => r.benchmark_id === benchmarkId)
        .sort((a, b) => a.created_at.localeCompare(b.created_at)),
    [completed, benchmarkId]
  );

  const metricNames = useMemo(() => {
    const s = new Set<string>();
    benchRuns.forEach((r) => r.metrics.forEach((m) => s.add(m.name)));
    return [...s];
  }, [benchRuns]);

  const [metricName, setMetricName] = useState<string>("");
  useEffect(() => {
    if (metricNames.length && !metricNames.includes(metricName)) setMetricName(metricNames[0]);
  }, [metricNames, metricName]);

  const { data, unit } = useMemo(() => {
    let unit = "";
    const data = benchRuns
      .map((r, i) => {
        const m = r.metrics.find((x) => x.name === metricName);
        if (!m) return null;
        unit = m.unit;
        return {
          idx: i + 1,
          date: new Date(r.created_at).toLocaleString(undefined, {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
          }),
          value: m.value,
          label: r.label,
        };
      })
      .filter(Boolean) as { idx: number; date: string; value: number; label: string }[];
    return { data, unit };
  }, [benchRuns, metricName]);

  const values = data.map((d) => d.value);
  const latest = values.length ? values[values.length - 1] : undefined;
  const best = values.length ? Math.max(...values) : undefined;
  const avg = values.length ? values.reduce((a, b) => a + b, 0) / values.length : undefined;

  if (completed.length === 0) {
    return (
      <div className="space-y-6">
        <SectionTitle title="Trends" subtitle="Track how your results change across runs over time" />
        <Empty>No completed runs yet. Run some benchmarks to build a history.</Empty>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Trends"
        subtitle="Track how a metric changes across runs over time (e.g. after driver or config changes)"
      />

      <Card>
        <div className="flex flex-wrap gap-4">
          <div className="min-w-[220px] flex-1">
            <label className="label">Benchmark</label>
            <select className="input mt-1" value={benchmarkId} onChange={(e) => setBenchmarkId(e.target.value)}>
              {benchmarks.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </div>
          <div className="min-w-[220px] flex-1">
            <label className="label">Metric</label>
            <select className="input mt-1" value={metricName} onChange={(e) => setMetricName(e.target.value)}>
              {metricNames.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
        </div>

        {data.length < 2 ? (
          <Empty>
            Only {data.length} run with this metric. Run this benchmark again to see a trend.
          </Empty>
        ) : (
          <>
            <div className="mt-4 grid grid-cols-3 gap-3">
              <Stat label="Latest" value={latest ?? "—"} unit={unit} />
              <Stat label="Best" value={best ?? "—"} unit={unit} />
              <Stat label="Average" value={avg ? Number(avg.toFixed(2)) : "—"} unit={unit} />
            </div>
            <div className="mt-5">
              <div className="label mb-2">
                {metricName} over time ({unit})
              </div>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="date" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{
                      background: "#0f172a",
                      border: "1px solid rgba(255,255,255,0.1)",
                      borderRadius: 12,
                      color: "#e6ebf5",
                    }}
                    formatter={(v: number) => [`${v} ${unit}`, metricName]}
                    labelFormatter={(l) => `Run: ${l}`}
                  />
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke="#3385fb"
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
