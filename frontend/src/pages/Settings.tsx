import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, getToken, post, put, setToken } from "../api";
import { ErrorNote, usePoll, useAction } from "../components/ui";

const SECTIONS: [string, string, string][] = [
  ["channel", "Channel", "format_mix sets the daily mix of meme / comparison / fact / storyline / ranking / hypothetical / news formats. youtube_channel_id (starts with UC — YouTube Studio → Settings → Channel → Advanced) lets the app confirm posts and read public view counts."],
  ["shorts", "Shorts", "times = daily posting times in the schedule timezone (3/day fits Zapier's free 100 posts/month; 4–5/day needs a paid Zapier plan or the weekly pack). target_seconds = length range."],
  ["publishing", "Publishing method", "zapier_rss (automatic, public) · manual_batch (weekly pack you schedule in YouTube Studio) · youtube_api (your own Google Cloud project; private until YouTube's audit). Don't change feed_key unless the feed URL leaked — then update it in your Zap."],
  ["schedule", "Automation & approval", "auto_produce keeps upcoming slots filled. approval_mode: 'auto' publishes only when every quality check passes; 'manual' waits for your Approve click. timezone applies to all posting times. days/time are for long-form."],
  ["budget", "Monthly budget & limits", "Jobs pause and notify you when a limit would be exceeded."],
  ["voice", "Voice", "format_voice picks the narrator per format (energetic commentator, funny meme narrator, casual Gen Z, analyst, documentary). Kokoro voices are free; ElevenLabs is the paid option."],
  ["video", "Video style", "art_style is appended to every image prompt. label_ai_visuals adds a small 'Artistic reconstruction' tag."],
  ["ai", "AI providers", "Model IDs for Claude and fal.ai endpoints. Check each fal model page for commercial-use terms."],
  ["pricing", "Price table (for estimates)", "Update these from your providers' current pricing pages."],
  ["quality", "Quality thresholds", ""],
];

function Field({ k, value, onChange }: { k: string; value: any; onChange: (v: any) => void }) {
  if (typeof value === "boolean")
    return <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={value} onChange={(e) => onChange(e.target.checked)} />{k.replaceAll("_", " ")}</label>;
  if (typeof value === "number")
    return <div><label className="label">{k.replaceAll("_", " ")}</label><input type="number" step="any" className="input" value={value} onChange={(e) => onChange(parseFloat(e.target.value))} /></div>;
  if (Array.isArray(value) && value.every((x) => typeof x !== "object"))
    return <div className="md:col-span-2"><label className="label">{k.replaceAll("_", " ")} (comma-separated)</label>
      <input className="input" value={value.join(", ")} onChange={(e) => onChange(e.target.value.split(",").map((s) => s.trim()).filter(Boolean).map((s) => (isNaN(+s) ? s : +s)))} /></div>;
  if (value && typeof value === "object")
    return (
      <fieldset className="rounded-lg border border-stone-800 p-3 md:col-span-2">
        <legend className="px-1 text-xs uppercase text-stone-400">{k.replaceAll("_", " ")}</legend>
        <div className="grid gap-3 md:grid-cols-2">
          {Object.entries(value).map(([kk, vv]) => <Field key={kk} k={kk} value={vv} onChange={(nv) => onChange({ ...value, [kk]: nv })} />)}
        </div>
      </fieldset>
    );
  const long = typeof value === "string" && value.length > 60;
  return <div className={long ? "md:col-span-2" : ""}><label className="label">{k.replaceAll("_", " ")}</label>
    {long ? <textarea className="input h-20" value={value} onChange={(e) => onChange(e.target.value)} />
      : <input className="input" value={value ?? ""} onChange={(e) => onChange(e.target.value)} />}</div>;
}

function Section({ id, title, help, initial }: { id: string; title: string; help: string; initial: any }) {
  const [val, setVal] = useState(initial);
  const act = useAction();
  useEffect(() => setVal(initial), [initial]);
  return (
    <details className="card">
      <summary className="cursor-pointer font-display text-parchment">{title}</summary>
      {help && <p className="mt-2 text-xs text-stone-400">{help}</p>}
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {Object.entries(val).map(([k, v]) => <Field key={k} k={k} value={v} onChange={(nv) => setVal({ ...val, [k]: nv })} />)}
      </div>
      <button className="btn-primary mt-4" disabled={act.busy} onClick={() => act.run(() => put(`/api/settings/${id}`, val), "Saved.")}>Save</button>
      {act.msg && <span className="ml-3 text-sm text-amber-300">{act.msg}</span>}
    </details>
  );
}

