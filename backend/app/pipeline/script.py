"""Basketball Shorts script generation: 7 formats, hook-first, verified numbers only."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import settings_store
from ..models import Clip, Scene, Video
from ..providers import llm
from . import research as research_mod

FORMATS = ["career_stats", "comparison", "recap", "fact", "storyline", "ranking", "news_reaction", "meme",
           "hypothetical"]
SFX = ["", "whoosh", "boom", "ding", "buzzer", "pop", "riser", "swish", "crowd", "scratch", "airhorn"]

VISUAL = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ["comeback_card", "slope", "season_bars", "line_compare", "big_number",
                                            "leaderboard", "head_to_head", "tally", "hype_text", "all_time_rank", "stat_card",
                                            "scoreboard", "photo", "big_text", "ranking", "meme", "reaction",
                                            "illustration", "clip"],
                 "description": "DATA CHARTS (preferred for stats formats; numbers are filled in from the data, "
                                "you only choose what to show): season_bars=one player's stat for every season as "
                                "animated bars (use reveal_to_season across consecutive scenes to build the chart "
                                "up while you narrate); line_compare=2–4 players' stat by season-in-league; "
                                "big_number=one verified number counting up; leaderboard=last night's top performers "
                                "(recap); comeback_card=one player's BEFORE vs AFTER seasons (e.g. around an injury, "
                                "a trade, a new coach) with player icon, event tag and +/- changes; slope=several "
                                "players' before→after on one chart; head_to_head=2–5 players' career totals (or one season via chart.season) for ONE stat as racing bars with a crown on the leader (chart.stat, chart.source_ids; chart.loss_stat for W–L records like Finals); tally=final scorecard of several categories (chart.categories=[{label, stat, loss_stat?}]) counting categories won; all_time_rank=all-time leaderboard from an L# source with this season's entry highlighted (chart.source_id, chart.highlight={player, season}, chart.top); hype_text=kinetic headline card (text, kicker) on the animated background. OTHER: meme=top/bottom-text meme over an original AI image; reaction=caption box ('POV:', "
                                "'When…') over an AI reaction image; big_text=punchline text card; illustration="
                                "full-screen AI image; stat_card=animated comparison of real numbers; scoreboard="
                                "a real final score from the data sources; ranking=big '#N' reveal; photo=a freely "
                                "licensed real photo of a real player (Wikimedia Commons); clip=one of the user's "
                                "licensed clips"},
        "image_prompt": {"type": "string", "description": "For meme/reaction/illustration/ranking: an ORIGINAL cartoon "
                         "scene with FICTIONAL generic players (describe jersey colours, expressions, situation). "
                         "Never name or depict a real person, real team logo or real arena."},
        "top_text": {"type": "string"}, "bottom_text": {"type": "string"},
        "caption": {"type": "string", "description": "reaction/photo/clip caption text"},
        "text": {"type": "string", "description": "big_text punchline (<= 8 words)"},
        "stat": {"type": "object", "properties": {
            "title": {"type": "string"}, "left_name": {"type": "string"}, "right_name": {"type": "string"},
            "rows": {"type": "array", "maxItems": 4, "items": {"type": "object", "properties": {
                "label": {"type": "string"}, "left": {"type": "string"}, "right": {"type": "string"},
                "lower_is_better": {"type": "boolean"}}, "required": ["label", "left", "right"]}},
            "source_ids": {"type": "array", "items": {"type": "string"}}}},
        "scoreboard": {"type": "object", "properties": {"headline": {"type": "string"},
                                                        "game_source_id": {"type": "string"}}},
        "ranking": {"type": "object", "properties": {"rank": {"type": "integer"}, "item": {"type": "string"}}},
        "photo_query": {"type": "string", "description": "For photo: the real player's full name"},
        "clip": {"type": "object", "properties": {"clip_id": {"type": "integer"}, "start": {"type": "number"},
                                                  "end": {"type": "number"}}},
        "chart": {"type": "object", "properties": {
            "source_id": {"type": "string", "description": "P# (player table) or R# (recap data) id"},
            "source_ids": {"type": "array", "items": {"type": "string"}, "description": "line_compare/head_to_head/tally: P# ids"},
            "loss_stat": {"type": "string", "description": "head_to_head: losses key for a W–L record, e.g. 'Finals L'"},
            "note": {"type": "string"},
            "players": {"type": "array", "items": {"type": "string"},
                        "description": "hype_text: player names whose licensed photos pop in under the headline"},
            "broll": {"type": "string", "description": "hype_text: Wikimedia Commons search for licensed basketball "
                      "b-roll shown blurred behind the text (generic motion only, never a specific player/game)"},
            "tone": {"type": "string", "enum": ["injury", "positive"], "description": "comeback_card tag colour"},
            "before_head": {"type": "string", "description": "comeback_card column header, e.g. 'LAST SEASON'"},
            "after_head": {"type": "string", "description": "comeback_card column header, e.g. 'THIS SEASON'"},
            "categories": {"type": "array", "items": {"type": "object", "properties": {
                "label": {"type": "string"}, "stat": {"type": "string"}, "loss_stat": {"type": "string"}}}},
            "stat": {"type": "string", "description": "Column name exactly as in the data: PPG, RPG, APG, SPG, "
                                                      "BPG, FG%, 3P%, FT%, MPG, GP (recap: pts, reb, ast)"},
            "season": {"type": "string", "description": "big_number: season label exactly as in data, or 'career'"},
            "reveal_to_season": {"type": "string"}, "highlight": {"type": "array", "items": {"type": "string"}},
            "show_career_average": {"type": "boolean"},
            "before_season": {"type": "string", "description": "comeback_card/slope: season label or 'career'"},
            "after_season": {"type": "string", "description": "comeback_card/slope: season label, or '?' if unknown"},
            "before_label": {"type": "string"}, "after_label": {"type": "string"},
            "event": {"type": "string", "description": "comeback_card tag, e.g. 'Ruptured Achilles' (a claim!)"},
            "when": {"type": "string", "description": "comeback_card tag date, e.g. 'Jan 1992' (a claim!)"},
            "stats": {"type": "array", "items": {"type": "string"}, "description": "comeback_card rows, e.g. "
                      "['PPG','FG%','RPG'] (max 3)"},
            "items": {"type": "array", "items": {"type": "object", "properties": {
                "source_id": {"type": "string"}, "before_season": {"type": "string"},
                "after_season": {"type": "string"}}}, "description": "slope: one entry per player"},
            "timeline": {"type": "array", "items": {"type": "integer"},
                         "description": "Years of every event in the video, for the era strip"},
            "year": {"type": "integer"},
            "team": {"type": "string", "description": "comeback_card: team at the time of the event (icon colours)"},
            "title": {"type": "string"}, "subtitle": {"type": "string"}, "label": {"type": "string"},
            "context": {"type": "string"}}},
        "camera": {"type": "string", "enum": ["punch", "push_in", "pull_out", "pan_left", "pan_right", "drift"]},
    },
    "required": ["type", "camera"],
}

SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "logline": {"type": "string"},
        "format": {"type": "string", "enum": FORMATS},
        "mood": {"type": "string", "enum": ["hype", "funny", "chill", "dramatic", "suspense"]},
        "narrated": {"type": "boolean", "description": "false = text-only meme with music + sound effects"},
        "style_bible": {"type": "object", "properties": {
            "art_direction": {"type": "string"},
            "characters": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string", "description": "fictional character label, e.g. 'the hooper in red'"},
                "look": {"type": "string"}}, "required": ["name", "look"]}},
            "locations": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string"}, "look": {"type": "string"}}, "required": ["name", "look"]}}},
            "required": ["art_direction", "characters", "locations"]},
        "pronunciations": {"type": "object", "additionalProperties": {"type": "string"}},
        "look": {"type": "object", "description": "Animated background colours: team = the main player's team "
                 "(its colours tint the glows); watermark = optional big faint jersey number",
                 "properties": {"team": {"type": "string"}, "watermark": {"type": "string"}}},
        "scenes": {"type": "array", "items": {"type": "object", "properties": {
            "section": {"type": "string", "enum": ["hook", "setup", "build", "punchline", "payoff", "question"]},
            "chapter": {"type": "string"},
            "narration": {"type": "string", "description": "Spoken line (empty string for text-only scenes)"},
            "hold_seconds": {"type": "number", "description": "Text-only scenes: how long to hold (1.2–3.5)"},
            "visual": VISUAL,
            "on_screen_text": {"type": "string"},
            "sfx": {"type": "string", "enum": SFX},
            "claims": {"type": "array", "items": {"type": "object", "properties": {
                "claim": {"type": "string"}, "source_ids": {"type": "array", "items": {"type": "string"}},
                "certainty": {"type": "string", "enum": ["established", "probable", "disputed", "legend"]}},
                "required": ["claim", "source_ids", "certainty"]},
                "description": "EVERY factual statement in narration OR on-screen text (stats, scores, records, "
                               "dates, events) with its source ids. Jokes/hypotheticals are not claims."},
            "quotes": {"type": "array", "items": {"type": "object", "properties": {
                "text": {"type": "string"}, "speaker": {"type": "string"}, "source_id": {"type": "string"}},
                "required": ["text", "speaker", "source_id"]}}},
            "required": ["section", "narration", "visual", "claims"]}},
        "engagement_question": {"type": "string"},
        "trending_sound_fit": {"type": "boolean", "description": "Would a trending song suit this better than our "
                                                                 "music bed? (you can add one in the YouTube app)"},
    },
    "required": ["title", "logline", "format", "mood", "narrated", "style_bible", "pronunciations", "scenes"],
}

SYSTEM = """You write basketball stats Shorts (think animated stat breakdowns and career races) — clear,
fast, surprising, and 100% accurate. Lead with the most surprising number, then show the data.
For stats formats, use data charts: build ONE season_bars chart across 3–5 consecutive scenes (each scene
reveals more seasons with reveal_to_season while you narrate the key seasons), then land on a big_number or
career average. Narration states numbers exactly as in the data (e.g. "30.1 points a game").

