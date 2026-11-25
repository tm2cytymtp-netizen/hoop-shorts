"""Basketball Shorts end-to-end: a text-only meme Short and a narrated comparison Short with a real-data
scoreboard, rendered for real (FFmpeg, cards, SFX, music, captions, QC). Kokoro narration is REAL.
Network services (Gemini, Cloudflare, Commons, BALLDONTLIE) are replaced with local stand-ins."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

TMP = Path(os.environ.get("E2E_DIR") or tempfile.mkdtemp(prefix="hoops_"))
os.environ["DATABASE_URL"] = f"sqlite:///{TMP / 'h.db'}"
os.environ["DATA_DIR"] = str(TMP / "data")

from app import media, settings_store  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import CostEntry, Topic, Video  # noqa: E402
from app.orchestrator import make_cover  # noqa: E402
from app.pipeline import edit, factcheck, metadata, narration, qc, script, sfx, visuals  # noqa: E402
from app.providers import cfai, commons, llm  # noqa: E402

for cache in [Path("/tmp/kok")]:
    dst = TMP / "data" / "models" / "kokoro"
    dst.mkdir(parents=True, exist_ok=True)
    for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
        if (cache / f).exists() and not (dst / f).exists():
            shutil.copy(cache / f, dst / f)

import random  # noqa: E402

from PIL import Image, ImageDraw, ImageFilter  # noqa: E402


def fake_image(db, video_id, prompt, dest, seed=None, width=None, height=None, negative=""):
    rnd = random.Random(hash(prompt) & 0xFFFF)
    w, h = width or 1920, height or 1088
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    top, bot = (rnd.randint(60, 140), rnd.randint(40, 90), 30), (200, rnd.randint(130, 170), 90)
    for y in range(h):
        k = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] * (1 - k) + bot[i] * k) for i in range(3)))
    for _ in range(40):
        x, y, r = rnd.randint(0, w), rnd.randint(h // 3, h), rnd.randint(20, 160)
        d.ellipse([x - r, y - r // 2, x + r, y + r // 2], fill=(rnd.randint(20, 80),) * 3)
    d.ellipse([w * 0.4, h * 0.25, w * 0.6, h * 0.75], fill=(150, 30, 30))
    img.filter(ImageFilter.GaussianBlur(2)).save(dest)
    return {"path": str(dest), "url": None, "model": "test", "seed": seed}




MEME = {
    "title": "Every pickup game has this guy", "logline": "x", "format": "meme", "mood": "funny", "narrated": False,
    "style_bible": {"art_direction": "", "characters": [], "locations": []}, "pronunciations": {},
    "scenes": [
        {"section": "hook", "narration": "", "hold_seconds": 2.2, "sfx": "boom", "claims": [],
         "visual": {"type": "meme", "camera": "punch", "image_prompt": "cartoon hooper in a red jersey flexing",
                    "top_text": "Me after hitting one three", "bottom_text": "Thinking I'm the greatest shooter alive"}},
        {"section": "build", "narration": "", "hold_seconds": 2.0, "sfx": "whoosh", "claims": [],
         "visual": {"type": "reaction", "camera": "punch", "image_prompt": "shocked cartoon teammates",
                    "caption": "POV: he calls for the ball every single possession"}},
        {"section": "punchline", "narration": "", "hold_seconds": 2.0, "sfx": "buzzer", "claims": [],
         "visual": {"type": "big_text", "camera": "punch", "text": "0 for his next 12"}},
        {"section": "payoff", "narration": "", "hold_seconds": 2.4, "sfx": "airhorn", "claims": [],
         "visual": {"type": "ranking", "camera": "punch", "ranking": {"rank": 1, "item": "Most confident 0-for-12 ever"},
                    "image_prompt": "cartoon hooper bricking a shot"}},
    ],
    "engagement_question": "Tag the friend who does this", "trending_sound_fit": True,
}
GAME = {"id": 99, "date": "2026-11-23", "status": "Final", "home": "Denver Nuggets", "home_abbr": "DEN",
        "away": "Boston Celtics", "away_abbr": "BOS", "home_score": 121, "away_score": 119, "postseason": False}
COMP = {
    "title": "Last night was chaos", "logline": "x", "format": "storyline", "mood": "hype", "narrated": True,
    "style_bible": {"art_direction": "", "characters": [], "locations": []}, "pronunciations": {},
    "scenes": [
        {"section": "hook", "narration": "Denver just survived a two point thriller against Boston.", "sfx": "riser",
         "visual": {"type": "scoreboard", "camera": "punch", "scoreboard": {"headline": "Nobody saw this coming",
                                                                         "game_source_id": "D1"}},
         "claims": [{"claim": "Denver beat Boston 121-119", "source_ids": ["D1"], "certainty": "established"}]},
        {"section": "build", "narration": "One possession. Two hundred and forty points.", "sfx": "whoosh",
         "visual": {"type": "stat_card", "camera": "punch", "stat": {"title": "The final", "left_name": "Celtics",
                    "right_name": "Nuggets", "rows": [{"label": "Points", "left": "119", "right": "121"}],
                    "source_ids": ["D1"]}},
         "claims": [{"claim": "Final score 121-119", "source_ids": ["D1"], "certainty": "established"}]},
        {"section": "question", "narration": "Was that the game of the week?", "sfx": "ding",
         "visual": {"type": "photo", "camera": "push_in", "photo_query": "Nikola Jokic", "caption": "Game of the week?"},
         "claims": []},
    ],
}


def fake_structured(db, *, tool_name, **kw):
    if tool_name == "submit_review":
        return {"value_score": 7, "script_quality": 7, "repetitive_ai_phrasing": [], "policy_concerns": [], "notes": "ok"}
    if tool_name == "submit_metadata":
        return {"title": "Every pickup game has this guy", "alt_titles": ["He really thought he was him", "0 for 12"],
                "platform_captions": {"tiktok": "we all know one 😭 #nba", "instagram": "tag him", "facebook": "Every gym."},
                "summary": "We all know this guy.", "keywords": ["nba memes"], "tags": ["nba memes", "basketball"],
                "hashtags": ["#basketball", "#hoops"], "playlist": "NBA Memes"}
    if tool_name == "submit_verdicts":
        return {"verdicts": [{"id": "0.0", "verdict": "supported", "reason": "D1"},
                             {"id": "1.0", "verdict": "supported", "reason": "D1"}]}
    raise AssertionError(tool_name)


def fake_photo(query, dest, tries=10):
    fake_image(None, None, "photo " + query, dest.with_suffix(".png"), width=900, height=1200)
    dest.with_suffix(".png").rename(dest)
    return {"path": str(dest), "license": "CC BY-SA 4.0", "artist": "Jane Photographer", "page": "https://commons...",
            "credit": "Photo: Jane Photographer / CC BY-SA 4.0 via Wikimedia Commons"}


def render(db, v, data):
    script.save_scenes(db, v, data)
    narration.run(db, v)
    vs = settings_store.get(db, "video")
    visuals.generate_images(db, v)
    visuals.render_procedural(db, v, float(vs["transition_s"]), int(vs["fps"]))
    edit.run(db, v)
    metadata.run(db, v, [])
    make_cover(db, v)
    rep = qc.run(db, v)
    v.qc_report = rep
    db.commit()
    for c in rep["checks"]:
        print(("PASS " if c["passed"] else "FAIL ") + f"{c['check']:26s} {c['detail'][:90]}")
    assert rep["passed"], [c for c in rep["checks"] if not c["passed"]]
    info = media.probe(v.output_path)
    vstream = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (vstream["width"], vstream["height"]) == (1080, 1920)
    print("RENDERED", v.output_path, v.duration_s)


def setup_module(_):
    init_db()
    sfx.ensure_library()
    sfx.ensure_beat()
    llm.structured = fake_structured
    cfai.generate_image = fake_image
    commons.find_photo = fake_photo


def test_text_only_meme_short():
    db = SessionLocal()
    t = Topic(title="pickup guy", format="meme", why_watch="x", main_event="x")
    db.add(t)
    db.commit()
    v = Video(kind="short", topic_id=t.id, working_title="meme",
              research={"bibliography": [], "notes": [], "format": "meme"})
    db.add(v)
    db.commit()
    script.save_scenes(db, v, MEME)
    v.fact_check = factcheck.run(db, v)
    db.commit()
    assert v.fact_check["passed"] and v.fact_check["claims"] == 0
    render(db, v, MEME)
    assert v.metadata_["alt_titles"] and v.metadata_["platform_captions"]["tiktok"]
    assert v.metadata_["trending_sound_fit"] is True
    assert sum(e.usd for e in db.query(CostEntry).filter(CostEntry.video_id == v.id)) == 0


def test_narrated_storyline_with_real_scoreboard():
    from app.providers import bdl
    db = SessionLocal()
    t = Topic(title="chaos", format="storyline", why_watch="x", main_event="x")
    db.add(t)
    db.commit()
    v = Video(kind="short", topic_id=t.id, working_title="storyline",
              research={"bibliography": [{**bdl.as_source(GAME), "id": "D1"}], "notes": [], "format": "storyline"})
    db.add(v)
    db.commit()
    script.save_scenes(db, v, COMP)
    v.fact_check = factcheck.run(db, v)
    db.commit()
    assert v.fact_check["passed"], v.fact_check
    render(db, v, COMP)
    assert any(s.alignment.get("words") for s in v.scenes)        # real Kokoro narration with captions


def test_scoreboard_rejects_made_up_game():
    db = SessionLocal()
    v = Video(kind="short", working_title="fake", research={"bibliography": [], "notes": []})
    db.add(v)
    db.commit()
    bad = {**COMP, "scenes": [COMP["scenes"][0]]}
    script.save_scenes(db, v, bad)
    narration.run(db, v)
    try:
        visuals.render_procedural(db, v, 0.0, 30)
        raise AssertionError("must refuse a scoreboard without real data")
    except RuntimeError as e:
        assert "not real game data" in str(e)
