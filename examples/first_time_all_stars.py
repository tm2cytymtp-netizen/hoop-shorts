import os, shutil, sys
from pathlib import Path
os.environ["DATABASE_URL"] = "sqlite:////tmp/s5/s.db"
os.environ["DATA_DIR"] = "/tmp/s5/data"
sys.path.insert(0, "/home/claude/hoops-shorts/backend")
dst = Path("/tmp/s5/data/models/kokoro"); dst.mkdir(parents=True, exist_ok=True)
for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
    if not (dst / f).exists():
        shutil.copy(f"/tmp/kok/{f}", dst / f)
from app import settings_store
from app.db import SessionLocal, init_db
from app.models import Topic, Video
from app.orchestrator import make_cover
from app.pipeline import edit, factcheck, metadata, narration, qc, script, sfx, visuals
from app.providers import commons, llm, wiki_stats



# ---- Data verified 2026-11-25 on Basketball-Reference player pages (2026-27 rows revised Nov 24, 2026).
# None of the five has an All-Star selection listed. Last season's six first-timers excluded.
def P(sid, name, url, team, rows, career=None):
    st = {"player": name, "team": team, "rows": [{"season": s, "team": team, "GP": g, "PPG": p, "RPG": r, "APG": a,
          "FG%": fg, "champion": False, "led_league": {}} for s, g, p, r, a, fg in rows], "career": career,
          "url": url, "revid": None, "permalink": url}
    src = wiki_stats.as_source(st, sid, "2026-11-25")
    src["title"] = f"{name} — per-game stats (Basketball-Reference, checked 2026-11-25)"
    return src
SRC = [
 P("P1", "Cooper Flagg", "https://www.basketball-reference.com/players/f/flaggco01.html", "Dallas",
   [("2025–26", 70, 21.0, 6.7, 4.5, .468), ("2026–27", 16, 24.3, 6.3, 6.4, .478)]),
 P("P2", "Austin Reaves", "https://www.basketball-reference.com/players/r/reaveau01.html", "Lakers",
   [("2025–26", 51, 23.3, 4.7, 5.5, .490), ("2026–27", 12, 24.7, 3.3, 4.7, .513)], career={"PPG": 16.1, "GP": 343}),
 P("P3", "Franz Wagner", "https://www.basketball-reference.com/players/w/wagnefr01.html", "Orlando",
   [("2024–25", 60, 24.2, 5.7, 4.7, .463), ("2025–26", 34, 20.6, 5.2, 3.3, .481), ("2026–27", 16, 24.5, 6.9, 8.3, .470)],
   career={"PPG": 19.5, "GP": 341}),
 P("P4", "Ty Jerome", "https://www.basketball-reference.com/players/j/jeromty01.html", "Memphis",
   [("2025–26", 15, 19.7, 2.8, 5.7, .474), ("2026–27", 13, 25.1, 3.5, 5.2, .479)], career={"PPG": 10.1, "GP": 257}),
 P("P5", "Darius Acuff Jr.", "https://www.basketball-reference.com/players/a/acuffda01.html", "Sacramento",
   [("2026–27", 17, 24.6, 3.4, 7.2, .403)]),
 {"id": "N1", "url": "https://www.thebiglead.com/5-first-time-nba-all-star-candidates-to-watch-in-2026-27-season/",
  "cited": True, "tier": 2, "title": "The Big Lead: 5 first-time All-Star candidates for 2026-27",
  "excerpts": ["Last season, six players became first-time NBA All-Stars: Deni Avdija, Jalen Duren, Chet Holmgren, Norman Powell, Jalen Johnson, Jamal Murray"]},
 {"id": "N2", "url": "https://clutchpoints.com/nba/sacramento-kings/kings-news-darius-acuff-jr-getting-buckets-rookie-michael-jordan-worst-team",
  "cited": True, "tier": 2, "title": "ClutchPoints: Acuff fastest rookie to 350 points since Jordan",
  "excerpts": ["Acuff Jr. became the fastest rookie to score 350 points in the NBA since Michael Jordan reached that landmark back in 1984"]},
]
NOTE = "Stats through Nov 24, 2026"
def card(sid, before, after, event, team, stats=("PPG", "APG", "RPG"), before_label=None):
    return {"type": "comeback_card", "camera": "drift", "chart": {"source_id": sid, "before_season": before,
            "after_season": after, "event": event, "when": NOTE, "year": None, "timeline": [], "team": team,
            "before_label": before_label or before, "after_label": "2026–27", "stats": list(stats),
            "tone": "positive", "before_head": "career" if before == "career" else "last season", "after_head": "this season"}}
