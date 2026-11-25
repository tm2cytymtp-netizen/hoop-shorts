import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, fileUrl, post } from "../api";
import { ErrorNote, usePoll, useAction } from "../components/ui";

export default function MemeStudio() {
  const { data, error, reload } = usePoll(() => api("/api/memes"), 15000);
  const templates = usePoll(() => api("/api/memes/templates"), 600000).data || [];
  const [topic, setTopic] = useState("");
  const act = useAction();
  const nav = useNavigate();
  return (
    <div>
      <h1 className="page">Meme Studio</h1>
      <ErrorNote error={error} />
      <div className="card mb-6 flex flex-wrap items-end gap-3">
        <div className="min-w-72 flex-1">
          <label className="label">Topic or angle (optional) — e.g. "rec league refs", "a player's last-second miss"</label>
          <input className="input" value={topic} onChange={(e) => setTopic(e.target.value)} />
        </div>
        <button className="btn-primary" disabled={act.busy} onClick={() => act.run(() => post("/api/memes/ideas", { topic, n: 6 })).then(reload)}>
          {act.busy ? "Writing…" : "Generate 6 meme ideas"}
        </button>
      </div>
      <div className="mb-4 flex flex-wrap gap-2 text-xs text-stone-400">
        Templates: {templates.map((t: any) => <span key={t.id} className="rounded bg-stone-800 px-2 py-1">{t.name} — <i>{t.example}</i></span>)}
      </div>
      {act.msg && <div className="mb-4 text-sm text-amber-300">{act.msg}</div>}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {(data || []).map((m: any) => (
          <div key={m.id} className="card">
            {m.image_url ? <img src={fileUrl(m.image_url)} className="mx-auto mb-3 max-h-96 rounded" /> : (
              <div className="mb-3 rounded bg-stone-950 p-4 text-center font-display text-xl leading-tight">
                {m.idea.top_text || m.idea.caption}<div className="my-2 text-xs font-sans text-stone-500">[{m.idea.template}] {m.idea.image_prompt}</div>{m.idea.bottom_text}
              </div>
            )}
            <div className="text-xs text-stone-400">{m.idea.why_funny}</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {m.status === "idea" && <button className="btn-ghost" disabled={act.busy} onClick={() => act.run(() => post(`/api/memes/${m.id}/render`)).then(reload)}>Render image</button>}
              {m.status !== "video" && <button className="btn-primary" disabled={act.busy} onClick={() => act.run(async () => { const r = await post(`/api/memes/${m.id}/video`); nav(`/videos/${r.video_id}`); })}>Make it a Short</button>}
              {m.video_id && <button className="btn-ghost" onClick={() => nav(`/videos/${m.video_id}`)}>View Short</button>}
              <button className="btn-danger" onClick={() => act.run(() => post(`/api/memes/${m.id}/reject`)).then(reload)}>Discard</button>
            </div>
          </div>
        ))}
      </div>
      {data && !data.length && <div className="text-sm text-stone-500">No memes yet — generate some ideas.</div>}
    </div>
  );
}
