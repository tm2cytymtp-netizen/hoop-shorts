"""Historical research: several web-search-grounded passes, a ranked bibliography built
ONLY from sources the search tool actually returned, and a dossier of cited excerpts."""
from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy.orm import Session

from ..events import emit
from ..models import Video
from ..providers import llm

SYSTEM = (
    "You are a meticulous basketball researcher. Use official league records, team sites, reputable outlets "
    "and reference sites; give exact numbers with their season. Also: "
    "Prioritise, in order: primary documents and archives; university and academic publications; museums; "
    "government archives; reputable history publications and encyclopaedias. Avoid forums, content farms "
    "and AI-generated sites. Separate established fact from interpretation and speculation, name where "
    "historians disagree, and record exact dates, names and places. Only report a quotation if a source you "
    "found reproduces it verbatim, and say who said it, when, and where it is recorded. Cite everything."
)

PASSES = [
    ("overview", "Give a thorough overview of: {topic}. Context, causes, key people, places, chronology, outcome."),
    ("chronology", "Build a precise dated chronology for: {topic}. Verify each date, name and location "
                   "against at least two reputable sources where possible; flag conflicts."),
    ("debates", "For: {topic} — what is uncertain, disputed or legendary? What do historians disagree on, "
                "which popular claims are myths, and what is the evidence on each side?"),
    ("primary", "For: {topic} — find primary sources (chronicles, letters, inscriptions, official records, "
                "archaeology) and any well-attested quotations, with exact wording and provenance. "
                "Also find geography: the key locations with approximate coordinates."),
]

TIER_HINTS = [
    (1, (".edu", ".ac.uk", ".ac.", "jstor.org", "doi.org", "cambridge.org", "oup.com", "academic.oup",
         "tandfonline", "springer", "brill.com", "persee.fr", "perseus.tufts", "archive.org", "loc.gov",
         "nationalarchives", "archives.gov", "gallica.bnf", "europeana", "metmuseum", "britishmuseum",
         "smithsonian", "louvre", "getty.edu", "worldhistory.org/article", "lacus.uchicago", "fordham.edu")),
    (2, ("britannica.com", "nationalgeographic", "history.com", "historytoday", "bbc.co.uk", "smithsonianmag",
         "worldhistory.org", "historynet", "iwm.org.uk", "nps.gov", "army.mil", "ushmm.org", "theguardian",
         "nytimes", "reuters", "apnews")),
]


def tier(url: str) -> int:
    host = (urlparse(url).netloc or "").lower() + urlparse(url).path.lower()
    for t, hints in TIER_HINTS:
        if any(h in host for h in hints):
            return t
    if "wikipedia.org" in host:
        return 3
    return 3


def run(db: Session, video: Video) -> dict:
    """Basketball research: Wikipedia facts (free) or live web search (paid) + real game data."""
    from datetime import datetime, timezone

    from ..providers import bdl
    topic = video.topic
    fmt = (topic.format if topic else "") or "meme"
    subject = f"{topic.title} — {topic.main_event}" if topic else video.working_title
    notes, sources = [], {}
    if fmt not in ("meme", "hypothetical"):
        emit(db, video, "Researching facts and stats")
        r = llm.web_research(
            db, video_id=video.id, category="research", system=SYSTEM, est_usd=0.4, note="research",
            prompt=(f"Collect verifiable facts for a basketball Short about: {subject}. Exact stats (season, "
                    "per-game or totals, with the season/year), records, dates, scores and key context. "
                    "Say which season each number belongs to. Flag anything disputed."))
        notes.append({"pass": "facts", "text": r["text"]})
        for c in r["citations"]:
            src = sources.setdefault(c["url"], {"url": c["url"], "title": c["title"], "excerpts": [], "cited": True})
            if c["cited_text"] and c["cited_text"] not in src["excerpts"]:
                src["excerpts"].append(c["cited_text"])
    bib = sorted(sources.values(), key=lambda s: (tier(s["url"]), -len(s["excerpts"])))
    for i, s in enumerate(bib, 1):
        s["id"], s["tier"] = f"S{i}", tier(s["url"])
    # Real scores from the last few days for news/storyline formats (and context for memes).
    if fmt in ("news_reaction", "storyline", "recap"):
        try:
            games = bdl.final_games(3)
            for j, g in enumerate(games[:15], 1):
                bib.append({**bdl.as_source(g), "id": f"D{j}"})
            emit(db, video, f"Loaded {len(games)} final scores from BALLDONTLIE "
                            f"({datetime.now(timezone.utc):%Y-%m-%d})")
        except Exception as e:
            emit(db, video, f"Game data unavailable ({e}); continuing without scores", level="warn")
    # Player stat tables (free, Wikipedia) → P# sources the chart scenes read numbers from.
    from ..providers import wiki_stats
    today = datetime.now(timezone.utc).date().isoformat()
    for j, name in enumerate((topic.players if topic else []) or [], 1):
        try:
            st = wiki_stats.player_stats(name)
        except Exception as e:
            st = None
            emit(db, video, f"Stats lookup failed for {name}: {e}", level="warn")
        if st and st["rows"]:
            bib.append(wiki_stats.as_source(st, f"P{j}", today))
            emit(db, video, f"Loaded {len(st['rows'])} seasons for {st['player']}")
        else:
            emit(db, video, f"No career stats table found for '{name}'", level="warn")
    if fmt == "recap":
        from datetime import timedelta
        day = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
        try:
            lines = bdl.player_lines(day)
            if lines:
                bib.append(bdl.recap_source(day, lines))
        except Exception as e:
            emit(db, video, f"Recap data unavailable ({e}). Recaps need the BALLDONTLIE ALL-STAR plan.", level="warn")
    emit(db, video, f"{sum(1 for s in bib if s.get('cited'))} sources ready")
    return {"subject": subject, "notes": notes, "bibliography": bib, "format": fmt}


def dossier_text(research: dict, max_chars: int = 60000) -> str:
    parts = []
    for n in research["notes"]:
        parts.append(f"## {n['pass'].upper()}\n{n['text']}")
    parts.append("## SOURCES (id, tier 1=academic/archival/museum, 2=reputable publication, 3=other)")
    for s in research["bibliography"]:
        if not s["cited"]:
            continue
        data_src = s["id"][:1] in ("P", "R", "D")            # data tables: every line matters
        ex = ("\n      " if data_src else " | ").join(e[:400] for e in (s["excerpts"] if data_src else s["excerpts"][:4]))
        parts.append(f"[{s['id']}] tier {s['tier']} — {s['title']} — {s['url']}\n    excerpts: {ex}")
    return "\n\n".join(parts)[:max_chars]
