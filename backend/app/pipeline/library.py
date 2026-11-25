"""Licensed music & SFX library. YOU supply the files plus their licence details in
assets/music/library.json and assets/sfx/library.json; only entries marked
commercial_use=true are ever used. See README → Music & SFX."""
from __future__ import annotations

import json
import random
from pathlib import Path

from ..config import env


def _load(kind: str) -> list[dict]:
    items = []
    for name in ("library.json", "generated.json"):
        p = env.assets_dir / kind / name
        if p.exists():
            items += json.loads(p.read_text())
    out = []
    for it in items:
        f = env.assets_dir / kind / it["file"]
        if f.exists() and it.get("commercial_use") and it.get("license"):
            out.append({**it, "path": str(f)})
    return out


def pick_music(mood: str, seed: int) -> dict | None:
    items = _load("music")
    if not items:
        return None
    match = [i for i in items if mood in (i.get("moods") or [])] or items
    return random.Random(seed).choice(match)


def pick_sfx(tag: str) -> dict | None:
    if not tag:
        return None
    items = [i for i in _load("sfx") if tag in (i.get("tags") or [])]
    # Prefer your own licensed library over the generated fallback when both exist.
    own = [i for i in items if "generated/" not in i["file"]]
    pool = own or items
    return random.Random(tag).choice(pool) if pool else None


def describe(item: dict) -> str:
    return f"{item.get('title', Path(item['path']).name)} — {item.get('artist', '')} ({item['license']})"
