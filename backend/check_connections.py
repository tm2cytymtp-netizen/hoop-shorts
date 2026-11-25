"""Verify every integration with the cheapest possible call.

    cd backend && python check_connections.py           # free checks only
    cd backend && python check_connections.py --paid    # also renders one test image on fal (~$0.04)
"""
from __future__ import annotations

import shutil
import sys

import httpx

from app.config import env
from app.db import SessionLocal, init_db


def ok(name, cond, detail=""):
    print(f"{'✅' if cond else '❌'} {name:28s} {detail}")
    return cond


def main():
    init_db()
    db = SessionLocal()
    from app import settings_store
    ok("ffmpeg", shutil.which(env.ffmpeg_bin) is not None, shutil.which(env.ffmpeg_bin) or "install ffmpeg")

    ai = settings_store.get(db, "ai")
    # Free stack
    if ai["llm_provider"] == "gemini":
        if env.gemini_api_key:
            try:
                from app.providers import gemini
                out = gemini.generate(db, video_id=None, category="other", system="Be brief.", prompt="Say OK",
                                      fast=True, max_tokens=20, note="connection check")
                ok("Gemini (free tier)", True, f"{ai['gemini_model_fast']}: {str(out).strip()[:30]}")
            except Exception as e:
                ok("Gemini (free tier)", False, str(e)[:200] + " — check model IDs in Settings → AI providers")
        else:
            ok("Gemini (free tier)", False, "GEMINI_API_KEY missing (free: aistudio.google.com/apikey)")
        try:
            from app.providers import wiki
            ok("Wikipedia (research)", bool(wiki.search("Battle of Hastings", 1)), "reachable")
        except Exception as e:
            ok("Wikipedia (research)", False, str(e)[:150])
    if ai["image_provider"] == "cloudflare":
        ok("Cloudflare Workers AI keys", bool(env.cloudflare_account_id and env.cloudflare_api_token),
           "CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN")
        if env.cloudflare_account_id and env.cloudflare_api_token and "--paid" not in sys.argv:
            try:
                from pathlib import Path

                from app.providers import cfai
                res = cfai.generate_image(db, None, "a Roman legionary standing guard at dawn, painted illustration",
                                          Path(env.data_dir) / "cf_test.png")
                ok("Cloudflare FLUX image (free)", True, res["path"])
            except Exception as e:
                ok("Cloudflare FLUX image (free)", False, str(e)[:200])
    try:
        from app.providers import bdl
        g = bdl.recent_games(2)
        ok("BALLDONTLIE (NBA scores)", True, f"{len(g)} games in the last 2 days")
    except Exception as e:
        ok("BALLDONTLIE (NBA scores)", False, str(e)[:150])
    try:
        from app.providers import news
        h = news.headlines(5)
        ok("NBA headlines (RSS)", bool(h), f"{len(h)} headlines, e.g. '{h[0]['title'][:60]}'" if h else "no headlines")
    except Exception as e:
        ok("NBA headlines (RSS)", False, str(e)[:150])
    try:
        from pathlib import Path

        from app.providers import commons
        ph = commons.find_photo("Stephen Curry", Path(env.data_dir) / "commons_test.jpg")
        ok("Wikimedia Commons photos", bool(ph), ph["credit"] if ph else "no licensed photo found")
    except Exception as e:
        ok("Wikimedia Commons photos", False, str(e)[:150])
    if settings_store.get(db, "voice").get("provider", "kokoro") == "kokoro":
        try:
            from pathlib import Path

            from app.providers import kokoro_tts
            res = kokoro_tts.synthesize("He really thought he was the greatest shooter alive.",
                                        Path(env.data_dir) / "voice_test.mp3", "am_puck")
            ok("Kokoro narration (local, free)", True, res["path"] + "  ← listen to it")
        except Exception as e:
            ok("Kokoro narration (local, free)", False, str(e)[:200])
    # Paid options
    if ai["llm_provider"] != "anthropic":
        pass
    elif env.anthropic_api_key:
        try:
            import anthropic
            m = settings_store.get(db, "ai")["llm_model_fast"]
            r = anthropic.Anthropic(api_key=env.anthropic_api_key).messages.create(
                model=m, max_tokens=5, messages=[{"role": "user", "content": "Say OK"}])
            ok("Anthropic", True, f"{m} replied")
            ok("Anthropic main model", True, settings_store.get(db, "ai")["llm_model"] + " (configured)")
        except Exception as e:
            ok("Anthropic", False, str(e)[:200])
    else:
        ok("Anthropic", False, "ANTHROPIC_API_KEY missing")
    # ElevenLabs
    if settings_store.get(db, "voice").get("provider") != "elevenlabs":
        pass
    elif env.elevenlabs_api_key:
        r = httpx.get("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": env.elevenlabs_api_key})
        if ok("ElevenLabs", r.status_code == 200, r.json().get("tier", "") if r.status_code == 200 else r.text[:150]):
            vs = settings_store.get(db, "voice")
            vid = vs["presets"][vs["preset"]].get("voice_id")
            if vid:
                v = httpx.get(f"https://api.elevenlabs.io/v1/voices/{vid}", headers={"xi-api-key": env.elevenlabs_api_key})
                ok("ElevenLabs voice", v.status_code == 200, v.json().get("name", "") if v.status_code == 200 else v.text[:150])
            else:
                ok("ElevenLabs voice", False, f"set a voice_id for preset '{vs['preset']}' in Settings → Voice")
    else:
        ok("ElevenLabs", False, "ELEVENLABS_API_KEY missing")
    # fal
    if ai["image_provider"] != "fal":
        pass
    elif env.fal_key and "--paid" in sys.argv:
        from pathlib import Path

        from app.providers import fal
        try:
            res = fal.generate_image(db, None, "a Roman legionary standing guard at dawn, painted illustration",
                                     Path(env.data_dir) / "fal_test.png", width=1024, height=576)
            ok("fal.ai image", True, res["path"])
        except Exception as e:
            ok("fal.ai image", False, str(e)[:200])
    else:
        ok("fal.ai key present", bool(env.fal_key), "run with --paid to test a real generation (~$0.04)")

    pub = settings_store.get(db, "publishing")["method"]
    ok("Publishing method", True, pub)
    if pub == "zapier_rss":
        local = any(h in env.public_base_url for h in ("localhost", "127.0.0.1"))
        ok("Public URL for Zapier", not local and env.public_base_url.startswith("https"),
           env.public_base_url + ("  ← Zapier can't reach localhost" if local else ""))
    cid = settings_store.get(db, "channel").get("youtube_channel_id")
    if cid:
        try:
            from app.pipeline.publish import channel_feed
            ok("Channel public feed", True, f"{len(channel_feed(cid))} recent videos visible")
        except Exception as e:
            ok("Channel public feed", False, str(e)[:150])
    else:
        ok("YouTube channel ID", False, "Settings → Channel → youtube_channel_id (UC...)")
    if pub == "youtube_api":
        ok("SECRET_KEY", bool(env.secret_key), "" if env.secret_key else "generate a Fernet key (README)")
        ok("Google OAuth client", bool(env.google_client_id and env.google_client_secret),
           f"redirect URI to register: {env.public_base_url.rstrip('/')}/api/youtube/oauth/callback")
        try:
            from app.providers import youtube
            yt = youtube.client(db)
            ch = yt.channels().list(part="snippet,statistics", mine=True).execute()["items"][0]
            ok("YouTube channel (API)", True, f"{ch['snippet']['title']}")
        except Exception as e:
            ok("YouTube channel (API)", False, str(e)[:200])
    from app.pipeline import library
    n = len(library._load("music"))
    ok("Licensed music tracks", n > 0, f"{n} usable tracks in assets/music/library.json")


if __name__ == "__main__":
    main()
