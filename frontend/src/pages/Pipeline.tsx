import { Link } from "react-router-dom";
import { api, fmtDate } from "../api";
import { ErrorNote, STATUS_LABEL, usePoll } from "../components/ui";

const COLUMNS = [
  "queued", "researching", "scripting", "fact_checking", "narrating", "generating_visuals", "animating", "editing",
  "rendering", "quality_check", "awaiting_approval", "approved", "uploading", "scheduled", "published",
];
const PROBLEMS = ["needs_review", "paused_budget", "failed"];

export default function Pipeline() {
  const { data, error } = usePoll(() => api("/api/pipeline"), 4000);
  const cols = data?.columns || {};
  const Col = ({ s }: { s: string }) => (
    <div className="w-56 shrink-0">
      <div className="mb-2 flex items-center justify-between text-xs uppercase tracking-wide text-stone-400">
        <span>{STATUS_LABEL[s]}</span><span className="rounded bg-stone-800 px-1.5">{cols[s]?.length || 0}</span>
      </div>
      <div className="space-y-2">
        {(cols[s] || []).map((v: any) => (
          <Link key={v.id} to={`/videos/${v.id}`} className="card block !p-3 text-sm hover:border-gold/60">
            <div className="line-clamp-2">{v.title}</div>
            <div className="mt-1 text-xs text-stone-500">${v.spend.toFixed(2)}{v.estimate ? ` / est $${v.estimate.toFixed(2)}` : ""}</div>
            {v.error && <div className="mt-1 line-clamp-2 text-xs text-red-400">{v.error}</div>}
          </Link>
        ))}
      </div>
    </div>
  );
  return (
    <div>
      <h1 className="page">Production Pipeline</h1>
      <ErrorNote error={error} />
      <div className="flex gap-4 overflow-x-auto pb-4">{COLUMNS.map((s) => <Col key={s} s={s} />)}</div>
      <h2 className="mt-6 mb-3 font-display text-lg text-parchment">Needs attention</h2>
      <div className="flex gap-4 overflow-x-auto pb-4">{PROBLEMS.map((s) => <Col key={s} s={s} />)}</div>
      <h2 className="mt-6 mb-3 font-display text-lg text-parchment">Job queue</h2>
      <div className="card overflow-x-auto !p-0">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-stone-500">
            <tr><th className="p-3">#</th><th>Job</th><th>Video</th><th>Status</th><th>Attempts</th><th>Created</th><th>Error</th></tr>
          </thead>
          <tbody>
            {(data?.jobs || []).map((j: any) => (
              <tr key={j.id} className="border-t border-stone-800">
                <td className="p-3">{j.id}</td><td>{j.kind}</td>
                <td>{j.video_id ? <Link className="text-sky-400" to={`/videos/${j.video_id}`}>#{j.video_id}</Link> : "—"}</td>
                <td>{j.status}</td><td>{j.attempts}</td><td>{fmtDate(j.created_at)}</td>
                <td className="max-w-md truncate text-xs text-red-400" title={j.error}>{j.error}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
