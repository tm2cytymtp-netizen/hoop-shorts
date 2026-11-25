import os, shutil, sys
from pathlib import Path
os.environ["DATABASE_URL"] = "sqlite:////tmp/s3/s.db"
os.environ["DATA_DIR"] = "/tmp/s3/data"
sys.path.insert(0, "/home/claude/hoops-shorts/backend")
dst = Path("/tmp/s3/data/models/kokoro"); dst.mkdir(parents=True, exist_ok=True)
for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
    if not (dst / f).exists():
        shutil.copy(f"/tmp/kok/{f}", dst / f)
from app import settings_store
from app.db import SessionLocal, init_db
from app.models import Topic, Video
from app.orchestrator import make_cover
from app.pipeline import edit, factcheck, metadata, narration, qc, script, sfx, visuals
from app.providers import commons, llm, wiki_stats

# ---- Data verified 2026-11-25: Basketball-Reference per-game tables == Wikipedia career-statistics tables ----
def P(sid, name, url, rows, career=None):
    st = {"player": name, "rows": [{"season": s, "team": t, "GP": g, "FG%": fg, "RPG": r, "PPG": p, "champion": False,
                                     "led_league": {}} for s, t, g, fg, r, p in rows], "career": career,
          "url": url, "revid": None, "permalink": url}
    src = wiki_stats.as_source(st, sid, "2026-11-25")
    src["title"] = f"{name} — career statistics (Wikipedia + Basketball-Reference, checked 2026-11-25)"
    return src
SRC = [
 P("P1", "Dominique Wilkins", "https://www.basketball-reference.com/players/w/wilkido01.html",
   [("1990–91", "Atlanta", 81, .470, 9.0, 25.9), ("1991–92", "Atlanta", 42, .464, 7.0, 28.1), ("1992–93", "Atlanta", 71, .468, 6.8, 29.9)]),
 P("P2", "Paul George", "https://www.basketball-reference.com/players/g/georgpa01.html",
   [("2013–14", "Indiana", 80, .424, 6.8, 21.7), ("2014–15", "Indiana", 6, .367, 3.7, 8.8), ("2015–16", "Indiana", 81, .418, 7.0, 23.1)]),
 P("P3", "Gordon Hayward", "https://www.basketball-reference.com/players/h/haywago01.html",
   [("2016–17", "Utah", 73, .471, 5.4, 21.9), ("2017–18", "Boston", 1, .500, 1.0, 2.0), ("2018–19", "Boston", 72, .466, 4.5, 11.5)]),
 P("P4", "Kevin Durant", "https://www.basketball-reference.com/players/d/duranke01.html",
   [("2018–19", "Golden State", 78, .521, 6.4, 26.0), ("2020–21", "Brooklyn", 35, .537, 7.1, 26.9)]),
 P("P5", "Jalen Williams", "https://www.clickondetroit.com/sports/2026/10/26/thunders-jalen-williams-has-fractured-leg-dislocated-ankle-and-will-need-surgery/",
   [("2026–27", "Oklahoma City", None, None, None, None)], career={"GP": 251, "PPG": 17.9}),
 {"id": "N1", "url": "https://www.ksat.com/sports/2026/10/26/thunders-jalen-williams-will-need-surgery-for-a-broken-leg-and-dislocated-ankle/",
  "title": "AP: Thunder's Jalen Williams will need surgery for a broken leg and dislocated ankle", "cited": True, "tier": 2,
  "excerpts": ["Oklahoma City guard Jalen Williams will need surgery to repair a broken left fibula and dislocated left ankle",
               "Williams — who has averaged 17.9 points in 251 games over his first five seasons"]},
 {"id": "N2", "url": "https://www.cbssports.com/nba/news/jalen-williams-leg-injury-thunder-star/", "cited": True, "tier": 2,
  "title": "CBS Sports: Jalen Williams leg injury", "excerpts": ["Williams' injury appears similar to George, Hayward"]},
 {"id": "W1", "url": "https://en.wikipedia.org/wiki/Dominique_Wilkins", "cited": True, "tier": 3, "title": "Dominique Wilkins (Wikipedia)",
  "excerpts": ["In the 1991–92 season, Wilkins's ruptured his Achilles tendon against the Philadelphia 76ers on January 28, 1992."]},
 {"id": "W2", "url": "https://en.wikipedia.org/wiki/Paul_George", "cited": True, "tier": 3, "title": "Paul George (Wikipedia)",
  "excerpts": ["during a Las Vegas scrimmage on August 1, and suffered a compound fracture of both bones in his lower right leg."]},
 {"id": "W3", "url": "https://en.wikipedia.org/wiki/Gordon_Hayward", "cited": True, "tier": 3, "title": "Gordon Hayward (Wikipedia)",
  "excerpts": ["suffered a fractured tibia and dislocated ankle in his left leg less than six minutes into the season opener"]},
 {"id": "W4", "url": "https://en.wikipedia.org/wiki/Kevin_Durant", "cited": True, "tier": 3, "title": "Kevin Durant (Wikipedia)",
  "excerpts": ["2019 NBA Finals Game 5: suffered an Achilles tendon injury, falling and grabbing his lower right calf; did not play in 2019–20"]},
]
TL = [1992, 2014, 2017, 2019, 2026]
def card(sid, before, after, event, when, year, team, before_label=None, after_label=None, stats=("PPG", "FG%", "RPG")):
    return {"type": "comeback_card", "camera": "drift", "chart": {"source_id": sid, "before_season": before,
            "after_season": after, "event": event, "when": when, "year": year, "timeline": TL, "team": team,
            "before_label": before_label, "after_label": after_label, "stats": list(stats)}}
