from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VideoStatus(str, enum.Enum):
    QUEUED = "queued"
    RESEARCHING = "researching"
    SCRIPTING = "scripting"
    FACT_CHECKING = "fact_checking"
    NARRATING = "narrating"
    GENERATING_VISUALS = "generating_visuals"
    ANIMATING = "animating"
    EDITING = "editing"
    RENDERING = "rendering"
    QUALITY_CHECK = "quality_check"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    UPLOADING = "uploading"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"
    PAUSED_BUDGET = "paused_budget"
    NEEDS_REVIEW = "needs_review"     # QC or fact-check failed; a human must look
    REJECTED = "rejected"


# Order used by the orchestrator to resume a job where it left off.
PRODUCTION_STAGES = [
    VideoStatus.RESEARCHING, VideoStatus.SCRIPTING, VideoStatus.FACT_CHECKING,
    VideoStatus.NARRATING, VideoStatus.GENERATING_VISUALS, VideoStatus.ANIMATING,
    VideoStatus.EDITING, VideoStatus.RENDERING, VideoStatus.QUALITY_CHECK,
]


class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    period: Mapped[str] = mapped_column(String(120), default="")
    category: Mapped[str] = mapped_column(String(80), default="")
    main_event: Mapped[str] = mapped_column(Text, default="")
    why_watch: Mapped[str] = mapped_column(Text, default="")
    target_minutes: Mapped[float] = mapped_column(Float, default=10)
    research_difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    format: Mapped[str] = mapped_column(String(30), default="")       # career_stats|comparison|recap|fact|...
    players: Mapped[list] = mapped_column(JSON, default=list)          # exact player names for stat lookups
    visual_style: Mapped[str] = mapped_column(Text, default="")
    scores: Mapped[dict] = mapped_column(JSON, default=dict)   # interest/originality/story/gap/overall
    score: Mapped[float] = mapped_column(Float, default=0)
    evidence: Mapped[list] = mapped_column(JSON, default=list)  # sources/competitor videos behind the idea
    status: Mapped[str] = mapped_column(String(20), default="suggested")  # suggested|approved|rejected|used
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Video(Base):
    __tablename__ = "videos"
    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(10), default="long")   # long|short
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default=VideoStatus.QUEUED.value)
    working_title: Mapped[str] = mapped_column(String(200), default="")
    research: Mapped[dict] = mapped_column(JSON, default=dict)      # dossier + bibliography
    script: Mapped[dict] = mapped_column(JSON, default=dict)        # sections/scenes/style bible
    fact_check: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    qc_report: Mapped[dict] = mapped_column(JSON, default=dict)
    cost_estimate: Mapped[dict] = mapped_column(JSON, default=dict)
    thumbnails: Mapped[list] = mapped_column(JSON, default=list)    # [{path, concept, score}]
    selected_thumbnail: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_s: Mapped[float] = mapped_column(Float, default=0)
    output_path: Mapped[str] = mapped_column(String(500), default="")
    subtitles_path: Mapped[str] = mapped_column(String(500), default="")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    youtube_id: Mapped[str] = mapped_column(String(40), default="")
    youtube_url: Mapped[str] = mapped_column(String(200), default="")
    upload_status: Mapped[str] = mapped_column(String(40), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    topic: Mapped[Topic | None] = relationship()
    scenes: Mapped[list["Scene"]] = relationship(back_populates="video", order_by="Scene.idx",
                                                 cascade="all, delete-orphan")
    events: Mapped[list["StageEvent"]] = relationship(back_populates="video", order_by="StageEvent.id",
                                                      cascade="all, delete-orphan")


class Scene(Base):
    __tablename__ = "scenes"
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"))
    idx: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(60), default="")
    narration: Mapped[str] = mapped_column(Text)
    visual: Mapped[dict] = mapped_column(JSON, default=dict)   # type, prompt, camera, map/timeline spec...
    on_screen_text: Mapped[str] = mapped_column(String(200), default="")
    sfx: Mapped[str] = mapped_column(String(60), default="")
    audio_path: Mapped[str] = mapped_column(String(500), default="")
    alignment: Mapped[dict] = mapped_column(JSON, default=dict)  # word timings from TTS
    audio_duration: Mapped[float] = mapped_column(Float, default=0)
    image_path: Mapped[str] = mapped_column(String(500), default="")
    motion_path: Mapped[str] = mapped_column(String(500), default="")   # AI image-to-video clip
    clip_path: Mapped[str] = mapped_column(String(500), default="")     # rendered 1080p scene clip
    start_s: Mapped[float] = mapped_column(Float, default=0)
    video: Mapped[Video] = relationship(back_populates="scenes")


class StageEvent(Base):
    __tablename__ = "stage_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"))
    stage: Mapped[str] = mapped_column(String(40))
    level: Mapped[str] = mapped_column(String(10), default="info")
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    video: Mapped[Video] = relationship(back_populates="events")


class Asset(Base):
    """Licensing ledger: every file that ends up in a video is recorded here."""
    __tablename__ = "assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))         # image|video|narration|music|sfx|map|font|thumbnail
    path: Mapped[str] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(200))      # provider/model or library entry
    license: Mapped[str] = mapped_column(String(200))
    commercial_use: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CostEntry(Base):
    __tablename__ = "cost_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(30))     # research|script|image|video|voice|storage|render|other
    provider: Mapped[str] = mapped_column(String(60))
    units: Mapped[float] = mapped_column(Float, default=0)
    unit_label: Mapped[str] = mapped_column(String(30), default="")
    usd: Mapped[float] = mapped_column(Float, default=0)
    note: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))         # produce|upload|discover_topics|sync_analytics|shorts
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id"), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|running|done|failed|paused
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    locked_by: Mapped[str] = mapped_column(String(60), default="")
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(30), unique=True)
    encrypted: Mapped[str] = mapped_column(Text)          # Fernet-encrypted JSON credentials
    account_label: Mapped[str] = mapped_column(String(200), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AnalyticsSnapshot(Base):
    __tablename__ = "analytics"
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id"), nullable=True)
    youtube_id: Mapped[str] = mapped_column(String(40))
    day: Mapped[str] = mapped_column(String(10))          # YYYY-MM-DD the snapshot was taken
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    retention: Mapped[list] = mapped_column(JSON, default=list)   # [[ratio, audienceWatchRatio], ...]


class Clip(Base):
    """Footage YOU have rights to (your own games, licensed packs). Never scraped."""
    __tablename__ = "clips"
    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(300))           # who shot it / where it was licensed
    license: Mapped[str] = mapped_column(String(300))
    attested_by_user: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_s: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Meme(Base):
    __tablename__ = "memes"
    id: Mapped[int] = mapped_column(primary_key=True)
    idea: Mapped[dict] = mapped_column(JSON, default=dict)
    image_path: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default="idea")   # idea|rendered|video|rejected
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Insight(Base):
    __tablename__ = "insights"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
