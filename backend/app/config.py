"""Process-level configuration loaded from environment / .env.

Secrets (API keys, OAuth client secret, encryption key) live ONLY here, never in
the database or the frontend. User-tunable behaviour (schedule, budgets, voices,
style) lives in the `settings` table and is edited from the dashboard.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Env(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    # Infrastructure
    database_url: str = f"sqlite:///{ROOT / 'data' / 'app.db'}"
    data_dir: Path = ROOT / "data"
    assets_dir: Path = ROOT / "assets"
    public_base_url: str = "http://localhost:8000"   # used for the OAuth redirect URI
    frontend_url: str = "http://localhost:5173"
    dashboard_token: str = ""                          # if set, required as Bearer token on /api
    secret_key: str = ""                               # Fernet key for encrypting OAuth tokens

    # AI providers — free defaults
    gemini_api_key: str = ""                           # https://aistudio.google.com/apikey (free tier)
    cloudflare_account_id: str = ""                    # free Cloudflare account → Workers AI
    cloudflare_api_token: str = ""
    balldontlie_api_key: str = ""                      # free account at app.balldontlie.io (scores, games)
    dashboard_password: str = ""                       # dashboard login
    # Optional paid upgrades
    anthropic_api_key: str = ""
    fal_key: str = ""
    elevenlabs_api_key: str = ""

    # Google / YouTube
    google_client_id: str = ""
    google_client_secret: str = ""
    youtube_api_key: str = ""                          # optional: public search for topic research

    # Notifications
    notify_webhook_url: str = ""                       # Discord / Slack incoming webhook
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    notify_email_to: str = ""

    # Rendering
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    x264_preset: str = "medium"                        # final render; 'veryfast' for quick drafts
    x264_crf: int = 18


env = Env()
env.data_dir.mkdir(parents=True, exist_ok=True)