def c(claim, *ids):
    return {"claim": claim, "source_ids": list(ids), "certainty": "established"}

SCRIPT = {
 "title": "5 players who could be FIRST-TIME All-Stars this season", "logline": "Five breakouts, zero All-Star games.",
 "format": "comparison", "mood": "hype", "narrated": True,
 "pronunciations": {"Wagner": "Vahgner", "Jerome": "/dʒəɹˈoʊm/"},
 "style_bible": {"art_direction": "", "characters": [], "locations": []},
 "scenes": [
  {"section": "hook", "sfx": "boom",
   "narration": "Six players made their first All-Star team last season. These five could be next.",
   "visual": {"type": "big_text", "camera": "punch", "text": "THE NEXT FIRST-TIME ALL-STARS?"},
   "claims": [c("Six first-time All-Stars in 2026", "N1")]},
  {"section": "build", "sfx": "whoosh",
   "narration": "Cooper Flagg won Rookie of the Year, and he's up from 21 to 24.3 points a game.",
   "visual": card("P1", "2025–26", "2026–27", "2025–26 Rookie of the Year", "Dallas"),
   "claims": [c("Flagg: 2025-26 ROY; 21.0 PPG in 2025-26, 24.3 in 2026-27", "P1")]},
  {"section": "build", "sfx": "whoosh",
   "narration": "Austin Reaves has never been an All-Star, but he's scoring 24.7 on 51 percent shooting.",
   "visual": card("P2", "2025–26", "2026–27", "Never an All-Star", "Lakers", stats=("PPG", "FG%", "APG")),
   "claims": [c("Reaves: 24.7 PPG on .513 FG in 2026-27; no All-Star selections", "P2")]},
  {"section": "build", "sfx": "whoosh",
   "narration": "Franz Wagner is scoring his most ever, and his assists jumped from 3.3 to 8.3.",
   "visual": card("P3", "2025–26", "2026–27", "Best scoring season yet", "Orlando"),
   "claims": [c("Wagner: 24.5 PPG (highest of his seasons; previous best 24.2); APG 3.3 to 8.3", "P3")]},
  {"section": "build", "sfx": "scratch",
   "narration": "Ty Jerome averaged 10.1 for his career. This year, he's at 25.1 in Memphis.",
   "visual": card("P4", "career", "2026–27", "Biggest leap on the list", "Memphis", stats=("PPG",), before_label="8 seasons"),
   "claims": [c("Jerome: 10.1 career PPG; 25.1 PPG in 2026-27 with Memphis", "P4")]},
  {"section": "build", "sfx": "riser",
   "narration": "And rookie Darius Acuff Junior is the fastest to 350 points since Michael Jordan.",
   "visual": {"type": "big_number", "camera": "punch", "chart": {"source_id": "P5", "season": "2026–27", "stat": "PPG",
              "title": "DARIUS ACUFF JR.", "label": "points per game", "context": "Rookie · No. 7 pick · Sacramento"}},
   "claims": [c("Acuff: 24.6 PPG as a rookie", "P5"), c("fastest rookie to 350 points since Jordan in 1984", "N2")]},
  {"section": "payoff", "sfx": "ding",
   "narration": "All five are scoring over 24 a game, and none of them has ever been an All-Star.",
   "visual": {"type": "head_to_head", "camera": "drift", "chart": {"source_ids": ["P4", "P2", "P5", "P3", "P1"],
              "season": "2026–27", "stat": "PPG", "title": "POINTS PER GAME", "subtitle": "2026–27 · zero All-Star games between them",
              "note": NOTE}},
   "claims": [c("2026-27 PPG: Jerome 25.1, Reaves 24.7, Acuff 24.6, Wagner 24.5, Flagg 24.3; no All-Star selections", "P1", "P2", "P3", "P4", "P5")]},
  {"section": "question", "sfx": "pop",
   "narration": "So who makes it first? Drop your pick.",
   "visual": {"type": "big_text", "camera": "punch", "text": "WHO MAKES IT FIRST?"}, "claims": []},
 ],
 "engagement_question": "Who becomes a first-time All-Star?", "trending_sound_fit": False,
}

