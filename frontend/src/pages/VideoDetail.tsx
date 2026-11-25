import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, fileUrl, fmtDate, fmtDur, patch, post, usd } from "../api";
import { ErrorNote, StatusBadge, usePoll, useAction } from "../components/ui";

const TABS = ["Overview", "Script & fact-check", "Sources", "Scenes & assets", "Thumbnails", "Metadata", "Shorts", "Log"];

export default function VideoDetail() {
  const { id } = useParams();
  const { data: v, error, reload } = usePoll(() => api(`/api/videos/${id}`), 5000);
  const [tab, setTab] = useState(TABS[0]);
  const act = useAction();
  const [when, setWhen] = useState("");
  if (!v) return <ErrorNote error={error} />;
  const doAct = (p: Promise<any>, ok: string) => act.run(() => p, ok).then(reload);

  return (
    <div>
      <div className="mb-2 text-sm text-stone-500"><Link to="/library">Library</Link> / #{v.id}</div>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="page !mb-2">{v.title}</h1>
          <div className="flex items-center gap-3 text-sm text-stone-400">
            <StatusBadge status={v.status} />
            {v.duration_s > 0 && <span>{fmtDur(v.duration_s)}</span>}
            <span>spent {usd(v.costs?.total)} {v.cost_estimate?.total ? `(est. ${usd(v.cost_estimate.total)})` : ""}</span>
            {v.scheduled_at && <span>publishes {fmtDate(v.scheduled_at)}</span>}
            {v.youtube_url && <a className="text-sky-400" href={v.youtube_url} target="_blank">YouTube ↗</a>}
            {v.upload_status && <span className="text-xs">({v.upload_status.replaceAll("_", " ")})</span>}
          </div>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          {v.status === "awaiting_approval" && (
            <>
              <div>
                <label className="label">Publish at (blank = next slot)</label>
                <input type="datetime-local" className="input" value={when} onChange={(e) => setWhen(e.target.value)} />
              </div>
              <button className="btn-primary" disabled={act.busy}
                onClick={() => doAct(post(`/api/videos/${v.id}/approve`, { scheduled_at: when ? new Date(when).toISOString() : null }), "Approved — upload queued.")}>
                Approve & schedule
              </button>
              <button className="btn-danger" onClick={() => doAct(post(`/api/videos/${v.id}/reject`), "Rejected.")}>Reject</button>
            </>
          )}
          {(["failed", "paused_budget", "needs_review"].includes(v.status) || (v.status === "approved" && v.upload_status?.startsWith("failed"))) && (
            <button className="btn-ghost" onClick={() => doAct(post(`/api/videos/${v.id}/retry`), "Retry queued (finished assets are reused).")}>Retry</button>
          )}
        </div>
      </div>
      {act.msg && <div className="mb-4 text-sm text-amber-300">{act.msg}</div>}
      {v.error && <ErrorNote error={v.error} />}
      <div className="mb-6 flex flex-wrap gap-1 border-b border-stone-800">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`px-3 py-2 text-sm ${tab === t ? "border-b-2 border-gold text-parchment" : "text-stone-400 hover:text-stone-200"}`}>{t}</button>
        ))}
      </div>
      {tab === "Overview" && <Overview v={v} />}
      {tab === "Script & fact-check" && <ScriptTab v={v} />}
      {tab === "Sources" && <Sources v={v} />}
      {tab === "Scenes & assets" && <Scenes v={v} />}
      {tab === "Thumbnails" && <Thumbs v={v} reload={reload} />}
      {tab === "Metadata" && <Meta v={v} reload={reload} />}
      {tab === "Shorts" && <Shorts v={v} reload={reload} />}
      {tab === "Log" && <Log v={v} />}
    </div>
  );
}

