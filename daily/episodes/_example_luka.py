"""EXAMPLE episode (Luka scoring pace, 2026-11-25). Copy this shape for each daily episode."""
from app.providers import wiki_stats

# ---- Data verified 2026-11-25: Basketball-Reference single-season PPG leaders page + Luka's player page.
def P(sid, name, url, team, rows, career=None):
    st = {"player": name, "team": team, "rows": [{"season": s, "team": tm, "GP": g, "PPG": p, "RPG": r, "APG": a,
          "FG%": fg, "champion": False, "led_league": ({"PPG": True} if led else {})}
          for s, tm, g, p, r, a, fg, led in rows], "career": career, "url": url, "revid": None, "permalink": url}
    src = wiki_stats.as_source(st, sid, "2026-11-25")
    src["title"] = f"{name} — per-game stats (Basketball-Reference, checked 2026-11-25)"
    return src
LEAD = [  # rank, player, season, PPG, team (colours only)
 (1, "Wilt Chamberlain", "1961–62", 50.4, ""), (2, "Wilt Chamberlain", "1962–63", 44.8, ""),
 (3, "Wilt Chamberlain", "1960–61", 38.4, ""), (4, "Wilt Chamberlain", "1959–60", 37.6, ""),
 (5, "Michael Jordan", "1986–87", 37.1, "Chicago"), (6, "Wilt Chamberlain", "1963–64", 36.9, ""),
 (7, "Luka Dončić", "2026–27", 36.6, "Lakers"), (8, "James Harden", "2018–19", 36.1, "Houston"),
 (9, "Rick Barry", "1966–67", 35.6, ""), (10, "Kobe Bryant", "2005–06", 35.4, "Lakers")]
SRC = [
 P("P1", "Luka Dončić", "https://www.basketball-reference.com/players/d/doncilu01.html", "Lakers",
   [("2023–24", "Dallas", 70, 33.9, 9.2, 9.8, .487, True), ("2024–25", "Dallas/Lakers", 50, 28.2, 8.2, 7.7, .450, False),
    ("2025–26", "Lakers", 64, 33.5, 7.7, 8.3, .476, True), ("2026–27", "Lakers", 16, 36.6, 6.6, 7.7, .460, False)],
   career={"PPG": 29.4}),
 {"id": "L1", "url": "https://www.basketball-reference.com/leaders/pts_per_g_season.html", "cited": True, "tier": 2,
  "title": "Basketball-Reference: single-season leaders, points per game (checked 2026-11-25)",
  "leaders": [{"rank": r, "player": p, "season": s, "value": v, "team": t} for r, p, s, v, t in LEAD],
  "excerpts": [f"{r}. {p} {s}: {v}" for r, p, s, v, t in LEAD]},
 {"id": "P2", "url": "https://www.basketball-reference.com/leaders/pts_per_g_season.html", "cited": True, "tier": 2,
  "title": "Single-season PPG (Basketball-Reference)",
  "player_stats": None, "excerpts": ["James Harden 36.13 (2018-19); Kobe Bryant 35.40 (2005-06); Luka Dončić 36.62 (2026-27)"]},
]
for sid, name, team, val in (("H1", "Luka Dončić", "Lakers", 36.6), ("H2", "James Harden", "Houston", 36.1),
                             ("H3", "Kobe Bryant", "Lakers", 35.4)):
    SRC.append(P(sid, name, "https://www.basketball-reference.com/leaders/pts_per_g_season.html", team,
                 [("best", team, None, None, None, None, None, False)], career={"Season PPG": val}))
SRC = [x for x in SRC if x["id"] != "P2"]
def c(claim, *ids):
    return {"claim": claim, "source_ids": list(ids), "certainty": "established"}

SCRIPT = {
 "title": "Luka is having one of the greatest scoring seasons EVER", "logline": "36.6 PPG, 7th all-time.",
 "format": "career_stats", "mood": "hype", "narrated": True, "pronunciations": {},
 "look": {"team": "Lakers", "watermark": "77"},
 "style_bible": {"art_direction": "", "characters": [], "locations": []},
 "scenes": [
  {"section": "hook", "sfx": "boom",
   "narration": "Luka Dončić is averaging 36.6 points a game. Only six seasons in NBA history were higher.",
   "visual": {"type": "hype_text", "camera": "none", "kicker": "Lakers · 2026–27", "text": "36.6 PPG. TOP 7 EVER.",
              "chart": {}},
   "claims": [c("Luka 36.6 PPG in 2026-27, 7th-highest single-season PPG", "P1", "L1")]},
  {"section": "build", "sfx": "whoosh",
   "narration": "Five of them belong to Wilt Chamberlain. The other is Michael Jordan's 37.1 in 1987.",
   "visual": {"type": "all_time_rank", "camera": "none", "chart": {"source_id": "L1", "top": 8,
              "highlight": {"player": "Luka Dončić", "season": "2026–27"}, "title": "BEST SCORING SEASONS EVER",
              "subtitle": "Points per game, single season", "note": "2026–27 through Nov 24 (16 games)"}},
   "claims": [c("Top 6: Wilt x5 and Jordan 37.1 (1986-87)", "L1")]},
  {"section": "build", "sfx": "whoosh",
   "narration": "That puts him ahead of James Harden's 36.1 and Kobe's 35.4.",
   "visual": {"type": "head_to_head", "camera": "none", "chart": {"source_ids": ["H1", "H2", "H3"], "stat": "Season PPG",
              "title": "BEST SEASON", "subtitle": "Points per game"}},
   "claims": [c("Harden 36.1 (2018-19), Kobe 35.4 (2005-06)", "L1")]},
  {"section": "build", "sfx": "riser",
   "narration": "And it's up from the 33.5 that won him the scoring title last season.",
   "visual": {"type": "season_bars", "camera": "none", "chart": {"source_id": "P1", "stat": "PPG",
              "highlight": ["2026–27"], "title": "LUKA: POINTS PER GAME", "subtitle": "Last four seasons"}},
   "claims": [c("2025-26: 33.5 PPG, scoring title", "P1")]},
  {"section": "payoff", "sfx": "scratch",
   "narration": "The catch? It's only 16 games. But if it holds, it's the best scoring season since Jordan.",
   "visual": {"type": "hype_text", "camera": "none", "kicker": "The catch", "text": "ONLY 16 GAMES IN", "chart": {}},
   "claims": [c("16 games played; no season above 36.6 since Jordan's 37.1 in 1986-87", "P1", "L1")]},
  {"section": "question", "sfx": "pop",
   "narration": "So can Luka keep this up all season?",
   "visual": {"type": "hype_text", "camera": "none", "kicker": "Your call", "text": "CAN HE KEEP IT UP?", "chart": {}},
   "claims": []},
 ],
 "engagement_question": "Can Luka keep it up?", "trending_sound_fit": False,
}


FORMAT = "career_stats"
PLAYERS = ["Luka Dončić"]
META = {
    "title": "Luka Is Having One of the Greatest Scoring Seasons EVER 🔥",
    "description": ("Luka Dončić is averaging 36.6 points per game through 16 games of 2026-27, the 7th-highest "
                    "single-season mark in NBA history, behind five Wilt Chamberlain seasons and Michael Jordan's 37.1 "
                    "(1986-87). Can he keep it up all season? 👇\n\nStats: Basketball-Reference, through Nov 24, 2026."
                    "\n\n#NBA #Lakers #LukaDoncic #Shorts"),
    "tags": ["Luka Doncic", "Lakers", "Michael Jordan", "Wilt Chamberlain", "James Harden", "Kobe Bryant", "NBA stats"],
}
