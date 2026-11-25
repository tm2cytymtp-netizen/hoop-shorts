"""Production state machine. Each stage is idempotent and checkpointed, so a crashed or
paused job resumes where it stopped without paying twice for finished assets."""
from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from . import costs, settings_store
from .events import emit, set_status
from .models import PRODUCTION_STAGES, Asset, Job, Topic, Video, VideoStatus as S
from .notify import notify
from .pipeline import (edit, factcheck, metadata, narration, qc, research, script, shorts, thumbnails, topics,
                       visuals)


def enqueue(db: Session, kind: str, video_id: int | None = None, payload: dict | None = None) -> Job:
    existing = db.query(Job).filter(Job.kind == kind, Job.video_id == video_id,
                                    Job.status.in_(["pending", "running"])).first()
    if existing:
        return existing
    j = Job(kind=kind, video_id=video_id, payload=payload or {})
    db.add(j)
    db.commit()
    return j


def channel_kind(db: Session) -> str:
    return "short" if settings_store.get(db, "channel").get("format") == "shorts" else "long"


def new_video(db: Session, topic: Topic | None = None, title: str = "", kind: str | None = None) -> Video:
    kind = kind or channel_kind(db)
    v = Video(kind=kind, topic_id=topic.id if topic else None,
              working_title=title or (topic.title if topic else "Untitled"))
    if topic:
        topic.status = "used"
    db.add(v)
    db.commit()
    v.cost_estimate = costs.estimate_short(db) if kind == "short" else \
        costs.estimate_video(db, topic.target_minutes if topic else 10)
    db.commit()
    enqueue(db, "produce", v.id)
    return v


def _done(video: Video, stage: S) -> bool:
    """True if the video has already moved past `stage`."""
    try:
        return PRODUCTION_STAGES.index(S(video.status)) > PRODUCTION_STAGES.index(stage)
    except ValueError:
        return False


def produce(db: Session, video: Video) -> None:
    if video.status in (S.QUEUED.value, S.PAUSED_BUDGET.value, S.FAILED.value):
        # Resume at the furthest stage that has data; otherwise start at research.
        video.status = (S.RESEARCHING if not video.research else S.SCRIPTING if not video.script else
                        S.FACT_CHECKING if not video.fact_check.get("passed") else S.NARRATING).value
        db.commit()
    budget = settings_store.get(db, "budget")
    est = video.cost_estimate or costs.estimate_video(db, 10)
    if est.get("total", 0) > budget["max_per_video_usd"]:
        raise costs.BudgetExceeded(f"Estimated cost ${est['total']:.2f} exceeds the per-video limit "
                                   f"${budget['max_per_video_usd']:.2f}. Raise the limit or reduce animated scenes.")

    if not _done(video, S.RESEARCHING):
        set_status(db, video, S.RESEARCHING.value)
        if not video.research:
            video.research = research.run(db, video)
            db.commit()

    if not _done(video, S.SCRIPTING):
        set_status(db, video, S.SCRIPTING.value)
        if not video.script:
            sc = script.generate(db, video)
            script.save_scenes(db, video, sc)
            emit(db, video, f"Script: {script.word_count(sc)} words, {len(sc['scenes'])} scenes")

    if not _done(video, S.FACT_CHECKING):
        set_status(db, video, S.FACT_CHECKING.value)
        for attempt in range(3):
            report = factcheck.run(db, video)
            flag_modified(video, "research")
            video.fact_check = report
            db.commit()
            emit(db, video, f"Fact-check: {report['supported']}/{report['claims']} supported, "
                            f"{report['blocking']} blocking issues")
            if report["passed"]:
                break
            if attempt == 2:
                set_status(db, video, S.NEEDS_REVIEW.value)
                notify("Fact-check needs your review", f"{video.working_title}: {report['blocking']} unresolved "
                                                       "issues after 2 revisions. Production stopped before any "
                                                       "media spend.")
                return
            emit(db, video, "Revising script to fix fact-check issues")
            sc = script.generate(db, video, revision_notes=factcheck.revision_notes(report))
            script.save_scenes(db, video, sc)

    if not _done(video, S.NARRATING):
        set_status(db, video, S.NARRATING.value)
        narration.run(db, video)
        if video.kind == "short":
            fit_short(db, video)

    vs = settings_store.get(db, "video")
    if not _done(video, S.GENERATING_VISUALS):
        set_status(db, video, S.GENERATING_VISUALS.value)
        visuals.generate_images(db, video)
        visuals.render_procedural(db, video, float(vs["transition_s"]), int(vs["fps"]))

    if not _done(video, S.ANIMATING):
        set_status(db, video, S.ANIMATING.value)
        visuals.animate(db, video)

    if not _done(video, S.RENDERING):
        set_status(db, video, S.EDITING.value)
        edit.run(db, video, stage_cb=lambda st: set_status(db, video, S.RENDERING.value))

    set_status(db, video, S.QUALITY_CHECK.value)
    credits = sorted({a.source for a in db.query(Asset).filter(Asset.video_id == video.id,
                                                              Asset.kind.in_(["music", "artwork"]))})
    metadata.run(db, video, credits)
    if not video.thumbnails and video.kind == "long":
        thumbnails.run(db, video)
    if video.kind == "short" and not video.thumbnails:
        make_cover(db, video)
    report = qc.run(db, video)
    video.qc_report = report
    db.commit()
    failed = [c for c in report["checks"] if c["blocking"] and not c["passed"]]
    if not report["passed"]:
        set_status(db, video, S.NEEDS_REVIEW.value)
        notify("Video needs review", f"{video.working_title}: failed checks — " +
               ", ".join(c["check"] for c in failed))
        return
    sch = settings_store.get(db, "schedule")
    if sch["approval_mode"] == "auto":
        set_status(db, video, S.APPROVED.value)
        enqueue(db, "upload", video.id)
    else:
        set_status(db, video, S.AWAITING_APPROVAL.value)
        notify("Video ready for review", f"{video.working_title} ({video.duration_s / 60:.1f} min, "
                                         f"${costs.video_spend(db, video.id):.2f}) passed all checks.")
    if sch.get("auto_shorts") and video.kind == "long":
        enqueue(db, "shorts", video.id)


