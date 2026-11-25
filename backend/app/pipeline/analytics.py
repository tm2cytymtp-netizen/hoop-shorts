"""Analytics sync and performance learning (never optimises on views alone)."""
from __future__ import annotations

from datetime import date, timedelta
from statistics import mean

from sqlalchemy.orm import Session

from ..models import AnalyticsSnapshot, Insight, Video
from ..providers import llm, youtube

INSIGHT_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {"type": "array", "items": {"type": "string"}},
        "recommendations": {"type": "array", "items": {"type": "string"},
                            "description": "Concrete changes for future topics, hooks, length, thumbnails"},
        "best_categories": {"type": "array", "items": {"type": "string"}},
        "hook_advice": {"type": "string"}},
    "required": ["findings", "recommendations", "best_categories", "hook_advice"],
}


def sync(db: Session) -> int:
    vids = db.query(Video).filter(Video.youtube_id != "", Video.status == "published").all()
    if not vids:
        return 0
    end = date.today()
    start = end - timedelta(days=365)
    data = youtube.analytics_for_videos(db, [v.youtube_id for v in vids], start, end)
    for v in vids:
        m = data.get(v.youtube_id)
        if not m:
            continue
        ret = youtube.retention_curve(db, v.youtube_id, start, end) if v.kind == "long" else []
        db.add(AnalyticsSnapshot(video_id=v.id, youtube_id=v.youtube_id, day=end.isoformat(), metrics=m,
                                 retention=ret))
    db.commit()
    return len(data)


def latest(db: Session) -> dict[int, AnalyticsSnapshot]:
    out = {}
    for s in db.query(AnalyticsSnapshot).order_by(AnalyticsSnapshot.id).all():
        out[s.video_id] = s
    return out


def composite_score(m: dict, duration_s: float) -> float:
    """Blend of reach and satisfaction: CTR, retention, watch time and subscriber conversion."""
    views = float(m.get("views", 0)) or 0
    if m.get("source") == "public_feed":   # only views & likes are public
        import math as _m
        return round(0.6 * min(10, _m.log10(views + 1) * 2.5) + 0.4 * min(10, float(m.get("likes", 0)) /
                                                                         max(1, views) * 250), 2)
    avp = float(m.get("averageViewPercentage", 0))
    ctr = float(m.get("videoThumbnailImpressionsClickRate", 0) or 0)
    subs = float(m.get("subscribersGained", 0)) - float(m.get("subscribersLost", 0))
    minutes = float(m.get("estimatedMinutesWatched", 0))
    import math
    return round(0.25 * min(10, math.log10(views + 1) * 2.5) + 0.3 * avp / 10 + 0.2 * min(10, ctr) +
                 0.15 * min(10, subs / max(1, views) * 1000 / 2) + 0.1 * min(10, math.log10(minutes + 1) * 2), 2)


def drop_offs(retention: list) -> list[dict]:
    """Largest relative drops in the retention curve (ratio of video elapsed)."""
    drops = []
    for (r0, w0, _), (r1, w1, _) in zip(retention, retention[1:]):
        if w0 > 0:
            drops.append({"at": round(r1, 3), "drop": round((w0 - w1) / w0, 3)})
    return sorted(drops, key=lambda d: -d["drop"])[:3]


def learn(db: Session) -> Insight | None:
    snaps = latest(db)
    rows = []
    for v in db.query(Video).filter(Video.id.in_(list(snaps))).all():
        s = snaps[v.id]
        first_scene = v.scenes[0].narration if v.scenes else (v.script or {}).get("hook", "")
        rows.append({
            "title": (v.metadata_ or {}).get("title"), "kind": v.kind, "category": v.topic.category if v.topic else "",
            "minutes": round(v.duration_s / 60, 1), "hook": first_scene,
            "thumbnail_text": (v.thumbnails[v.selected_thumbnail]["concept"]["text"]
                               if v.thumbnails and v.selected_thumbnail is not None else ""),
            "metrics": s.metrics, "score": composite_score(s.metrics, v.duration_s),
            "drop_offs": drop_offs(s.retention)})
    if len(rows) < 3:
        return None
    res = llm.structured(
        db, video_id=None, category="research", tool_name="submit_insights", schema=INSIGHT_SCHEMA, fast=True,
        est_usd=0.05, note="analytics insights",
        system=("You analyse YouTube performance for a history channel. Weigh CTR, average view percentage, "
                "retention drop-offs, subscriber conversion and watch time together when available. If only "
                "public views and likes exist (source=public_feed), use like rate and views relative to video age, "
                "and say clearly that the conclusions are tentative. Distinguish Shorts from long-form. Be specific "
                "and evidence-based; say when data is thin."),
        prompt=llm.to_json(rows) + f"\n\nChannel average composite score: {mean(r['score'] for r in rows):.2f}")
    ins = Insight(summary=res)
    db.add(ins)
    db.commit()
    return ins
