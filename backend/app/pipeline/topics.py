"""Daily basketball trend discovery and idea scoring."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from .. import settings_store
from ..models import Insight, Topic, Video
from ..providers import llm, youtube

log = logging.getLogger("topics")

CRITERIA = ["current_popularity", "audience_interest", "entertainment", "relevance", "originality", "timeliness"]
WEIGHTS = {"current_popularity": 0.2, "audience_interest": 0.2, "entertainment": 0.25, "relevance": 0.1,
           "originality": 0.15, "timeliness": 0.1}

TOPIC_SCHEMA = {
    "type": "object",
    "properties": {"ideas": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Working title, <= 60 chars, honest"},
            "format": {"type": "string", "enum": ["career_stats", "comparison", "recap", "fact", "storyline",
                                                  "ranking", "news_reaction", "meme", "hypothetical"]},
            "players": {"type": "array", "items": {"type": "string"},
                        "description": "Exact full names (as on Wikipedia) of the players whose stats are needed"},
            "category": {"type": "string"},
            "angle": {"type": "string", "description": "The joke or the hook — why people will watch/share"},
            "context": {"type": "string", "description": "The real event/stat/trend it's based on, and its date"},
            "based_on": {"type": "array", "items": {"type": "string"},
                         "description": "Headline links / data ids from the inputs this idea relies on"},
            "scores": {"type": "object", "properties": {k: {"type": "number"} for k in CRITERIA},
                       "required": CRITERIA},
        },
        "required": ["title", "format", "category", "angle", "context", "scores"]}}},
    "required": ["ideas"],
}


def overall(scores: dict) -> float:
    return round(sum(scores.get(k, 0) * w for k, w in WEIGHTS.items()), 2)


def discover(db: Session, n: int = 15, focus: str = "") -> list[Topic]:
    from ..providers import bdl, news, wiki
    ch = settings_store.get(db, "channel")
    signals = []
    heads = []
    try:
        heads = news.headlines(20)
        signals.append("NBA HEADLINES (leads only — verify before using as fact):\n" + "\n".join(
            f"- [{h['published']}] {h['title']} ({h['feed']}) {h['link']}" for h in heads[:45]))
    except Exception as e:
        log.info("news unavailable: %s", e)
    try:
        games = bdl.final_games(2)
        signals.append("FINAL SCORES (last 2 days, BALLDONTLIE):\n" + "\n".join(
            f"- {g['date']}: {g['away']} {g['away_score']} @ {g['home']} {g['home_score']}" for g in games))
    except Exception as e:
        log.info("scores unavailable: %s", e)
    try:
        pop = []
        for q in ["nba shorts", "nba memes", "basketball funny", focus or "nba highlights reaction"]:
            pop += youtube.search_popular(db, q, max_results=10, days=7, duration="short")
        signals.append("MOST-VIEWED BASKETBALL SHORTS THIS WEEK (study the angles; never copy):\n" + "\n".join(
            f"- {p['title']} — {p['channel']} ({p['views']:,} views)" for p in sorted(pop, key=lambda p: -p["views"])[:30]))
    except Exception as e:
        log.info("YouTube trend search unavailable: %s", e)
    try:
        anniv = [a for a in wiki.on_this_day(5) if any(w in a.lower() for w in ("nba", "basketball", "slam dunk"))]
        if anniv:
            signals.append("BASKETBALL ANNIVERSARIES:\n" + "\n".join(anniv))
    except Exception:
        pass
    done = [v.working_title for v in db.query(Video).order_by(Video.id.desc()).limit(150)]
    pending = [t.title for t in db.query(Topic).filter(Topic.status.in_(["suggested", "approved"]))]
    ins = db.query(Insight).order_by(Insight.id.desc()).first()
    learn = llm.to_json(ins.summary.get("recommendations", [])) if ins else "(no performance data yet)"
    mix = ch.get("format_mix", {})
    res = llm.structured(
        db, video_id=None, category="research", tool_name="submit_ideas", schema=TOPIC_SCHEMA, est_usd=0.1,
        note="trend ideas",
        system=("You are the head writer of a basketball STATS Shorts channel (animated stat breakdowns, career "
                "arcs, GOAT debates settled by numbers, nightly recaps). Formats with weight 0 must not be used. "
                "Ideas must be ORIGINAL "
                "(never a remake of another creator's video), funny or genuinely surprising, and any factual angle "
                "must be checkable. Jokes target situations and plays, never people's bodies, families or identity."),
        prompt=("\n\n".join(signals) or "(no live signals available — use evergreen basketball culture)") + \
               f"\n\nFORMAT MIX WEIGHTS: {mix}\nCATEGORIES: {', '.join(ch['categories'])}\n"
               f"FOCUS: {focus or 'none'}\nPERFORMANCE LEARNINGS: {learn}\n"
               "ALREADY MADE OR QUEUED (no near-duplicates):\n" + "\n".join(done + pending) + \
               f"\n\nPropose {n} Short ideas across the formats, weighted by the mix. Score each 0-10 on "
               "current_popularity (evidence in the signals), audience_interest, entertainment, relevance (to "
               "basketball fans now), originality (vs the popular Shorts above), timeliness (expires soon = high).")
    real_links = {h["link"] for h in heads}
    out = []
    for t in res["ideas"]:
        if t["format"] == "recap" and settings_store.get(db, "data")["balldontlie_tier"] == "free":
            continue          # needs per-game player stats (paid tier)
        topic = Topic(title=t["title"][:200], format=t["format"], players=t.get("players", [])[:4],
                      category=t["category"], main_event=t["context"],
                      why_watch=t["angle"], target_minutes=0.5, period="", research_difficulty="easy",
                      visual_style="", scores=t["scores"], score=overall(t["scores"]),
                      evidence=[u for u in t.get("based_on", []) if u in real_links])
        db.add(topic)
        out.append(topic)
    db.commit()
    return out


def pick_best(db: Session) -> Topic | None:
    q = db.query(Topic).filter(Topic.status.in_(["approved", "suggested"]))
    approved = q.filter(Topic.status == "approved").order_by(Topic.score.desc()).first()
    return approved or q.order_by(Topic.score.desc()).first()
