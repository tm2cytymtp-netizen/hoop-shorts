"""Automated quality control. A video is only eligible for publishing if every
blocking check passes; warnings are shown in the dashboard for your review."""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image
from sqlalchemy.orm import Session

from .. import media, settings_store
from ..models import Asset, Video
from ..providers import llm

VALUE_SCHEMA = {
    "type": "object",
    "properties": {
        "value_score": {"type": "number", "description": "0-10 educational value & originality"},
        "script_quality": {"type": "number", "description": "0-10 storytelling, pacing, clarity"},
        "repetitive_ai_phrasing": {"type": "array", "items": {"type": "string"}},
        "policy_concerns": {"type": "array", "items": {"type": "string"},
                            "description": "YouTube Community Guidelines / advertiser-friendliness concerns "
                                           "(graphic violence description, hate, misinformation)"},
        "notes": {"type": "string"}},
    "required": ["value_score", "script_quality", "repetitive_ai_phrasing", "policy_concerns", "notes"],
}


def _shingles(text: str, k: int = 5) -> set:
    w = re.findall(r"[a-z']+", text.lower())
    return {" ".join(w[i:i + k]) for i in range(max(0, len(w) - k + 1))}


def similarity(a: str, b: str) -> float:
    sa, sb = _shingles(a), _shingles(b)
    return len(sa & sb) / max(1, min(len(sa), len(sb)))


def _check(results: list, name: str, ok: bool, detail: str, blocking: bool = True) -> None:
    results.append({"check": name, "passed": bool(ok), "blocking": blocking, "detail": detail})


def technical(path: Path, expected: float | None, *, w: int = 1920, h: int = 1080, lufs: float = -14) -> list[dict]:
    r: list[dict] = []
    if not path.exists():
        _check(r, "file_exists", False, f"{path} missing")
        return r
    info = media.probe(path)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = float(info["format"]["duration"])
    _check(r, "resolution", v and v["width"] == w and v["height"] == h, f"{v and v['width']}x{v and v['height']}")
    _check(r, "video_codec", v and v["codec_name"] == "h264" and v.get("pix_fmt") == "yuv420p",
           f"{v and v['codec_name']} {v and v.get('pix_fmt')}")
    _check(r, "audio_present", a is not None and a["codec_name"] == "aac", f"{a and a['codec_name']}")
    if expected:
        _check(r, "duration_matches_timeline", abs(dur - expected) < 1.5, f"{dur:.2f}s vs expected {expected:.2f}s")
    log = media.run_capture_stderr(["-i", str(path), "-vf", "blackdetect=d=1.0:pix_th=0.08:pic_th=0.98",
                                    "-af", "silencedetect=n=-45dB:d=3", "-f", "null", "-"])
    blacks = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", log)
    _check(r, "no_black_frames", not blacks, f"{len(blacks)} black segments {blacks[:3]}")
    silences = re.findall(r"silence_start: ([\d.]+)", log)
    _check(r, "no_dead_air", len(silences) == 0, f"{len(silences)} silences > 3s {silences[:3]}")
    ebu = media.run_capture_stderr(["-i", str(path), "-map", "0:a", "-af", "ebur128=peak=true", "-f", "null", "-"])
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", ebu)
    peak = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", ebu)
    il = float(m[-1]) if m else -99
    _check(r, "loudness", abs(il - lufs) <= 2.0, f"integrated {il} LUFS (target {lufs})")
    if peak:
        _check(r, "true_peak", float(peak[-1]) <= -0.5, f"peak {peak[-1]} dBFS")
    return r


