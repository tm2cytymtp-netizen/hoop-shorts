"""User-editable settings with safe defaults (stored in the DB, edited from the dashboard)."""
from __future__ import annotations

import copy

from sqlalchemy.orm import Session

from .models import Setting

DEFAULTS: dict = {
    "channel": {
        "name": "",
        "language": "en",
        "format": "shorts",            # shorts | long — what "Generate New Video" and auto-production make
        "youtube_channel_id": "",      # UC... — used to confirm posts and read public view counts (no API)
        "categories": [
            "NBA memes", "Funny basketball moments", "Player comparisons", "Crazy basketball statistics",
            "Basketball hot takes", "NBA rivalries", "Unexpected basketball moments", "Historical NBA moments",
            "Greatest players debates", "NBA news and trending stories", "What-if scenarios", "NBA rankings",
            "Basketball facts", "Funny hypothetical situations", "Legendary NBA moments", "Basketball storytimes",
        ],
        # Relative weights for the daily mix of formats (A–G in the brief)
        # Stats-first channel (hoopgraphs / NBArecap style). recap needs the BALLDONTLIE ALL-STAR plan.
        "format_mix": {"career_stats": 4, "comparison": 3, "fact": 2, "recap": 2, "ranking": 1, "storyline": 1,
                       "news_reaction": 1, "meme": 0, "hypothetical": 0},
    },
    "ai": {
        # Free stack: gemini (free tier) + Wikipedia research, cloudflare (free FLUX) + The Met CC0 artworks.
        # Paid upgrade: llm_provider "anthropic" (+ live web search), image_provider "fal" (+ AI motion).
        "llm_provider": "gemini",
        "gemini_model": "gemini-3.5-flash",
        "gemini_model_fast": "gemini-3.1-flash-lite",
        "image_provider": "cloudflare",
        "cf_image_model": "@cf/black-forest-labs/flux-1-schnell",
        "use_museum_artworks": True,
        "llm_model": "claude-sonnet-5-5",           # research, scripting, fact-checking
        "llm_model_fast": "claude-haiku-5-5",       # cheap helper calls (scoring, metadata)
        "web_search_max_uses": 12,
        "web_search_tool": "web_search_20250305",   # Anthropic server tool version
        "blocked_domains": ["quora.com", "reddit.com", "pinterest.com", "facebook.com", "tiktok.com"],
        "image_model": "fal-ai/flux-pro/v1.1",      # any fal text-to-image endpoint
        "image_size": {"width": 1920, "height": 1088},
        "video_model": "fal-ai/kling-video/v2.1/standard/image-to-video",
        "video_clip_seconds": 5,
        "animated_scene_ratio": 0.25,                # share of scenes that get AI motion (rest: camera moves)
    },
    "voice": {
        # respellings checked against Kokoro's phonemizer (Celtics -> "sel-tiks", not "kel-tiks")
        "pronunciations": {"Celtics": "Selltix", "Hayward": "Hayword", "Kobe": "Kobey", "Dončić": "Donchich",
                           "Doncic": "Donchich", "Jerome": "/dʒəɹˈoʊm/", "Wagner": "Vahgner"},
        "provider": "kokoro",          # kokoro = free, runs on your computer | elevenlabs = paid
        "kokoro_presets": {
            "energetic_commentator": "am_puck", "funny_meme_narrator": "am_eric",
            "debate_host": "am_fenrir",     # original fiery hot-take host (not a real person)
            "warm_storyteller": "am_michael",  # deeper, warmer, most natural-sounding free male voice
            "casual_genz": "am_liam", "sports_analyst": "am_michael", "dramatic_documentary": "bm_george",
        },
        "format_voice": {"career_stats": "sports_analyst", "recap": "energetic_commentator",
                         "meme": "funny_meme_narrator", "comparison": "sports_analyst", "fact": "energetic_commentator",
                         "storyline": "casual_genz", "ranking": "energetic_commentator",
                         "hypothetical": "funny_meme_narrator", "news_reaction": "casual_genz"},
        "speed": 1.08,
        "preset": "sports_analyst",
        "presets": {
            # ElevenLabs voice IDs: replace with voices from your ElevenLabs Voice Library.
            "male_documentary": {"voice_id": "", "stability": 0.5, "similarity_boost": 0.8, "style": 0.15},
            "female_documentary": {"voice_id": "", "stability": 0.5, "similarity_boost": 0.8, "style": 0.15},
            "deep_cinematic": {"voice_id": "", "stability": 0.4, "similarity_boost": 0.85, "style": 0.35},
            "calm_educational": {"voice_id": "", "stability": 0.65, "similarity_boost": 0.75, "style": 0.05},
        },
        "model_id": "eleven_multilingual_v2",
        "speed": 1.0,
    },
    "video": {
        "target_minutes": [8, 15],
        "art_style": ("bold cartoon illustration, vibrant saturated colors, thick clean outlines, exaggerated "
                      "funny facial expressions, basketball arena lighting, meme style"),
        "music_volume_db_textonly": -9,  # louder bed when a meme has no narration
        "label_ai_visuals": False,
        "show_data_footer": False,     # source line at the bottom of charts (sources are always in the description)     # cartoon memes are obviously stylised; disclosure goes in the description
        "burn_subtitles": False,       # captions are always uploaded as a track; burn-in optional
        "music_volume_db": -20,
        "transition": "fade",
        "transition_s": 0.0,           # 0 = hard cuts with sound-effect hits (Shorts style)
        "dynamic_bg": True,            # animated broadcast-style backgrounds behind charts
        "fps": 30,
    },
    "publishing": {
        # zapier_rss   — fully automatic & public: a Zap (RSS → YouTube 'Upload Video') posts each Short
        #                at its scheduled time. No Google Cloud project needed.
        # manual_batch — download a weekly pack and schedule it yourself in YouTube Studio (~10 min/week).
        # youtube_api  — your own Google Cloud project (needs YouTube's audit before uploads can be public).
        "method": "zapier_rss",
        "feed_key": "",                # auto-generated secret that protects the feed URL
    },
    "data": {
        "balldontlie_tier": "free",    # free | all_star ($9.99/mo: per-game player stats → nightly recaps)
    },
    "shorts": {
        "target_seconds": [15, 45],
        "max_seconds": 59,
        "animated_scenes": 0,          # AI image-to-video clips per Short (paid: fal.ai only)
        "times": ["11:00", "15:00", "19:00"],   # daily posting times; 3/day ≈ 90 posts/month fits Zapier's free 100
        "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        "image_size": {"width": 816, "height": 1440},
    },
    "schedule": {
        "days": ["mon", "wed", "fri"],
        "time": "15:00",
        "timezone": "America/New_York",
        "lead_days": 4,                 # start production this many days before a slot
        "auto_produce": True,           # produce videos automatically to fill upcoming slots
        "approval_mode": "auto",        # auto = publish only when ALL checks pass | manual = you approve each
        "shorts_per_video": 3,
        "auto_shorts": True,
        "shorts_upload": False,
    },
    "budget": {
        "max_per_video_usd": 25.0,
        "max_monthly_usd": 300.0,
        "max_images_per_video": 70,
        "max_video_requests_per_video": 15,
    },
    # Editable price table used for estimates and the cost ledger. Check your providers'
    # current pricing pages and update these — they are estimates, not quotes.
    "pricing": {
        "llm_input_per_mtok": 3.0,
        "llm_output_per_mtok": 15.0,
        "llm_fast_input_per_mtok": 1.0,
        "llm_fast_output_per_mtok": 5.0,
        "web_search_per_1k": 10.0,
        "image_each": 0.04,
        "video_per_second": 0.056,
        "tts_per_1k_chars": 0.20,
        "storage_per_gb_month": 0.021,
    },
    "quality": {
        "min_factcheck_supported_ratio": 0.95,
        "max_similarity_to_previous": 0.35,
        "min_value_score": 6,
        "target_lufs": -14,
    },
}


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def get_all(db: Session) -> dict:
    stored = {s.key: s.value for s in db.query(Setting).all()}
    out = {k: _deep_merge(v, stored.get(k) or {}) if isinstance(v, dict) else stored.get(k, v)
           for k, v in DEFAULTS.items()}
    if not out["publishing"]["feed_key"]:
        import secrets
        update(db, "publishing", {"feed_key": secrets.token_urlsafe(24)})
        return get_all(db)
    return out


def get(db: Session, section: str) -> dict:
    return get_all(db)[section]


def update(db: Session, section: str, value: dict) -> dict:
    if section not in DEFAULTS:
        raise KeyError(section)
    row = db.get(Setting, section)
    merged = _deep_merge((row.value if row else {}) or {}, value)
    if row:
        row.value = merged
    else:
        db.add(Setting(key=section, value=merged))
    db.commit()
    return get(db, section)
