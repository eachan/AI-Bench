import { useCallback, useEffect, useRef, useState } from "react";
import { Download, HardDriveDownload, Plus, Trash2 } from "lucide-react";
import { api, CatalogModel, DownloadState, LocalModel } from "../api";
import { Card, Empty, ProgressBar, SectionTitle } from "../components/ui";

export default function Models() {
  const [local, setLocal] = useState<LocalModel[]>([]);
  const [downloads, setDownloads] = useState<DownloadState[]>([]);
  const [catalog, setCatalog] = useState<CatalogModel[]>([]);
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval>>();

  const refresh = useCallback(async () => {
    const r = await api.models();
    setLocal(r.local);
    setDownloads(r.downloads);
  }, []);

  useEffect(() => {
    refresh();
    api.modelsCatalog().then((r) => setCatalog(r.models)).catch(() => undefined);
  }, [refresh]);

  // Poll while any download is active so progress bars update live.
  const active = downloads.some((d) => d.status === "downloading" || d.status === "pending");
  useEffect(() => {
    clearInterval(timer.current);
    if (active) timer.current = setInterval(refresh, 1000);
    return () => clearInterval(timer.current);
  }, [active, refresh]);

  const download = async (body: { url: string; filename?: string }) => {
    setError(null);
    try {
      await api.startDownload(body);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const localModelNames = new Set(local.map((m) => m.name));

  const remove = async (path: string) => {
    await api.deleteModel(path);
    refresh();
  };

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Models"
        subtitle="Download and manage the GGUF models used by the llama.cpp benchmark"
      />

      {error && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">
          {error}
        </div>
      )}

      <Card>
        <div className="mb-3 flex items-center gap-2 text-slate-200">
          <HardDriveDownload size={18} className="text-brand-400" />
          <span className="font-medium">Suggested models</span>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {catalog.map((m) => {
            const have = localModelNames.has(m.filename);
            const inflight = downloads.find((d) => d.name === m.filename && d.status !== "completed");
            return (
              <div key={m.id} className="rounded-xl border border-white/10 bg-slate-900/40 p-4">
                <div className="font-medium text-white">{m.name}</div>
                <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-400">
                  <span className="badge bg-white/5">{m.quant}</span>
                  <span className="badge bg-white/5">~{m.size_mb} MB</span>
                </div>
                <button
                  className="btn-primary mt-3 w-full justify-center"
                  disabled={have || !!inflight}
                  onClick={() => download({ url: m.url, filename: m.filename })}
                >
                  <Download size={15} />
                  {have ? "Downloaded" : inflight ? "Downloading…" : "Download"}
                </button>
              </div>
            );
          })}
        </div>

        <div className="mt-5 border-t border-white/10 pt-4">
          <label className="label">Or download from a direct URL</label>
          <div className="mt-1 flex gap-2">
            <input
              className="input"
              placeholder="https://huggingface.co/…/model.gguf"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
            <button
              className="btn-ghost shrink-0"
              disabled={!url.trim()}
              onClick={() => {
                download({ url: url.trim() });
                setUrl("");
              }}
            >
              <Plus size={16} />
              Add
            </button>
          </div>
        </div>
      </Card>

      {downloads.length > 0 && (
        <Card>
          <SectionTitle title="Downloads" />
          <div className="space-y-3">
            {downloads.map((d) => (
              <div key={d.id}>
                <div className="mb-1 flex items-center justify-between text-sm">
                  <span className="text-slate-200">{d.name}</span>
                  <span className="text-xs text-slate-400">
                    {d.status === "downloading"
                      ? `${d.downloaded_mb} / ${d.total_mb || "?"} MB (${d.percent}%)`
                      : d.status}
                  </span>
                </div>
                <ProgressBar value={d.percent} />
                {d.error && <p className="mt-1 text-xs text-rose-300">{d.error}</p>}
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card>
        <SectionTitle title="Installed models" />
        {local.length === 0 ? (
          <Empty>No models yet. Download one above to use it in the llama.cpp benchmark.</Empty>
        ) : (
          <div className="divide-y divide-white/5">
            {local.map((m) => (
              <div key={m.path} className="flex items-center justify-between py-2.5">
                <div>
                  <div className="text-sm font-medium text-slate-100">{m.name}</div>
                  <div className="text-xs text-slate-500">
                    {m.kind} · {m.size_mb} MB
                  </div>
                </div>
                <button className="btn-ghost !px-2" onClick={() => remove(m.path)} title="Delete">
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
