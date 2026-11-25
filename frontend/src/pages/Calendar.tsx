import { Link } from "react-router-dom";
import { api, fileUrl, fmtDate, getToken } from "../api";
import { ErrorNote, StatusBadge, usePoll } from "../components/ui";

export default function Calendar() {
  const { data, error } = usePoll(() => api("/api/calendar"), 20000);
  const items: any[] = data?.items || [];
  const byDay = new Map<string, any[]>();
  for (const v of items) {
    const k = new Date(v.scheduled_at).toDateString();
    byDay.set(k, [...(byDay.get(k) || []), v]);
  }
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7)); // Monday
  const days = Array.from({ length: 28 }, (_, i) => new Date(start.getTime() + i * 86400000));
  const slotDays = new Set((data?.slots || []).map((s: string) => new Date(s).toDateString()));
  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="page !mb-0">Content Calendar</h1>
        <a className="btn-ghost" href={`/api/publishing/export?days=7${getToken() ? `&token=${encodeURIComponent(getToken())}` : ""}`}>
          Download next 7 days (for YouTube Studio scheduling)
        </a>
      </div>
      <ErrorNote error={error} />
      <div className="grid grid-cols-7 gap-2">
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => <div key={d} className="text-center text-xs uppercase text-stone-500">{d}</div>)}
        {days.map((d) => {
          const k = d.toDateString();
          const today = k === new Date().toDateString();
          return (
            <div key={k} className={`min-h-28 rounded-lg border p-2 ${today ? "border-gold/70" : "border-stone-800"} ${slotDays.has(k) ? "bg-stone-900" : "bg-stone-950"}`}>
              <div className="mb-1 flex justify-between text-xs text-stone-500">
                <span>{d.getDate()}</span>{slotDays.has(k) && <span className="text-gold/80">slot</span>}
              </div>
              {(byDay.get(k) || []).map((v) => (
                <Link key={v.id} to={`/videos/${v.parent_id || v.id}`} className="mb-1 block rounded bg-stone-800 p-1 text-xs hover:bg-stone-700">
                  {v.thumbnail && <img src={fileUrl(v.thumbnail)} className="mb-1 rounded" />}
                  <div className="line-clamp-2">{v.kind === "short" ? "▮ " : ""}{v.title}</div>
                </Link>
              ))}
            </div>
          );
        })}
      </div>
      <h2 className="mt-8 mb-3 font-display text-lg text-parchment">Upcoming publications</h2>
      <div className="card !p-0">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-stone-500"><tr><th className="p-3">When</th><th>Title</th><th>Type</th><th>Status</th><th>YouTube</th></tr></thead>
          <tbody>
            {items.map((v) => (
              <tr key={v.id} className="border-t border-stone-800">
                <td className="p-3">{fmtDate(v.scheduled_at)}</td>
                <td><Link className="hover:text-gold" to={`/videos/${v.parent_id || v.id}`}>{v.title}</Link></td>
                <td>{v.kind}</td><td><StatusBadge status={v.status} /></td>
                <td>{v.youtube_url ? <a className="text-sky-400" href={v.youtube_url} target="_blank">open</a> : v.upload_status || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