KEEP_SCHEMA = {"type": "object", "properties": {"keep": {"type": "array", "items": {"type": "integer"}}},
               "required": ["keep"]}


def fit_short(db: Session, video: Video) -> None:
    """If narration runs past the Shorts limit, drop the least essential scenes (already fact-checked text,
    so nothing new needs verifying) instead of speeding up the voice."""
    from .pipeline.visuals import LEAD_PAD, TAIL_PAD
    mx = settings_store.get(db, "shorts")["max_seconds"] - 1.5
    length = lambda scs: sum(LEAD_PAD + s.audio_duration + TAIL_PAD for s in scs)   # noqa: E731
    if length(video.scenes) <= mx:
        return
    res = structured_keep(db, video, mx)
    keep = [s for s in video.scenes if s.idx in set(res)] or video.scenes
    while length(keep) > mx and len(keep) > 3:
        keep.pop(-2)                      # keep the hook and the final payoff line
    kept_idx = [s.idx for s in keep]
    old_scenes = video.script.get("scenes", [])
    for s in list(video.scenes):
        if s not in keep:
            video.scenes.remove(s)
    for i, s in enumerate(video.scenes):
        s.idx = i
    video.script = {**video.script, "scenes": [old_scenes[i] for i in kept_idx if i < len(old_scenes)]}
    db.commit()
    emit(db, video, f"Trimmed to {len(video.scenes)} scenes ({length(video.scenes):.1f}s) to fit the Shorts limit")


def structured_keep(db: Session, video: Video, mx: float) -> list[int]:
    from .providers import llm
    lines = "\n".join(f"{s.idx} ({s.audio_duration:.1f}s) {s.narration}" for s in video.scenes)
    r = llm.structured(db, video_id=video.id, category="script", tool_name="submit_keep", schema=KEEP_SCHEMA,
                       fast=True, est_usd=0.01, note="fit short length",
                       system="You edit YouTube Shorts. Keep the hook (first scene) and the payoff (last scene).",
                       prompt=f"Choose scene indices to KEEP so the total is under {mx:.0f}s (each scene adds ~0.6s "
                              f"of padding) and the story still makes sense:\n{lines}")
    return sorted(set(r["keep"]))


def make_cover(db: Session, video: Video) -> None:
    """Cover options for Shorts: frames from the hook and the punchline (YouTube picks Shorts covers from frames)."""
    from . import media
    from .events import video_dir
    d = video_dir(video.id) / "thumbs"
    picks = []
    for label, sc in (("Hook", video.scenes[0]), ("Punchline", video.scenes[-1])):
        t = sc.start_s + min(1.0, sc.audio_duration / 2)
        out = d / f"cover_{label.lower()}.jpg"
        try:
            media.run(["-ss", f"{t:.2f}", "-i", video.output_path, "-frames:v", "1", "-q:v", "3", str(out)])
            picks.append({"path": str(out), "concept": {"idea": f"{label} frame"}, "score": None})
        except Exception:
            continue
    video.thumbnails = picks
    video.selected_thumbnail = 0 if picks else None
    db.commit()


def make_shorts(db: Session, video: Video) -> None:
    made = shorts.run(db, video)
    sch = settings_store.get(db, "schedule")
    for s in made:
        if sch.get("shorts_upload") and sch["approval_mode"] == "auto" and s.status == "awaiting_approval":
            s.status = "approved"
            db.commit()
            enqueue(db, "upload", s.id)


def auto_fill_schedule(db: Session) -> list[Video]:
    """Start productions so every slot inside the lead window has a video."""
    from datetime import datetime, timedelta, timezone

    from .pipeline.publish import upcoming_slots
    sch = settings_store.get(db, "schedule")
    if not sch.get("auto_produce"):
        return []
    kind = channel_kind(db)
    lead = 2 if kind == "short" else int(sch["lead_days"]) + 3
    horizon = datetime.now(timezone.utc) + timedelta(days=lead)
    slots = [s for s in upcoming_slots(db, 30, kind=kind) if s <= horizon]
    active = db.query(Video).filter(Video.kind == kind, Video.parent_id.is_(None), Video.status.notin_(
        ["published", "failed", "rejected", "needs_review", "scheduled", "paused_budget"])).count()
    scheduled_future = db.query(Video).filter(Video.kind == kind, Video.status == "scheduled",
                                              Video.scheduled_at >= datetime.now(timezone.utc)).count()
    need = len(slots) - active - scheduled_future
    # Don't pile up work if something is stuck: at most 2 productions running at once.
    need = min(need, 2 - active)
    started = []
    for _ in range(max(0, need)):
        if db.query(Topic).filter(Topic.status.in_(["suggested", "approved"])).count() < 3:
            topics.discover(db)
        t = topics.pick_best(db)
        if not t:
            break
        started.append(new_video(db, t))
    return started
