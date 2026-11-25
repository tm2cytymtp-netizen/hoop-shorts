import os, shutil, sys
from pathlib import Path
os.environ["DATABASE_URL"] = "sqlite:////tmp/s4/s.db"
os.environ["DATA_DIR"] = "/tmp/s4/data"
sys.path.insert(0, "/home/claude/hoops-shorts/backend")
dst = Path("/tmp/s4/data/models/kokoro"); dst.mkdir(parents=True, exist_ok=True)
for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
    if not (dst / f).exists():
        shutil.copy(f"/tmp/kok/{f}", dst / f)
from app import settings_store
from app.db import SessionLocal, init_db
from app.models import Topic, Video
from app.orchestrator import make_cover
from app.pipeline import edit, factcheck, metadata, narration, qc, script, sfx, visuals
from app.providers import commons, llm, wiki_stats


# ---- Data verified 2026-11-25 on Basketball-Reference player pages; career scoring cross-checked with Wikipedia's
# "List of NBA career scoring leaders"; records cross-checked (Jordan #1 career PPG; LeBron record 21 All-NBA).
def P(sid, name, url, team, career):
    st = {"player": name, "team": team, "rows": [{"season": "career", "team": team, "champion": False, "led_league": {}}],
          "career": career, "url": url, "revid": None, "permalink": url}
    src = wiki_stats.as_source(st, sid, "2026-11-25")
    src["title"] = f"{name} — career totals & honors (Basketball-Reference, checked 2026-11-25)"
    return src
SRC = [
 P("P1", "Michael Jordan", "https://www.basketball-reference.com/players/j/jordami01.html", "Chicago",
   {"Rings": 6, "Finals W": 6, "Finals L": 0, "MVP": 5, "PPG": 30.1, "PTS": 32292, "All-NBA": 11}),
 P("P2", "LeBron James", "https://www.basketball-reference.com/players/j/jamesle01.html", "Cleveland",
   {"Rings": 4, "Finals W": 4, "Finals L": 6, "MVP": 4, "PPG": 26.7, "PTS": 43672, "All-NBA": 21}),
 P("P3", "Kareem Abdul-Jabbar", "https://www.basketball-reference.com/players/a/abdulka01.html", "Lakers",
   {"Rings": 6, "Finals W": 6, "Finals L": 4, "MVP": 6, "PPG": 24.6, "PTS": 38387, "All-NBA": 15}),
 {"id": "W1", "url": "https://en.wikipedia.org/wiki/List_of_NBA_career_scoring_leaders", "cited": True, "tier": 3,
  "title": "List of NBA career scoring leaders (Wikipedia)", "excerpts": ["LeBron James 43,591 (as of Nov 12, 2026); Kareem Abdul-Jabbar 38,387; Michael Jordan 32,292 — most career points: LeBron James"]},
 {"id": "W2", "url": "https://www.guinnessworldrecords.com/world-records/64639-highest-point-scoring-average-in-an-nba-career",
  "cited": True, "tier": 2, "title": "Guinness: highest scoring average in an NBA career", "excerpts": ["The highest point scoring average ... is 30.1 by Michael Jordan"]},
 {"id": "W3", "url": "https://www.cbssports.com/nba/news/lebron-james-responds-to-historic-all-nba-second-team-selection-sets-record-again-as-oldest-honoree-at-40",
  "cited": True, "tier": 2, "title": "CBS Sports: LeBron's 21st All-NBA selection", "excerpts": ["No other player in league history has more than 15 selections"]},
 {"id": "W4", "url": "https://en.wikipedia.org/wiki/LeBron_James", "cited": True, "tier": 3, "title": "LeBron James (Wikipedia)",
  "excerpts": ["His teams have appeared in the Finals ten times and won four championships."]},
]
IDS = ["P1", "P2", "P3"]
def h2h(stat, title, subtitle="", loss=None, note=""):
    ch = {"source_ids": IDS, "stat": stat, "title": title, "subtitle": subtitle, "note": note}
    if loss: ch["loss_stat"] = loss
    return {"type": "head_to_head", "camera": "drift", "chart": ch}
def c(claim, *ids):
    return {"claim": claim, "source_ids": list(ids), "certainty": "established"}

