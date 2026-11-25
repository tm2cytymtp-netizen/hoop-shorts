"""Cloudflare Workers AI image generation (free: 10,000 neurons/day; FLUX.1 schnell ≈ 60 neurons/image).
Needs a free Cloudflare account: CLOUDFLARE_ACCOUNT_ID + an API token with 'Workers AI' permission."""
from __future__ import annotations

import base64
import time
from pathlib import Path

import httpx
from PIL import Image
from sqlalchemy.orm import Session

from .. import costs, settings_store
from ..config import env


class CFError(Exception):
    pass


def generate_image(db: Session, video_id, prompt: str, dest: Path, *, seed: int | None = None,
                   width: int | None = None, height: int | None = None, negative: str = "") -> dict:
    if not (env.cloudflare_account_id and env.cloudflare_api_token):
        raise CFError("CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN not configured (free account — see README).")
    model = settings_store.get(db, "ai")["cf_image_model"]
    costs.guard(db, video_id, "image", 0)
    body = {"prompt": prompt[:2000], "steps": 8 if "schnell" in model else 20}
    if seed is not None:
        body["seed"] = int(seed)
    if "schnell" not in model and width and height:       # newer FLUX models accept a size
        body.update(width=width, height=height)
    url = f"https://api.cloudflare.com/client/v4/accounts/{env.cloudflare_account_id}/ai/run/{model}"
    r = None
    for attempt in range(5):
        r = httpx.post(url, json=body, headers={"Authorization": f"Bearer {env.cloudflare_api_token}"}, timeout=180)
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(10 * (attempt + 1))
            continue
        break
    if r.status_code >= 400:
        msg = r.text[:400]
        if "neuron" in msg.lower() or r.status_code == 429:
            msg += " — daily free allocation probably used up; it resets at 00:00 UTC."
        raise CFError(f"Cloudflare AI error {r.status_code}: {msg}")
    if r.headers.get("content-type", "").startswith("image/"):
        raw = r.content
    else:
        res = r.json().get("result") or {}
        if not res.get("image"):
            raise CFError(f"No image returned: {r.text[:300]}")
        raw = base64.b64decode(res["image"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".raw")
    tmp.write_bytes(raw)
    img = Image.open(tmp).convert("RGB")
    if width and height and abs(img.width / img.height - width / height) > 0.05:
        # Square output → centre-crop to the requested aspect (prompts ask for a centred subject).
        tw = min(img.width, int(img.height * width / height))
        th = min(img.height, int(img.width * height / width))
        l, t = (img.width - tw) // 2, (img.height - th) // 2
        img = img.crop((l, t, l + tw, t + th))
    img.save(dest)
    tmp.unlink(missing_ok=True)
    costs.record(db, video_id, "image", f"cloudflare:{model} (free allocation)", 1, "image", 0.0, prompt[:120])
    return {"path": str(dest), "url": None, "model": model, "seed": seed}
