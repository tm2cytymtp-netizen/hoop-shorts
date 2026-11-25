import { Link } from "react-router-dom";
import { api, fmtDur, post, usd } from "../api";
import { Bars, ErrorNote, LineChart, usePoll, useAction } from "../components/ui";

const n = (x: any) => Number(x || 0);

export default function Analytics() {
  const { data, error } = usePoll(() => api("/api/analytics"), 60000);
  const costs = usePoll(() => api("/api/costs"), 60000).data;
  const act = useAction();
  const vids: any[] = data?.videos || [];
  const long = vids.filter((v) => v.kind === "long");
  const shorts = vids.filter((v) => v.kind === "short");
  const byCat = Object.entries(
    long.reduce((acc: any, v) => {
      const c = v.category || "Uncategorised";
      acc[c] = acc[c] || { views: 0, score: 0, n: 0 };
      acc[c].views += n(v.metrics.views);
      acc[c].score += v.score;
      acc[c].n += 1;
      return acc;
    }, {}),
  ).map(([k, x]: any) => ({ k, views: x.views, score: x.score / x.n }));

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="page !mb-0">Analytics</h1>
        <button className="btn-ghost" onClick={() => act.run(() => post("/api/analytics/sync"), "Sync queued.")}>Sync now</button>
      </div>
      <ErrorNote error={error} />
      {act.msg && <div className="mb-4 text-sm text-amber-300">{act.msg}</div>}
      {!vids.length && <div className="card mb-6 text-sm text-stone-400">No analytics yet. Data appears after your first video is published and the daily sync runs (YouTube Analytics typically lags 1–3 days).</div>}

      {data?.insights && (
        <div className="card mb-6">
          <div className="label">What's working (learned from CTR, retention, watch time and subscriber conversion — not views alone)</div>
          <ul className="list-disc space-y-1 pl-5 text-sm">{data.insights.findings.map((f: string) => <li key={f}>{f}</li>)}</ul>
          <div className="label mt-4">Recommendations fed into topic discovery</div>
          <ul className="list-disc space-y-1 pl-5 text-sm text-parchment">{data.insights.recommendations.map((f: string) => <li key={f}>{f}</li>)}</ul>
          <div className="mt-3 text-sm text-stone-400"><b>Hooks:</b> {data.insights.hook_advice}</div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card"><div className="label">Channel views over time (snapshots)</div><LineChart points={(data?.trend || []).map((t: any) => ({ x: t.day, y: t.views }))} /></div>
        <div className="card"><div className="label">Performance score by category</div>
          <Bars data={byCat.sort((a, b) => b.score - a.score)} label={(d) => d.k} value={(d) => d.score} fmt={(x) => x.toFixed(2)} /></div>
        <div className="card"><div className="label">Average view % by video</div>
          <Bars data={long.slice(0, 15)} label={(d) => d.title} value={(d) => n(d.metrics.averageViewPercentage)} fmt={(x) => `${x.toFixed(0)}%`} /></div>
        <div className="card"><div className="label">Thumbnail CTR by video</div>
          <Bars data={long.filter((v) => v.metrics.videoThumbnailImpressionsClickRate != null).slice(0, 15)} label={(d) => d.title}
            value={(d) => n(d.metrics.videoThumbnailImpressionsClickRate)} fmt={(x) => `${x.toFixed(1)}%`} /></div>
      </div>

      <h2 className="mt-8 mb-3 font-display text-lg text-parchment">Videos</h2>
      <div className="card overflow-x-auto !p-0">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-stone-500">
            <tr><th className="p-3">Video</th><th>Length</th><th>Views</th><th>Watch hrs</th><th>Avg view</th><th>CTR</th><th>Subs</th><th>Score</th><th>Biggest drop-off</th></tr>
          </thead>
          <tbody>
            {[...long, ...shorts].map((v) => (
              <tr key={v.id} className="border-t border-stone-800">
                <td className="max-w-xs truncate p-3"><Link to={`/videos/${v.parent_id || v.id}`} className="hover:text-gold">{v.kind === "short" ? "▮ " : ""}{v.title}</Link></td>
                <td>{fmtDur(v.duration_s)}</td><td>{n(v.metrics.views).toLocaleString()}</td>
                <td>{(n(v.metrics.estimatedMinutesWatched) / 60).toFixed(1)}</td><td>{n(v.metrics.averageViewPercentage).toFixed(0)}%</td>
                <td>{v.metrics.videoThumbnailImpressionsClickRate != null ? `${n(v.metrics.videoThumbnailImpressionsClickRate).toFixed(1)}%` : "—"}</td>
                <td>{n(v.metrics.subscribersGained) - n(v.metrics.subscribersLost)}</td><td>{v.score}</td>
                <td className="text-xs text-stone-400">{v.drop_offs?.[0] ? `${Math.round(v.drop_offs[0].at * 100)}% in (−${Math.round(v.drop_offs[0].drop * 100)}%)` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {costs && (
        <>
          <h2 className="mt-8 mb-3 font-display text-lg text-parchment">AI & API spend this month — {usd(costs.month_total)} of {usd(costs.budget.max_monthly_usd)}</h2>
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="card"><div className="label">By category</div>
              <Bars data={Object.entries(costs.by_category).map(([k, u]) => ({ k, u }))} label={(d) => d.k} value={(d) => d.u as number} fmt={(x) => usd(x)} /></div>
            <div className="card"><div className="label">By provider</div>
              <Bars data={costs.by_provider} label={(d) => `${d.provider} (${d.calls})`} value={(d) => d.usd} fmt={(x) => usd(x)} /></div>
          </div>
        </>
      )}
    </div>
  );
}