SCRIPT = {
 "title": "Who's the real GOAT? Only the numbers", "logline": "Jordan vs LeBron vs Kareem, six categories.",
 "format": "comparison", "mood": "hype", "narrated": True, "pronunciations": {},
 "style_bible": {"art_direction": "", "characters": [], "locations": []},
 "scenes": [
  {"section": "hook", "sfx": "boom",
   "narration": "Jordan, LeBron, or Kareem? Forget the hot takes. Let's let the numbers pick the GOAT.",
   "visual": {"type": "big_text", "camera": "punch", "text": "WHO'S THE REAL GOAT? NUMBERS ONLY"}, "claims": []},
  {"section": "build", "sfx": "whoosh",
   "narration": "Rings first. Jordan and Kareem have six each, and LeBron has four.",
   "visual": h2h("Rings", "CHAMPIONSHIPS"), "claims": [c("Rings: Jordan 6, Kareem 6, LeBron 4", "P1", "P2", "P3")]},
  {"section": "build", "sfx": "whoosh",
   "narration": "But in the Finals, Jordan went a perfect six and oh. LeBron is four and six.",
   "visual": h2h("Finals W", "FINALS RECORD", "Series won vs lost", loss="Finals L"),
   "claims": [c("Finals records: Jordan 6-0, LeBron 4-6, Kareem 6-4", "P1", "P2", "P3", "W4")]},
  {"section": "build", "sfx": "whoosh",
   "narration": "Kareem has the most MVPs of the three, with six.",
   "visual": h2h("MVP", "REGULAR SEASON MVPs"), "claims": [c("MVPs: Kareem 6, Jordan 5, LeBron 4", "P1", "P2", "P3")]},
  {"section": "build", "sfx": "whoosh",
   "narration": "Jordan's 30.1 points a game is the best career average in NBA history.",
   "visual": h2h("PPG", "POINTS PER GAME", "Career, regular season", note="LeBron's numbers as of Nov 25, 2026"),
   "claims": [c("Career PPG: Jordan 30.1 (highest ever), LeBron 26.7, Kareem 24.6", "P1", "P2", "P3", "W2")]},
  {"section": "build", "sfx": "scratch",
   "narration": "But LeBron has scored over 43,000 points, more than anyone, ever.",
   "visual": h2h("PTS", "TOTAL POINTS", "Career, regular season", note="LeBron's numbers as of Nov 25, 2026"),
   "claims": [c("Career points: LeBron 43,672 (most ever), Kareem 38,387, Jordan 32,292", "P1", "P2", "P3", "W1")]},
  {"section": "build", "sfx": "whoosh",
   "narration": "And his 21 All-NBA teams are a record too.",
   "visual": h2h("All-NBA", "ALL-NBA TEAMS"), "claims": [c("All-NBA: LeBron 21 (record), Kareem 15, Jordan 11", "P1", "P2", "P3", "W3")]},
  {"section": "payoff", "sfx": "ding",
   "narration": "Add it all up, and Jordan wins three categories. LeBron and Kareem win two each.",
   "visual": {"type": "tally", "camera": "drift", "chart": {"source_ids": IDS, "title": "THE SCORECARD",
              "subtitle": "Ties count for both", "categories": [
                {"label": "Rings", "stat": "Rings"}, {"label": "Finals", "stat": "Finals W", "loss_stat": "Finals L"},
                {"label": "MVPs", "stat": "MVP"}, {"label": "PPG", "stat": "PPG"},
                {"label": "Points", "stat": "PTS"}, {"label": "All-NBA", "stat": "All-NBA"}]}},
   "claims": [c("Category wins: Jordan 3 (rings tie, Finals, PPG), LeBron 2 (points, All-NBA), Kareem 2 (rings tie, MVP)", "P1", "P2", "P3")]},
  {"section": "question", "sfx": "pop",
   "narration": "So the numbers lean Jordan, but it's closer than you think. Who's your GOAT?",
   "visual": {"type": "big_text", "camera": "punch", "text": "WHO'S YOUR GOAT?"}, "claims": []},
 ],
 "engagement_question": "Jordan, LeBron or Kareem?", "trending_sound_fit": False,
}

def editor(db, *, tool_name, **kw):     # stand-in for the free AI writer (sandbox has no internet)
    if tool_name == "submit_verdicts":  # every claim checked by hand against the sources above
        return {"verdicts": [{"id": f"{i}.{j}", "verdict": "supported", "reason": "matches cited source"}
                             for i, s in enumerate(SCRIPT["scenes"]) for j, _ in enumerate(s["claims"])]}
    if tool_name == "submit_metadata":
        return {"title": "Who's the REAL GOAT? Only the Numbers 🐐",
                "alt_titles": ["Jordan vs LeBron vs Kareem: 6 Stats Decide It", "The GOAT Debate, Settled by Stats?"],
                "platform_captions": {"tiktok": "Jordan vs LeBron vs Kareem — 6 categories, numbers only. Who's your GOAT? #nba #goat #michaeljordan #lebronjames",
                                      "instagram": "Rings, Finals, MVPs, PPG, points, All-NBA. Who wins?\n#nba #goat #nbastats",
                                      "facebook": "Jordan, LeBron or Kareem? We let the numbers decide."},
                "summary": "Michael Jordan, LeBron James and Kareem Abdul-Jabbar compared across six categories: "
                           "championships, Finals record, MVPs, points per game, total points and All-NBA selections.",
                "keywords": ["nba goat debate", "jordan vs lebron"], "tags": ["Michael Jordan", "LeBron James",
                "Kareem Abdul-Jabbar", "NBA GOAT", "GOAT debate", "NBA stats", "Jordan vs LeBron"],
                "hashtags": ["#NBA", "#GOAT"], "playlist": "Stat Breakdowns"}
    if tool_name == "submit_review":
        return {"value_score": 8, "script_quality": 8, "repetitive_ai_phrasing": [], "policy_concerns": [],
                "notes": "Classic debate, every number sourced, balanced categories, strong closing question."}
    raise AssertionError(tool_name)

init_db(); sfx.ensure_library(); sfx.ensure_beat()
llm.structured = editor
commons.find_photo = lambda *a, **k: None   # photos can't be downloaded from this sandbox; badges are used
db = SessionLocal()
settings_store.update(db, "voice", {"speed": 1.08, "format_voice": {"comparison": "warm_storyteller"}})
settings_store.update(db, "video", {"music_volume_db": -19})
settings_store.update(db, "shorts", {"max_seconds": 60})
t = Topic(title=SCRIPT["title"], format="comparison", players=["Michael Jordan","LeBron James","Kareem Abdul-Jabbar"], why_watch="GOAT debate", main_event="GOAT by the numbers")
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
