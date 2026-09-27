import { useCallback, useEffect, useMemo, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Activity, Boxes, Cpu, FlaskConical, GitCompare, TrendingUp, Wifi, WifiOff } from "lucide-react";
import {
  api,
  Benchmark,
  Hardware,
  ProgressEvent,
  RunResult,
  useProgressSocket,
} from "./api";
import Dashboard from "./pages/Dashboard";
import Tests from "./pages/Tests";
import Results from "./pages/Results";
import Compare from "./pages/Compare";
import Models from "./pages/Models";
import Trends from "./pages/Trends";

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: Cpu },
  { to: "/tests", label: "Tests", icon: FlaskConical },
  { to: "/models", label: "Models", icon: Boxes },
  { to: "/results", label: "Results", icon: Activity },
  { to: "/compare", label: "Compare", icon: GitCompare },
  { to: "/trends", label: "Trends", icon: TrendingUp },
];

export default function App() {
  const [hardware, setHardware] = useState<Hardware | null>(null);
  const [benchmarks, setBenchmarks] = useState<Benchmark[]>([]);
  const [runs, setRuns] = useState<RunResult[]>([]);
  const [version, setVersion] = useState("");

  const refreshRuns = useCallback(async () => {
    setRuns(await api.runs());
  }, []);

  useEffect(() => {
    api.hardware().then(setHardware).catch(() => undefined);
    api.benchmarks().then(setBenchmarks).catch(() => undefined);
    api.health().then((h) => setVersion(h.version)).catch(() => undefined);
    refreshRuns();
  }, [refreshRuns]);

  // Live progress: patch the matching run in place; on terminal status refetch.
  const onEvent = useCallback(
    (e: ProgressEvent) => {
      setRuns((prev) => {
        const idx = prev.findIndex((r) => r.id === e.run_id);
        if (idx === -1) {
          refreshRuns();
          return prev;
        }
        const next = [...prev];
        const r = { ...next[idx] };
        if (e.percent != null) r.progress = e.percent;
        if (e.phase) r.phase = e.phase;
        if (e.status) r.status = e.status;
        if (e.message) r.logs = [...r.logs, e.message].slice(-500);
        next[idx] = r;
        return next;
      });
      if (e.status && ["completed", "failed", "cancelled"].includes(e.status)) {
        setTimeout(refreshRuns, 300);
      }
    },
    [refreshRuns]
  );
  const connected = useProgressSocket(onEvent);

  const activeRun = useMemo(
    () => runs.find((r) => r.status === "running" || r.status === "queued"),
    [runs]
  );

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-60 flex-col border-r border-white/10 bg-slate-950/60 p-4">
        <div className="mb-8 flex items-center gap-2 px-2">
          <img
            src="/logo.png"
            alt="AI-Bench"
            className="h-9 w-9 rounded-xl object-cover ring-1 ring-white/10"
          />
          <div>
            <div className="font-semibold leading-tight text-white">AI-Bench</div>
            <div className="text-[11px] text-slate-500">Local ML/LLM profiler</div>
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-1">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition ${
                  isActive
                    ? "bg-brand-600/20 text-brand-200"
                    : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
                }`
              }
            >
              <Icon size={18} />
              {label}
              {label === "Tests" && activeRun && (
                <span className="ml-auto h-2 w-2 animate-pulse rounded-full bg-brand-400" />
              )}
            </NavLink>
          ))}
        </nav>
        <div className="mt-4 flex items-center justify-between border-t border-white/10 px-2 pt-3 text-xs text-slate-500">
          <span>v{version || "…"}</span>
          <span className="flex items-center gap-1" title={connected ? "Live" : "Reconnecting"}>
            {connected ? (
              <Wifi size={14} className="text-emerald-400" />
            ) : (
              <WifiOff size={14} className="text-rose-400" />
            )}
            {connected ? "live" : "offline"}
          </span>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl px-8 py-8">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route
              path="/dashboard"
              element={<Dashboard hardware={hardware} setHardware={setHardware} runs={runs} />}
            />
            <Route
              path="/tests"
              element={
                <Tests
                  benchmarks={benchmarks}
                  runs={runs}
                  onRunsChanged={refreshRuns}
                />
              }
            />
            <Route path="/models" element={<Models />} />
            <Route path="/results" element={<Results runs={runs} onRunsChanged={refreshRuns} />} />
            <Route path="/compare" element={<Compare runs={runs} />} />
            <Route path="/trends" element={<Trends runs={runs} />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
