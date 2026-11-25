"""Freely licensed player photos from Wikimedia Commons (CC0 / public domain / CC BY / CC BY-SA),
with the attribution each licence requires. Shown as-is with credit — never used to fake quotes."""
from __future__ import annotations

import re
from pathlib import Path

import httpx

API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "HoopsShorts/1.0 (self-hosted; licence-aware photo lookup)"}
OK_LICENSES = re.compile(r"^(cc0|public domain|pd|cc by(-sa)? ?\d(\.\d)?)", re.I)


def _fold(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def reachable() -> bool:
    try:
        return httpx.get(API, headers=UA, timeout=8, params={"action": "query", "format": "json",
                                                              "meta": "siteinfo"}).status_code == 200
    except Exception:
        return False


def find_photo(query: str, dest: Path, tries: int = 10) -> dict | None:
    """query is a player's name. Only files whose title contains the player's last name are used, so a
    search miss never puts the wrong person on screen."""
    last = _fold(query.replace("Jr.", "").split()[-1])
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
        if last not in _fold(p.get("title", "")):
            continue
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


def find_clip(query: str, dest: Path, tries: int = 15) -> dict | None:
    """A freely licensed basketball video from Wikimedia Commons, used only as heavily blurred background
    motion (never presented as a specific player or game). Returns credit info like find_photo."""
    try:
        r = httpx.get(API, headers=UA, timeout=30, params={
            "action": "query", "format": "json", "formatversion": 2, "generator": "search",
            "gsrsearch": f"{query} filetype:video", "gsrnamespace": 6, "gsrlimit": tries,
            "prop": "imageinfo", "iiprop": "url|extmetadata|size|mediatype"})
        pages = r.json().get("query", {}).get("pages", [])
    except Exception:
        return None
    pages.sort(key=lambda p: p.get("index", 99))
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata", {})
        lic = (md.get("LicenseShortName", {}) or {}).get("value", "")
        if not OK_LICENSES.match(lic.strip()) or ii.get("size", 0) > 120_000_000 or ii.get("width", 0) < 480:
            continue
        artist = re.sub(r"<[^>]+>", "", (md.get("Artist", {}) or {}).get("value", "")).strip() or "Unknown author"
        try:
            v = httpx.get(ii["url"], headers=UA, timeout=180, follow_redirects=True)
            v.raise_for_status()
        except Exception:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(v.content)
        return {"path": str(dest), "license": lic, "artist": artist[:80], "page": ii.get("descriptionurl", ""),
                "credit": f"Clip: {artist[:50]} / {lic} via Wikimedia Commons"}
    return None