You also write occasional funny/fast basketball Shorts:

Voice: a hooper who's chronically online — quick, playful, confident, specific. Short punchy lines.
No "Did you know", no "In this video", no "Let's dive in", no "buckle up", no "absolutely", no tired
"bro really thought" chains, no explaining the joke. Vary rhythm. Land the punchline on its own beat.

Structure: HOOK in the first second (the funniest image, the wildest number, or the hottest take) →
setup → build/escalate → punchline/payoff → optional one-line engagement question (not "like and subscribe").

Formats:
- meme: setup / escalation / punchline; usually text-only (narrated=false) with top/bottom-text or POV
  reaction scenes, sound-effect hits and music. Relatable hooper humour (pickup games, rec league, fans).
- career_stats: one player's career told through a season-by-season chart: the rise, the peak, the dip,
  the comeback. Mark championship seasons and league-leading seasons only if the data marks them.
- comparison: 2–4 players — line_compare of career arcs and/or a stat_card; any verdict is clearly opinion.
- recap: last night's top performers (leaderboard from R# data) + the one stat that matters.
- fact: one jaw-dropping verified fact/stat, built up and paid off.
- storyline: an interesting current development, explained fast with the real numbers/scores.
- ranking: countdown with ranking reveals; funny but each item real if it claims to be real.
- hypothetical: "what if…" — clearly framed as imagination; no fake facts.
- news_reaction: real news with verified facts, then the funny take.

