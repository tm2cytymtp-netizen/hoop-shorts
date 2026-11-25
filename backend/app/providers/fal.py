"""fal.ai queue API: text-to-image and image-to-video.

Model endpoints are configurable in Settings → AI, so you can swap to any fal model
(e.g. a newer FLUX or Kling version) without code changes. Verify your chosen models'
licence allows commercial use on fal's model page.
"""
from __future__ import annotations

import base64
import time
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from .. import costs, settings_store
from ..config import env

QUEUE = "https://queue.fal.run"


class FalError(Exception):
    pass


def _headers() -> dict:
    if not env.fal_key:
        raise FalError("FAL_KEY is not configured (see README → Connect your accounts).")
    return {"Authorization": f"Key {env.fal_key}", "Content-Type": "application/json"}


def _run(model: str, payload: dict, timeout_s: int = 900) -> dict:
    with httpx.Client(timeout=60) as c:
        for attempt in range(4):
            r = c.post(f"{QUEUE}/{model}", headers=_headers(), json=payload)
            if r.status_code < 500 and r.status_code != 429:
                break
            time.sleep(2 ** attempt * 3)
        if r.status_code >= 400:
            raise FalError(f"fal submit failed {r.status_code}: {r.text[:400]}")
        sub = r.json()
        status_url, response_url = sub["status_url"], sub["response_url"]
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            s = c.get(status_url, headers=_headers())
            if s.status_code >= 500:
                time.sleep(5)
                continue
            st = s.json().get("status")
            if st == "COMPLETED":
                res = c.get(response_url, headers=_headers())
                if res.status_code >= 400:
                    raise FalError(f"fal result failed {res.status_code}: {res.text[:400]}")
                return res.json()
            if st not in ("IN_QUEUE", "IN_PROGRESS"):
                raise FalError(f"fal request ended with status {st}: {s.text[:400]}")
            time.sleep(3)
        raise FalError(f"fal request timed out after {timeout_s}s")


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, timeout=300, follow_redirects=True) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    return dest


def generate_image(db: Session, video_id: int | None, prompt: str, dest: Path, *, seed: int | None = None,
                   width: int | None = None, height: int | None = None, negative: str = "") -> dict:
    ai = settings_store.get(db, "ai")
    price = settings_store.get(db, "pricing")["image_each"]
    costs.guard(db, video_id, "image", price)
    payload = {"prompt": prompt, "num_images": 1, "output_format": "png",
               "image_size": {"width": width or ai["image_size"]["width"],
                              "height": height or ai["image_size"]["height"]}}
    if seed is not None:
        payload["seed"] = seed
    if negative:
        payload["negative_prompt"] = negative
    res = _run(ai["image_model"], payload)
    costs.record(db, video_id, "image", f"fal:{ai['image_model']}", 1, "image", price, prompt[:120])
    img = (res.get("images") or [None])[0]
    if not img:
        raise FalError(f"No image returned: {str(res)[:300]}")
    if res.get("has_nsfw_concepts") and any(res["has_nsfw_concepts"]):
        raise FalError("Image was flagged by the provider's safety checker; will regenerate with a softer prompt.")
    _download(img["url"], dest)
    return {"path": str(dest), "url": img["url"], "model": ai["image_model"], "seed": res.get("seed", seed)}


def animate_image(db: Session, video_id: int | None, image: Path, image_url: str | None, prompt: str,
                  dest: Path) -> dict:
    ai = settings_store.get(db, "ai")
    secs = int(ai["video_clip_seconds"])
    price = settings_store.get(db, "pricing")["video_per_second"] * secs
    costs.guard(db, video_id, "video", price)
    if not image_url:
        image_url = "data:image/png;base64," + base64.b64encode(Path(image).read_bytes()).decode()
    payload = {"prompt": prompt, "image_url": image_url, "duration": str(secs),
               "negative_prompt": "blur, distortion, morphing faces, extra limbs, text, watermark, modern objects"}
    res = _run(ai["video_model"], payload, timeout_s=1500)
    costs.record(db, video_id, "video", f"fal:{ai['video_model']}", secs, "seconds", price, prompt[:120])
    url = (res.get("video") or {}).get("url")
    if not url:
        raise FalError(f"No video returned: {str(res)[:300]}")
    _download(url, dest)
    return {"path": str(dest), "url": url, "model": ai["video_model"]}