def run(db: Session, video: Video) -> dict:
    q = settings_store.get(db, "quality")
    short = video.kind == "short"
    w, h = (1080, 1920) if short else (1920, 1080)
    results = technical(Path(video.output_path), (video.metadata_ or {}).get("timeline_s"), w=w, h=h,
                        lufs=q["target_lufs"])
    # Scene/asset completeness & sync
    missing = [s.idx for s in video.scenes if not (s.clip_path and Path(s.clip_path).exists())]
    _check(results, "all_scenes_rendered", not missing, f"missing scenes: {missing}" if missing else "all present")
    no_audio = [s.idx for s in video.scenes if not s.audio_duration]
    _check(results, "all_narration_present", not no_audio, f"missing narration: {no_audio}" if no_audio else "ok")
    words_total = sum(len(s.narration.split()) for s in video.scenes)
    srt = Path(video.subtitles_path) if video.subtitles_path else None
    sub_words = len(re.findall(r"\S+", "\n".join(l for l in srt.read_text().splitlines()
                                                 if l and "-->" not in l and not l.isdigit()))) if srt and srt.exists() else 0
    _check(results, "subtitle_coverage", sub_words >= words_total * 0.97, f"{sub_words}/{words_total} words captioned")
    if video.scenes and video.scenes[-1].start_s:
        _check(results, "scene_sync", video.scenes[-1].start_s < video.duration_s, "last scene starts before end")
    if short:
        mx = settings_store.get(db, "shorts")["max_seconds"]
        _check(results, "short_length", 8 <= video.duration_s <= mx, f"{video.duration_s:.1f}s (max {mx}s)")
    else:
        lo, hi = settings_store.get(db, "video")["target_minutes"]
        _check(results, "length_in_range", lo * 60 * 0.85 <= video.duration_s <= hi * 60 * 1.15,
               f"{video.duration_s / 60:.1f} min (target {lo}-{hi})", blocking=False)
    # Facts
    fc = video.fact_check or {}
    _check(results, "fact_check", fc.get("passed", False),
           f"{fc.get('supported')}/{fc.get('claims')} claims supported, {fc.get('blocking')} blocking issues")
    bib = [s for s in (video.research or {}).get("bibliography", []) if s.get("cited")]
    has_claims = (video.fact_check or {}).get("claims", 0) > 0
    _check(results, "bibliography", (len(bib) >= 1 if short else len(bib) >= 5) or not has_claims, f"{len(bib)} cited sources "
           f"({sum(1 for s in bib if s.get('tier') == 1)} academic/archival)")
    # Licensing ledger
    assets = db.query(Asset).filter(Asset.video_id == video.id).all()
    bad = [a.path for a in assets if not (a.commercial_use and a.license)]
    _check(results, "asset_licensing", not bad, f"{len(assets)} assets tracked; unlicensed: {bad[:5]}")
    # Thumbnails
    th = video.thumbnails or []
    ok_th = [t for t in th if Path(t["path"]).exists() and Path(t["path"]).stat().st_size < 2_000_000 and
             Image.open(t["path"]).size == (1280, 720)]
    if not short:   # Shorts use a frame from the video; custom Shorts thumbnails aren't settable everywhere
        _check(results, "thumbnails", len(ok_th) >= 1, f"{len(ok_th)}/{len(th)} valid (1280x720, <2MB)")
    # Metadata limits (YouTube: title ≤100 chars, description ≤5000 bytes, tags ≤500 chars, no < >)
    md = video.metadata_ or {}
    title, desc, tags = md.get("title", ""), md.get("description", ""), md.get("tags", [])
    _check(results, "metadata_limits", 0 < len(title) <= 100 and len(desc.encode()) <= 5000 and
           sum(len(t) + (2 if " " in t else 0) + 1 for t in tags) <= 500 and not re.search(r"[<>]", title + desc),
           f"title {len(title)} chars, description {len(desc.encode())} bytes, {len(tags)} tags")
    _check(results, "synthetic_disclosure", md.get("contains_synthetic_media") is not None,
           f"containsSyntheticMedia={md.get('contains_synthetic_media')}")
    # Originality vs previous videos
    text = " ".join(s.narration for s in video.scenes)
    prev = db.query(Video).filter(Video.id != video.id, Video.kind == video.kind,
                                  Video.status.in_(["published", "scheduled", "awaiting_approval", "approved"])).all()
    sims = [(p.id, similarity(text, " ".join(s["narration"] for s in (p.script or {}).get("scenes", []))))
            for p in prev]
    worst = max(sims, key=lambda x: x[1], default=(None, 0))
    _check(results, "originality_vs_channel", worst[1] <= q["max_similarity_to_previous"],
           f"max overlap {worst[1]:.2f} with video {worst[0]}")
    # Editorial review (independent model pass)
    review = llm.structured(
        db, video_id=video.id, category="script", tool_name="submit_review", schema=VALUE_SCHEMA, est_usd=0.15,
        note="QC editorial review",
        system=("You are a demanding YouTube Shorts editor and policy reviewer for a basketball meme channel. "
                "Score honestly; a generic, unfunny AI script is a 4. value_score = entertainment + originality. "
                "Flag as policy_concerns: impersonating a real athlete or putting words in a real person's mouth, "
                "harassment or jokes about bodies/families/identity, fake news, fabricated stats, sexual or "
                "violent content, and anything that looks copied from another creator."),
        prompt=("FORMAT: YouTube Short (judge the hook in the first second, the punchline, the pacing).\n") +
               "SCRIPT (narration | visual):\n" + "\n".join(
                   f"[{s.section}] {s.narration or '(text-only)'} | {s.visual.get('type')}: "
                   f"{s.visual.get('top_text', '')} {s.visual.get('bottom_text', '')} {s.visual.get('caption', '')} "
                   f"{s.visual.get('text', '')} {s.visual.get('image_prompt', '')}" for s in video.scenes))
    _check(results, "educational_value", review["value_score"] >= q["min_value_score"],
           f"value {review['value_score']}/10, script {review['script_quality']}/10 — {review['notes'][:300]}")
    _check(results, "policy_review", not review["policy_concerns"], "; ".join(review["policy_concerns"]) or "none")
    _check(results, "ai_phrasing", len(review["repetitive_ai_phrasing"]) <= 3,
           ", ".join(review["repetitive_ai_phrasing"][:8]) or "none", blocking=False)
    passed = all(r["passed"] for r in results if r["blocking"])
    return {"passed": passed, "checks": results, "review": review}
