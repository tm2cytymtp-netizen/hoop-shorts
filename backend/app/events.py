from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from .config import env
from .models import StageEvent, Video

log = logging.getLogger("pipeline")


def emit(db: Session, video: Video, message: str, level: str = "info", stage: str | None = None) -> None:
    db.add(StageEvent(video_id=video.id, stage=stage or video.status, level=level, message=message[:4000]))
    db.commit()
    getattr(log, "warning" if level == "warn" else level if level in ("info", "error") else "info")(
        "[video %s] %s", video.id, message)


def set_status(db: Session, video: Video, status: str) -> None:
    video.status = status
    db.commit()
    emit(db, video, f"→ {status}", stage=status)


def video_dir(video_id: int) -> Path:
    d = env.data_dir / "videos" / str(video_id)
    for sub in ("audio", "images", "motion", "clips", "thumbs", "shorts", "work"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d
