"""FastAPI app: dashboard API + static frontend.

Run with:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from . import costs, settings_store
from .config import ROOT, env
from .db import get_db, init_db
from .events import emit, set_status
from .models import AnalyticsSnapshot, Asset, Clip, CostEntry, Insight, Job, Meme, Setting, Topic, Video
from .orchestrator import channel_kind, enqueue, new_video
from .pipeline import analytics as an
from .pipeline import library, publish, topics
from .providers import youtube

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="History Channel Automation")
app.add_middleware(CORSMiddleware, allow_origins=[env.frontend_url], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _startup():
    init_db()
    from .pipeline.sfx import ensure_beat, ensure_library
    ensure_library()
    ensure_beat()


def session_token() -> str:
    import hashlib
    import hmac
    return hmac.new(env.dashboard_password.encode(), b"hoops-dashboard-session", hashlib.sha256).hexdigest()


@app.middleware("http")
async def auth(request: Request, call_next):
    p = request.url.path
    if (env.dashboard_token or env.dashboard_password) and p.startswith("/api") and \
            not p.startswith("/api/youtube/oauth/callback") and p not in ("/api/health", "/api/login"):
        tok = request.headers.get("authorization", "").removeprefix("Bearer ").strip() or \
            request.query_params.get("token", "")
        valid = {t for t in (env.dashboard_token, session_token() if env.dashboard_password else "") if t}
        if tok not in valid:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)


def _video_or_404(db: Session, vid: int) -> Video:
    v = db.get(Video, vid)
    if not v:
        raise HTTPException(404, "video not found")
    return v


def topic_dict(t: Topic) -> dict:
    return {c.name: getattr(t, c.name) for c in Topic.__table__.columns}


def video_summary(db: Session, v: Video) -> dict:
    return {"id": v.id, "kind": v.kind, "parent_id": v.parent_id, "status": v.status,
            "title": (v.metadata_ or {}).get("title") or v.working_title, "duration_s": v.duration_s,
            "scheduled_at": v.scheduled_at, "youtube_url": v.youtube_url, "upload_status": v.upload_status,
            "created_at": v.created_at, "updated_at": v.updated_at, "error": v.error[:300],
            "spend": costs.video_spend(db, v.id), "estimate": (v.cost_estimate or {}).get("total"),
            "thumbnail": (f"/api/files/{v.id}/thumbs/{Path(v.thumbnails[v.selected_thumbnail]['path']).name}"
                          if v.thumbnails and v.selected_thumbnail is not None else None),
            "qc_passed": (v.qc_report or {}).get("passed")}


# ---------------------------------------------------------------- health / auth
@app.get("/api/health")
def health():
    return {"ok": True, "auth_required": bool(env.dashboard_token or env.dashboard_password)}


class LoginReq(BaseModel):
    password: str


@app.post("/api/login")
def login(req: LoginReq):
    import hmac
    import time
    time.sleep(0.5)  # slow down guessing
    if not env.dashboard_password:
        raise HTTPException(400, "Set DASHBOARD_PASSWORD in .env to enable login.")
    if not hmac.compare_digest(req.password, env.dashboard_password):
        raise HTTPException(401, "Wrong password")
    return {"token": session_token()}


@app.get("/api/integrations")
def integrations(db: Session = Depends(get_db)):
    vs = settings_store.get(db, "voice")
    return {
        "anthropic": bool(env.anthropic_api_key), "fal": bool(env.fal_key),
        "elevenlabs": bool(env.elevenlabs_api_key),
        "elevenlabs_voice": bool(vs["presets"][vs["preset"]].get("voice_id")),
        "gemini": bool(env.gemini_api_key),
        "cloudflare": bool(env.cloudflare_account_id and env.cloudflare_api_token),
        "llm_provider": settings_store.get(db, "ai")["llm_provider"],
        "image_provider": settings_store.get(db, "ai")["image_provider"],
        "voice_provider": vs.get("provider", "kokoro"),
        "google_oauth_client": bool(env.google_client_id and env.google_client_secret),
        "youtube": youtube.connection(db), "youtube_api_key": bool(env.youtube_api_key),
        "secret_key": bool(env.secret_key), "notifications": bool(env.notify_webhook_url or env.smtp_host),
        "music_tracks": len(library._load("music")),
        "oauth_redirect_uri": youtube.redirect_uri(),
        "format": settings_store.get(db, "channel")["format"],
        "publishing_method": settings_store.get(db, "publishing")["method"],
        "feed_url": f"{env.public_base_url.rstrip('/')}/feed/{settings_store.get(db, 'publishing')['feed_key']}/videos.xml",
        "youtube_channel_id": bool(settings_store.get(db, "channel").get("youtube_channel_id")),
        "public_url_is_local": any(h in env.public_base_url for h in ("localhost", "127.0.0.1")),
    }


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db)):
    kind = channel_kind(db)
    counts = dict(db.query(Video.status, func.count(Video.id)).filter(Video.kind == kind, Video.parent_id.is_(None))
                  .group_by(Video.status).all())
    snaps = an.latest(db)
    total_views = sum(int(float(s.metrics.get("views", 0))) for s in snaps.values())
    revenue = sum(float(s.metrics.get("estimatedRevenue", 0) or 0) for s in snaps.values())
    in_prod = sum(n for s, n in counts.items() if s not in (
        "published", "scheduled", "awaiting_approval", "failed", "rejected", "needs_review", "approved"))
    recent = db.query(Video).order_by(Video.updated_at.desc()).limit(8).all()
    return {
        "total_created": sum(counts.values()), "in_production": in_prod,
        "awaiting_approval": counts.get("awaiting_approval", 0), "needs_review": counts.get("needs_review", 0),
        "scheduled": counts.get("scheduled", 0), "published": counts.get("published", 0),
        "failed": counts.get("failed", 0) + counts.get("paused_budget", 0),
        "total_views": total_views, "estimated_revenue": round(revenue, 2) if revenue else None,
        "month_spend": round(costs.month_spend(db), 2), "budget": settings_store.get(db, "budget"),
        "shorts": db.query(Video).filter(Video.kind == "short").count(),
        "recent": [video_summary(db, v) for v in recent],
        "next_slots": publish.upcoming_slots(db, 4),
        "format": kind, "publishing_method": publish.method(db),
    }


# ---------------------------------------------------------------- topics
class DiscoverReq(BaseModel):
    n: int = 12
    focus: str = ""


class TopicIn(BaseModel):
    title: str
    format: str = "career_stats"
    players: list[str] = []
    period: str = ""
    category: str = ""
    main_event: str = ""
    why_watch: str = ""
    target_minutes: float = 10


@app.get("/api/topics")
def list_topics(status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Topic)
    if status:
        q = q.filter(Topic.status == status)
    return [topic_dict(t) for t in q.order_by(Topic.score.desc()).limit(200).all()]


@app.post("/api/topics/discover")
def discover(req: DiscoverReq, db: Session = Depends(get_db)):
    j = enqueue(db, "discover_topics", None, {"n": req.n, "focus": req.focus})
    return {"job_id": j.id}


@app.post("/api/topics")
def add_topic(t: TopicIn, db: Session = Depends(get_db)):
    topic = Topic(**t.model_dump(), status="approved", score=0, scores={"manual": True})
    db.add(topic)
    db.commit()
    return {"id": topic.id}


@app.post("/api/topics/{tid}/{action}")
def topic_action(tid: int, action: str, db: Session = Depends(get_db)):
    t = db.get(Topic, tid)
    if not t or action not in ("approve", "reject", "produce"):
        raise HTTPException(404)
    if action == "produce":
        v = new_video(db, t)
        return {"video_id": v.id}
    t.status = "approved" if action == "approve" else "rejected"
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- videos
class GenerateReq(BaseModel):
    topic_id: int | None = None


@app.post("/api/videos/generate")
def generate(req: GenerateReq, db: Session = Depends(get_db)):
    """'Generate New Video': uses the chosen topic, or the highest-scoring approved/suggested one.
    If there are no topics yet, discovery runs first inside the job."""
    t = db.get(Topic, req.topic_id) if req.topic_id else topics.pick_best(db)
    if not t:
        j = enqueue(db, "discover_topics", None, {"n": 12})
        return {"queued_discovery": j.id, "detail": "No topics yet — discovering topics first. Click Generate "
                                                    "again when suggestions appear, or approve one."}
    v = new_video(db, t)
    return {"video_id": v.id, "estimate": v.cost_estimate, "kind": v.kind}


@app.get("/api/estimate")
def estimate(minutes: float | None = None, db: Session = Depends(get_db)):
    if minutes is None and channel_kind(db) == "short":
        return costs.estimate_short(db)
    return costs.estimate_video(db, minutes or 10)


@app.get("/api/videos")
def list_videos(kind: str | None = None, status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Video)
    if kind:
        q = q.filter(Video.kind == kind)
    if status:
        q = q.filter(Video.status.in_(status.split(",")))
    return [video_summary(db, v) for v in q.order_by(Video.id.desc()).limit(500).all()]


@app.get("/api/videos/{vid}")
def video_detail(vid: int, db: Session = Depends(get_db)):
    v = _video_or_404(db, vid)
    base = f"/api/files/{v.id}"

    def rel(p: str) -> str | None:
        if not p:
            return None
        try:
            return f"{base}/{Path(p).relative_to(env.data_dir / 'videos' / str(v.id)).as_posix()}"
        except ValueError:
            return None
    return {
        **video_summary(db, v), "topic": topic_dict(v.topic) if v.topic else None,
        "research": {"bibliography": [s for s in (v.research or {}).get("bibliography", []) if s.get("cited")],
                     "notes": (v.research or {}).get("notes", [])},
        "script": v.script, "fact_check": v.fact_check, "metadata": v.metadata_, "qc_report": v.qc_report,
        "cost_estimate": v.cost_estimate, "costs": costs.breakdown(db, v.id),
        "video_url": rel(v.output_path), "subtitles_url": rel(v.subtitles_path),
        "thumbnails": [{**t, "url": rel(t["path"])} for t in v.thumbnails or []],
        "selected_thumbnail": v.selected_thumbnail,
        "scenes": [{"idx": s.idx, "section": s.section, "narration": s.narration, "visual": s.visual,
                    "on_screen_text": s.on_screen_text, "audio_url": rel(s.audio_path), "image_url": rel(s.image_path),
                    "clip_url": rel(s.clip_path), "duration": s.audio_duration, "start_s": s.start_s}
                   for s in v.scenes],
        "events": [{"at": e.created_at, "stage": e.stage, "level": e.level, "message": e.message}
                   for e in v.events[-200:]],
        "assets": [{"kind": a.kind, "source": a.source, "license": a.license, "commercial_use": a.commercial_use,
                    "ai_generated": a.ai_generated, "url": rel(a.path)}
                   for a in db.query(Asset).filter(Asset.video_id == v.id).all()],
        "shorts": [video_summary(db, s) | {"video_url": rel(s.output_path)} for s in
                   db.query(Video).filter(Video.parent_id == v.id).all()],
        "jobs": [{"id": j.id, "kind": j.kind, "status": j.status, "attempts": j.attempts, "error": j.error[:500]}
                 for j in db.query(Job).filter(Job.video_id == v.id).order_by(Job.id.desc()).limit(10)],
    }


class ApproveReq(BaseModel):
    scheduled_at: datetime | None = None


@app.post("/api/videos/{vid}/approve")
def approve(vid: int, req: ApproveReq, db: Session = Depends(get_db)):
    v = _video_or_404(db, vid)
    if v.status not in ("awaiting_approval",):
        raise HTTPException(400, f"Video is '{v.status}'; only videos awaiting approval can be approved.")
    if not (v.qc_report or {}).get("passed"):
        raise HTTPException(400, "Quality checks have not passed.")
    if publish.method(db) == "youtube_api" and not youtube.connection(db)["connected"]:
        raise HTTPException(400, "Connect your YouTube account first (Settings), or switch publishing method.")
    v.scheduled_at = req.scheduled_at or publish.next_free_slot(db, v.kind)
    set_status(db, v, "approved")
    enqueue(db, "upload", v.id)
    return {"scheduled_at": v.scheduled_at}


@app.post("/api/videos/{vid}/reject")
def reject(vid: int, db: Session = Depends(get_db)):
    v = _video_or_404(db, vid)
    set_status(db, v, "rejected")
    return {"ok": True}


@app.post("/api/videos/{vid}/retry")
def retry(vid: int, db: Session = Depends(get_db)):
    v = _video_or_404(db, vid)
    if v.status == "approved" and v.upload_status.startswith("failed"):
        v.upload_status = ""
        db.commit()
        enqueue(db, "upload", v.id)
        return {"ok": True, "job": "upload"}
    if v.status not in ("failed", "paused_budget", "needs_review"):
        raise HTTPException(400, f"Nothing to retry for status '{v.status}'.")
    if v.status == "needs_review" and (v.fact_check or {}).get("passed"):
        v.status = "editing"           # re-run render/QC only (assets are cached)
    else:
        v.status = "failed"
    db.query(Job).filter(Job.video_id == v.id, Job.status == "paused").update({"status": "failed"})
    db.commit()
    enqueue(db, "produce", v.id)
    return {"ok": True, "job": "produce"}


class MetaPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    playlist: str | None = None


@app.patch("/api/videos/{vid}/metadata")
def patch_meta(vid: int, m: MetaPatch, db: Session = Depends(get_db)):
    v = _video_or_404(db, vid)
    if v.youtube_id:
        raise HTTPException(400, "Already uploaded; edit on YouTube Studio.")
    v.metadata_ = {**(v.metadata_ or {}), **{k: val for k, val in m.model_dump().items() if val is not None}}
    flag_modified(v, "metadata_")
    db.commit()
    return v.metadata_


class ThumbReq(BaseModel):
    index: int


@app.post("/api/videos/{vid}/thumbnail")
def pick_thumb(vid: int, req: ThumbReq, db: Session = Depends(get_db)):
    v = _video_or_404(db, vid)
    if not (0 <= req.index < len(v.thumbnails or [])):
        raise HTTPException(400, "bad index")
    v.selected_thumbnail = req.index
    db.commit()
    return {"ok": True}


@app.get("/api/files/{vid}/{path:path}")
def files(vid: int, path: str):
    base = (env.data_dir / "videos" / str(vid)).resolve()
    f = (base / path).resolve()
    if not str(f).startswith(str(base)) or not f.is_file():
        raise HTTPException(404)
    return FileResponse(f)


# ---------------------------------------------------------------- pipeline / jobs / calendar
@app.get("/api/pipeline")
def pipeline(db: Session = Depends(get_db)):
    vids = db.query(Video).filter(Video.kind == channel_kind(db), Video.parent_id.is_(None)) \
        .order_by(Video.updated_at.desc()).limit(300).all()
    out: dict[str, list] = {}
    for v in vids:
        out.setdefault(v.status, []).append(video_summary(db, v))
    jobs = db.query(Job).order_by(Job.id.desc()).limit(30).all()
    return {"columns": out, "jobs": [{"id": j.id, "kind": j.kind, "video_id": j.video_id, "status": j.status,
                                      "attempts": j.attempts, "error": j.error[:300], "created_at": j.created_at}
                                     for j in jobs]}


@app.get("/api/calendar")
def calendar(db: Session = Depends(get_db)):
    vids = db.query(Video).filter(Video.scheduled_at.isnot(None)).order_by(Video.scheduled_at).all()
    return {"slots": publish.upcoming_slots(db, 12), "items": [video_summary(db, v) for v in vids]}


# ---------------------------------------------------------------- analytics & costs
@app.get("/api/analytics")
def analytics_view(db: Session = Depends(get_db)):
    snaps = an.latest(db)
    rows = []
    for v in db.query(Video).filter(Video.id.in_(list(snaps))).all():
        s = snaps[v.id]
        rows.append({**video_summary(db, v), "metrics": s.metrics, "retention": s.retention,
                     "score": an.composite_score(s.metrics, v.duration_s), "drop_offs": an.drop_offs(s.retention),
                     "category": v.topic.category if v.topic else ""})
    history = db.query(AnalyticsSnapshot.day, func.count(AnalyticsSnapshot.id)).group_by(AnalyticsSnapshot.day).all()
    trend = []
    for day, _ in sorted(history):
        day_rows = db.query(AnalyticsSnapshot).filter(AnalyticsSnapshot.day == day).all()
        trend.append({"day": day, "views": sum(int(float(r.metrics.get("views", 0))) for r in day_rows),
                      "minutes": sum(float(r.metrics.get("estimatedMinutesWatched", 0)) for r in day_rows)})
    ins = db.query(Insight).order_by(Insight.id.desc()).first()
    return {"videos": rows, "trend": trend, "insights": ins.summary if ins else None}


@app.post("/api/analytics/sync")
def analytics_sync(db: Session = Depends(get_db)):
    return {"job_id": enqueue(db, "sync_analytics").id}


@app.get("/api/costs")
def cost_view(db: Session = Depends(get_db)):
    start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    by_cat = db.query(CostEntry.category, func.sum(CostEntry.usd)).filter(CostEntry.created_at >= start) \
        .group_by(CostEntry.category).all()
    by_provider = db.query(CostEntry.provider, func.sum(CostEntry.usd), func.count(CostEntry.id)) \
        .filter(CostEntry.created_at >= start).group_by(CostEntry.provider).all()
    return {"month_total": round(costs.month_spend(db), 2), "budget": settings_store.get(db, "budget"),
            "by_category": {c: round(float(u), 3) for c, u in by_cat},
            "by_provider": [{"provider": p, "usd": round(float(u), 3), "calls": n} for p, u, n in by_provider]}


# ---------------------------------------------------------------- settings
@app.get("/api/settings")
def get_settings(db: Session = Depends(get_db)):
    return settings_store.get_all(db)


@app.put("/api/settings/{section}")
def put_settings(section: str, value: dict, db: Session = Depends(get_db)):
    if section == "schedule" and value.get("approval_mode") not in (None, "manual", "auto"):
        raise HTTPException(400, "approval_mode must be manual or auto")
    try:
        return settings_store.update(db, section, value)
    except KeyError:
        raise HTTPException(404, "unknown settings section")


# ---------------------------------------------------------------- YouTube OAuth
@app.get("/api/youtube/connect")
def yt_connect(db: Session = Depends(get_db)):
    try:
        url, state, verifier = youtube.auth_url()
    except youtube.YouTubeError as e:
        raise HTTPException(400, str(e))
    row = db.get(Setting, "_oauth") or Setting(key="_oauth", value={})
    row.value = {"state": state, "verifier": verifier, "at": datetime.now(timezone.utc).isoformat()}
    db.merge(row)
    db.commit()
    return {"url": url}


@app.get("/api/youtube/oauth/callback")
def yt_callback(code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)):
    row = db.get(Setting, "_oauth")
    if error:
        return RedirectResponse(f"{env.frontend_url}/settings?youtube=error&reason={error}")
    if not row or row.value.get("state") != state or \
            datetime.now(timezone.utc) - datetime.fromisoformat(row.value["at"]) > timedelta(minutes=15):
        raise HTTPException(400, "OAuth state mismatch or expired; start the connection again.")
    label = youtube.finish_auth(db, code, state, row.value.get("verifier"))
    db.delete(row)
    db.commit()
    return RedirectResponse(f"{env.frontend_url}/settings?youtube=connected&channel={label}")


@app.post("/api/youtube/disconnect")
def yt_disconnect(db: Session = Depends(get_db)):
    youtube.disconnect(db)
    return {"ok": True}


# ---------------------------------------------------------------- meme studio
MEME_SCHEMA = {"type": "object", "properties": {"memes": {"type": "array", "items": {"type": "object", "properties": {
    "template": {"type": "string", "enum": ["top_bottom", "reaction", "punchline"]},
    "top_text": {"type": "string"}, "bottom_text": {"type": "string"},
    "caption": {"type": "string", "description": "reaction template: 'POV: …' / 'When …' caption"},
    "image_prompt": {"type": "string", "description": "ORIGINAL cartoon scene with fictional generic players; no real "
                     "people, names, logos"},
    "why_funny": {"type": "string"}, "based_on": {"type": "string"}},
    "required": ["template", "image_prompt", "why_funny"]}}}, "required": ["memes"]}

TEMPLATES = [
    {"id": "top_bottom", "name": "Top / bottom text", "example": "ME AFTER HITTING ONE THREE / THINKING I'M THE GOAT"},
    {"id": "reaction", "name": "POV / reaction caption", "example": "POV: your teammate says he can guard anyone"},
    {"id": "punchline", "name": "Punchline card", "example": "HE WAS NOT READY"},
]


class MemeIdeasReq(BaseModel):
    topic: str = ""
    n: int = 6


def meme_dict(m: Meme) -> dict:
    return {"id": m.id, "idea": m.idea, "status": m.status, "video_id": m.video_id, "created_at": m.created_at,
            "image_url": f"/api/memes/{m.id}/image" if m.image_path else None}


@app.get("/api/memes/templates")
def meme_templates():
    return TEMPLATES


@app.get("/api/memes")
def list_memes(db: Session = Depends(get_db)):
    return [meme_dict(m) for m in db.query(Meme).filter(Meme.status != "rejected").order_by(Meme.id.desc()).limit(100)]


@app.post("/api/memes/ideas")
def meme_ideas(req: MemeIdeasReq, db: Session = Depends(get_db)):
    from .providers import llm
    ctx = ""
    try:
        from .providers import news
        ctx = "\n".join(f"- {h['title']}" for h in news.headlines(10)[:20])
    except Exception:
        pass
    res = llm.structured(
        db, video_id=None, category="script", tool_name="submit_memes", schema=MEME_SCHEMA, est_usd=0.05,
        note="meme ideas",
        system=("You write ORIGINAL basketball memes for young fans: relatable hooper humour (pickup, rec league, "
                "fans, game situations). Never copy known meme templates' images, never use real people's likeness, "
                "never invent quotes or stats. Short text that reads in 2 seconds."),
        prompt=f"Topic/angle: {req.topic or 'anything funny in basketball right now'}\nCurrent headlines (for "
               f"timeliness, don't state them as fact unless they are the joke's premise):\n{ctx}\n\n"
               f"Write {max(1, min(12, req.n))} memes across the templates.")
    out = []
    for m in res["memes"]:
        row = Meme(idea=m, status="idea")
        db.add(row)
        out.append(row)
    db.commit()
    return [meme_dict(m) for m in out]


@app.post("/api/memes/{mid}/render")
def meme_render(mid: int, db: Session = Depends(get_db)):
    from .pipeline import cards
    from .providers import cfai, fal
    m = db.get(Meme, mid)
    if not m:
        raise HTTPException(404)
    d = env.data_dir / "memes"
    d.mkdir(parents=True, exist_ok=True)
    i = m.idea
    raw, out = d / f"meme_{m.id}_raw.png", d / f"meme_{m.id}.png"
    gen = cfai.generate_image if settings_store.get(db, "ai")["image_provider"] == "cloudflare" else fal.generate_image
    if i.get("template") != "punchline":
        prompt = (i["image_prompt"] + ". " + settings_store.get(db, "video")["art_style"] +
                  ". fictional generic characters (not real people), no team logos, no text")
        try:
            gen(db, None, prompt, raw, width=1024, height=1024, seed=m.id)
        except Exception as e:
            raise HTTPException(502, f"Image generation failed: {e}")
    if i.get("template") == "reaction":
        cards.reaction_card(str(raw), i.get("caption") or i.get("top_text", ""), out)
    elif i.get("template") == "punchline":
        cards.big_text_card(i.get("top_text") or i.get("caption") or "", out)
    else:
        cards.meme_card(str(raw), i.get("top_text", ""), i.get("bottom_text", ""), out)
    m.image_path, m.status = str(out), "rendered"
    db.commit()
    return meme_dict(m)


@app.get("/api/memes/{mid}/image")
def meme_image(mid: int, db: Session = Depends(get_db)):
    m = db.get(Meme, mid)
    if not m or not m.image_path:
        raise HTTPException(404)
    return FileResponse(m.image_path)


@app.post("/api/memes/{mid}/video")
def meme_to_video(mid: int, db: Session = Depends(get_db)):
    m = db.get(Meme, mid)
    if not m:
        raise HTTPException(404)
    i = m.idea
    t = Topic(title=(i.get("top_text") or i.get("caption") or "Basketball meme")[:200], format="meme",
              category="NBA memes", why_watch=i.get("why_funny", ""),
              main_event=f"Build a short meme video around this meme (keep its joke, escalate it): {llm_json(i)}",
              target_minutes=0.4, status="approved", score=0, scores={"from_meme_studio": True})
    db.add(t)
    db.commit()
    v = new_video(db, t)
    m.status, m.video_id = "video", v.id
    db.commit()
    return {"video_id": v.id}


@app.post("/api/memes/{mid}/reject")
def meme_reject(mid: int, db: Session = Depends(get_db)):
    m = db.get(Meme, mid)
    if m:
        m.status = "rejected"
        db.commit()
    return {"ok": True}


def llm_json(o) -> str:
    import json
    return json.dumps(o, ensure_ascii=False)


# ---------------------------------------------------------------- user clips (footage you have rights to)
from fastapi import File, Form, UploadFile  # noqa: E402


@app.get("/api/clips")
def list_clips(db: Session = Depends(get_db)):
    return [{"id": c.id, "title": c.title, "description": c.description, "source": c.source, "license": c.license,
             "duration_s": c.duration_s, "url": f"/api/clips/{c.id}/file", "created_at": c.created_at}
            for c in db.query(Clip).order_by(Clip.id.desc())]


@app.post("/api/clips")
async def upload_clip(file: UploadFile = File(...), title: str = Form(...), description: str = Form(""),
                      source: str = Form(...), license: str = Form(...), attest: bool = Form(False),
                      db: Session = Depends(get_db)):
    from . import media
    if not attest:
        raise HTTPException(400, "You must confirm you own this footage or have permission to use it.")
    low = (source + " " + license + " " + title).lower()
    if any(w in low for w in ("nba.com", "espn", "tnt", "broadcast", "house of highlights", "downloaded from youtube")):
        raise HTTPException(400, "That looks like broadcast or another creator's footage. Only upload clips you "
                                 "shot yourself or licensed for reuse.")
    d = env.data_dir / "clips"
    d.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "clip.mp4").suffix.lower() or ".mp4"
    if ext not in (".mp4", ".mov", ".m4v", ".webm", ".mkv"):
        raise HTTPException(400, "Upload a video file (mp4, mov, webm, mkv).")
    c = Clip(path="", title=title[:200], description=description, source=source[:300], license=license[:300],
             attested_by_user=True)
    db.add(c)
    db.commit()
    dest = d / f"clip_{c.id}{ext}"
    with open(dest, "wb") as fh:
        while chunk := await file.read(1024 * 1024):
            fh.write(chunk)
    try:
        c.duration_s = media.duration(dest)
    except Exception:
        dest.unlink(missing_ok=True)
        db.delete(c)
        db.commit()
        raise HTTPException(400, "Could not read that video file.")
    c.path = str(dest)
    db.commit()
    return {"id": c.id, "duration_s": c.duration_s}


@app.get("/api/clips/{cid}/file")
def clip_file(cid: int, db: Session = Depends(get_db)):
    c = db.get(Clip, cid)
    if not c or not Path(c.path).exists():
        raise HTTPException(404)
    return FileResponse(c.path)


@app.delete("/api/clips/{cid}")
def delete_clip(cid: int, db: Session = Depends(get_db)):
    c = db.get(Clip, cid)
    if c:
        Path(c.path).unlink(missing_ok=True)
        db.delete(c)
        db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- no-API publishing
def _feed_guard(db: Session, key: str) -> None:
    import secrets
    if not secrets.compare_digest(key, settings_store.get(db, "publishing")["feed_key"]):
        raise HTTPException(404)


@app.get("/feed/{key}/videos.xml")
def publish_feed(key: str, db: Session = Depends(get_db)):
    """RSS feed for Zapier. An item appears only once its scheduled time has arrived."""
    from email.utils import format_datetime
    from xml.sax.saxutils import escape
    _feed_guard(db, key)
    base = env.public_base_url.rstrip("/")
    items = []
    for v in publish.released(db):
        md = v.metadata_ or {}
        media_url = f"{base}/feed/{key}/media/{v.id}.mp4"
        size = Path(v.output_path).stat().st_size if v.output_path and Path(v.output_path).exists() else 0
        items.append(
            f"<item><title>{escape(md.get('title', v.working_title))}</title>"
            f"<link>{escape(media_url)}</link><guid isPermaLink=\"false\">chronicle-video-{v.id}</guid>"
            f"<pubDate>{format_datetime(publish._utc(v.scheduled_at))}</pubDate>"
            f"<description>{escape(md.get('description', ''))}</description>"
            + "".join(f"<category>{escape(t)}</category>" for t in md.get("tags", [])[:15]) +
            f"<enclosure url=\"{escape(media_url)}\" length=\"{size}\" type=\"video/mp4\"/></item>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Chronicle publishing queue'
           f'</title><link>{escape(base)}</link><description>Videos due for upload</description>'
           + "".join(items) + "</channel></rss>")
    return Response(xml, media_type="application/rss+xml")


@app.get("/feed/{key}/media/{vid}.mp4")
def publish_media(key: str, vid: int, db: Session = Depends(get_db)):
    _feed_guard(db, key)
    v = db.get(Video, vid)
    if not v or v not in publish.released(db, limit=200) or not Path(v.output_path).exists():
        raise HTTPException(404)
    return FileResponse(v.output_path, media_type="video/mp4", filename=f"video-{vid}.mp4")


@app.get("/api/publishing/export")
def export_pack(days: int = 7, db: Session = Depends(get_db)):
    """Weekly pack for manual scheduling in YouTube Studio: MP4s + schedule.csv (+ descriptions)."""
    import csv
    import io
    import tempfile
    import zipfile
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(settings_store.get(db, "schedule")["timezone"])
    now = datetime.now(timezone.utc)
    vids = [v for v in db.query(Video).filter(Video.status == "scheduled", Video.scheduled_at.isnot(None)).all()
            if now - timedelta(hours=1) <= publish._utc(v.scheduled_at) <= now + timedelta(days=days)]
    vids.sort(key=lambda v: v.scheduled_at)
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["file", "publish_at_local", "timezone", "title", "tags", "description_file"])
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_STORED) as z:
        for i, v in enumerate(vids, 1):
            md = v.metadata_ or {}
            when = publish._utc(v.scheduled_at).astimezone(tz)
            name = f"{i:02d}_{when:%a_%m-%d_%H%M}"
            z.write(v.output_path, f"{name}.mp4")
            z.writestr(f"{name}_description.txt", md.get("description", ""))
            pc = md.get("platform_captions") or {}
            if pc:
                z.writestr(f"{name}_other_platforms.txt", "\n\n".join(
                    f"=== {k.upper()} ===\n{v}" for k, v in pc.items()))
            w.writerow([f"{name}.mp4", when.strftime("%Y-%m-%d %H:%M"), str(tz), md.get("title", ""),
                        ", ".join(md.get("tags", [])), f"{name}_description.txt"])
        z.writestr("schedule.csv", buf.getvalue())
        z.writestr("HOW_TO_SCHEDULE.txt",
                   "In YouTube Studio: Create → Upload videos → select all MP4s. For each one: paste the title and "
                   "description from schedule.csv / the _description file, choose 'No, it's not made for kids', "
                   "under 'Altered content' choose YES (AI-generated visuals), then Visibility → Schedule → "
                   "set the date/time from schedule.csv.\n")
    return FileResponse(tmp.name, media_type="application/zip",
                        filename=f"shorts-pack-{now:%Y-%m-%d}.zip")


# ---------------------------------------------------------------- frontend
_dist = ROOT / "frontend" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        f = _dist / full_path
        return FileResponse(f if full_path and f.is_file() else _dist / "index.html")
