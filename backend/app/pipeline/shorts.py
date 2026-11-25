"""Turn a finished long-form video into 2–4 vertical Shorts with a spoken hook and animated captions."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from .. import media, settings_store
from ..events import emit, video_dir
from ..models import Scene, Video
from ..providers import llm, tts
from . import subtitles
from .visuals import LEAD_PAD

SCHEMA = {
    "type": "object",
    "properties": {"shorts": {"type": "array", "minItems": 1, "maxItems": 4, "items": {"type": "object", "properties": {
        "first_scene": {"type": "integer"}, "last_scene": {"type": "integer"},
        "hook": {"type": "string", "description": "<= 12 spoken words that make the clip self-contained and "
                 "gripping; must be accurate to the clip"},
        "title": {"type": "string", "description": "<= 60 chars, no #Shorts (added automatically)"},
        "description": {"type": "string"}},
        "required": ["first_scene", "last_scene", "hook", "title", "description"]}}},
    "required": ["shorts"],
}
W, H = 1080, 1920


def _scene_words(sc: Scene, i: int, T: float) -> list[dict]:
    off = sc.start_s + LEAD_PAD + (T / 2 if i else 0)
    return [{**w, "start": w["start"] + off, "end": w["end"] + off} for w in sc.alignment.get("words", [])]


def plan(db: Session, video: Video, n: int) -> list[dict]:
    lines = "\n".join(f"{s.idx} [{s.section}] ({s.audio_duration:.1f}s) {s.narration}" for s in video.scenes)
    res = llm.structured(
        db, video_id=video.id, category="script", tool_name="submit_shorts", schema=SCHEMA, fast=True, est_usd=0.05,
        note="shorts plan",
        system=("Pick the most gripping, self-contained moments of a history documentary for YouTube Shorts. "
                "Each clip: contiguous scenes totalling 25-50 seconds of narration, understandable without the "
                "full video, ending on a strong line. No overlap between clips."),
        prompt=f"Pick {n} clips from these scenes (index, section, duration, narration):\n{lines}")
    out = []
    for s in res["shorts"][:n]:
        a, b = max(0, s["first_scene"]), min(len(video.scenes) - 1, s["last_scene"])
        if b >= a:
            out.append({**s, "first_scene": a, "last_scene": b})
    return out


def render(db: Session, video: Video, spec: dict, k: int) -> Video:
    vs = settings_store.get(db, "video")
    T = float(vs["transition_s"])
    d = video_dir(video.id) / "shorts"
    scenes = video.scenes
    a, b = spec["first_scene"], spec["last_scene"]
    t0 = scenes[a].start_s + (T / 2 if a else 0)
    t1 = scenes[b + 1].start_s + T / 2 if b + 1 < len(scenes) else video.duration_s
    t1 = min(t1, t0 + 55)
    hook = tts.synthesize(db, video.id, spec["hook"], d / f"hook_{k}.mp3")
    hook_dur = media.duration(hook["path"]) + 0.25
    words = [{**w, "start": w["start"], "end": w["end"]} for w in hook["words"]]
    for i in range(a, b + 1):
        for w in _scene_words(scenes[i], i, T):
            if t0 <= w["start"] < t1:
                words.append({**w, "start": w["start"] - t0 + hook_dur, "end": min(w["end"], t1) - t0 + hook_dur})
    ass = subtitles.write_ass_karaoke(words, d / f"short_{k}.ass")
    frame = d / f"hookframe_{k}.png"
    # Hook backdrop: the middle of the first illustrated scene in the clip (never a dark title card).
    pick = next((scenes[i] for i in range(a, b + 1) if scenes[i].visual.get("type") in ("illustration", "animated")),
                scenes[a])
    t_frame = pick.start_s + (pick.audio_duration / 2 + T)
    media.run(["-ss", f"{t_frame:.3f}", "-i", video.output_path, "-frames:v", "1", str(frame)])
    out = d / f"short_{k}.mp4"
    total = hook_dur + (t1 - t0)
    fonts_dir = (Path(__file__).resolve().parents[3] / "assets" / "fonts").as_posix()
    layout = (f"split[bg][fg];[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:2,"
              f"eq=brightness=-0.22[bgb];[fg]crop=ih*4/5:ih,scale={W}:1350[fgs];[bgb][fgs]overlay=0:150")
    fc = (f"[0:v]scale=1920:1080,setsar=1,zoompan=z='1+0.06*on/{int(hook_dur * 30)}':d={int(hook_dur * 30)}:"
          f"s=1920x1080:fps=30,trim=duration={hook_dur:.3f}[hv];"
          f"[1:v]trim={t0:.3f}:{t1:.3f},setpts=PTS-STARTPTS,fps=30[sv];"
          f"[hv][sv]concat=n=2:v=1:a=0,{layout},ass={ass.as_posix()}:fontsdir={fonts_dir}[v];"
          f"[2:a]aresample=48000,apad=whole_dur={hook_dur:.3f},aformat=channel_layouts=stereo[ha];"
          f"[1:a]atrim={t0:.3f}:{t1:.3f},asetpts=PTS-STARTPTS,afade=t=out:st={max(0, t1 - t0 - 0.8):.3f}:d=0.8[sa];"
          f"[ha][sa]concat=n=2:v=0:a=1,loudnorm=I=-14:TP=-1.5[a]")
    media.run(["-i", str(frame), "-i", video.output_path, "-i", hook["path"], "-filter_complex", fc,
               "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)])
    md_parent = video.metadata_ or {}
    short = Video(kind="short", parent_id=video.id, topic_id=video.topic_id, status="awaiting_approval",
                  working_title=spec["title"], output_path=str(out), duration_s=round(media.duration(out), 2),
                  script={"hook": spec["hook"], "scenes": [{"narration": s.narration} for s in scenes[a:b + 1]]},
                  metadata_={"title": (spec["title"][:90] + " #Shorts")[:100],
                             "description": (spec["description"] + "\n\nFull documentary: "
                                             + (video.youtube_url or "(link added after publishing)") +
                                             "\n\nVisuals are AI-assisted artistic reconstructions.\n" +
                                             " ".join(md_parent.get("hashtags", [])[:2]) + " #Shorts")[:4900],
                             "tags": md_parent.get("tags", [])[:10], "category_id": "27",
                             "contains_synthetic_media": True, "made_for_kids": False},
                  thumbnails=[], qc_report={})
    db.add(short)
    db.commit()
    return short


def run(db: Session, video: Video) -> list[Video]:
    n = int(settings_store.get(db, "schedule")["shorts_per_video"])
    if n <= 0:
        return []
    made = []
    for k, spec in enumerate(plan(db, video, max(2, min(4, n)))):
        s = render(db, video, spec, k)
        from .qc import technical
        checks = technical(Path(s.output_path), None, w=W, h=H)
        s.qc_report = {"passed": all(c["passed"] for c in checks if c["blocking"] and c["check"] != "no_dead_air"),
                       "checks": checks}
        s.status = "awaiting_approval" if s.qc_report["passed"] else "needs_review"
        db.commit()
        made.append(s)
    emit(db, video, f"Created {len(made)} Shorts")
    return made
