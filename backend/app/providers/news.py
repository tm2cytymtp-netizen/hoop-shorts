"""Public RSS headline feeds for trend discovery (ESPN NBA, Google News). Headlines are leads:
facts used in a video must still be verified by the research/fact-check stages."""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import httpx

FEEDS = {
    "ESPN NBA": "https://www.espn.com/espn/rss/nba/news",
    "Google News: NBA": "https://news.google.com/rss/search?q=NBA&hl=en-US&gl=US&ceid=US:en",
    "Google News: NBA viral": "https://news.google.com/rss/search?q=NBA+viral+OR+meme+OR+funny&hl=en-US&gl=US&ceid=US:en",
}
UA = {"User-Agent": "Mozilla/5.0 (RSS reader)"}


def headlines(limit_per_feed: int = 25) -> list[dict]:
    out, seen = [], set()
    for name, url in FEEDS.items():
        try:
            r = httpx.get(url, headers=UA, timeout=20, follow_redirects=True)
            root = ET.fromstring(r.content)
        except Exception:
            continue
        for it in root.iter("item"):
            title = html.unescape(it.findtext("title", "")).strip()
            key = re.sub(r"\W+", "", title.lower())[:60]
            if not title or key in seen:
                continue
            seen.add(key)
            desc = re.sub(r"<[^>]+>", " ", html.unescape(it.findtext("description", "")))
            pub = it.findtext("pubDate", "")
            try:
                pub = parsedate_to_datetime(pub).date().isoformat()
            except Exception:
                pass
            out.append({"feed": name, "title": title, "link": it.findtext("link", ""), "published": pub,
                        "summary": re.sub(r"\s+", " ", desc).strip()[:400]})
            if sum(1 for o in out if o["feed"] == name) >= limit_per_feed:
                break
    return out
