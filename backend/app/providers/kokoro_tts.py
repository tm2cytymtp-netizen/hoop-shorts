"""Free local narration with Kokoro (Apache-2.0 open-weight TTS), via kokoro-onnx on CPU.
Model files (~350 MB) download once from GitHub into data/models.

Kokoro doesn't return word timestamps, so caption timing is estimated from word length and
punctuation pauses within each scene (scenes are 1–2 sentences, so drift stays small)."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import httpx

from .. import media
from ..config import env

BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
FILES = ["kokoro-v1.0.onnx", "voices-v1.0.bin"]
SENTENCE_PAUSE, CLAUSE_PAUSE = 0.18, 0.06     # short, human-like breaths (Kokoro defaults feel robotic)


def _model_dir() -> Path:
    d = env.data_dir / "models" / "kokoro"
    d.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        p = d / f
        if not p.exists() or p.stat().st_size < 1_000_000:
            tmp = p.with_suffix(".part")
            with httpx.stream("GET", f"{BASE}/{f}", follow_redirects=True, timeout=600) as r:
                r.raise_for_status()
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_bytes():
                        fh.write(chunk)
            tmp.rename(p)
    return d


@lru_cache(maxsize=1)
def _engine():
    from kokoro_onnx import Kokoro
    d = _model_dir()
    return Kokoro(str(d / FILES[0]), str(d / FILES[1]))


def estimate_words(text: str, duration: float, lead: float = 0.05) -> list[dict]:
    words = text.split()
    if not words:
        return []
    pauses = sum(SENTENCE_PAUSE if re.search(r"[.!?]$", w) else CLAUSE_PAUSE if re.search(r"[,;:—]$", w) else 0
                 for w in words[:-1])
    weights = [len(re.sub(r"[^\w]", "", w)) + 1.5 for w in words]
    speak = max(0.1, duration - lead - pauses - 0.05)
    t, out = lead, []
    for w, wt in zip(words, weights):
        d = speak * wt / sum(weights)
        out.append({"word": w, "start": round(t, 3), "end": round(t + d, 3)})
        t += d + (SENTENCE_PAUSE if re.search(r"[.!?]$", w) else CLAUSE_PAUSE if re.search(r"[,;:—]$", w) else 0)
    return out


def _with_ipa(text: str, lang: str) -> str:
    """Phonemize text, splicing in exact IPA for ⟦…⟧ segments (see tts.apply_pronunciations)."""
    from kokoro_onnx.tokenizer import Tokenizer
    tok = Tokenizer()
    out = []
    for i, part in enumerate(re.split(r"⟦(.*?)⟧", text)):
        if i % 2:
            out.append(part)
        elif part.strip():
            ph = tok.phonemize(part, lang)
            out.append((" " if part[:1].isspace() else "") + ph.strip() + (" " if part[-1:].isspace() else ""))
        else:
            out.append(part)
    return "".join(out).strip()


def synthesize(text: str, dest: Path, voice: str, speed: float = 1.0) -> dict:
    import soundfile as sf
    lang = "en-gb" if voice.startswith("b") else "en-us"
    ipa = "⟦" in text
    samples, sr = _engine().create(_with_ipa(text, lang) if ipa else text, voice=voice, speed=speed, lang=lang,
                                   is_phonemes=ipa, sentence_pause=SENTENCE_PAUSE, clause_pause=CLAUSE_PAUSE)
    text = re.sub(r"⟦.*?⟧", "name", text)   # timing estimate only
    wav = dest.with_suffix(".wav")
    sf.write(str(wav), samples, sr)
    # Trim leading/trailing silence so consecutive lines flow like one take (gaps are added deliberately later).
    # 1) trim leading/trailing silence; 2) shorten Kokoro's long internal pauses (commas/sentences) to a
    #    natural breath so it sounds like someone talking, not a TTS reading punctuation.
    trim = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.02,"
            "silenceremove=stop_periods=-1:stop_duration=0.2:stop_threshold=-42dB:stop_silence=0.16,"
            "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.04,areverse")
    media.run(["-i", str(wav), "-af", trim, "-c:a", "libmp3lame", "-b:a", "192k", str(dest)])
    wav.unlink(missing_ok=True)
    return {"path": str(dest), "words": estimate_words(text, media.duration(dest), lead=0.0), "voice_id": f"kokoro:{voice}"}