export default function Settings() {
  const { data, error } = usePoll(() => api("/api/settings"), 600000);
  const integ = usePoll(() => api("/api/integrations"), 15000);
  const [params] = useSearchParams();
  const [tok, setTok] = useState(getToken());
  const act = useAction();
  const i = integ.data;
  const Row = ({ ok, label, hint }: { ok: boolean; label: string; hint: string }) => (
    <tr className="border-t border-stone-800"><td className="py-2 pr-3">{ok ? "✅" : "⬜"}</td><td className="pr-3">{label}</td><td className="text-xs text-stone-400">{hint}</td></tr>
  );
  return (
    <div className="max-w-5xl">
      <h1 className="page">Settings</h1>
      <ErrorNote error={error || integ.error} />
      {params.get("youtube") === "connected" && <div className="mb-4 text-sm text-emerald-400">YouTube connected: {params.get("channel")}</div>}
      {params.get("youtube") === "error" && <div className="mb-4 text-sm text-red-400">YouTube connection failed: {params.get("reason")}</div>}

      {i && i.publishing_method === "zapier_rss" && (
        <div className="card mb-4">
          <div className="font-display text-parchment">Automatic public posting with Zapier (no Google Cloud project)</div>
          {i.public_url_is_local && (
            <div className="mt-2 rounded border border-amber-900 bg-amber-950/40 p-2 text-sm text-amber-200">
              PUBLIC_BASE_URL is localhost — Zapier can't reach it. Run this on a server with a public HTTPS address
              (or a Cloudflare Tunnel) and set PUBLIC_BASE_URL to it.
            </div>
          )}
          <div className="mt-3 text-sm">
            <label className="label">Your private feed URL (keep it secret)</label>
            <div className="flex gap-2">
              <input className="input font-mono text-xs" readOnly value={i.feed_url} />
              <button className="btn-ghost" onClick={() => navigator.clipboard.writeText(i.feed_url)}>Copy</button>
            </div>
          </div>
          <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm text-stone-300">
            <li>In Zapier, create a Zap. Trigger: <b>RSS by Zapier → New Item in Feed</b>, paste the feed URL above.</li>
            <li>Action: <b>YouTube → Upload Video</b>. Connect your YouTube account (you sign in on Google's page).</li>
            <li>Map <b>Video</b> ← Item <i>Link</i>, <b>Title</b> ← <i>Title</i>, <b>Description</b> ← <i>Description</i>, <b>Privacy</b> = Public, <b>Made for kids</b> = No, <b>Category</b> = Education.</li>
            <li>Turn the Zap on. Each Short enters the feed at its scheduled time; Zapier posts it on its next check (every 1–15 min depending on your Zapier plan).</li>
            <li>Set <b>youtube_channel_id</b> under Channel below so the dashboard confirms each post and tracks views.</li>
          </ol>
        </div>
      )}
      <div className="card mb-4">
        <div className="font-display text-parchment">Connections</div>
        <p className="mt-1 text-xs text-stone-400">API keys live only in the server's .env file — never in the browser or database. This list shows which are present.</p>
        {i && (
          <table className="mt-3 w-full text-sm"><tbody>
            {i.llm_provider === "gemini"
              ? <Row ok={i.gemini} label="Gemini API key (free)" hint="GEMINI_API_KEY — free at aistudio.google.com/apikey · research uses Wikipedia" />
              : <Row ok={i.anthropic} label="Anthropic (Claude) API key" hint="ANTHROPIC_API_KEY — paid upgrade with live web search" />}
            {i.image_provider === "cloudflare"
              ? <Row ok={i.cloudflare} label="Cloudflare Workers AI (free)" hint="CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN — 10,000 free neurons/day · plus The Met CC0 artworks" />
              : <Row ok={i.fal} label="fal.ai API key" hint="FAL_KEY — paid images + AI motion" />}
            {i.voice_provider === "kokoro"
              ? <Row ok={true} label="Narration: Kokoro (free, runs locally)" hint="No key needed; the voice model downloads once (~350 MB)" />
              : <><Row ok={i.elevenlabs} label="ElevenLabs API key" hint="ELEVENLABS_API_KEY — paid plan for commercial use" />
                 <Row ok={i.elevenlabs_voice} label="Narrator voice selected" hint="Settings → Voice → paste a voice_id" /></>}
            <Row ok={i.youtube_channel_id} label="YouTube channel ID" hint="Settings → Channel → youtube_channel_id (confirms posts, public view counts)" />
            {i.publishing_method === "youtube_api" && <>
              <Row ok={i.google_oauth_client} label="Google OAuth client" hint={`GOOGLE_CLIENT_ID/SECRET. Authorised redirect URI: ${i.oauth_redirect_uri}`} />
              <Row ok={i.secret_key} label="Token encryption key" hint="SECRET_KEY (Fernet) — encrypts your YouTube refresh token" />
              <Row ok={i.youtube?.connected} label={`YouTube channel${i.youtube?.channel ? `: ${i.youtube.channel}` : ""}`} hint="Sign in on Google's page; your password never touches this app" />
            </>}
            <Row ok={i.music_tracks > 0} label={`Licensed music (${i.music_tracks} tracks)`} hint="assets/music/library.json — see README" />
            <Row ok={i.notifications} label="Notifications" hint="NOTIFY_WEBHOOK_URL (Discord/Slack) or SMTP_* for email" />
            <Row ok={i.youtube_api_key} label="YouTube API key (optional)" hint="YOUTUBE_API_KEY — lets topic discovery see what's trending; a simple free key, not an upload project" />
          </tbody></table>
        )}
        {i?.publishing_method === "youtube_api" && <div className="mt-4 flex gap-2">
          {!i?.youtube?.connected ? (
            <button className="btn-primary" disabled={act.busy} onClick={() => act.run(async () => { const r = await api("/api/youtube/connect"); window.location.href = r.url; })}>Connect YouTube</button>
          ) : (
            <button className="btn-danger" onClick={() => act.run(() => post("/api/youtube/disconnect")).then(integ.reload)}>Disconnect YouTube</button>
          )}
        </div>}
        {act.msg && <div className="mt-2 text-sm text-amber-300">{act.msg}</div>}
        <div className="mt-4 flex items-end gap-2">
          <div className="flex-1"><label className="label">Dashboard access token (if DASHBOARD_TOKEN is set on the server)</label>
            <input className="input" type="password" value={tok} onChange={(e) => setTok(e.target.value)} /></div>
          <button className="btn-ghost" onClick={() => { setToken(tok); location.reload(); }}>Save token</button>
        </div>
      </div>
      <div className="space-y-3">
        {data && SECTIONS.map(([id, title, help]) => <Section key={id} id={id} title={title} help={help} initial={data[id]} />)}
      </div>
    </div>
  );
}
