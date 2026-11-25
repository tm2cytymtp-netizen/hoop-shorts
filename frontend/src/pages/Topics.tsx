import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, post } from "../api";
import { ErrorNote, usePoll, useAction } from "../components/ui";

const SCORE_KEYS = ["current_popularity", "audience_interest", "entertainment", "relevance", "originality", "timeliness"];

export default function Topics() {
  const [filter, setFilter] = useState("suggested");
  const { data, error, reload } = usePoll(() => api(`/api/topics${filter ? `?status=${filter}` : ""}`), 10000);
  const [focus, setFocus] = useState("");
  const act = useAction();
  const nav = useNavigate();
  const [manual, setManual] = useState({ title: "", category: "", main_event: "", why_watch: "" });
  const [mfmt, setMfmt] = useState("career_stats");
  const [players, setPlayers] = useState("");

  return (
    <div>
      <h1 className="page">Idea Generator</h1>
      <ErrorNote error={error} />
      <div className="card mb-6 flex flex-wrap items-end gap-3">
        <div className="min-w-64 flex-1">
          <label className="label">Optional focus (e.g. "rookies", "rivalries", "last night's games")</label>
          <input className="input" value={focus} onChange={(e) => setFocus(e.target.value)} />
        </div>
        <button className="btn-primary" disabled={act.busy}
          onClick={() => act.run(() => post("/api/topics/discover", { n: 12, focus }), "Discovery job queued — results appear here in a few minutes.")}>
          Find today's ideas
        </button>
        <select className="input !w-40" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="suggested">Suggested</option><option value="approved">Approved</option>
          <option value="used">Used</option><option value="rejected">Rejected</option><option value="">All</option>
        </select>
      </div>
      {act.msg && <div className="mb-4 text-sm text-amber-300">{act.msg}</div>}
      <div className="space-y-3">
        {(data || []).map((t: any) => (
          <div key={t.id} className="card">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-3">
                  <span className="font-display text-xl text-gold">{t.score?.toFixed?.(1) ?? "—"}</span>
                  <span className="text-base font-medium text-parchment">{t.title}</span>
                </div>
                <div className="mt-1 text-xs text-stone-400">
                  <span className="rounded bg-gold/20 px-1.5 py-0.5 text-gold">{t.format || "idea"}</span> · {t.category}
                  {t.players?.length > 0 && <> · {t.players.join(", ")}</>}
                </div>
                <p className="mt-2 text-sm text-stone-300"><b className="text-stone-400">Angle:</b> {t.why_watch}</p>
                <p className="mt-1 text-sm text-stone-300"><b className="text-stone-400">Based on:</b> {t.main_event}</p>
                {t.evidence?.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2 text-xs">
                    {t.evidence.map((u: string) => <a key={u} href={u} target="_blank" className="text-sky-400 hover:underline">{new URL(u).hostname}</a>)}
                  </div>
                )}
              </div>
              <div className="w-56 space-y-1">
                {SCORE_KEYS.filter((k) => t.scores?.[k] != null).map((k) => (
                  <div key={k} className="grid grid-cols-[1fr_5rem] items-center gap-2 text-xs">
                    <span className="text-stone-400">{k.replace("_", " ")}</span>
                    <div className="h-1.5 rounded bg-stone-800"><div className="h-1.5 rounded bg-gold" style={{ width: `${t.scores[k] * 10}%` }} /></div>
                  </div>
                ))}
              </div>
            </div>
            <div className="mt-3 flex gap-2">
              {t.status !== "used" && (
                <button className="btn-primary" onClick={() => act.run(async () => { const r = await post(`/api/topics/${t.id}/produce`); nav(`/videos/${r.video_id}`); })}>
                  Make this Short
                </button>
              )}
              {t.status === "suggested" && <button className="btn-ghost" onClick={() => act.run(() => post(`/api/topics/${t.id}/approve`)).then(reload)}>Approve</button>}
              {t.status !== "rejected" && t.status !== "used" && <button className="btn-danger" onClick={() => act.run(() => post(`/api/topics/${t.id}/reject`)).then(reload)}>Reject</button>}
            </div>
          </div>
        ))}
        {data && !data.length && <div className="text-sm text-stone-500">No topics here yet.</div>}
      </div>
      <div className="card mt-8">
        <div className="label">Add your own topic</div>
        <div className="grid gap-2 md:grid-cols-4">
          {(["title", "category", "main_event", "why_watch"] as const).map((k) => (
            <input key={k} className="input" placeholder={k.replace("_", " ")} value={manual[k]} onChange={(e) => setManual({ ...manual, [k]: e.target.value })} />
          ))}
        </div>
        <div className="mt-2 grid gap-2 md:grid-cols-2">
          <select className="input" value={mfmt} onChange={(e) => setMfmt(e.target.value)}>
            {["career_stats", "comparison", "recap", "fact", "storyline", "ranking", "news_reaction", "meme", "hypothetical"].map((f) => <option key={f}>{f}</option>)}
          </select>
          <input className="input" placeholder="Players (exact names, comma-separated) — e.g. Stephen Curry, Kevin Durant" value={players} onChange={(e) => setPlayers(e.target.value)} />
        </div>
        <button className="btn-ghost mt-3" disabled={!manual.title}
          onClick={() => act.run(() => post("/api/topics", { ...manual, format: mfmt, players: players.split(",").map((p) => p.trim()).filter(Boolean) }), "Topic added to Approved.").then(() => setManual({ title: "", category: "", main_event: "", why_watch: "" }))}>
          Add topic
        </button>
      </div>
    </div>
  );
}
