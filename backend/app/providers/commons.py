"""Freely licensed player photos from Wikimedia Commons (CC0 / public domain / CC BY / CC BY-SA),
with the attribution each licence requires. Shown as-is with credit — never used to fake quotes."""
from __future__ import annotations

import re
from pathlib import Path

import httpx

API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "HoopShorts/1.0 (https://github.com/tm2cytymtp-netizen/hoop-shorts; licence-aware photo lookup)"}
OK_LICENSES = re.compile(r"^(cc0|public domain|pd|cc by(-sa)? ?\d(\.\d)?)", re.I)


def _fold(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def _api(params: dict, tries: int = 4):
    import time
    for i in range(tries):
        r = httpx.get(API, headers=UA, timeout=30, params=params)
        if r.status_code != 429:
            return r
        time.sleep(3 * (i + 1))
    return r


def _download(url: str, timeout: int = 90, tries: int = 3):
    """GET with polite backoff: Wikimedia rate-limits (429) bursts of original-file downloads."""
    import time
    url = url.split("?")[0]
    for i in range(tries):
        r = httpx.get(url, headers=UA, timeout=timeout, follow_redirects=True)
        if r.status_code != 429:
            r.raise_for_status()
            time.sleep(1.5)
            return r
        wait = r.headers.get("retry-after")
        time.sleep(min(20, int(wait)) if wait and wait.isdigit() else 5 * (i + 1))
    r.raise_for_status()
    return r


def reachable() -> bool:
    try:
        return _api({"action": "query", "format": "json", "meta": "siteinfo"}).status_code == 200
    except Exception:
        return False


def _cache_dir() -> Path | None:
    import os
    d = os.environ.get("HOOP_PHOTO_CACHE")
    return Path(d) if d else None


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _fold(name)).strip("-")


def find_photo(query: str, dest: Path, tries: int = 10) -> dict | None:
    """query is a player's name. Only files whose title contains the player's last name are used, so a
    search miss never puts the wrong person on screen. Results are cached in HOOP_PHOTO_CACHE (the repo's
    assets/photos/) with their credit, so each player is downloaded from Commons only once."""
    import json
    import shutil
    cache = _cache_dir()
    if cache:
        cj, cp = cache / f"{_slug(query)}.json", cache / f"{_slug(query)}.jpg"
        if cj.exists() and cp.exists():
            meta = json.loads(cj.read_text())
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(cp, dest)
            return {**meta, "path": str(dest)}
    res = _find_photo(query, dest, tries)
    if res and cache:
        cache.mkdir(parents=True, exist_ok=True)
        shutil.copy(res["path"], cache / f"{_slug(query)}.jpg")
        (cache / f"{_slug(query)}.json").write_text(json.dumps({k: v for k, v in res.items() if k != "path"}, indent=1))
    return res


