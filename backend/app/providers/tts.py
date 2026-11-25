"""ElevenLabs text-to-speech with character-level timestamps (used for exact subtitle
and scene sync). Docs: https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps
"""
from __future__ import annotations

import base64
import re
import time
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from .. import costs, settings_store
from ..config import env

API = "https://api.elevenlabs.io/v1"


class TTSError(Exception):
    pass


_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen " \
        "seventeen eighteen nineteen".split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def _two(n: int) -> str:
    if n < 20:
        return _ONES[n]
    return _TENS[n // 10] + ("" if n % 10 == 0 else "-" + _ONES[n % 10])


def _year(y: int) -> str:
    hi, lo = divmod(y, 100)
    if lo == 0:
        return f"{_two(hi)} hundred" if y < 2000 else "two thousand"
    if y >= 2000 and lo < 10:
        return f"two thousand {_ONES[lo]}"
    return f"{_two(hi)} {'oh-' + _ONES[lo] if lo < 10 else _two(lo)}"


def speakable(text: str) -> str:
    """'2015-16' → 'twenty-fifteen sixteen'; 'in 1996' → 'in nineteen ninety-six' (spoken text only)."""
    import re as _re
    text = _re.sub(r"\b(19|20)(\d\d)[–-](\d\d)\b",
                   lambda m: f"{_year(int(m.group(1) + m.group(2)))} {_two(int(m.group(3))) if int(m.group(3)) >= 10 else 'oh-' + _ONES[int(m.group(3))]}",
                   text)
    # Plain years only after a year-ish word ("in 1996", "since 2003") so stats like "2015 points" stay numbers.
    text = _re.sub(r"\b(in|since|of|from|by|until|before|after|back in) (19[5-9]\d|20[0-4]\d)\b(?!\d|[.,]\d)",
                   lambda m: f"{m.group(1)} {_year(int(m.group(2)))}", text)
    return text


def apply_pronunciations(text: str, pron: dict[str, str], ipa: bool = True) -> str:
    """Replace hard names with phonetic respellings in the *spoken* text only.
    A value wrapped in slashes is exact IPA for Kokoro (e.g. "Jerome": "/dʒəɹˈoʊm/") — use it when no
    respelling gets the stress right. It is passed through as ⟦ipa⟧ and spliced in by the Kokoro provider."""
    text = speakable(text)
    for word, say in sorted((pron or {}).items(), key=lambda kv: -len(kv[0])):
        if len(say) > 2 and say.startswith("/") and say.endswith("/"):
            if not ipa:          # other voice providers can't take IPA: leave the word as written
                continue
            say = f"⟦{say[1:-1]}⟧"
        text = re.sub(rf"\b{re.escape(word)}\b", lambda m, s=say: s, text)
    return text


def words_from_alignment(alignment: dict) -> list[dict]:
    """Collapse ElevenLabs character alignment into [{word, start, end}]."""
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    words, cur, ws, we = [], "", None, None
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if cur:
                words.append({"word": cur, "start": ws, "end": we})
            cur, ws = "", None
            continue
        if ws is None:
            ws = s
        cur += ch
        we = e
    if cur:
        words.append({"word": cur, "start": ws, "end": we})
    return words


def synthesize(db: Session, video_id: int | None, text: str, dest: Path, *, preset: str | None = None,
               previous_text: str = "", next_text: str = "") -> dict:
    vs = settings_store.get(db, "voice")
    if vs.get("provider", "kokoro") == "kokoro":
        from . import kokoro_tts
        voice = vs["kokoro_presets"].get(preset or vs["preset"], "bm_george")
        res = kokoro_tts.synthesize(text, dest, voice, speed=vs.get("speed", 1.0))
        costs.record(db, video_id, "voice", f"kokoro:{voice} (local, free)", len(text), "chars", 0.0)
        return {**res, "alignment": {}}
    if not env.elevenlabs_api_key:
        raise TTSError("ELEVENLABS_API_KEY is not configured (see README → Connect your accounts).")
    vs = settings_store.get(db, "voice")
    p = vs["presets"][preset or vs["preset"]]
    if not p.get("voice_id"):
        raise TTSError(f"No ElevenLabs voice_id set for voice preset '{preset or vs['preset']}' (Settings → Voice).")
    price = len(text) / 1000 * settings_store.get(db, "pricing")["tts_per_1k_chars"]
    costs.guard(db, video_id, "voice", price)
    body = {
        "text": text,
        "model_id": vs["model_id"],
        "voice_settings": {"stability": p["stability"], "similarity_boost": p["similarity_boost"],
                           "style": p.get("style", 0), "use_speaker_boost": True, "speed": vs.get("speed", 1.0)},
    }
    # Request stitching keeps prosody continuous across scene boundaries.
    if previous_text:
        body["previous_text"] = previous_text[-500:]
    if next_text:
        body["next_text"] = next_text[:500]
    url = f"{API}/text-to-speech/{p['voice_id']}/with-timestamps?output_format=mp3_44100_192"
    for attempt in range(5):
        r = httpx.post(url, json=body, headers={"xi-api-key": env.elevenlabs_api_key}, timeout=300)
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 ** attempt * 2)
            continue
        break
    if r.status_code >= 400:
        raise TTSError(f"ElevenLabs error {r.status_code}: {r.text[:400]}")
    data = r.json()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(base64.b64decode(data["audio_base64"]))
    costs.record(db, video_id, "voice", f"elevenlabs:{vs['model_id']}", len(text), "chars", price)
    alignment = data.get("alignment") or {}
    return {"path": str(dest), "alignment": alignment, "words": words_from_alignment(alignment),
            "voice_id": p["voice_id"]}
