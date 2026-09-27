import type { ParamSpec } from "../api";

export default function ParamControl({
  spec,
  value,
  onChange,
}: {
  spec: ParamSpec;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const label = (
    <div className="mb-1 flex items-center justify-between">
      <label className="label">
        {spec.label}
        {spec.unit ? ` (${spec.unit})` : ""}
      </label>
      {spec.type === "int" || spec.type === "float" ? (
        <span className="text-xs font-semibold text-brand-300">{String(value)}</span>
      ) : null}
    </div>
  );

  if (spec.type === "bool") {
    return (
      <div className="flex items-center justify-between rounded-lg border border-white/10 bg-slate-900/40 px-3 py-2">
        <div>
          <span className="text-sm text-slate-200">{spec.label}</span>
          {spec.help && <p className="text-xs text-slate-500">{spec.help}</p>}
        </div>
        <button
          role="switch"
          aria-checked={Boolean(value)}
          onClick={() => onChange(!value)}
          className={`relative h-6 w-11 rounded-full transition ${value ? "bg-brand-500" : "bg-white/15"}`}
        >
          <span
            className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all ${
              value ? "left-[22px]" : "left-0.5"
            }`}
          />
        </button>
      </div>
    );
  }

  if (spec.type === "select") {
    return (
      <div>
        {label}
        <select className="input" value={String(value)} onChange={(e) => onChange(e.target.value)}>
          {spec.options?.map((o) => (
            <option key={String(o.value)} value={String(o.value)}>
              {o.label}
            </option>
          ))}
        </select>
        {spec.help && <p className="mt-1 text-xs text-slate-500">{spec.help}</p>}
      </div>
    );
  }

  if (spec.type === "string") {
    return (
      <div>
        {label}
        <input
          className="input"
          value={String(value ?? "")}
          placeholder={spec.help}
          onChange={(e) => onChange(e.target.value)}
        />
        {spec.help && <p className="mt-1 text-xs text-slate-500">{spec.help}</p>}
      </div>
    );
  }

  // int / float: slider + number input combo for granular control.
  const num = Number(value ?? 0);
  return (
    <div>
      {label}
      <div className="flex items-center gap-3">
        <input
          type="range"
          className="flex-1 accent-brand-500"
          min={spec.min ?? 0}
          max={spec.max ?? 100}
          step={spec.step ?? 1}
          value={num}
          onChange={(e) => onChange(Number(e.target.value))}
        />
        <input
          type="number"
          className="input w-24"
          min={spec.min}
          max={spec.max}
          step={spec.step ?? 1}
          value={num}
          onChange={(e) => onChange(Number(e.target.value))}
        />
      </div>
      {spec.help && <p className="mt-1 text-xs text-slate-500">{spec.help}</p>}
    </div>
  );
}
