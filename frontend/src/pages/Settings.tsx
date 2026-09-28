import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Download, RefreshCw, RotateCw } from "lucide-react";
import { api, UpdateCheck, UpdateStatus } from "../api";
import { Card, Empty, ProgressBar, SectionTitle } from "../components/ui";

export default function Settings() {
  const [check, setCheck] = useState<UpdateCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const timer = useRef<ReturnType<typeof setInterval>>();

  const runCheck = async () => {
    setChecking(true);
    try {
      setCheck(await api.checkUpdate());
    } catch {
      /* surfaced via check.status on next try */
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    runCheck();
    return () => clearInterval(timer.current);
  }, []);

  const applying = status
    ? ["downloading", "installing"].includes(status.status)
    : false;

  const apply = async () => {
    const s = await api.applyUpdate();
    setStatus(s);
    clearInterval(timer.current);
    timer.current = setInterval(async () => {
      try {
        const st = await api.updateStatus();
        setStatus(st);
        if (!["downloading", "installing"].includes(st.status)) clearInterval(timer.current);
      } catch {
        clearInterval(timer.current);
      }
    }, 800);
  };

  return (
    <div className="space-y-6">
      <SectionTitle title="Settings" subtitle="Software updates and bundled components" />

      <Card>
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-slate-200">
              <RotateCw size={18} className="text-brand-400" />
              <span className="font-medium">Software updates</span>
            </div>
            <p className="mt-1 text-sm text-slate-400">
              Current version{" "}
              <span className="font-semibold text-slate-100">
                v{check?.current_version ?? "…"}
              </span>
              . Updates come from GitHub Releases and bundle the app plus all
              dependencies and benchmark engines together.
            </p>
          </div>
          <button className="btn-ghost" onClick={runCheck} disabled={checking || applying}>
            <RefreshCw size={16} className={checking ? "animate-spin" : ""} />
            Check for updates
          </button>
        </div>

        <div className="mt-4">
          {!check ? (
            <Empty>Checking for updates…</Empty>
          ) : check.update_available && check.release ? (
            <div className="rounded-xl border border-brand-500/40 bg-brand-600/10 p-4">
              <div className="flex items-center justify-between">
                <div className="font-medium text-brand-100">
                  Update available: v{check.latest_version}
                </div>
                {check.release.url && (
                  <a
                    className="text-xs text-brand-300 underline"
                    href={check.release.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Release notes
                  </a>
                )}
              </div>
              {check.release.notes && (
                <pre className="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap rounded-lg bg-black/30 p-3 text-xs text-slate-300">
                  {check.release.notes}
                </pre>
              )}

              {!applying && status?.status !== "unsupported" && status?.status !== "installing" && (
                <button className="btn-primary mt-3" onClick={apply}>
                  <Download size={16} />
                  {check.packaged ? "Update & restart" : "Download update"}
                </button>
              )}

              {status && ["downloading", "installing"].includes(status.status) && (
                <div className="mt-3">
                  <div className="mb-1 flex justify-between text-xs text-slate-400">
                    <span>{status.status === "downloading" ? "Downloading…" : "Installing…"}</span>
                    <span>{status.percent.toFixed(0)}%</span>
                  </div>
                  <ProgressBar value={status.percent} />
                </div>
              )}
              {status && ["unsupported", "error", "done"].includes(status.status) && (
                <p className="mt-3 text-sm text-slate-300">{status.message}</p>
              )}
              {!check.packaged && (
                <p className="mt-2 text-xs text-slate-500">
                  Automatic in-place install &amp; restart runs in the installed Windows app; in dev,
                  update via git.
                </p>
              )}
            </div>
          ) : check.status === "no_releases" ? (
            <div className="rounded-xl border border-white/10 bg-slate-900/40 p-4 text-sm text-slate-300">
              No releases have been published yet. Once a release is tagged on GitHub, updates will
              appear here.
            </div>
          ) : check.status === "error" ? (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-200">
              Couldn’t check for updates: {check.message}
            </div>
          ) : (
            <div className="flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm text-emerald-200">
              <CheckCircle2 size={16} />
              You’re on the latest version.
            </div>
          )}
        </div>
      </Card>

      <Card>
        <SectionTitle title="Bundled components" subtitle="Updated together with the app" />
        <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
          {(check?.components ?? []).map((c) => (
            <div key={c.name} className="flex justify-between gap-2 border-b border-white/5 py-1">
              <span className="text-slate-400">{c.name}</span>
              <span className="font-medium text-slate-200">{c.version}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
