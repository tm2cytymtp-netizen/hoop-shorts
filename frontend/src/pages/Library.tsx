import { useState } from "react";
import { api } from "../api";
import { ErrorNote, usePoll, VideoCard } from "../components/ui";

export default function Library() {
  const [kind, setKind] = useState("short");
  const [status, setStatus] = useState("");
  const { data, error } = usePoll(() => api(`/api/videos?kind=${kind}${status ? `&status=${status}` : ""}`), 15000);
  return (
    <div>
      <h1 className="page">Video Library</h1>
      <ErrorNote error={error} />
      <div className="mb-6 flex gap-3">
        <select className="input !w-40" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="long">Long-form</option><option value="short">Shorts</option>
        </select>
        <select className="input !w-56" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          <option value="awaiting_approval,needs_review">Ready / needs review</option>
          <option value="approved,uploading,scheduled">Approved & scheduled</option>
          <option value="published">Published</option>
          <option value="failed,paused_budget,rejected">Failed / paused / rejected</option>
        </select>
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4 xl:grid-cols-5">
        {(data || []).map((v: any) => <VideoCard key={v.id} v={v} />)}
      </div>
      {data && !data.length && <div className="text-sm text-stone-500">Nothing here yet.</div>}
    </div>
  );
}