function Overview({ v }: any) {
  const qc = v.qc_report || {};
  return (
    <div className={`grid gap-6 ${v.kind === "short" ? "xl:grid-cols-[1fr_1fr]" : "xl:grid-cols-[2fr_1fr]"}`}>
      <div>
        {v.video_url ? (
          <video controls className={`rounded-xl border border-stone-800 ${v.kind === "short" ? "mx-auto max-h-[78vh] aspect-[9/16]" : "w-full"}`} src={fileUrl(v.video_url)}>
            {v.subtitles_url && <track kind="captions" src={fileUrl(v.subtitles_url)} default />}
          </video>
        ) : (
          <div className="card flex aspect-video items-center justify-center text-stone-500">Video not rendered yet — current stage: {v.status}</div>
        )}
        {qc.checks && (
          <div className="card mt-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="label !mb-0">Quality control</span>
              <span className={qc.passed ? "text-emerald-400" : "text-red-400"}>{qc.passed ? "All blocking checks passed" : "Failed"}</span>
            </div>
            <table className="w-full text-sm">
              <tbody>
                {qc.checks.map((c: any) => (
                  <tr key={c.check} className="border-t border-stone-800">
                    <td className="py-1.5 pr-2">{c.passed ? "✅" : c.blocking ? "❌" : "⚠️"}</td>
                    <td className="pr-3 font-medium">{c.check.replaceAll("_", " ")}</td>
                    <td className="text-xs text-stone-400">{c.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <div className="space-y-4">
        <div className="card">
          <div className="label">Cost</div>
          <table className="w-full text-sm">
            <thead className="text-xs text-stone-500"><tr><th className="text-left">Category</th><th className="text-right">Estimate</th><th className="text-right">Actual</th></tr></thead>
            <tbody>
              {["research", "script", "image", "video", "voice"].map((k) => (
                <tr key={k}><td>{k}</td><td className="text-right text-stone-400">{usd(v.cost_estimate?.[k])}</td><td className="text-right">{usd(v.costs?.[k] ?? 0)}</td></tr>
              ))}
              <tr className="border-t border-stone-700 font-medium"><td>total</td><td className="text-right">{usd(v.cost_estimate?.total)}</td><td className="text-right">{usd(v.costs?.total)}</td></tr>
            </tbody>
          </table>
        </div>
        {v.topic && (
          <div className="card text-sm">
            <div className="label">Topic</div>
            <div>{v.topic.title}</div>
            <div className="mt-1 text-stone-400">{v.topic.period} · {v.topic.category}</div>
            <div className="mt-2 text-stone-400">{v.topic.why_watch}</div>
          </div>
        )}
        {v.fact_check?.claims != null && (
          <div className="card text-sm">
            <div className="label">Fact-check</div>
            <div>{v.fact_check.supported}/{v.fact_check.claims} claims supported{v.fact_check.claims ? ` (${Math.round(v.fact_check.ratio * 100)}%)` : ""}</div>
            <div className={v.fact_check.passed ? "text-emerald-400" : "text-red-400"}>{v.fact_check.passed ? "Passed" : `${v.fact_check.blocking} blocking issues`}</div>
          </div>
        )}
        {v.jobs?.length > 0 && (
          <div className="card text-sm">
            <div className="label">Jobs</div>
            {v.jobs.map((j: any) => <div key={j.id} className="flex justify-between"><span>{j.kind}</span><span className="text-stone-400">{j.status} ({j.attempts})</span></div>)}
          </div>
        )}
      </div>
    </div>
  );
}

function ScriptTab({ v }: any) {
  const issues: any[] = v.fact_check?.issues || [];
  const byScene = new Map<number, any[]>();
  for (const i of issues) {
    const s = parseInt(i.id);
    byScene.set(s, [...(byScene.get(s) || []), i]);
  }
  if (!v.script?.scenes) return <div className="text-stone-500">No script yet.</div>;
  return (
    <div className="space-y-3">
      <div className="card text-sm"><b>Logline:</b> {v.script.logline} · <b>Mood:</b> {v.script.mood}</div>
      {v.script.scenes.map((s: any, i: number) => (
        <div key={i} className="card">
          <div className="mb-1 flex justify-between text-xs uppercase text-stone-500">
            <span>{i + 1}. {s.section} · {s.chapter}</span><span>{s.visual?.type} · {s.visual?.camera}</span>
          </div>
          <p className="text-parchment">{s.narration}</p>
          {s.claims?.length > 0 && (
            <ul className="mt-2 space-y-0.5 text-xs text-stone-400">
              {s.claims.map((c: any, k: number) => {
                const issue = issues.find((x) => x.id === `${i}.${k}`);
                return (
                  <li key={k}>
                    {issue ? "⚠️" : "✓"} {c.claim} <span className="text-stone-600">[{c.source_ids.join(", ")}] {c.certainty}</span>
                    {issue && <span className="text-amber-400"> — {issue.verdict}: {issue.reason}</span>}
                  </li>
                );
              })}
            </ul>
          )}
          {(byScene.get(i) || []).filter((x) => x.id.endsWith("quote")).map((x, k) => <div key={k} className="mt-1 text-xs text-red-400">Quote issue: {x.reason}</div>)}
        </div>
      ))}
    </div>
  );
}

function Sources({ v }: any) {
  const bib = v.research?.bibliography || [];
  const tierName = ["", "Academic / archival / museum", "Reputable publication", "Other"];
  return (
    <div className="space-y-2">
      <div className="text-sm text-stone-400">{bib.length} cited sources. Every source here was returned by a live web search during research — none are written from memory.</div>
      {bib.map((s: any) => (
        <div key={s.id} className="card !p-3 text-sm">
          <div className="flex justify-between gap-3">
            <a href={s.url} target="_blank" className="text-sky-400 hover:underline">[{s.id}] {s.title || s.url}</a>
            <span className="shrink-0 text-xs text-stone-500">{tierName[s.tier] || ""}{s.added_by ? " · fact-check" : ""}</span>
          </div>
          {s.excerpts?.[0] && <div className="mt-1 line-clamp-2 text-xs text-stone-400">“{s.excerpts[0]}”</div>}
        </div>
      ))}
    </div>
  );
}

function Scenes({ v }: any) {
  return (
    <div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {v.scenes.map((s: any) => (
          <div key={s.idx} className="card !p-3 text-sm">
            <div className="mb-2 aspect-video overflow-hidden rounded bg-stone-800">
              {s.clip_url ? <video src={fileUrl(s.clip_url)} controls preload="none" poster={fileUrl(s.image_url)} className="h-full w-full object-cover" />
                : s.image_url ? <img src={fileUrl(s.image_url)} className="h-full w-full object-cover" /> : null}
            </div>
            <div className="mb-1 text-xs text-stone-500">#{s.idx + 1} · {s.visual?.type}{s.visual?.demoted ? " (demoted)" : ""} · {s.duration?.toFixed(1)}s · @{fmtDur(s.start_s)}</div>
            <div className="line-clamp-3">{s.narration}</div>
            {s.audio_url && <audio controls preload="none" src={fileUrl(s.audio_url)} className="mt-2 h-8 w-full" />}
          </div>
        ))}
      </div>
      <h3 className="mt-8 mb-2 font-display text-parchment">Licensing ledger</h3>
      <div className="card !p-0">
        <table className="w-full text-xs">
          <thead className="text-left uppercase text-stone-500"><tr><th className="p-2">Kind</th><th>Source</th><th>License</th><th>Commercial</th><th>AI</th></tr></thead>
          <tbody>
            {v.assets.map((a: any, i: number) => (
              <tr key={i} className="border-t border-stone-800"><td className="p-2">{a.kind}</td><td>{a.source}</td><td>{a.license}</td><td>{a.commercial_use ? "yes" : "NO"}</td><td>{a.ai_generated ? "yes" : "no"}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Thumbs({ v, reload }: any) {
  const act = useAction();
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {v.thumbnails.map((t: any, i: number) => (
        <div key={i} className={`card ${v.selected_thumbnail === i ? "!border-gold" : ""}`}>
          <img src={fileUrl(t.url)} className="rounded" />
          <div className="mt-2 text-sm">{t.concept?.idea}</div>
          <div className="text-xs text-stone-400">score {t.score ?? "—"} · contrast {t.contrast} {t.review?.comment ? `· ${t.review.comment}` : ""}</div>
          {v.selected_thumbnail === i ? <div className="mt-2 text-sm text-gold">Selected</div> : (
            <button className="btn-ghost mt-2" disabled={!!v.youtube_url || act.busy} onClick={() => act.run(() => post(`/api/videos/${v.id}/thumbnail`, { index: i })).then(reload)}>Use this</button>
          )}
        </div>
      ))}
      {!v.thumbnails.length && <div className="text-stone-500">Thumbnails are generated after rendering.</div>}
    </div>
  );
}

function Meta({ v, reload }: any) {
  const md = v.metadata || {};
  const [f, setF] = useState({ title: md.title || "", description: md.description || "", tags: (md.tags || []).join(", "), playlist: md.playlist || "" });
  const act = useAction();
  const locked = !!v.youtube_url;
  return (
    <div className="max-w-3xl space-y-4">
      <div><label className="label">Title ({f.title.length}/100)</label><input className="input" disabled={locked} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></div>
      {md.alt_titles?.length > 0 && (
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="text-stone-400">Other title options:</span>
          {md.alt_titles.map((t: string) => <button key={t} disabled={locked} className="rounded bg-stone-800 px-2 py-1 hover:bg-stone-700" onClick={() => setF({ ...f, title: t })}>{t}</button>)}
        </div>
      )}
      {md.trending_sound_fit && (
        <div className="rounded border border-sky-900 bg-sky-950/40 p-2 text-sm text-sky-200">
          A trending song would suit this one. YouTube only lets you add songs from its licensed Shorts library inside the YouTube app:
          switch this video to the weekly pack (Calendar → Download) and add the sound while uploading from your phone.
        </div>
      )}
      {md.platform_captions && Object.keys(md.platform_captions).length > 0 && (
        <div className="text-sm"><span className="label">Captions for other platforms (post manually until their APIs are connected)</span>
          {Object.entries(md.platform_captions).map(([k, v]: any) => (
            <div key={k} className="mb-2 flex gap-2"><span className="w-20 shrink-0 text-xs uppercase text-stone-500">{k}</span>
              <div className="flex-1 whitespace-pre-wrap rounded bg-stone-950 p-2 text-xs">{v}</div>
              <button className="btn-ghost h-8" onClick={() => navigator.clipboard.writeText(v)}>Copy</button></div>
          ))}
        </div>
      )}
      <div><label className="label">Description ({new TextEncoder().encode(f.description).length}/5000 bytes)</label>
        <textarea className="input h-80 font-mono text-xs" disabled={locked} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></div>
      <div><label className="label">Tags (comma-separated)</label><input className="input" disabled={locked} value={f.tags} onChange={(e) => setF({ ...f, tags: e.target.value })} /></div>
      <div><label className="label">Playlist</label><input className="input" disabled={locked} value={f.playlist} onChange={(e) => setF({ ...f, playlist: e.target.value })} /></div>
      <div className="text-sm text-stone-400">Category: Sports (17) · AI disclosure in description · Made for kids: no</div>
      {md.chapters && <div className="text-sm"><span className="label">Chapters</span>{md.chapters.map((c: any) => <div key={c.start}>{fmtDur(c.start)} {c.title}</div>)}</div>}
      {!locked && (
        <button className="btn-primary" disabled={act.busy} onClick={() => act.run(() => patch(`/api/videos/${v.id}/metadata`, {
          title: f.title, description: f.description, tags: f.tags.split(",").map((t: string) => t.trim()).filter(Boolean), playlist: f.playlist,
        }), "Saved.").then(reload)}>Save metadata</button>
      )}
      {act.msg && <div className="text-sm text-amber-300">{act.msg}</div>}
    </div>
  );
}

function Shorts({ v, reload }: any) {
  const act = useAction();
  return (
    <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-4">
      {v.shorts.map((s: any) => (
        <div key={s.id} className="card">
          {s.video_url && <video controls preload="none" src={fileUrl(s.video_url)} className="aspect-[9/16] w-full rounded bg-black" />}
          <div className="mt-2 text-sm">{s.title}</div>
          <div className="mt-1 flex items-center justify-between"><StatusBadge status={s.status} /><span className="text-xs text-stone-400">{fmtDur(s.duration_s)}</span></div>
          {s.status === "awaiting_approval" && (
            <div className="mt-2 flex gap-2">
              <button className="btn-primary" onClick={() => act.run(() => post(`/api/videos/${s.id}/approve`, {})).then(reload)}>Approve</button>
              <button className="btn-danger" onClick={() => act.run(() => post(`/api/videos/${s.id}/reject`)).then(reload)}>Reject</button>
            </div>
          )}
          {s.youtube_url && <a className="mt-2 block text-sm text-sky-400" href={s.youtube_url} target="_blank">YouTube ↗</a>}
        </div>
      ))}
      {!v.shorts.length && <div className="text-stone-500">Shorts are created after the main video passes QC.</div>}
      {act.msg && <div className="text-sm text-amber-300">{act.msg}</div>}
    </div>
  );
}

function Log({ v }: any) {
  return (
    <div className="card max-h-[70vh] overflow-y-auto font-mono text-xs">
      {[...v.events].reverse().map((e: any, i: number) => (
        <div key={i} className={`border-b border-stone-900 py-1 ${e.level === "error" ? "text-red-400" : e.level === "warn" ? "text-amber-300" : "text-stone-300"}`}>
          <span className="text-stone-600">{new Date(e.at).toLocaleTimeString()}</span> [{e.stage}] {e.message}
        </div>
      ))}
    </div>
  );
}
