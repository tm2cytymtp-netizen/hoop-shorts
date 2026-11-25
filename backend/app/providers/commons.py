"""Freely licensed player photos from Wikimedia Commons (CC0 / public domain / CC BY / CC BY-SA),
with the attribution each licence requires. Shown as-is with credit — never used to fake quotes."""
from __future__ import annotations

import re
from pathlib import Path

import httpx

API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "HoopsShorts/1.0 (self-hosted; licence-aware photo lookup)"}
OK_LICENSES = re.compile(r"^(cc0|public domain|pd|cc by(-sa)? ?\d(\.\d)?)", re.I)


def find_photo(query: str, dest: Path, tries: int = 10) -> dict | None:
    try:
        r = httpx.get(API, headers=UA, timeout=30, params={
            "action": "query", "format": "json", "formatversion": 2, "generator": "search",
            "gsrsearch": f"{query} basketball filetype:bitmap", "gsrnamespace": 6, "gsrlimit": tries,
            "prop": "imageinfo", "iiprop": "url|extmetadata|size", "iiurlwidth": 1400})
        pages = r.json().get("query", {}).get("pages", [])
    except Exception:
        return None
    pages.sort(key=lambda p: p.get("index", 99))
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata", {})
        lic = (md.get("LicenseShortName", {}) or {}).get("value", "")
        if not OK_LICENSES.match(lic.strip()) or ii.get("width", 0) < 500:
            continue
        artist = re.sub(r"<[^>]+>", "", (md.get("Artist", {}) or {}).get("value", "")).strip() or "Unknown author"
        url = ii.get("thumburl") or ii.get("url")
        try:
            img = httpx.get(url, headers=UA, timeout=60, follow_redirects=True)
            img.raise_for_status()
        except Exception:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(img.content)
        page = ii.get("descriptionurl", "")
        return {"path": str(dest), "license": lic, "artist": artist[:80], "page": page,
                "credit": f"Photo: {artist[:50]} / {lic} via Wikimedia Commons"}
    return None
