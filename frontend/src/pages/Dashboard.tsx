import { Link, useNavigate } from "react-router-dom";
import { api, fmtDate, post, usd } from "../api";
import { ErrorNote, Stat, usePoll, useAction, VideoCard } from "../components/ui";

export default function Dashboard() {
  const { data, error } = usePoll(() => api("/api/dashboard"), 8000);
  const integ = usePoll(() => api("/api/integrations"), 30000).data;
  const nav = useNavigate();
  const act = useAction();

  const generate = () =>
    act.run(async () => {
      const r = await post("/api/videos/generate", {});
      if (r.video_id) nav(`/videos/${r.video_id}`);
      else act.setMsg(r.detail);
    });

  const missing = integ
    ? [
        integ.llm_provider === "gemini" ? !integ.gemini && "free Gemini key" : !integ.anthropic && "Anthropic API key",
        integ.image_provider === "cloudflare" ? !integ.cloudflare && "free Cloudflare keys" : !integ.fal && "fal.ai key",
        integ.voice_provider === "elevenlabs" && !integ.elevenlabs && "ElevenLabs key",
        integ.publishing_method === "youtube_api" && !integ.youtube?.connected && "YouTube account",
        integ.publishing_method === "zapier_rss" && integ.public_url_is_local && "public server URL for Zapier",
        !integ.youtube_channel_id && "YouTube channel ID", integ.music_tracks === 0 && "licensed music tracks",
      ].filter(Boolean)
    : [];

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="page !mb-0">Dashboard</h1>
        <button className="btn-primary text-base" disabled={act.busy} onClick={generate}>
          {act.busy ? "Starting…" : "Make a Short now"}
        </button>
      </div>
      <ErrorNote error={error} />
      {act.msg && <div className="mb-4 text-sm text-amber-300">{act.msg}</div>}
      {missing.length > 0 && (
        <div className="mb-6 rounded-lg border border-amber-900 bg-amber-950/40 p-3 text-sm text-amber-200">
          Setup incomplete: {missing.join(", ")}. See Settings → Connections.
        </div>
      )}
      {data && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Stat label="Videos created" value={data.total_created} hint={`${data.shorts} Shorts`} />
            <Stat label="In production" value={data.in_production} />
            <Stat label="Awaiting approval" value={data.awaiting_approval} hint={data.needs_review ? `${data.needs_review} need review` : undefined} />
            <Stat label="Scheduled" value={data.scheduled} />
            <Stat label="Published" value={data.published} />
            <Stat label="Failed / paused" value={data.failed} />
            <Stat label="Total views" value={data.total_views.toLocaleString()} />
            <Stat label="Est. revenue" value={data.estimated_revenue == null ? "n/a" : usd(data.estimated_revenue)}
              hint="Shown when the channel is monetised" />
          </div>
          <div className="mt-6 grid gap-4 lg:grid-cols-3">
            <div className="card">
              <div className="label">AI spend this month</div>
              <div className="font-display text-2xl text-parchment">{usd(data.month_spend)} <span className="text-sm text-stone-500">/ {usd(data.budget.max_monthly_usd)}</span></div>
              <div className="mt-2 h-2 rounded bg-stone-800">
                <div className="h-2 rounded bg-gold" style={{ width: `${Math.min(100, (data.month_spend / data.budget.max_monthly_usd) * 100)}%` }} />
              </div>
            </div>
            <div className="card lg:col-span-2">
              <div className="label">Next publishing slots</div>
              <div className="flex flex-wrap gap-2 text-sm">
                {data.next_slots.map((s: string) => <span key={s} className="rounded bg-stone-800 px-2 py-1">{fmtDate(s)}</span>)}
              </div>
            </div>
          </div>
          <TodayIdeas />
          <h2 className="mt-8 mb-3 font-display text-lg text-parchment">Recent Shorts</h2>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {data.recent.map((v: any) => <VideoCard key={v.id} v={v} />)}
            {!data.recent.length && <div className="text-sm text-stone-500">No videos yet — click "Generate New Video".</div>}
          </div>
        </>
      )}
    </div>
  );
}

function TodayIdeas() {
  const { data } = usePoll(() => api("/api/topics?status=suggested"), 60000);
  const top = (data || []).slice(0, 5);
  return (
    <div className="mt-8">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-display text-lg text-parchment">Today's top ideas</h2>
        <Link to="/topics" className="text-sm text-gold">All ideas →</Link>
      </div>
      <div className="grid gap-3 md:grid-cols-5">
        {top.map((t: any) => (
          <Link key={t.id} to="/topics" className="card block !p-3 text-sm hover:border-gold/60">
            <div className="font-display text-2xl text-gold">{t.score?.toFixed(1)}</div>
            <div className="line-clamp-2">{t.title}</div>
            <div className="mt-1 text-xs text-stone-500">{t.format}</div>
          </Link>
        ))}
        {!top.length && <div className="text-sm text-stone-500">No ideas yet — the system finds them daily, or open the Idea Generator.</div>}
      </div>
    </div>
  );
}
