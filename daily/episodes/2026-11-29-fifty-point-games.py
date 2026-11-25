"""Sunday Nov 29, 2026 — "7 fifty-point games already" (week-in-numbers slot, extra flashy).

PREPARED IN ADVANCE on Wed Nov 25 (photos + b-roll on) with data through Nov 24. The Sunday run MUST refresh every number below
(new 50-point games, scoring leaders, best records), update claims/narration/description to match, then render
and publish. Sources checked Nov 25:
- 50-point games: Yahoo Sports list (updated Nov 23) cross-checked with NBA.com, SI, Eurohoops, Field Level Media.
  An NBA.com recap mentions a Wembanyama "54-point career high" that no other source lists — not used.
- Scoring leaders + standings: Basketball-Reference 2026-27 per-game and standings pages (revised Nov 24).
"""
from app.providers import wiki_stats

THRU = "Nov 24, 2026"


def P(sid, name, url, team, rows):
    st = {"player": name, "team": team,
          "rows": [{"season": s, "team": team, **stats, "champion": False, "led_league": {}} for s, stats in rows],
          "career": None, "url": url, "revid": None, "permalink": url}
    src = wiki_stats.as_source(st, sid, "2026-11-25")
    src["title"] = f"{name} — {rows[0][0]} box score line"
    return src


FIFTY = [  # rank, player, "date · opponent", points, team (colours)
    (1, "Luka Dončić", "Nov 6 · at POR", 53, "Lakers"),
    (2, "Victor Wembanyama", "Nov 4 · vs DAL", 52, "San Antonio"),
    (3, "Cade Cunningham", "Nov 12 · at WAS", 52, "Detroit"),
    (4, "Luka Dončić", "Oct 25 · at UTA", 52, "Lakers"),
    (5, "James Harden", "Nov 20 · vs IND", 51, "Cleveland"),
    (6, "Victor Wembanyama", "Nov 21 · vs NOP", 50, "San Antonio"),
    (7, "Tyler Herro", "Nov 21 · vs PHI", 50, "Milwaukee"),
]
SCORERS = [  # min. 15 games played
    (1, "Luka Dončić", "Lakers · 16 games", 36.6, "Lakers"),
    (2, "Shai Gilgeous-Alexander", "Thunder · 17 games", 32.1, "Oklahoma City"),
    (3, "Victor Wembanyama", "Spurs · 17 games", 29.9, "San Antonio"),
    (4, "Giannis Antetokounmpo", "Heat · 15 games", 28.2, "Miami"),
    (5, "Jalen Brunson", "Knicks · 17 games", 26.5, "New York"),
]

SRC = [
    {"id": "L1", "url": "https://au.news.yahoo.com/nba-50-point-games-season-154329021.html", "cited": True, "tier": 2,
     "title": "NBA 50-point games this season (Yahoo Sports, updated Nov 23, 2026)",
     "leaders": [{"rank": r, "player": p, "season": s, "value": v, "team": t} for r, p, s, v, t in FIFTY],
     "excerpts": [f"{p} {v} ({s})" for r, p, s, v, t in FIFTY] + ["Total 50-point games: 7"]},
    {"id": "L2", "url": "https://www.basketball-reference.com/leagues/NBA_2027_per_game.html", "cited": True,
     "tier": 2, "title": f"Basketball-Reference 2026-27 per game (through {THRU})",
     "leaders": [{"rank": r, "player": p, "season": s, "value": v, "team": t} for r, p, s, v, t in SCORERS],
     "excerpts": [f"{p} {v} PPG ({s})" for r, p, s, v, t in SCORERS]},
    P("C1", "Cade Cunningham", "https://www.nba.com/news/cade-cunningham-50-points-no-turnovers-pistons-wizards",
      "Detroit", [("Nov 12, 2026", {"PTS": 52, "AST": 11, "TOV": 0})]),
    P("W1", "Victor Wembanyama", "https://www.eurohoops.net/en/nba-news/2030924/", "San Antonio",
      [("Nov 4, 2026", {"PTS": 52, "TRB": 24, "BLK": 8})]),
    {"id": "N1", "url": "https://www.nba.com/news/cade-cunningham-50-points-no-turnovers-pistons-wizards", "cited": True,
     "tier": 1, "title": "NBA.com: Cunningham 50+ pts, 10+ ast, zero turnovers",
     "excerpts": ["first player in NBA history to record a 50+ point, 10+ assist game with zero turnovers",
                  "Field Level Media: since individual turnovers began being tracked in 1977-78"]},
    {"id": "N2", "url": "https://www.eurohoops.net/en/nba-news/2030924/", "cited": True, "tier": 2,
     "title": "Eurohoops / NBA.com: Wembanyama 52-24-8",
     "excerpts": ["second player since blocks became official in 1973-74 with at least 50 points, 20 rebounds, "
                  "and five blocks in a game, joining Bob McAdoo in 1974"]},
    {"id": "S1", "url": "https://www.basketball-reference.com/leagues/NBA_2027_standings.html", "cited": True,
     "tier": 2, "title": f"Basketball-Reference standings (through {THRU})",
     "excerpts": ["San Antonio Spurs 15-3", "Los Angeles Lakers 15-3"]},
]


def c(claim, *ids):
    return {"claim": claim, "source_ids": list(ids), "certainty": "established"}