def c(claim, *ids):
    return {"claim": claim, "source_ids": list(ids), "certainty": "established"}

SCRIPT = {
 "title": "What happens when NBA stars come back from brutal injuries?", "logline": "Four comebacks, one question.",
 "format": "career_stats", "mood": "dramatic", "narrated": True, "pronunciations": {"Hayward": "Hayword", "Celtics": "Selltix"},
 "style_bible": {"art_direction": "", "characters": [], "locations": []},
 "scenes": [
  {"section": "hook", "sfx": "boom",
   "narration": "Jalen Williams just broke his leg. So what really happens when stars come back from injuries like this?",
   "visual": {"type": "big_text", "camera": "punch", "text": "DO STARS EVER COME BACK THE SAME?"},
   "claims": [c("Jalen Williams broke his leg (left fibula) and dislocated his ankle, Oct 2026", "N1")]},
  {"section": "build", "sfx": "whoosh",
   "narration": "In 1992, Dominique Wilkins ruptures his Achilles, then averages 29.9 the very next season.",
   "visual": card("P1", "1991–92", "1992–93", "Ruptured Achilles", "Jan 1992", 1992, "Atlanta", "1991–92", "1992–93"),
   "claims": [c("Wilkins ruptured his Achilles on January 28, 1992", "W1"), c("1991–92: 28.1 PPG; 1992–93: 29.9 PPG", "P1")]},
  {"section": "build", "sfx": "whoosh",
   "narration": "Paul George breaks his leg with Team USA in 2014, then comes back scoring 23.1 a night.",
   "visual": card("P2", "2013–14", "2015–16", "Broken right leg", "Aug 2014", 2014, "Indiana"),
   "claims": [c("George broke both bones in his lower right leg in a Team USA scrimmage, August 2014", "W2"),
              c("2015–16, first full season back: 23.1 PPG (2013–14: 21.7)", "P2")]},
  {"section": "build", "sfx": "scratch",
   "narration": "Gordon Hayward fractures his leg minutes into his Celtics debut, and his scoring drops from 21.9 to 11.5.",
   "visual": card("P3", "2016–17", "2018–19", "Broken leg + dislocated ankle", "Oct 2017", 2017, "Boston"),
   "claims": [c("Hayward fractured his tibia and dislocated his ankle minutes into his Celtics debut", "W3"),
              c("2016–17: 21.9 PPG; 2018–19: 11.5 PPG", "P3")]},
  {"section": "build", "sfx": "whoosh",
   "narration": "Kevin Durant tears his Achilles in the 2019 Finals, misses a full season, and returns at 26.9.",
   "visual": card("P4", "2018–19", "2020–21", "Achilles tendon injury", "June 2019", 2019, "Golden State"),
   "claims": [c("Durant's Achilles injury in the 2019 Finals; did not play 2019–20", "W4"),
              c("2020–21: 26.9 PPG (2018–19: 26.0)", "P4")]},
  {"section": "payoff", "sfx": "ding",
   "narration": "Three of the four came back scoring more. One lost over ten points a game.",
   "visual": {"type": "slope", "camera": "drift", "chart": {"stat": "PPG", "title": "Points per game",
              "subtitle": "Season before → first full season back", "items": [
                {"source_id": "P1", "before_season": "1991–92", "after_season": "1992–93"},
                {"source_id": "P2", "before_season": "2013–14", "after_season": "2015–16"},
                {"source_id": "P3", "before_season": "2016–17", "after_season": "2018–19"},
                {"source_id": "P4", "before_season": "2018–19", "after_season": "2020–21"}]}},
   "claims": [c("Wilkins, George and Durant scored more after; Hayward dropped 10.4 PPG (21.9 to 11.5)", "P1", "P2", "P3", "P4")]},
  {"section": "build", "sfx": "riser",
   "narration": "Jalen's averaged 17.9 points in his first five seasons, and his injury looks a lot like George's and Hayward's.",
   "visual": card("P5", "career", "?", "Broken left fibula + dislocated ankle", "Oct 2026", 2026, "Oklahoma City",
                  "first 5 seasons", "after return", stats=("PPG", "GP")),
   "claims": [c("17.9 PPG in 251 games over his first five seasons", "N1", "P5"), c("injury similar to George and Hayward", "N2")]},
  {"section": "question", "sfx": "pop",
   "narration": "So what do you think? Is he the next Paul George, or the next Gordon Hayward?",
   "visual": {"type": "big_text", "camera": "punch", "text": "NEXT PAUL GEORGE OR NEXT GORDON HAYWARD?"}, "claims": []},
 ],
 "engagement_question": "Next Paul George or next Gordon Hayward?", "trending_sound_fit": False,
}

