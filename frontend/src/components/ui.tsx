import { ReactNode } from "react";
import type { RunResult } from "../api";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`card ${className}`}>{children}</div>;
}

export function SectionTitle({ title, subtitle, right }: { title: string; subtitle?: string; right?: ReactNode }) {
  return (
    <div className="mb-4 flex items-end justify-between gap-4">
      <div>
        <h2 className="text-lg font-semibold text-white">{title}</h2>
        {subtitle && <p className="mt-0.5 text-sm text-slate-400">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

export function Stat({ label, value, unit }: { label: string; value: ReactNode; unit?: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-slate-900/40 p-4">
      <div className="label">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-white">
        {value}
        {unit && <span className="ml-1 text-sm font-normal text-slate-400">{unit}</span>}
      </div>
    </div>
  );
}

const STATUS_STYLES: Record<RunResult["status"], string> = {
  queued: "bg-slate-500/20 text-slate-300",
  downloading: "bg-amber-500/20 text-amber-300",
  running: "bg-brand-500/20 text-brand-300",
  completed: "bg-emerald-500/20 text-emerald-300",
  failed: "bg-rose-500/20 text-rose-300",
  cancelled: "bg-slate-500/20 text-slate-400",
};

export function StatusBadge({ status }: { status: RunResult["status"] }) {
  return (
    <span className={`badge ${STATUS_STYLES[status]}`}>
      {status === "running" && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
      )}
      {status}
    </span>
  );
}

export function ProgressBar({ value }: { value: number }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
      <div
        className="h-full rounded-full bg-brand-500 transition-all duration-300"
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-white/10 p-8 text-center text-sm text-slate-400">
      {children}
    </div>
  );
}
