"""Background worker: runs queued jobs and the publishing scheduler.

Run with:  python -m app.worker
"""
from __future__ import annotations

import logging
import os
import socket
import time
import traceback
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from . import costs
from .db import SessionLocal, init_db
from .events import emit
from .models import Job, Setting, Video
from .notify import notify
from .orchestrator import auto_fill_schedule, enqueue, make_shorts, produce
from .pipeline import analytics, publish, topics

log = logging.getLogger("worker")
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


def _state(db, key: str, default=None):
    row = db.get(Setting, "_state")
    return ((row.value or {}) if row else {}).get(key, default)


def _set_state(db, key: str, value) -> None:
    row = db.get(Setting, "_state")
    if not row:
        row = Setting(key="_state", value={})
        db.add(row)
    row.value = {**(row.value or {}), key: value}
    db.commit()


def claim(db) -> Job | None:
    now = datetime.now(timezone.utc)
    q = select(Job).where(Job.status == "pending", Job.run_after <= now).order_by(Job.id).limit(1)
    if db.bind.dialect.name == "postgresql":
        q = q.with_for_update(skip_locked=True)
    job = db.execute(q).scalars().first()
    if not job:
        return None
    job.status, job.locked_by, job.heartbeat_at = "running", WORKER_ID, now
    job.attempts += 1
    db.commit()
    return job


def run_job(db, job: Job) -> None:
    video = db.get(Video, job.video_id) if job.video_id else None
    if job.kind == "produce":
        produce(db, video)
    elif job.kind == "upload":
        publish.upload(db, video)
    elif job.kind == "shorts":
        make_shorts(db, video)
    elif job.kind == "discover_topics":
        topics.discover(db, n=job.payload.get("n", 12), focus=job.payload.get("focus", ""))
    elif job.kind == "sync_analytics":
        if publish.method(db) == "youtube_api":
            analytics.sync(db)
        analytics.learn(db)     # with feed-based publishing this learns from public views/likes
    else:
        raise ValueError(f"unknown job kind {job.kind}")


def process_one() -> bool:
    db = SessionLocal()
    try:
        job = claim(db)
        if not job:
            return False
        video = db.get(Video, job.video_id) if job.video_id else None
        try:
            run_job(db, job)
            job.status, job.finished_at, job.error = "done", datetime.now(timezone.utc), ""
            db.commit()
        except costs.BudgetExceeded as e:
            db.rollback()
            job.status, job.error = "paused", str(e)
            if video:
                video.status, video.error = "paused_budget", str(e)
                emit(db, video, f"Paused: {e}", level="warn")
            db.commit()
            notify("Production paused — budget", str(e))
        except Exception as e:
            db.rollback()
            tb = traceback.format_exc()
            log.error("job %s failed: %s", job.id, tb)
            job.error = f"{e}\n{tb[-3000:]}"
            if job.attempts < job.max_attempts:
                job.status = "pending"
                job.run_after = datetime.now(timezone.utc) + timedelta(minutes=2 ** job.attempts * 3)
                if video:
                    emit(db, video, f"Attempt {job.attempts} failed, retrying: {e}", level="warn")
            else:
                job.status = "failed"
                if video:
                    if job.kind == "upload":
                        video.status = "approved"     # keep it approved; you can retry the upload
                        video.upload_status = f"failed: {str(e)[:200]}"
                    else:
                        video.status = "failed"
                    video.error = str(e)[:2000]
                    emit(db, video, f"Job failed permanently: {e}", level="error")
                notify(f"Job failed: {job.kind}", f"video {job.video_id}: {e}")
            db.commit()
        return True
    finally:
        db.close()


def scheduler_tick() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        # Approved videos (manual approval clicked) → upload job.
        for v in db.query(Video).filter(Video.status == "approved", Video.youtube_id == "").all():
            if not v.upload_status.startswith("failed"):
                enqueue(db, "upload", v.id)
        auto_fill_schedule(db)
        last_pub = _state(db, "last_publish_check")
        if not last_pub or now - datetime.fromisoformat(last_pub) > timedelta(minutes=15):
            try:
                publish.refresh_published(db)
            except Exception as e:
                log.info("publish refresh skipped: %s", e)
            _set_state(db, "last_publish_check", now.isoformat())
        last_an = _state(db, "last_analytics")
        if not last_an or now - datetime.fromisoformat(last_an) > timedelta(hours=24):
            if db.query(Video).filter(Video.status == "published").count():
                enqueue(db, "sync_analytics")
            _set_state(db, "last_analytics", now.isoformat())
    except Exception:
        log.error("scheduler tick failed: %s", traceback.format_exc())
    finally:
        db.close()


def recover_stale() -> None:
    db = SessionLocal()
    try:
        for j in db.query(Job).filter(Job.status == "running").all():
            j.status = "pending"
            j.attempts = max(0, j.attempts - 1)
        db.commit()
    finally:
        db.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_db()
    recover_stale()   # single-worker deployment: anything 'running' at start-up was interrupted
    log.info("worker %s started", WORKER_ID)
    last_tick = 0.0
    while True:
        if time.time() - last_tick > 60:
            scheduler_tick()
            last_tick = time.time()
        if not process_one():
            time.sleep(3)


if __name__ == "__main__":
    main()
