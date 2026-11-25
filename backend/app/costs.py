"""Cost estimation, ledger and budget enforcement.

Every paid provider call goes through `guard()` BEFORE it is made and `record()`
after. If a call would push the video or the month over budget, BudgetExceeded is
raised, the orchestrator pauses the job and you get notified.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import settings_store
from .models import CostEntry


class BudgetExceeded(Exception):
    pass


def video_spend(db: Session, video_id: int) -> float:
    return float(db.query(func.coalesce(func.sum(CostEntry.usd), 0)).filter(CostEntry.video_id == video_id).scalar())


def month_spend(db: Session) -> float:
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return float(db.query(func.coalesce(func.sum(CostEntry.usd), 0)).filter(CostEntry.created_at >= start).scalar())


def count(db: Session, video_id: int, category: str) -> int:
    return int(db.query(func.count(CostEntry.id)).filter(
        CostEntry.video_id == video_id, CostEntry.category == category).scalar())


def guard(db: Session, video_id: int | None, category: str, est_usd: float) -> None:
    b = settings_store.get(db, "budget")
    if month_spend(db) + est_usd > b["max_monthly_usd"]:
        raise BudgetExceeded(f"Monthly budget ${b['max_monthly_usd']:.2f} would be exceeded "
                             f"(spent ${month_spend(db):.2f}, next call ~${est_usd:.2f}).")
    if video_id is None:
        return
    if video_spend(db, video_id) + est_usd > b["max_per_video_usd"]:
        raise BudgetExceeded(f"Per-video budget ${b['max_per_video_usd']:.2f} would be exceeded "
                             f"(spent ${video_spend(db, video_id):.2f}, next call ~${est_usd:.2f}).")
    if category == "image" and count(db, video_id, "image") >= b["max_images_per_video"]:
        raise BudgetExceeded(f"Image generation limit ({b['max_images_per_video']}) reached for this video.")
    if category == "video" and count(db, video_id, "video") >= b["max_video_requests_per_video"]:
        raise BudgetExceeded(f"Video generation limit ({b['max_video_requests_per_video']}) reached for this video.")


def record(db: Session, video_id: int | None, category: str, provider: str, units: float,
           unit_label: str, usd: float, note: str = "") -> None:
    db.add(CostEntry(video_id=video_id, category=category, provider=provider, units=units,
                     unit_label=unit_label, usd=round(usd, 5), note=note[:300]))
    db.commit()


def llm_cost(db: Session, input_tokens: int, output_tokens: int, fast: bool = False, searches: int = 0) -> float:
    p = settings_store.get(db, "pricing")
    if fast:
        c = input_tokens / 1e6 * p["llm_fast_input_per_mtok"] + output_tokens / 1e6 * p["llm_fast_output_per_mtok"]
    else:
        c = input_tokens / 1e6 * p["llm_input_per_mtok"] + output_tokens / 1e6 * p["llm_output_per_mtok"]
    return c + searches / 1000 * p["web_search_per_1k"]


def _free_factors(db: Session) -> dict:
    ai = settings_store.get(db, "ai")
    vo = settings_store.get(db, "voice")
    return {"llm": 0.0 if ai.get("llm_provider") == "gemini" else 1.0,
            "image": 0.0 if ai.get("image_provider") == "cloudflare" else 1.0,
            "video": 0.0 if ai.get("image_provider") != "fal" else 1.0,
            "voice": 0.0 if vo.get("provider") == "kokoro" else 1.0}


def _apply_free(db: Session, est: dict) -> dict:
    f = _free_factors(db)
    for k in ("research", "script", "fact_check", "metadata_and_qc"):
        est[k] = round(est[k] * f["llm"], 3)
    for k in ("image", "video", "voice"):
        est[k] = round(est[k] * f[k], 3)
    est["total"] = round(sum(v for k, v in est.items() if isinstance(v, (int, float)) and k != "total"), 2)
    return est


def estimate_short(db: Session) -> dict:
    p = settings_store.get(db, "pricing")
    ai = settings_store.get(db, "ai")
    sh = settings_store.get(db, "shorts")
    secs = sum(sh["target_seconds"]) / 2
    scenes = max(5, int(secs / 6.5))
    est = {
        "research": llm_cost(db, 30_000, 3_000, searches=min(8, ai["web_search_max_uses"])),
        "script": llm_cost(db, 15_000, 3_000) * 1.5,
        "fact_check": llm_cost(db, 12_000, 2_000, searches=3),
        "metadata_and_qc": llm_cost(db, 8_000, 1_500, fast=True) + llm_cost(db, 4_000, 800),
        "image": scenes * p["image_each"] * 1.2,
        "video": sh["animated_scenes"] * ai["video_clip_seconds"] * p["video_per_second"],
        "voice": secs * 2.5 * 6 / 1000 * p["tts_per_1k_chars"] * 1.1,
        "storage": 0.0, "render": 0.0,
    }
    est = {k: round(v, 3) for k, v in est.items()}
    est["total"] = round(sum(est.values()), 2)
    est["assumptions"] = {"seconds": secs, "scenes": scenes, "animated_scenes": sh["animated_scenes"]}
    return _apply_free(db, est)


def estimate_video(db: Session, target_minutes: float, scenes: int | None = None) -> dict:
    """Pre-production estimate shown in the dashboard and checked against the budget."""
    p = settings_store.get(db, "pricing")
    ai = settings_store.get(db, "ai")
    words = target_minutes * 150                       # documentary narration ~150 wpm
    scenes = scenes or max(12, int(target_minutes * 60 / 9))  # a new visual every ~9 s
    chars = words * 6
    animated = int(scenes * ai["animated_scene_ratio"])
    est = {
        "research": llm_cost(db, 60_000, 6_000, searches=ai["web_search_max_uses"]),
        "script": llm_cost(db, 40_000, 12_000) * 2,           # draft + one revision
        "fact_check": llm_cost(db, 50_000, 8_000, searches=ai["web_search_max_uses"]),
        "metadata_and_qc": llm_cost(db, 30_000, 6_000, fast=True) + llm_cost(db, 20_000, 3_000),
        "image": (scenes + 3) * p["image_each"] * 1.15,       # + thumbnails, 15% retry margin
        "video": animated * ai["video_clip_seconds"] * p["video_per_second"],
        "voice": chars / 1000 * p["tts_per_1k_chars"] * 1.05,
        "storage": 2.0 * p["storage_per_gb_month"],
        "render": 0.0,                                         # runs on your own server
    }
    est = {k: round(v, 3) for k, v in est.items()}
    est["total"] = round(sum(est.values()), 2)
    est["assumptions"] = {"minutes": target_minutes, "scenes": scenes, "animated_scenes": animated,
                          "narration_chars": int(chars)}
    return _apply_free(db, est)


def breakdown(db: Session, video_id: int) -> dict:
    rows = db.query(CostEntry.category, func.sum(CostEntry.usd)).filter(
        CostEntry.video_id == video_id).group_by(CostEntry.category).all()
    out = {c: round(float(u), 4) for c, u in rows}
    out["total"] = round(sum(out.values()), 4)
    return out
