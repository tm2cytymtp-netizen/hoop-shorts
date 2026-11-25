"""Publishing: scheduling slots and three ways to get videos onto YouTube.

zapier_rss   Fully automatic and public, no Google Cloud project. At each video's scheduled time it appears
             in a private RSS feed served by this app; a Zap ("RSS by Zapier → YouTube: Upload Video",
             privacy Public) posts it within the Zap's polling interval.
manual_batch No third party. Download a weekly pack (videos + schedule.csv) and schedule them in YouTube
             Studio yourself.
youtube_api  Your own Google Cloud project via OAuth. Uploads stay private until the project passes
             YouTube's API audit.

For the first two methods, publication is confirmed by reading the channel's public RSS feed
(youtube.com/feeds/videos.xml), which also provides view and like counts — no API key involved.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.orm import Session

from .. import settings_store
from ..events import emit, set_status
from ..models import AnalyticsSnapshot, Video
from ..notify import notify
from ..providers import youtube

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def upcoming_slots(db: Session, count: int = 12, after: datetime | None = None, kind: str | None = None) -> list[datetime]:
    sch = settings_store.get(db, "schedule")
    if kind is None:
        kind = "short" if settings_store.get(db, "channel").get("format") == "shorts" else "long"
    if kind == "short":
        sh = settings_store.get(db, "shorts")
        days, times = sh["days"], sh["times"]
    else:
        days, times = sch["days"], [sch["time"]]
    tz = ZoneInfo(sch["timezone"])
    now = (after or datetime.now(timezone.utc)).astimezone(tz)
    out, day = [], now.replace(hour=0, minute=0, second=0, microsecond=0)
    for _ in range(120):
        if DAYS[day.weekday()] in days:
            for t in sorted(times):
                hh, mm = map(int, t.split(":"))
                slot = day.replace(hour=hh, minute=mm)
                if slot > now + timedelta(minutes=45):
                    out.append(slot.astimezone(timezone.utc))
                    if len(out) >= count:
                        return out
        day += timedelta(days=1)
    return out


def next_free_slot(db: Session, kind: str = "long") -> datetime:
    taken = {_utc(v.scheduled_at) for v in db.query(Video).filter(
        Video.kind == kind, Video.scheduled_at.isnot(None), Video.status.notin_(["failed", "rejected"])).all()}
    for s in upcoming_slots(db, 200, kind=kind):
        if s not in taken:
            return s
    raise RuntimeError("No free publishing slot found.")


def method(db: Session) -> str:
    return settings_store.get(db, "publishing")["method"]


def upload(db: Session, video: Video) -> None:
    if video.status not in ("approved", "uploading"):
        raise RuntimeError(f"Video {video.id} is '{video.status}', not approved — refusing to upload.")
    if not (video.qc_report or {}).get("passed"):
        raise RuntimeError("Quality checks have not passed — refusing to upload.")
    if not video.scheduled_at:
        video.scheduled_at = next_free_slot(db, video.kind)
        db.commit()
    m = method(db)
    if m == "youtube_api":
        return _upload_api(db, video)
    video.upload_status = "queued_for_feed" if m == "zapier_rss" else "awaiting_manual_upload"
    set_status(db, video, "scheduled")
    when = _utc(video.scheduled_at)
    how = ("will be released to your Zap" if m == "zapier_rss" else
           "is in this week's upload pack — schedule it in YouTube Studio")
    notify("Video ready & scheduled", f"{video.metadata_.get('title')} — {how} at {when:%a %d %b %H:%M UTC}")


def _upload_api(db: Session, video: Video) -> None:
    md = video.metadata_ or {}
    set_status(db, video, "uploading")
    publish_at = _utc(video.scheduled_at)
    if publish_at < datetime.now(timezone.utc) + timedelta(minutes=20):
        publish_at = datetime.now(timezone.utc) + timedelta(minutes=30)
        video.scheduled_at = publish_at
    if not video.youtube_id:
        lang = settings_store.get(db, "channel").get("language", "en")
        yt_id = youtube.upload_video(
            db, Path(video.output_path), title=md["title"], description=md["description"], tags=md.get("tags", []),
            category_id=md.get("category_id", "27"), publish_at=publish_at,
            synthetic=bool(md.get("contains_synthetic_media", True)), made_for_kids=False, language=lang)
        video.youtube_id = yt_id
        video.youtube_url = (f"https://www.youtube.com/shorts/{yt_id}" if video.kind == "short"
                             else f"https://www.youtube.com/watch?v={yt_id}")
        video.upload_status = "uploaded"
        db.commit()
        emit(db, video, f"Uploaded to YouTube: {video.youtube_url}")
    if video.kind == "long":
        if video.selected_thumbnail is not None and video.thumbnails and video.upload_status == "uploaded":
            try:
                youtube.set_thumbnail(db, video.youtube_id, Path(video.thumbnails[video.selected_thumbnail]["path"]))
            except Exception as e:
                emit(db, video, f"Thumbnail upload failed (is the channel phone-verified?): {e}", level="warn")
            video.upload_status = "thumbnail_set"
            db.commit()
        if video.subtitles_path and video.upload_status == "thumbnail_set":
            try:
                youtube.upload_captions(db, video.youtube_id, Path(video.subtitles_path),
                                        settings_store.get(db, "channel").get("language", "en"))
            except Exception as e:
                emit(db, video, f"Caption upload failed: {e}", level="warn")
            video.upload_status = "captions_set"
            db.commit()
        if md.get("playlist") and video.upload_status == "captions_set":
            try:
                youtube.add_to_playlist(db, youtube.ensure_playlist(db, md["playlist"]), video.youtube_id)
            except Exception as e:
                emit(db, video, f"Playlist assignment failed: {e}", level="warn")
            video.upload_status = "complete"
            db.commit()
    st = youtube.video_status(db, video.youtube_id).get("status", {})
    if st.get("uploadStatus") in ("rejected", "failed"):
        raise RuntimeError(f"YouTube rejected the upload: {st}")
    set_status(db, video, "scheduled")
    notify("Video scheduled", f"{md.get('title')} — publishes {publish_at:%a %d %b %H:%M UTC}", video.youtube_url)


# ---------------------------------------------------------------- feed for Zapier
def released(db: Session, limit: int = 25) -> list[Video]:
    """Videos whose scheduled time has arrived — these are what the Zapier feed exposes."""
    now = datetime.now(timezone.utc)
    vids = db.query(Video).filter(Video.status.in_(["scheduled", "published"]), Video.scheduled_at.isnot(None),
                                  Video.upload_status.in_(["queued_for_feed", "in_feed", "confirmed"])) \
        .order_by(Video.scheduled_at.desc()).limit(200).all()
    return [v for v in vids if _utc(v.scheduled_at) <= now][:limit]


# ---------------------------------------------------------------- public channel feed (no API)
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
      "media": "http://search.yahoo.com/mrss/"}


def channel_feed(channel_id: str) -> list[dict]:
    r = httpx.get(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}", timeout=20,
                  headers={"User-Agent": "Mozilla/5.0 (feed reader)"})
    r.raise_for_status()
    root = ET.fromstring(r.content)
    out = []
    for e in root.findall("a:entry", NS):
        stats = e.find("media:group/media:community/media:statistics", NS)
        rating = e.find("media:group/media:community/media:starRating", NS)
        out.append({"id": e.findtext("yt:videoId", "", NS), "title": e.findtext("a:title", "", NS),
                    "published": e.findtext("a:published", "", NS),
                    "views": int(stats.get("views", 0)) if stats is not None else 0,
                    "likes": int(rating.get("count", 0)) if rating is not None else 0})
    return out


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", re.sub(r"#\w+", "", t.lower())).strip()


def refresh_published(db: Session) -> None:
    now = datetime.now(timezone.utc)
    m = method(db)
    if m == "youtube_api":
        for v in db.query(Video).filter(Video.status == "scheduled").all():
            if _utc(v.scheduled_at) <= now:
                try:
                    st = youtube.video_status(db, v.youtube_id).get("status", {})
                except Exception:
                    continue
                if st.get("privacyStatus") == "public":
                    set_status(db, v, "published")
                    notify("Video published", v.metadata_.get("title", v.working_title), v.youtube_url)
                elif _utc(v.scheduled_at) < now - timedelta(hours=2):
                    emit(db, v, "Scheduled time passed but the video is still private. Uploads from unverified "
                                "API projects stay private until YouTube's API audit is passed.", level="warn")
        return
    # Feed-based methods: mark release, then confirm through the public channel feed.
    for v in db.query(Video).filter(Video.status == "scheduled", Video.upload_status == "queued_for_feed").all():
        if _utc(v.scheduled_at) <= now:
            v.upload_status = "in_feed"
            db.commit()
            emit(db, v, "Released to the publishing feed")
    channel_id = settings_store.get(db, "channel").get("youtube_channel_id", "")
    if not channel_id:
        return
    try:
        entries = channel_feed(channel_id)
    except Exception as e:
        emit_once = db.query(Video).filter(Video.upload_status == "in_feed").first()
        if emit_once:
            emit(db, emit_once, f"Could not read the channel feed: {e}", level="warn")
        return
    by_title = {_norm(e["title"]): e for e in entries}
    for v in db.query(Video).filter(Video.status.in_(["scheduled", "published"]),
                                    Video.upload_status.in_(["in_feed", "awaiting_manual_upload", "confirmed"])).all():
        e = by_title.get(_norm((v.metadata_ or {}).get("title", "")))
        if e and v.upload_status != "confirmed":
            v.youtube_id = e["id"]
            v.youtube_url = (f"https://www.youtube.com/shorts/{e['id']}" if v.kind == "short"
                             else f"https://www.youtube.com/watch?v={e['id']}")
            v.upload_status = "confirmed"
            db.commit()
            set_status(db, v, "published")
            notify("Published on YouTube", v.metadata_.get("title", ""), v.youtube_url)
        elif e is None and v.upload_status == "in_feed" and _utc(v.scheduled_at) < now - timedelta(hours=3) \
                and not v.error:
            v.error = ("Released to the feed 3h ago but not seen on the channel. Check the Zap's history in "
                       "Zapier (file size, task limits, disconnected YouTube account).")
            db.commit()
            emit(db, v, v.error, level="warn")
            notify("Short not seen on YouTube yet", v.metadata_.get("title", ""))
        if e and not db.query(AnalyticsSnapshot).filter_by(video_id=v.id, day=date.today().isoformat()).first():
            # lightweight daily analytics from the public feed: views + likes
            db.add(AnalyticsSnapshot(video_id=v.id, youtube_id=e["id"], day=date.today().isoformat(),
                                     metrics={"views": e["views"], "likes": e["likes"], "source": "public_feed"}))
    db.commit()
