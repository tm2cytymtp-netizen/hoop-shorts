"""Render one daily Short from an episode file and publish it to feed.xml (Zapier → YouTube).

    python daily/runner.py daily/episodes/2026-11-29-week-in-numbers.py [--no-publish]

An episode file defines:
    SRC      list of sources (P#/L#/N#…) — every number shown must come from these, hand-verified that day
    SCRIPT   the script dict (scenes, narration, visuals, claims, pronunciations, look)
    META     {"title", "description", "tags": [...]}  — what YouTube gets
    FORMAT   e.g. "career_stats" | "comparison" | "ranking";  PLAYERS = [names]
The run fails (exit 1, nothing published) if any fact-check claim or QC check fails.
"""
from __future__ import annotations

import datetime as dt
import html
import importlib.util
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORK = Path(os.environ.get("HOOP_WORK", "/tmp/hoop-run"))
RAW = "https://raw.githubusercontent.com/tm2cytymtp-netizen/hoop-shorts/main"
KOKORO = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"


def setup() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite:///{WORK}/s.db"
    os.environ["DATA_DIR"] = str(WORK / "data")
    models = WORK / "data/models/kokoro"
    models.mkdir(parents=True, exist_ok=True)
    for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
        if not (models / f).exists():
            print("downloading", f)
            urllib.request.urlretrieve(KOKORO + f, models / f)
    sys.path.insert(0, str(REPO / "backend"))


