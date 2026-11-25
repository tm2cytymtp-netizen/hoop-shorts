import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { fileUrl, fmtDur, VideoSummary } from "../api";

export const STATUS_LABEL: Record<string, string> = {
  queued: "Queued", researching: "Researching", scripting: "Writing script", fact_checking: "Fact-checking",
  narrating: "Generating narration", generating_visuals: "Creating visuals", animating: "Animating scenes",
  editing: "Editing video", rendering: "Rendering", quality_check: "Quality checking",
  awaiting_approval: "Awaiting approval", approved: "Approved", uploading: "Uploading", scheduled: "Scheduled",
  published: "Published", failed: "Failed", paused_budget: "Paused (budget)", needs_review: "Needs review",
  rejected: "Rejected",
};

const TONE: Record<string, string> = {
  failed: "bg-red-950 text-red-300 border-red-900", paused_budget: "bg-amber-950 text-amber-300 border-amber-900",
  needs_review: "bg-orange-950 text-orange-300 border-orange-900",
  awaiting_approval: "bg-sky-950 text-sky-300 border-sky-900", approved: "bg-emerald-950 text-emerald-300 border-emerald-900",
  scheduled: "bg-violet-950 text-violet-300 border-violet-900", published: "bg-emerald-900 text-emerald-100 border-emerald-700",
  rejected: "bg-stone-800 text-stone-400 border-stone-700",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-block rounded-full border px-2 py-0.5 text-xs ${TONE[status] || "bg-stone-800 text-stone-300 border-stone-700"}`}>
      {STATUS_LABEL[status] || status}
    </span>
  );
}

export function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="card">
      <div className="text-xs uppercase tracking-wide text-stone-400">{label}</div>
      <div className="mt-1 font-display text-2xl text-parchment">{value}</div>
      {hint && <div className="mt-1 text-xs text-stone-500">{hint}</div>}
    </div>
  );
}

export function VideoCard({ v }: { v: VideoSummary }) {
  return (
    <Link to={`/videos/${v.id}`} className="card block hover:border-gold/60">
      <div className="mb-2 aspect-video overflow-hidden rounded-lg bg-stone-800">
        {v.thumbnail && <img src={fileUrl(v.thumbnail)} className="h-full w-full object-cover" />}
      </div>
      <div className="line-clamp-2 text-sm font-medium">{v.title}</div>
      <div className="mt-2 flex items-center justify-between text-xs text-stone-400">
        <StatusBadge status={v.status} />
        <span>{v.duration_s ? fmtDur(v.duration_s) : ""} · ${v.spend.toFixed(2)}</span>
      </div>
    </Link>
  );
}

export function usePoll<T>(fn: () => Promise<T>, ms = 5000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string>("");
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const reload = useCallback(async () => {
    try {
      setData(await fnRef.current());
      setError("");
    } catch (e: any) {
      setError(e.message);
    }
  }, []);
  useEffect(() => {
    reload();
    const t = setInterval(reload, ms);
    return () => clearInterval(t);
  }, [reload, ms]);
  return { data, error, reload };
}

export function ErrorNote({ error }: { error?: string }) {
  if (!error) return null;
  return <div className="mb-4 rounded-lg border border-red-900 bg-red-950/50 p-3 text-sm text-red-300">{error}</div>;
}

export function useAction() {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const run = async (f: () => Promise<any>, ok?: string) => {
    setBusy(true);
    setMsg("");
    try {
      const r = await f();
      if (ok) setMsg(ok);
      return r;
    } catch (e: any) {
      setMsg("Error: " + e.message);
    } finally {
      setBusy(false);
    }
  };
  return { busy, msg, run, setMsg };
}

export function Bars({ data, label, value, fmt = (n: number) => n.toLocaleString() }: {
  data: any[]; label: (d: any) => string; value: (d: any) => number; fmt?: (n: number) => string;
}) {
  const max = Math.max(1, ...data.map(value));
  return (
    <div className="space-y-1.5">
      {data.map((d, i) => (
        <div key={i} className="grid grid-cols-[minmax(0,14rem)_1fr_4.5rem] items-center gap-2 text-xs">
          <div className="truncate text-stone-300" title={label(d)}>{label(d)}</div>
          <div className="h-3 rounded bg-stone-800">
            <div className="h-3 rounded bg-gold/80" style={{ width: `${(value(d) / max) * 100}%` }} />
          </div>
          <div className="text-right tabular-nums text-stone-400">{fmt(value(d))}</div>
        </div>
      ))}
    </div>
  );
}

export function LineChart({ points, height = 140 }: { points: { x: string; y: number }[]; height?: number }) {
  if (points.length < 2) return <div className="text-sm text-stone-500">Not enough data yet.</div>;
  const w = 600, max = Math.max(...points.map((p) => p.y), 1);
  const xy = points.map((p, i) => [(i / (points.length - 1)) * w, height - (p.y / max) * (height - 10)]);
  return (
    <svg viewBox={`0 0 ${w} ${height}`} className="w-full">
      <polyline fill="none" stroke="#d6b26a" strokeWidth="2.5" points={xy.map((p) => p.join(",")).join(" ")} />
      {xy.map(([x, y], i) => <circle key={i} cx={x} cy={y} r="3" fill="#d6b26a"><title>{`${points[i].x}: ${points[i].y.toLocaleString()}`}</title></circle>)}
    </svg>
  );
}
