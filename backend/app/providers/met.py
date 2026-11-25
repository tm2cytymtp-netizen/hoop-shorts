"""The Met Collection API — real public-domain artworks (CC0), free, no key.
https://metmuseum.github.io/"""
from __future__ import annotations

from pathlib import Path

import httpx

API = "https://collectionapi.metmuseum.org/public/collection/v1"
UA = {"User-Agent": "ChronicleHistoryShorts/1.0"}


def find_artwork(query: str, dest: Path, tries: int = 12) -> dict | None:
    try:
        r = httpx.get(f"{API}/search", params={"q": query, "hasImages": "true"}, headers=UA, timeout=30)
        ids = (r.json() or {}).get("objectIDs") or []
    except Exception:
        return None
    for oid in ids[:tries]:
        try:
            o = httpx.get(f"{API}/objects/{oid}", headers=UA, timeout=30).json()
        except Exception:
            continue
        if not (o.get("isPublicDomain") and o.get("primaryImage")):
            continue
        try:
            img = httpx.get(o["primaryImage"], headers=UA, timeout=120, follow_redirects=True)
            img.raise_for_status()
        except Exception:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(img.content)
        title = o.get("title", "")
        artist = o.get("artistDisplayName") or o.get("culture") or ""
        return {"path": str(dest), "title": title, "artist": artist, "date": o.get("objectDate", ""),
                "url": o.get("objectURL", ""), "credit": f"{title}{', ' + artist if artist else ''}"
                                                       f"{', ' + o['objectDate'] if o.get('objectDate') else ''} — The Met (CC0)"}
    return None
