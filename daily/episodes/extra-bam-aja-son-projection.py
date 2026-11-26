"""EXTRA (not on the daily schedule): "What would Bam & A'ja's son average?" — theoretical, just for fun.

Made Nov 25, 2026. Real numbers only; the "projection" is clearly labelled joke math.
Sources checked Nov 25: Basketball-Reference (Bam), WNBA.com 2026 MVP release (A'ja), AP/NPR (83-point game).
The couple have said kids are "in their future"; nothing is announced, and the description says so.
"""
from app.providers import wiki_stats

THRU = "Nov 24, 2026"


def P(sid, name, url, team, rows, career=None, title=None):
    st = {"player": name, "team": team,
          "rows": [{"season": s, "team": team, **stats, "champion": False, "led_league": {}} for s, stats in rows],
          "career": career, "url": url, "revid": None, "permalink": url}
    src = wiki_stats.as_source(st, sid, "2026-11-25")
    src["title"] = title or f"{name} (checked 2026-11-25)"
    return src


SRC = [
    P("P1", "Bam Adebayo", "https://www.basketball-reference.com/players/a/adebaba01.html", "Miami",
      [("2026–27", {"GP": 16, "PPG": 19.2})], career={"Career PPG": 16.3, "Height in": 81},
      title=f"Bam Adebayo — Basketball-Reference (6-9; career 16.3 PPG; 2026-27 19.2 PPG through {THRU})"),
    P("P2", "A'ja Wilson", "https://wnba.com/news/wilson-named-2026-most-valuable-player", "Las Vegas",
      [("2026", {"PPG": 26.2})], career={"Career PPG": 22.1, "Height in": 76, "MVP": 5},
      title="A'ja Wilson — WNBA.com 2026 MVP release (6-4; record 5th MVP; 22.1 career PPG, highest in WNBA history)"),
    P("G1", "Bam Adebayo", "https://www.npr.org/2026/03/11/g-s1-113255/bam-heats-adebayo-scores-83-points-2nd-only-to-wilt-chamberlain-in-nba-history",
      "Miami", [("Mar 10, 2026", {"PTS": 83})], title="AP/NPR: Adebayo 83 points, 2nd only to Wilt Chamberlain's 100"),
    {**P("J1", "Projection", "https://www.basketball-reference.com/players/a/adebaba01.html", "Miami",
         [("projection", {"PPG": 19.2})],
         title="Joke math: (Bam career 16.3 + A'ja career 22.1) / 2 = 19.2, from P1 and P2"), "no_photo": True},
    {"id": "H1", "url": "https://en.wikipedia.org/wiki/Mid-parental_height", "cited": True, "tier": 3,
     "title": "Mid-parental height (Tanner method): boys = (father + mother + 5 in) / 2",
     "excerpts": ["(81 in + 76 in + 5 in) / 2 = 81 in = 6 ft 9 in"]},
]


def c(claim, *ids):
    return {"claim": claim, "source_ids": list(ids), "certainty": "established"}