FLOW (the narration must sound like ONE continuous take, not a list of captions):
- Read all scene lines in a row before submitting: they must flow as connected speech. A scene line may be part
  of a sentence that continues into the next scene (end it without punctuation, e.g. "and by 2014-15 he was"
  → next scene "a champion.").
- Vary sentence length; use connective words (so, but, and then, which means, here's the thing).
- No one-word fragments, no "Then X." / "Next season?" stubs, no repeating the on-screen title out loud.
- Say seasons naturally ("the 2015-16 season", "that year"); round nothing — use the exact data values.

HOST PERSONA (when the format calls for hot takes): an ORIGINAL loud sports-debate host — big declarations,
rhetorical questions, emphasis on the numbers ("Thirty. Point. One."), playful outrage. Never imitate or name a
real broadcaster, never use a real person's catchphrases.

HARD RULES (non-negotiable):
- Every number, score, record, date, trade, injury or news fact must come from the provided sources and be
  listed in claims with source ids. If the sources don't have it, don't say it.
- Never invent quotes. Never write lines as if a real player said them, never impersonate an athlete.
- AI images show FICTIONAL generic players only (no real names, faces, logos or arenas in image prompts).
  Real players appear only via photo scenes (licensed photos) or stat/scoreboard cards.
- Roast plays and situations, not people's bodies, families, race, or personal lives. No harassment.
- Scenes are 1–2 seconds of text or ONE short spoken sentence. Change the visual every scene.
- Total length must fit the target. Text in images must be short enough to read in the hold time."""


def generate(db: Session, video: Video, revision_notes: str = "") -> dict:
    sh = settings_store.get(db, "shorts")
    lo, hi = sh["target_seconds"]
    secs = (lo + hi) / 2
    topic = video.topic
    fmt = (topic.format if topic and topic.format else "") or "meme"
    clips = db.query(Clip).filter(Clip.attested_by_user.is_(True)).order_by(Clip.id.desc()).limit(30).all()
    clip_txt = "\n".join(f"- clip_id {c.id}: {c.title} ({c.duration_s:.0f}s) — {c.description[:150]}" for c in clips) \
        or "(none uploaded — don't use clip scenes)"
    prev = ""
    if revision_notes:
        prev = ("\n\nPREVIOUS DRAFT (revise; keep what works):\n" + llm.to_json(video.script) +
                "\n\nFACT-CHECK ISSUES TO FIX (correct or cut every one):\n" + revision_notes)
    brief = (f"Format: {fmt}\nIdea: {topic.title}\nAngle: {topic.why_watch}\nContext: {topic.main_event}"
             if topic else f"Format: {fmt}\nIdea: {video.working_title}")
    return llm.structured(
        db, video_id=video.id, category="script", tool_name="submit_script", schema=SCRIPT_SCHEMA, system=SYSTEM,
        max_tokens=12000, est_usd=0.3, note="script" + (" revision" if revision_notes else ""),
        prompt=(f"{brief}\n\nTarget: {lo}-{hi} seconds (aim ~{secs:.0f}s): narrated ≈ {int(secs * 2.6)} words, "
                f"or text-only ≈ {max(5, int(secs / 2.2))} scenes.\n\nUSER'S LICENSED CLIPS:\n{clip_txt}\n\n"
                f"SOURCES (only these may back facts; ids like S1, D1):\n{research_mod.dossier_text(video.research)}"
                f"{prev}"))


def save_scenes(db: Session, video: Video, script: dict) -> None:
    video.script = script
    video.working_title = script.get("title") or video.working_title
    video.scenes.clear()
    db.flush()
    for i, s in enumerate(script["scenes"]):
        hold = float(s.get("hold_seconds") or 0)
        video.scenes.append(Scene(idx=i, section=s["section"], narration=(s.get("narration") or "").strip(),
                                  visual={**s["visual"], "chapter": s.get("chapter", ""),
                                          "hold_seconds": max(1.0, min(4.0, hold or 2.0))},
                                  on_screen_text=(s.get("on_screen_text") or "")[:200], sfx=s.get("sfx") or ""))
    db.commit()


def word_count(script: dict) -> int:
    return sum(len((s.get("narration") or "").split()) for s in script.get("scenes", []))