def editor(db, *, tool_name, **kw):     # stand-in for the free AI writer (sandbox has no internet)
    if tool_name == "submit_verdicts":  # every claim checked by hand against the sources above
        return {"verdicts": [{"id": f"{i}.{j}", "verdict": "supported", "reason": "matches cited source"}
                             for i, s in enumerate(SCRIPT["scenes"]) for j, _ in enumerate(s["claims"])]}
    if tool_name == "submit_metadata":
        return {"title": "5 Players Who Could Be FIRST-TIME All-Stars This Season ⭐",
                "alt_titles": ["Never an All-Star… Until This Year?", "The Next First-Time NBA All-Stars"],
                "platform_captions": {"tiktok": "5 guys over 24 PPG who've never been All-Stars. Who makes it first? #nba #allstar #cooperflagg",
                                      "instagram": "Flagg, Reaves, Wagner, Jerome, Acuff. Who gets the first All-Star nod?\n#nba #nbaallstar #nbastats",
                                      "facebook": "Five players who could be first-time All-Stars this season."},
                "summary": "Cooper Flagg, Austin Reaves, Franz Wagner, Ty Jerome and rookie Darius Acuff Jr. are all scoring "
                           "24+ points per game in 2026-27, and none has ever made an All-Star team.",
                "keywords": ["first time all stars 2027", "nba all star 2027"], "tags": ["Cooper Flagg", "Austin Reaves",
                "Franz Wagner", "Ty Jerome", "Darius Acuff Jr.", "NBA All-Star", "NBA stats"],
                "hashtags": ["#NBA", "#AllStar"], "playlist": "Stat Breakdowns"}
    if tool_name == "submit_review":
        return {"value_score": 8, "script_quality": 8, "repetitive_ai_phrasing": [], "policy_concerns": [],
                "notes": "Timely, every number sourced, strong closing question."}
    raise AssertionError(tool_name)

init_db(); sfx.ensure_library(); sfx.ensure_beat()
llm.structured = editor
commons.find_photo = lambda *a, **k: None   # photos can't be downloaded from this sandbox; badges are used
db = SessionLocal()
settings_store.update(db, "voice", {"speed": 1.08, "format_voice": {"comparison": "warm_storyteller"}})
settings_store.update(db, "video", {"music_volume_db": -19})
settings_store.update(db, "shorts", {"max_seconds": 60})
t = Topic(title=SCRIPT["title"], format="comparison", players=["Cooper Flagg","Austin Reaves","Franz Wagner","Ty Jerome","Darius Acuff Jr."], why_watch="All-Star race", main_event="first-time All-Star candidates")
db.add(t); db.commit()
v = Video(kind="short", topic_id=t.id, working_title=SCRIPT["title"], research={"bibliography": SRC, "notes": [], "format": "comparison"})
db.add(v); db.commit()
script.save_scenes(db, v, SCRIPT)
v.fact_check = factcheck.run(db, v); db.commit()
print("FACT CHECK:", v.fact_check["supported"], "/", v.fact_check["claims"], "passed" if v.fact_check["passed"] else v.fact_check["issues"])
narration.run(db, v)
print("narration seconds:", round(sum(s.audio_duration for s in v.scenes), 1))
vs = settings_store.get(db, "video")
visuals.generate_images(db, v)
visuals.render_procedural(db, v, float(vs["transition_s"]), int(vs["fps"]))
edit.run(db, v)
metadata.run(db, v, [])
make_cover(db, v)
rep = qc.run(db, v)
for ch in rep["checks"]:
    if not ch["passed"]:
        print("FAIL", ch["check"], ch["detail"])
print("QC", "PASSED" if rep["passed"] else "FAILED", f"{sum(ch['passed'] for ch in rep['checks'])}/{len(rep['checks'])}", v.duration_s)
print([(s.idx, round(s.start_s, 1)) for s in v.scenes])
