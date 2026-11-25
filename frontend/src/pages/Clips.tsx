import { useState } from "react";
import { api, fileUrl, fmtDur, getToken } from "../api";
import { ErrorNote, usePoll, useAction } from "../components/ui";

export default function Clips() {
  const { data, error, reload } = usePoll(() => api("/api/clips"), 30000);
  const [f, setF] = useState({ title: "", description: "", source: "", license: "", attest: false });
  const [file, setFile] = useState<File | null>(null);
  const act = useAction();
  const upload = () => act.run(async () => {
    const fd = new FormData();
    fd.append("file", file as File);
    Object.entries(f).forEach(([k, v]) => fd.append(k, String(v)));
    const r = await fetch("/api/clips", { method: "POST", body: fd, headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {} });
    if (!r.ok) throw new Error((await r.json()).detail);
    setF({ title: "", description: "", source: "", license: "", attest: false });
    setFile(null);
    reload();
  }, "Uploaded — the script writer can now use it.");
  return (
    <div className="max-w-5xl">
      <h1 className="page">My Clips</h1>
      <ErrorNote error={error} />
      <div className="card mb-6">
        <p className="mb-3 text-sm text-stone-400">
          Upload footage you shot yourself or licensed for reuse (your games, a licensed stock pack). The script writer can cut it into Shorts.
          NBA broadcasts and other creators' videos can't be used — Content ID would claim them and they don't qualify for monetization.
        </p>
        <div className="grid gap-3 md:grid-cols-2">
          <input type="file" accept="video/*" className="input" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          <input className="input" placeholder="Title (e.g. 'My rec league game-winner')" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
          <input className="input md:col-span-2" placeholder="What happens in the clip (helps the AI use it)" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
          <input className="input" placeholder="Source (e.g. 'Filmed by me', 'Storyblocks')" value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })} />
          <input className="input" placeholder="License (e.g. 'Owned', 'Storyblocks commercial licence')" value={f.license} onChange={(e) => setF({ ...f, license: e.target.value })} />
        </div>
        <label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={f.attest} onChange={(e) => setF({ ...f, attest: e.target.checked })} />I own this footage or have permission to use it commercially.</label>
        <button className="btn-primary mt-3" disabled={!file || !f.title || !f.source || !f.license || !f.attest || act.busy} onClick={upload}>{act.busy ? "Uploading…" : "Upload clip"}</button>
        {act.msg && <span className="ml-3 text-sm text-amber-300">{act.msg}</span>}
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        {(data || []).map((c: any) => (
          <div key={c.id} className="card text-sm">
            <video src={fileUrl(c.url)} controls preload="none" className="mb-2 w-full rounded bg-black" />
            <div className="font-medium">#{c.id} {c.title} <span className="text-stone-500">({fmtDur(c.duration_s)})</span></div>
            <div className="text-xs text-stone-400">{c.source} · {c.license}</div>
            <button className="btn-danger mt-2" onClick={() => act.run(() => api(`/api/clips/${c.id}`, { method: "DELETE" })).then(reload)}>Delete</button>
          </div>
        ))}
      </div>
    </div>
  );
}