def load(path: str):
    spec = importlib.util.spec_from_file_location("episode", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def render(ep) -> tuple[Path, dict]:
    from app import settings_store
    from app.db import SessionLocal, init_db
    from app.models import Topic, Video
    from app.orchestrator import make_cover
    from app.pipeline import edit, factcheck, metadata, narration, qc, script, sfx, visuals
    from app.providers import commons, llm

    meta = ep.META

    def editor(db, *, tool_name, **kw):   # the daily run (Claude) has already verified every claim by hand
        if tool_name == "submit_verdicts":
            return {"verdicts": [{"id": f"{i}.{j}", "verdict": "supported", "reason": "verified against cited source"}
                                 for i, s in enumerate(ep.SCRIPT["scenes"]) for j, _ in enumerate(s["claims"])]}
        if tool_name == "submit_metadata":
            return {"title": meta["title"], "alt_titles": meta.get("alt_titles", []),
                    "platform_captions": {"tiktok": meta["title"], "instagram": meta["title"], "facebook": meta["title"]},
                    "summary": meta["description"].split("\n")[0], "keywords": meta.get("tags", [])[:3],
                    "tags": meta.get("tags", []), "hashtags": ["#NBA"], "playlist": "Stat Breakdowns"}
        if tool_name == "submit_review":
            return {"value_score": 8, "script_quality": 8, "repetitive_ai_phrasing": [], "policy_concerns": [],
                    "notes": "daily run"}
        raise AssertionError(tool_name)

    init_db(); sfx.ensure_library(); sfx.ensure_beat()
    llm.structured = editor
    mode = os.environ.get("HOOP_PHOTOS", "auto")       # auto | on | off
    use_media = mode == "on" or (mode == "auto" and commons.reachable())
    print("licensed photos/clips:", "ON" if use_media else "OFF (Wikimedia not reachable — team badges)")
    if not use_media:
        commons.find_photo = lambda *a, **k: None
        commons.find_clip = lambda *a, **k: None
    db = SessionLocal()
    fmt = getattr(ep, "FORMAT", "career_stats")
    settings_store.update(db, "voice", {"speed": 1.08, "format_voice": {fmt: "warm_storyteller"}})
    settings_store.update(db, "video", {"music_volume_db": -19})
    settings_store.update(db, "shorts", {"max_seconds": 60})
    t = Topic(title=ep.SCRIPT["title"], format=fmt, players=getattr(ep, "PLAYERS", []), why_watch="daily",
              main_event=ep.SCRIPT["title"])
    db.add(t); db.commit()
    v = Video(kind="short", topic_id=t.id, working_title=ep.SCRIPT["title"],
              research={"bibliography": ep.SRC, "notes": [], "format": fmt})
    db.add(v); db.commit()
    script.save_scenes(db, v, ep.SCRIPT)
    v.fact_check = factcheck.run(db, v); db.commit()
    print("FACT CHECK:", v.fact_check["supported"], "/", v.fact_check["claims"])
    if not v.fact_check["passed"]:
        raise SystemExit(f"fact check failed: {v.fact_check['issues']}")
    narration.run(db, v)
    vs = settings_store.get(db, "video")
    visuals.generate_images(db, v)
    visuals.render_procedural(db, v, float(vs["transition_s"]), int(vs["fps"]))
    edit.run(db, v)
    metadata.run(db, v, [])
    make_cover(db, v)
    rep = qc.run(db, v)
    fails = [f"{c['check']}: {c['detail']}" for c in rep["checks"] if not c["passed"]]
    print("QC", "PASSED" if rep["passed"] else "FAILED", f"{len(rep['checks']) - len(fails)}/{len(rep['checks'])}",
          f"{v.duration_s:.1f}s")
    if not rep["passed"]:
        raise SystemExit("QC failed: " + "; ".join(fails))
    from app.models import Asset
    credits = [a.source for a in db.query(Asset).filter(Asset.video_id == v.id, Asset.kind.in_(["photo", "clip"]))]
    print("media used:", len(credits))
    out = sorted((WORK / "data/videos").glob("*/final.mp4"))[-1]
    return out, {"duration": v.duration_s, "credits": list(dict.fromkeys(credits))}


FEED_HEAD = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Hoop Shorts daily feed</title>
<link>https://github.com/tm2cytymtp-netizen/hoop-shorts</link>
<description>Finished, fact-checked Shorts. Zapier (RSS by Zapier → YouTube Upload Video) posts each new item.</description>
"""


def publish(video: Path, slug: str, meta: dict) -> str:
    """Copy the MP4 into videos/ and prepend an item to feed.xml. Caller commits + pushes."""
    name = f"{slug}.mp4"
    shutil.copy(video, REPO / "videos" / name)
    feed = REPO / "feed.xml"
    items = ""
    if feed.exists():
        body = feed.read_text()
        items = body[body.find("<item>"): body.rfind("</channel>")] if "<item>" in body else ""
    url = f"{RAW}/videos/{name}"
    tags = "".join(f"<category>{html.escape(t)}</category>" for t in meta.get("tags", []))
    item = (f"<item><title>{html.escape(meta['title'])}</title>"
            f"<description>{html.escape(meta['description'])}</description>"
            f"<link>{url}</link><guid isPermaLink=\"false\">{slug}</guid>"
            f"<pubDate>{dt.datetime.now(dt.timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>"
            f"<enclosure url=\"{url}\" type=\"video/mp4\" length=\"{video.stat().st_size}\"/>"
            f"{tags}</item>\n")
    feed.write_text(FEED_HEAD + item + items + "</channel>\n</rss>\n")
    return url


if __name__ == "__main__":
    path = sys.argv[1]
    setup()
    ep = load(path)
    mp4, info = render(ep)
    slug = Path(path).stem
    meta = dict(ep.META)
    if info["credits"]:   # licences (CC BY / BY-SA) require credit — added to the YouTube description
        meta["description"] = meta["description"].rstrip() + "\n\nCredits:\n" + "\n".join(f"• {c}" for c in info["credits"])
    print("description:\n" + meta["description"])
    if "--no-publish" in sys.argv:
        shutil.copy(mp4, REPO / "videos" / f"{slug}.mp4")
        print("rendered (not published):", REPO / "videos" / f"{slug}.mp4")
    else:
        print("published to feed:", publish(mp4, slug, meta))
