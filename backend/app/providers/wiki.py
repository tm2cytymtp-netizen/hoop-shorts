"""Free research sources: Wikipedia (text + the article's own references) and Wikimedia 'On this day'.
Wikipedia is a tertiary source, so the dashboard labels these sources as such; the fact-checker
still verifies every claim against the exact paragraphs used."""
from __future__ import annotations

import re
from datetime import date, timedelta

import httpx

API = "https://en.wikipedia.org/w/api.php"
UA = {"User-Agent": "ChronicleHistoryShorts/1.0 (self-hosted educational video tool)"}


def _get(params: dict) -> dict:
    r = httpx.get(API, params={**params, "format": "json", "formatversion": 2}, headers=UA, timeout=30)
    r.raise_for_status()
    return r.json()


def search(query: str, n: int = 4) -> list[str]:
    res = _get({"action": "query", "list": "search", "srsearch": query, "srlimit": n})
    return [h["title"] for h in res.get("query", {}).get("search", [])]


def article(title: str) -> dict | None:
    res = _get({"action": "query", "prop": "extracts|info", "explaintext": 1, "titles": title, "inprop": "url",
                "redirects": 1})
    pages = res.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return None
    p = pages[0]
    text = p.get("extract", "")
    text = re.split(r"\n== (See also|References|Notes|Further reading|External links|Bibliography|Sources) ==",
                    text)[0]
    paras = []
    section = ""
    for block in text.split("\n"):
        b = block.strip()
        if not b:
            continue
        m = re.match(r"^=+ (.*?) =+$", b)
        if m:
            section = m.group(1)
            continue
        if len(b) > 80:
            paras.append({"section": section, "text": b})
    return {"title": p["title"], "url": p.get("fullurl", f"https://en.wikipedia.org/wiki/{title}"),
            "revid": p.get("lastrevid"), "paragraphs": paras}


def relevant(paragraphs: list[dict], query: str, k: int = 25) -> list[dict]:
    words = {w for w in re.findall(r"[a-z0-9]{4,}", query.lower())}
    def score(p):
        t = p["text"].lower()
        return sum(t.count(w) for w in words) + (2 if p["i"] < 3 else 0)
    return sorted(paragraphs, key=score, reverse=True)[:k]


def on_this_day(days: int = 10) -> list[str]:
    """Real anniversaries in the coming days (Wikimedia feed, free)."""
    out = []
    for i in range(days):
        d = date.today() + timedelta(days=i)
        try:
            r = httpx.get(f"https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/events/{d.month:02d}/{d.day:02d}",
                          headers=UA, timeout=20)
            for e in r.json().get("events", [])[:15]:
                if e.get("year", 3000) < 1950:
                    out.append(f"{d:%b %d}, {e['year']}: {e['text']}")
        except Exception:
            continue
    return out