def editor(db, *, tool_name, **kw):     # stand-in for the free AI writer (sandbox has no internet)
    if tool_name == "submit_verdicts":  # every claim checked by hand against the sources above
        return {"verdicts": [{"id": f"{i}.{j}", "verdict": "supported", "reason": "matches cited source"}
                             for i, s in enumerate(SCRIPT["scenes"]) for j, _ in enumerate(s["claims"])]}
    if tool_name == "submit_metadata":
        return {"title": "What happens when NBA stars come back from brutal injuries?",
                "alt_titles": ["Next Paul George or next Gordon Hayward?", "4 NBA comebacks, by the numbers"],
                "platform_captions": {"tiktok": "4 comebacks from brutal injuries — by the numbers. Next PG or next Hayward? #nba #jalenwilliams #thunder",
                                      "instagram": "Before vs after: Wilkins, George, Hayward, Durant. Where does Jalen Williams land?\n#nba #okcthunder #nbastats",
                                      "facebook": "How did NBA stars play after brutal injuries? And what happens to Jalen Williams?"},
                "summary": "Dominique Wilkins, Paul George, Gordon Hayward and Kevin Durant: points per game before their "
                           "major injuries vs their first full season back. Now Jalen Williams faces the same road.",
                "keywords": ["jalen williams injury", "nba injury comebacks"], "tags": ["Jalen Williams", "Paul George",
                "Gordon Hayward", "Kevin Durant", "Dominique Wilkins", "NBA injuries", "NBA stats", "Thunder"],
                "hashtags": ["#JalenWilliams", "#Thunder"], "playlist": "Stat Breakdowns"}
    if tool_name == "submit_review":
        return {"value_score": 8, "script_quality": 8, "repetitive_ai_phrasing": [], "policy_concerns": [],
                "notes": "Timely hook, clear before/after data, strong closing question."}
    raise AssertionError(tool_name)

init_db(); sfx.ensure_library(); sfx.ensure_beat()
llm.structured = editor
commons.find_photo = lambda *a, **k: None   # photos can't be downloaded from this sandbox; badges are used
db = SessionLocal()
settings_store.update(db, "voice", {"speed": 1.08, "format_voice": {"career_stats": "warm_storyteller"}})
settings_store.update(db, "video", {"music_volume_db": -19})
settings_store.update(db, "shorts", {"max_seconds": 60})
t = Topic(title=SCRIPT["title"], format="career_stats", players=[], why_watch="timely", main_event="injury comebacks")
db.add(t); db.commit()
v = Video(kind="short", topic_id=t.id, working_title=SCRIPT["title"], research={"bibliography": SRC, "notes": [], "format": "career_stats"})
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
