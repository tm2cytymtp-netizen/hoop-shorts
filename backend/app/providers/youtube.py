"""YouTube Data API v3 + YouTube Analytics API via OAuth 2.0.

- Your Google password is never seen or stored: you sign in on Google's own page.
- Refresh tokens are stored encrypted (Fernet, key in .env).
- Quota: videos.insert and search.list have their own daily buckets (100 calls/day
  each by default); other calls share 10,000 units/day.
- IMPORTANT: uploads from an *unverified* API project are locked to private. Complete
  YouTube's API compliance audit before relying on scheduled public publishing.
"""
from __future__ import annotations

import json
import random
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from sqlalchemy.orm import Session

from ..config import env
from ..crypto import decrypt_json, encrypt_json
from ..models import OAuthToken

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",           # captions.insert
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
]
RETRIABLE = {500, 502, 503, 504}


class YouTubeError(Exception):
    pass


def redirect_uri() -> str:
    return f"{env.public_base_url.rstrip('/')}/api/youtube/oauth/callback"


def _flow(state: str | None = None) -> Flow:
    if not (env.google_client_id and env.google_client_secret):
        raise YouTubeError("GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET not configured (see README).")
    cfg = {"web": {"client_id": env.google_client_id, "client_secret": env.google_client_secret,
                   "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                   "token_uri": "https://oauth2.googleapis.com/token",
                   "redirect_uris": [redirect_uri()]}}
    return Flow.from_client_config(cfg, scopes=SCOPES, state=state, redirect_uri=redirect_uri())


def auth_url() -> tuple[str, str, str | None]:
    flow = _flow()
    url, state = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
    return url, state, getattr(flow, "code_verifier", None)


def finish_auth(db: Session, code: str, state: str, code_verifier: str | None = None) -> str:
    flow = _flow(state)
    if code_verifier:
        flow.code_verifier = code_verifier
    flow.fetch_token(code=code)
    creds = flow.credentials
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    ch = yt.channels().list(part="snippet", mine=True).execute().get("items", [])
    label = ch[0]["snippet"]["title"] if ch else "unknown channel"
    _save(db, creds, label)
    return label


def _save(db: Session, creds: Credentials, label: str | None = None) -> None:
    row = db.query(OAuthToken).filter_by(provider="youtube").first()
    data = json.loads(creds.to_json())
    if row:
        row.encrypted = encrypt_json(data)
        if label:
            row.account_label = label
    else:
        db.add(OAuthToken(provider="youtube", encrypted=encrypt_json(data), account_label=label or ""))
    db.commit()


def connection(db: Session) -> dict:
    row = db.query(OAuthToken).filter_by(provider="youtube").first()
    return {"connected": bool(row), "channel": row.account_label if row else ""}


def disconnect(db: Session) -> None:
    db.query(OAuthToken).filter_by(provider="youtube").delete()
    db.commit()


def credentials(db: Session) -> Credentials:
    row = db.query(OAuthToken).filter_by(provider="youtube").first()
    if not row:
        raise YouTubeError("YouTube account not connected (Settings → YouTube → Connect).")
    creds = Credentials.from_authorized_user_info(decrypt_json(row.encrypted), SCOPES)
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        _save(db, creds)
    return creds


def client(db: Session):
    return build("youtube", "v3", credentials=credentials(db), cache_discovery=False)


def analytics_client(db: Session):
    return build("youtubeAnalytics", "v2", credentials=credentials(db), cache_discovery=False)


def _execute(req, tries: int = 5):
    for attempt in range(tries):
        try:
            return req.execute()
        except HttpError as e:
            if e.resp.status in RETRIABLE and attempt < tries - 1:
                time.sleep(2 ** attempt + random.random())
                continue
            raise


def upload_video(db: Session, path: Path, *, title: str, description: str, tags: list[str], category_id: str,
                 publish_at: datetime | None, synthetic: bool, made_for_kids: bool = False,
                 language: str = "en", progress=None) -> str:
    yt = client(db)
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": made_for_kids,
              "containsSyntheticMedia": synthetic, "embeddable": True, "license": "youtube"}
    if publish_at:
        status["publishAt"] = publish_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    body = {"snippet": {"title": title, "description": description, "tags": tags, "categoryId": category_id,
                        "defaultLanguage": language, "defaultAudioLanguage": language},
            "status": status}
    media = MediaFileUpload(str(path), chunksize=16 * 1024 * 1024, resumable=True, mimetype="video/mp4")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media, notifySubscribers=True)
    response, attempt = None, 0
    while response is None:
        try:
            st, response = req.next_chunk()
            if st and progress:
                progress(st.progress())
        except HttpError as e:
            if e.resp.status in RETRIABLE and attempt < 8:
                attempt += 1
                time.sleep(min(60, 2 ** attempt) + random.random())
                continue
            raise YouTubeError(f"Upload failed: {e}") from e
        except (ConnectionError, TimeoutError, OSError) as e:
            if attempt < 8:
                attempt += 1
                time.sleep(min(60, 2 ** attempt) + random.random())
                continue
            raise YouTubeError(f"Upload failed: {e}") from e
    if "id" not in response:
        raise YouTubeError(f"Unexpected upload response: {response}")
    return response["id"]