BOTH = ["Bam Adebayo", "A'ja Wilson"]
SCRIPT = {
    "title": "What would Bam and A'ja's son average?", "logline": "Theoretical. Just for fun. Real numbers.",
    "format": "hypothetical", "mood": "funny", "narrated": True, "pronunciations": {},
    "look": {"team": "Miami", "watermark": "83"},
    "style_bible": {"art_direction": "", "characters": [], "locations": []},
    "scenes": [
        {"section": "hook", "sfx": "boom",
         "narration": "Bam Adebayo and A'ja Wilson might be the most stacked gene pool in basketball. So, just for fun, what would their son average?",
         "visual": {"type": "hype_text", "camera": "none", "kicker": "Theoretical · just for fun",
                    "text": "WHAT WOULD BAM & A'JA'S SON AVERAGE?",
                    "chart": {"players": BOTH, "broll": "basketball game"}},
         "claims": []},
        {"section": "build", "sfx": "whoosh",
         "narration": "First, the parents. Bam averages 16.3 for his career. A'ja is at 22.1, the best career average in WNBA history. Sorry, Bam.",
         "visual": {"type": "head_to_head", "camera": "none", "chart": {
             "source_ids": ["P1", "P2"], "stat": "Career PPG", "title": "WHO SCORES MORE AT HOME?",
             "subtitle": "Career points per game"}},
         "claims": [c("Bam career 16.3 PPG; A'ja career 22.1 PPG, highest in WNBA history", "P1", "P2")]},
        {"section": "build", "sfx": "riser",
         "narration": "But Bam did drop 83 in one game. Only Wilt has ever scored more.",
         "visual": {"type": "big_number", "camera": "punch", "chart": {
             "source_id": "G1", "season": "Mar 10, 2026", "stat": "PTS", "title": "BAM ADEBAYO",
             "label": "points in one game", "context": "Only Wilt's 100 is higher · Mar 10, 2026"}},
         "claims": [c("Bam scored 83 on Mar 10, 2026, second only to Wilt Chamberlain's 100", "G1")]},
        {"section": "build", "sfx": "whoosh",
         "narration": "And A'ja has five MVPs. Nobody in WNBA history has more.",
         "visual": {"type": "big_number", "camera": "punch", "chart": {
             "source_id": "P2", "season": "career", "stat": "MVP", "title": "A'JA WILSON",
             "label": "WNBA MVPs", "context": "The most in league history"}},
         "claims": [c("A'ja Wilson has a record five WNBA MVPs", "P2")]},
        {"section": "build", "sfx": "whoosh",
         "narration": "Plug their heights into the doctors' growth formula, and their son lands around six-nine. Same as dad.",
         "visual": {"type": "hype_text", "camera": "none", "kicker": "Real doctor math",
                    "text": "PROJECTED HEIGHT: 6'9\"", "chart": {"players": BOTH}},
         "claims": [c("Bam 6-9, A'ja 6-4; mid-parental formula (81+76+5)/2 = 81 in = 6-9", "P1", "P2", "H1")]},
        {"section": "payoff", "sfx": "ding",
         "narration": "Now average the parents. 19.2 points a game. Which is exactly what Bam is averaging this season. So the kid's already his dad.",
         "visual": {"type": "big_number", "camera": "punch", "chart": {
             "source_id": "J1", "season": "projection", "stat": "PPG", "title": "THE PROJECTION",
             "label": "points per game", "context": "(16.3 + 22.1) / 2 · very scientific"}},
         "claims": [c("(16.3 + 22.1) / 2 = 19.2; Bam's 2026-27 average is 19.2 PPG", "J1", "P1")]},
        {"section": "build", "sfx": "scratch",
         "narration": "Pray for whoever has to guard him in middle school.",
         "visual": {"type": "hype_text", "camera": "none", "kicker": "Thoughts & prayers",
                    "text": "POV: YOU HAVE TO GUARD HIM AT RECESS", "chart": {"broll": "basketball game"}},
         "claims": []},
        {"section": "question", "sfx": "pop",
         "narration": "What's your projection? Drop it below.",
         "visual": {"type": "hype_text", "camera": "none", "kicker": "Your call",
                    "text": "WHAT'S YOUR PROJECTION?", "chart": {"players": BOTH}},
         "claims": []},
    ],
    "engagement_question": "What's your projection?", "trending_sound_fit": False,
}

FORMAT = "hypothetical"
PLAYERS = BOTH
META = {
    "title": "What Would Bam & A'ja's Son Average? 🧬🏀",
    "description": ("Just for fun: Bam Adebayo (16.3 career PPG, an 83-point game) + A'ja Wilson (record 5 MVPs, "
                    "22.1 career PPG, best in WNBA history). Very scientific projection inside. "
                    "A hypothetical only, nothing has been announced. What's your projection? 👇\n\n"
                    f"Stats: Basketball-Reference, WNBA.com, AP, through {THRU}.\n\n"
                    "#NBA #WNBA #BamAdebayo #AjaWilson #Shorts"),
    "tags": ["Bam Adebayo", "A'ja Wilson", "Miami Heat", "Las Vegas Aces", "NBA", "WNBA", "NBA stats", "funny NBA"],
}