def _find_photo(query: str, dest: Path, tries: int = 10) -> dict | None:
    last = _fold(query.replace("Jr.", "").split()[-1])
    try:
        r = _api({
            "action": "query", "format": "json", "formatversion": 2, "generator": "search",
            "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": 6, "gsrlimit": max(tries, 20),
            "prop": "imageinfo", "iiprop": "url|extmetadata|size", "iiurlwidth": 1400})
        pages = r.json().get("query", {}).get("pages", [])
    except Exception:
        return None
    first = _fold(query.split()[0])

    def score(p):   # close-up portraits first: "(cropped)" files, taller-than-wide, full name in the title
        ii = (p.get("imageinfo") or [{}])[0]
        t = _fold(p.get("title", ""))
        tall = ii.get("height", 0) >= ii.get("width", 1) * 0.95
        return (("cropped" in t) * 3 + tall * 2 + (first in t) * 1 + ("headshot" in t or "portrait" in t) * 2,
                -p.get("index", 99))
    pages.sort(key=score, reverse=True)
    for p in pages:
        if last not in _fold(p.get("title", "")):
            continue
        ii = (p.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata", {})
        lic = (md.get("LicenseShortName", {}) or {}).get("value", "")
        if not OK_LICENSES.match(lic.strip()) or ii.get("width", 0) < 500:
            continue
        artist = re.sub(r"<[^>]+>", "", (md.get("Artist", {}) or {}).get("value", "")).strip() or "Unknown author"
        img = None
        orig = (ii.get("url") or "").split("?")[0]
        thumbs = []
        if "/wikipedia/commons/" in orig:   # standard-width thumbnails on upload.* (fast, not throttled)
            head, tail = orig.split("/wikipedia/commons/", 1)
            fname = tail.split("/")[-1]
            thumbs = [f"{head}/wikipedia/commons/thumb/{tail}/{w}px-{fname}" for w in (960, 500)
                      if w < ii.get("width", 0)]
        for url in thumbs + [orig]:
            if not url:
                continue
            try:
                img = _download(url)
                break
            except Exception:
                img = None
        if img is None:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:   # store a sane-size JPEG whatever the original was
            from io import BytesIO
            from PIL import Image, ImageOps
            pic = ImageOps.exif_transpose(Image.open(BytesIO(img.content))).convert("RGB")
            pic.thumbnail((1400, 1400))
            pic.save(dest, "JPEG", quality=90)
        except Exception:
            continue
        page = ii.get("descriptionurl", "")
        fname = p.get("title", "").replace("File:", "")
        return {"path": str(dest), "license": lic, "artist": artist[:80], "page": page,
                "credit": f"{query} photo: {artist[:50]}, {lic}, Wikimedia Commons ({fname})"}
    return None


def find_clip(query: str, dest: Path, tries: int = 15) -> dict | None:
    """Cached wrapper: clips are trimmed to a 12 s, 540x960 background loop (~1-2 MB) and kept in
    HOOP_PHOTO_CACHE/../broll with their credit, so each search is downloaded once."""
    import json
    import shutil
    import subprocess
    cache = _cache_dir()
    bdir = cache.parent / "broll" if cache else None
    if bdir:
        cj, cv = bdir / f"{_slug(query)}.json", bdir / f"{_slug(query)}.mp4"
        if cj.exists() and cv.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(cv, dest)
            return {**json.loads(cj.read_text()), "path": str(dest)}
    res = _find_clip(query, dest, tries)
    if not res:
        return None
    small = dest.with_suffix(".bg.mp4")
    try:   # skip the first half: news-style clips open with title cards and name captions
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                    res["path"]], capture_output=True, text=True).stdout.strip() or 0)
    except ValueError:
        dur = 0.0
    start = f"{dur * 0.5:.2f}" if dur > 8 else "0"
    ok = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", start, "-i", res["path"], "-t", "12", "-an", "-vf",
                         "scale=540:960:force_original_aspect_ratio=increase,crop=540:960,fps=30",
                         "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", str(small)]).returncode == 0
    if ok:
        res["path"] = str(small)
        if bdir:
            bdir.mkdir(parents=True, exist_ok=True)
            shutil.copy(small, bdir / f"{_slug(query)}.mp4")
            (bdir / f"{_slug(query)}.json").write_text(json.dumps({k: v for k, v in res.items() if k != "path"}, indent=1))
    return res


def _find_clip(query: str, dest: Path, tries: int = 15) -> dict | None:
    """A freely licensed basketball video from Wikimedia Commons, used only as heavily blurred background
    motion (never presented as a specific player or game). Returns credit info like find_photo."""
    try:
        r = _api({
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
            v = _download(ii["url"], timeout=180)
        except Exception:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(v.content)
        return {"path": str(dest), "license": lic, "artist": artist[:80], "page": ii.get("descriptionurl", ""),
                "credit": f"Clip: {artist[:50]} / {lic} via Wikimedia Commons"}
    return None