def set_thumbnail(db: Session, video_id: str, path: Path) -> None:
    _execute(client(db).thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(path), mimetype="image/jpeg")))


def upload_captions(db: Session, video_id: str, srt: Path, language: str = "en") -> None:
    body = {"snippet": {"videoId": video_id, "language": language, "name": "", "isDraft": False}}
    _execute(client(db).captions().insert(part="snippet", body=body,
                                          media_body=MediaFileUpload(str(srt), mimetype="application/octet-stream")))


def ensure_playlist(db: Session, title: str, description: str = "") -> str:
    yt = client(db)
    page = None
    while True:
        res = _execute(yt.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=page))
        for p in res.get("items", []):
            if p["snippet"]["title"].strip().lower() == title.strip().lower():
                return p["id"]
        page = res.get("nextPageToken")
        if not page:
            break
    res = _execute(yt.playlists().insert(part="snippet,status", body={
        "snippet": {"title": title, "description": description}, "status": {"privacyStatus": "public"}}))
    return res["id"]


def add_to_playlist(db: Session, playlist_id: str, video_id: str) -> None:
    _execute(client(db).playlistItems().insert(part="snippet", body={
        "snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}))


def video_status(db: Session, video_id: str) -> dict:
    res = _execute(client(db).videos().list(part="status,processingDetails", id=video_id))
    items = res.get("items", [])
    return items[0] if items else {}


def search_popular(db: Session | None, query: str, max_results: int = 15, days: int = 365,
                   duration: str = "medium") -> list[dict]:
    """Public search used for topic research / gap analysis (search.list: own quota bucket)."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if env.youtube_api_key:
        yt = build("youtube", "v3", developerKey=env.youtube_api_key, cache_discovery=False)
    elif db is not None:
        yt = client(db)
    else:
        raise YouTubeError("No YouTube API key or OAuth connection for search.")
    res = _execute(yt.search().list(part="snippet", q=query, type="video", order="viewCount", maxResults=max_results,
                                    publishedAfter=since, relevanceLanguage="en", videoDuration=duration))
    ids = [i["id"]["videoId"] for i in res.get("items", [])]
    if not ids:
        return []
    stats = _execute(yt.videos().list(part="statistics,snippet,contentDetails", id=",".join(ids)))
    out = []
    for v in stats.get("items", []):
        out.append({"id": v["id"], "title": v["snippet"]["title"], "channel": v["snippet"]["channelTitle"],
                    "published": v["snippet"]["publishedAt"][:10],
                    "views": int(v["statistics"].get("viewCount", 0)), "duration": v["contentDetails"]["duration"]})
    return out


def analytics_for_videos(db: Session, video_ids: list[str], start: date, end: date) -> dict[str, dict]:
    ya = analytics_client(db)
    out: dict[str, dict] = {}
    base_metrics = ("views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
                    "subscribersGained,subscribersLost,likes,comments,shares")
    for chunk in [video_ids[i:i + 50] for i in range(0, len(video_ids), 50)]:
        filt = "video==" + ",".join(chunk)
        res = _execute(ya.reports().query(ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(),
                                          metrics=base_metrics, dimensions="video", filters=filt))
        cols = [h["name"] for h in res.get("columnHeaders", [])]
        for row in res.get("rows", []):
            d = dict(zip(cols, row))
            out[d.pop("video")] = d
        # Thumbnail impressions / CTR and revenue are only available for some channels; best-effort.
        for extra in ("videoThumbnailImpressions,videoThumbnailImpressionsClickRate",
                      "estimatedRevenue"):
            try:
                r2 = _execute(ya.reports().query(ids="channel==MINE", startDate=start.isoformat(),
                                                 endDate=end.isoformat(), metrics=extra, dimensions="video",
                                                 filters=filt), tries=2)
                c2 = [h["name"] for h in r2.get("columnHeaders", [])]
                for row in r2.get("rows", []):
                    d = dict(zip(c2, row))
                    out.setdefault(d.pop("video"), {}).update(d)
            except HttpError:
                pass
    return out


def retention_curve(db: Session, video_id: str, start: date, end: date) -> list[list[float]]:
    try:
        res = _execute(analytics_client(db).reports().query(
            ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(),
            metrics="audienceWatchRatio,relativeRetentionPerformance", dimensions="elapsedVideoTimeRatio",
            filters=f"video=={video_id}"), tries=2)
        return [[float(r[0]), float(r[1]), float(r[2])] for r in res.get("rows", [])]
    except HttpError:
        return []