SCRIPT = {
    "title": "7 fifty-point games already", "logline": "The season's first month, in its biggest numbers.",
    "format": "ranking", "mood": "hype", "narrated": True,
    "pronunciations": {"Giannis": "Yahnis", "Cunningham": "Cunninghum"},
    "look": {"team": "", "watermark": "50"},
    "style_bible": {"art_direction": "", "characters": [], "locations": []},
    "scenes": [
        {"section": "hook", "sfx": "boom",
         "narration": "We're barely a month into the season, and there have already been seven 50-point games.",
         "visual": {"type": "hype_text", "camera": "none", "kicker": "2026–27 · month one",
                    "text": "7 FIFTY-POINT GAMES ALREADY",
                    "chart": {"players": ["Luka Dončić", "Victor Wembanyama", "Cade Cunningham", "James Harden"],
                              "broll": "basketball game"}},
         "claims": [c("Seven 50-point games in 2026-27 so far", "L1")]},
        {"section": "build", "sfx": "whoosh",
         "narration": "Luka has the biggest, 53 in Portland, and he and Wemby have both done it twice.",
         "visual": {"type": "all_time_rank", "camera": "none", "chart": {
             "source_id": "L1", "top": 7, "decimals": 0, "highlight": {"player": "Luka Dončić", "season": "Nov 6 · at POR"},
             "title": "50-POINT GAMES THIS SEASON", "subtitle": "2026–27 regular season", "note": f"Through {THRU}"}},
         "claims": [c("Luka 53 at Portland Nov 6 is the highest; Luka and Wembanyama have two each", "L1")]},
        {"section": "build", "sfx": "riser",
         "narration": "Cade Cunningham scored 52 with 11 assists and zero turnovers, a first since the league started tracking them.",
         "visual": {"type": "big_number", "camera": "punch", "chart": {
             "source_id": "C1", "season": "Nov 12, 2026", "stat": "PTS", "title": "CADE CUNNINGHAM",
             "label": "points", "context": "11 assists · 0 turnovers · Nov 12"}},
         "claims": [c("Cunningham 52 pts, 11 ast, 0 TO on Nov 12; first 50/10/0-TO game since turnovers were tracked (1977-78)",
                      "C1", "N1")]},
        {"section": "build", "sfx": "whoosh",
         "narration": "Wemby's 52 came with 24 rebounds and 8 blocks. The last player to go 50, 20 and 5 was Bob McAdoo in 1974.",
         "visual": {"type": "big_number", "camera": "punch", "chart": {
             "source_id": "W1", "season": "Nov 4, 2026", "stat": "PTS", "title": "VICTOR WEMBANYAMA",
             "label": "points", "context": "24 rebounds · 8 blocks · Nov 4"}},
         "claims": [c("Wembanyama 52 pts, 24 reb, 8 blk on Nov 4; only Bob McAdoo (1974) had 50/20/5 before", "W1", "N2")]},
        {"section": "build", "sfx": "whoosh",
         "narration": "In the scoring race, Luka leads at 36.6, ahead of Shai at 32.1 and Wemby at 29.9.",
         "visual": {"type": "all_time_rank", "camera": "none", "chart": {
             "source_id": "L2", "top": 5, "decimals": 1, "highlight": {"player": "Luka Dončić", "season": "Lakers · 16 games"},
             "title": "SCORING LEADERS", "subtitle": "Points per game · min. 15 games", "note": f"Through {THRU}"}},
         "claims": [c("PPG leaders (15+ games): Luka 36.6, SGA 32.1, Wembanyama 29.9, Giannis 28.2, Brunson 26.5", "L2")]},
        {"section": "payoff", "sfx": "ding",
         "narration": "And the Spurs and Lakers share the best record in the league at 15 and 3.",
         "visual": {"type": "hype_text", "camera": "none", "kicker": "Best record", "text": "SPURS & LAKERS: 15–3",
                    "chart": {"players": ["Victor Wembanyama", "Luka Dončić"], "broll": "basketball game"}},
         "claims": [c("Spurs and Lakers both 15-3, best record", "S1")]},
        {"section": "question", "sfx": "pop",
         "narration": "So who drops the next 50? Drop a name.",
         "visual": {"type": "hype_text", "camera": "none", "kicker": "Your call", "text": "WHO DROPS THE NEXT 50?",
                    "chart": {"players": ["Tyler Herro", "James Harden", "Cade Cunningham"], "broll": "basketball game"}},
         "claims": []},
    ],
    "engagement_question": "Who drops the next 50?", "trending_sound_fit": False,
}

FORMAT = "ranking"
PLAYERS = ["Luka Dončić", "Victor Wembanyama", "Cade Cunningham", "James Harden", "Tyler Herro"]
META = {
    "title": "7 Fifty-Point Games Already This Season 🔥",
    "description": ("A month into 2026-27, the NBA has already seen seven 50-point games: Luka Dončić (twice), "
                    "Victor Wembanyama (twice), Cade Cunningham, James Harden and Tyler Herro. Plus the scoring race "
                    "and the league's best records. Who drops the next 50? 👇\n\n"
                    f"Stats: Basketball-Reference, NBA.com, through {THRU}.\n\n#NBA #NBAStats #Wembanyama #Luka #Shorts"),
    "tags": ["NBA 50 point games", "Luka Doncic", "Victor Wembanyama", "Cade Cunningham", "James Harden",
             "Tyler Herro", "NBA scoring leaders", "NBA stats"],
}
