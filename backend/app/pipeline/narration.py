"""Narration: one TTS file per scene (request-stitched for continuous prosody) with word timings."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from .. import media
from ..events import emit, video_dir
from ..models import Asset, Video
from ..providers import tts


def _display_words(text: str, duration: float) -> list[dict]:
    """Caption words as WRITTEN ("2015-16"), timed by how long each takes to SAY ("twenty-fifteen sixteen")."""
    import re
    words = text.split()
    if not words:
        return []
    weights = [len(re.sub(r"[^A-Za-z0-9]", "", tts.speakable(w))) + 1.5 for w in words]
    pauses = [0.22 if re.search(r"[.!?]$", w) else 0.09 if re.search(r"[,;:—]$", w) else 0 for w in words[:-1]] + [0]
    speak = max(0.1, duration - sum(pauses) - 0.03)
    t, out = 0.0, []
    for w, wt, p in zip(words, weights, pauses):
        dd = speak * wt / sum(weights)
        out.append({"word": w, "start": round(t, 3), "end": round(t + dd, 3)})
        t += dd + p
    return out


def _groups(scenes) -> list[list]:
    """Consecutive narrated scenes that form one sentence are recorded as ONE take (natural intonation)."""
    groups, cur = [], []
    for sc in scenes:
        if not sc.narration.strip():
            if cur:
                groups.append(cur)
                cur = []
            groups.append([sc])
            continue
        cur.append(sc)
        if sc.narration.rstrip().endswith((".", "!", "?", "…")):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def run(db: Session, video: Video) -> None:
    from .. import settings_store
    d = video_dir(video.id) / "audio"
    scenes = video.scenes
    vs = settings_store.get(db, "voice")
    # global fixes first, then per-script ones override
    pron = {**vs.get("pronunciations", {}), **(video.script.get("pronunciations") or {})}
    preset = vs.get("format_voice", {}).get(video.script.get("format", ""), vs["preset"])
    for g in _groups(scenes):
        if all(sc.audio_path and Path(sc.audio_path).exists() and sc.alignment for sc in g):
            continue  # resume: never pay twice for the same audio
        sc0 = g[0]
        if not sc0.narration.strip():
            hold = float(sc0.visual.get("hold_seconds", 2.0))
            dest = d / f"scene_{sc0.idx:03d}.mp3"
            media.run(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", f"{hold:.2f}", "-c:a", "libmp3lame",
                       "-b:a", "64k", str(dest)])
            sc0.audio_path, sc0.audio_duration, sc0.alignment = str(dest), media.duration(dest), {"words": [], "silent": True}
            db.commit()
            continue
        text = " ".join(sc.narration.strip() for sc in g)
        take = d / f"take_{sc0.idx:03d}.mp3"
        res = tts.synthesize(db, video.id, tts.apply_pronunciations(text, pron, ipa=vs.get("provider") == "kokoro"), take, preset=preset)
        dur = media.duration(take)
        words = _display_words(text, dur)
        # Split the take at the word boundaries between scenes (the audio stays continuous).
        bounds, wi = [0.0], 0
        for sc in g[:-1]:
            wi += len(sc.narration.split())
            bounds.append(round((words[wi - 1]["end"] + words[wi]["start"]) / 2, 3))
        bounds.append(dur)
        wi = 0
        for j, sc in enumerate(g):
            a, b = bounds[j], bounds[j + 1]
            dest = d / f"scene_{sc.idx:03d}.mp3"
            if len(g) == 1:
                import shutil
                shutil.copy(take, dest)
            else:
                media.run(["-i", str(take), "-af", f"atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS", "-c:a", "libmp3lame",
                           "-b:a", "192k", str(dest)])
            n = len(sc.narration.split())
            sc.audio_path = str(dest)
            sc.audio_duration = media.duration(dest)
            sc.alignment = {"words": [{**w, "start": max(0.0, w["start"] - a), "end": max(0.0, w["end"] - a)}
                                      for w in words[wi:wi + n]],
                            "continues": j < len(g) - 1}
            wi += n
        free = str(res["voice_id"]).startswith("kokoro")
        db.add(Asset(video_id=video.id, kind="narration", path=str(take),
                     source=("Kokoro TTS " if free else "ElevenLabs voice ") + str(res["voice_id"]),
                     license="Kokoro-82M, Apache-2.0" if free else "ElevenLabs paid plan — commercial use permitted",
                     commercial_use=True, ai_generated=True))
        db.commit()
    total = sum(s.audio_duration for s in scenes)
    emit(db, video, f"Narration complete: {total:.1f}s across {len(scenes)} scenes")
