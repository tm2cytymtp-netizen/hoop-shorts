"""Automated editing with FFmpeg.

Timeline model (T = transition length):
  clip_i duration  d_i = LEAD + narration_i + TAIL + T
  clip_i start     S_i = Σ_{j<i} (d_j − T)          (cross-dissolves overlap by T)
  narration_i at   S_i + LEAD + (T/2 if i > 0)      (speech begins mid-dissolve)
Audio is built segment by segment with exactly the same arithmetic, so picture,
narration and subtitles cannot drift apart.
"""
from __future__ import annotations

from .charts import CHART_TYPES

import json
import re
from pathlib import Path

from sqlalchemy.orm import Session

from .. import media, settings_store
from ..config import env
from ..events import emit, video_dir
from ..models import Asset, Video
from . import library, procedural, subtitles
from .visuals import LEAD_PAD, scene_seconds

W, H = 1920, 1080


def set_canvas(w: int, h: int) -> None:
    global W, H
    W, H = w, h
    procedural.set_canvas(w, h)
GRADE = "eq=contrast=1.05:saturation=0.95:gamma=0.98,vignette=angle=PI/5,noise=alls=4:allf=t"
EASE = "(on/{N})*(on/{N})*(3-2*on/{N})"


def _zoompan(camera: str, frames: int) -> str:
    e = EASE.format(N=max(1, frames - 1))
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    punch = f"if(lt(on,6),1.18-0.18*on/6,1+0.05*(on-6)/{max(1, frames - 7)})"   # snap-in then slow creep
    z, x, y = {
        "punch": (punch, cx, cy),
        "push_in": (f"1+0.14*{e}", cx, cy),
        "pull_out": (f"1.14-0.14*{e}", cx, cy),
        "pan_left": ("1.12", f"(iw-iw/zoom)*(1-{e})", cy),
        "pan_right": ("1.12", f"(iw-iw/zoom)*{e}", cy),
        "tilt_up": ("1.12", cx, f"(ih-ih/zoom)*(1-{e})"),
        "tilt_down": ("1.12", cx, f"(ih-ih/zoom)*{e}"),
    }.get(camera, (f"1.05+0.05*{e}", f"(iw-iw/zoom)*(0.35+0.3*{e})", cy))
    return f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}"


def _pingpong(src: Path, out: Path, fps: int) -> Path:
    if not out.exists():
        media.run(["-i", str(src), "-filter_complex",
                   f"[0:v]fps={fps},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,"
                   f"setpts=1.2*PTS,split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1[v]", "-map", "[v]", "-an",
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", str(out)])
    return out


def render_scene(db: Session, video: Video, sc, T: float, fps: int, overlays: dict) -> Path:
    d = video_dir(video.id)
    out = d / "clips" / f"scene_{sc.idx:03d}.mp4"
    dur = scene_seconds(sc, T)
    frames = max(2, round(dur * fps))
    kind = sc.visual.get("type")
    inputs: list[str] = []
    if kind == "clip" and sc.motion_path and Path(sc.motion_path).exists():
        c = sc.visual.get("clip") or {}
        st, en = float(c.get("start") or 0), c.get("end")
        inputs = ["-ss", f"{st:.2f}"] + (["-to", f"{float(en):.2f}"] if en else []) + ["-i", sc.motion_path]
        # Horizontal footage → blurred fill + full frame in the middle (nothing important cropped away).
        base = (f"[0:v]fps={fps},split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"boxblur=30:2,eq=brightness=-0.2[bg];[b]scale={W}:-2[fg];[bg][fg]overlay=0:(H-h)/2,setsar=1,"
                f"tpad=stop_mode=clone:stop_duration={dur},trim=duration={dur}")
        if sc.visual.get("caption"):
            from . import cards
            from PIL import Image, ImageDraw
            cap = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            cards.meme_text(ImageDraw.Draw(cap), sc.visual["caption"], (50, 140, W - 50, 440), size=96)
            capp = d / "work" / f"clipcap_{sc.idx:03d}.png"
            cap.save(capp)
            inputs += ["-loop", "1", "-t", f"{dur}", "-i", str(capp)]
            base += "[cl];[cl][1:v]overlay=0:0"
    elif kind in ("map", "timeline", "title_card", "stat_card", "scoreboard", "ranking") + CHART_TYPES:
        inputs = ["-i", sc.motion_path]
        base = f"[0:v]fps={fps},scale={W}:{H},setsar=1,tpad=stop_mode=clone:stop_duration={dur},trim=duration={dur}"
    elif kind == "animated" and sc.motion_path and Path(sc.motion_path).exists():
        pp = _pingpong(Path(sc.motion_path), d / "motion" / f"pp_{sc.idx:03d}.mp4", fps)
        inputs = ["-stream_loop", "-1", "-i", str(pp)]
        base = f"[0:v]trim=duration={dur},setpts=PTS-STARTPTS,{GRADE}"
    else:
        if not sc.image_path or not Path(sc.image_path).exists():
            raise RuntimeError(f"Scene {sc.idx} has no image (missing visual).")
        inputs = ["-i", sc.image_path]
        if kind == "artwork":
            # Real artworks are shown whole over a blurred copy of themselves — never cropped or distorted.
            base = (f"[0:v]split[a][b];[a]scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,"
                    f"crop={W * 2}:{H * 2},boxblur=40:3,eq=brightness=-0.15[bg];"
                    f"[b]scale={int(W * 1.84)}:{int(H * 1.7)}:force_original_aspect_ratio=decrease[fg];"
                    f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{_zoompan('push_in', frames)},fps={fps},setsar=1,"
                    f"vignette=angle=PI/5")
        else:
            grade = f",{GRADE}" if kind == "illustration" else ""      # cards stay crisp
            cam = sc.visual.get("camera") or "punch"
            base = (f"[0:v]scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
                    f"{_zoompan(cam, frames)},fps={fps},setsar=1{grade}")
    chain = [base + "[v0]"]
    last = "v0"
    idx = len([a for a in inputs if a == "-i"])
    if sc.on_screen_text:
        png = procedural.render_text_overlay(sc.on_screen_text, d / "work" / f"lt_{sc.idx:03d}.png")
        inputs += ["-loop", "1", "-t", f"{dur}", "-i", str(png)]
        fade_out = max(1.0, dur - T - 0.9)
        chain.append(f"[{idx}:v]format=rgba,fade=in:st={T + 0.3}:d=0.5:alpha=1,"
                     f"fade=out:st={fade_out}:d=0.5:alpha=1[t{idx}]")
        chain.append(f"[{last}][t{idx}]overlay=0:0[v{idx}]")
        last, idx = f"v{idx}", idx + 1
    if sc.visual.get("credit") and kind != "photo":      # photo cards already carry their credit
        png = procedural.render_text_overlay(sc.visual["credit"], d / "work" / f"cr_{sc.idx:03d}.png", kind="credit")
        inputs += ["-loop", "1", "-t", f"{dur}", "-i", str(png)]
        chain.append(f"[{last}][{idx}:v]overlay=0:0[v{idx}]")
        last, idx = f"v{idx}", idx + 1
    if overlays.get("ai_label") and kind in ("illustration", "animated"):
        inputs += ["-loop", "1", "-t", f"{dur}", "-i", str(overlays["ai_label"])]
        chain.append(f"[{last}][{idx}:v]overlay=0:0[v{idx}]")
        last, idx = f"v{idx}", idx + 1
    chain.append(f"[{last}]format=yuv420p[out]")
    media.run([*inputs, "-filter_complex", ";".join(chain), "-map", "[out]", "-t", f"{dur:.3f}", "-r", str(fps),
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-an", str(out)])
    return out


def _xfade(clips: list[Path], durs: list[float], T: float, transition: str, out: Path, fps: int,
           final: bool = False) -> tuple[Path, float]:
    """Cross-dissolve a list of clips; chunked so filter graphs stay small."""
    if len(clips) == 1:
        return clips[0], durs[0]
    if T <= 0.001:   # hard cuts (Shorts style)
        args = []
        for c in clips:
            args += ["-i", str(c)]
        fc = "".join(f"[{i}:v]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=0[v]"
        preset, crf = (env.x264_preset, env.x264_crf) if final else ("veryfast", 16)
        media.run([*args, "-filter_complex", fc, "-map", "[v]", "-r", str(fps), "-c:v", "libx264", "-preset", preset,
                   "-crf", str(crf), "-pix_fmt", "yuv420p", str(out)])
        return out, sum(durs)
    if len(clips) > 16:
        parts, pd = [], []
        for k in range(0, len(clips), 16):
            p, dd = _xfade(clips[k:k + 16], durs[k:k + 16], T, transition, out.with_name(f"{out.stem}_c{k}.mp4"), fps)
            parts.append(p)
            pd.append(dd)
        return _xfade(parts, pd, T, transition, out, fps, final)
    args, fc, acc = [], [], durs[0]
    for c in clips:
        args += ["-i", str(c)]
    last = "0:v"
    for i in range(1, len(clips)):
        off = acc - T
        fc.append(f"[{last}][{i}:v]xfade=transition={transition}:duration={T}:offset={off:.3f}[x{i}]")
        last = f"x{i}"
        acc = off + durs[i]
    preset, crf = (env.x264_preset, env.x264_crf) if final else ("veryfast", 16)
    media.run([*args, "-filter_complex", ";".join(fc), "-map", f"[{last}]", "-r", str(fps), "-c:v", "libx264",
               "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p", str(out)])
    return out, acc


def build_audio(db: Session, video: Video, T: float, starts: list[float], total: float) -> tuple[Path, list, list]:
    d = video_dir(video.id) / "work"
    segs, all_cues, all_words = [], [], []
    scenes = video.scenes
    for i, sc in enumerate(scenes):
        seg_len = (starts[i + 1] - starts[i]) if i + 1 < len(scenes) else total - starts[i]
        lead = LEAD_PAD + (T / 2 if i else 0)
        seg = d / f"seg_{i:03d}.wav"
        media.run(["-i", sc.audio_path, "-af", f"adelay={int(lead * 1000)}:all=1,apad=whole_dur={seg_len:.4f},"
                   f"atrim=0:{seg_len:.4f}", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(seg)])
        segs.append(seg)
        off = starts[i] + lead
        words = [{**w, "start": w["start"] + off, "end": w["end"] + off} for w in sc.alignment.get("words", [])]
        all_cues += subtitles.cues(words)
        all_words += words
        sc.start_s = round(starts[i], 3)
    db.commit()
    lst = d / "segments.txt"
    lst.write_text("".join(f"file '{s.as_posix()}'\n" for s in segs))
    narration = d / "narration.wav"
    media.run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(narration)])

    # Music bed (ducked under narration) + ambience SFX.
    vs = settings_store.get(db, "video")
    music = library.pick_music(video.script.get("mood", "hype"), video.id)
    if not music:
        from .sfx import ensure_beat
        ensure_beat()
        music = library.pick_music(video.script.get("mood", "hype"), video.id)
    text_only = all((s.alignment or {}).get("silent") for s in scenes)
    music_db = vs.get("music_volume_db_textonly", -9) if text_only else vs["music_volume_db"]
    inputs, fc, mixes = ["-i", str(narration)], ["[0:a]asplit=2[n][sc]"], ["[n]"]
    if music:
        inputs += ["-stream_loop", "-1", "-i", music["path"]]
        fc.append(f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={music_db}dB,"
                  f"atrim=0:{total:.3f},afade=t=in:d={min(2, total * 0.1):.2f},"
                  f"afade=t=out:st={max(0, total - min(5, total * 0.15)):.3f}:d={min(5, total * 0.15):.2f}[m]")
        fc.append("[m][sc]sidechaincompress=threshold=0.02:ratio=6:attack=30:release=600[md]")
        mixes.append("[md]")
        db.add(Asset(video_id=video.id, kind="music", path=music["path"], source=library.describe(music),
                     license=music["license"], commercial_use=True, ai_generated=False,
                     meta={k: music.get(k) for k in ("title", "artist", "license_url", "attribution")}))
    else:
        fc[0] = "[0:a]anull[n]"
        emit(db, video, "No licensed music in assets/music/library.json — rendering without a music bed.", level="warn")
    for i, sc in enumerate(scenes):
        s = library.pick_sfx(sc.sfx)
        if not s:
            continue
        k = inputs.count("-i")          # index of the input about to be added
        seg_len = (starts[i + 1] - starts[i]) if i + 1 < len(scenes) else total - starts[i]
        if s.get("oneshot"):      # hit on the cut
            inputs += ["-i", s["path"]]
            fc.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,volume=-7dB,"
                      f"adelay={int(starts[i] * 1000)}:all=1[s{k}]")
        else:                     # ambience bed for the scene
            inputs += ["-stream_loop", "-1", "-i", s["path"]]
            fc.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{seg_len + T:.3f},"
                      f"afade=t=in:d=0.6,afade=t=out:st={max(0, seg_len + T - 0.8):.3f}:d=0.8,volume=-22dB,"
                      f"adelay={int(starts[i] * 1000)}:all=1[s{k}]")
        mixes.append(f"[s{k}]")
        db.add(Asset(video_id=video.id, kind="sfx", path=s["path"], source=library.describe(s), license=s["license"],
                     commercial_use=True, ai_generated=False))
    if len(mixes) == 1 and not music:
        fc = ["[0:a]anull[mix]"]
    else:
        fc.append(f"{''.join(mixes)}amix=inputs={len(mixes)}:normalize=0:duration=first[mix]")
    mix = d / "mix.wav"
    media.run([*inputs, "-filter_complex", ";".join(fc), "-map", "[mix]", "-t", f"{total:.3f}", "-ar", "48000",
               "-c:a", "pcm_s16le", str(mix)])
    db.commit()
    return mix, all_cues, all_words


def loudnorm_filter(src: Path, target: float) -> str:
    out = media.run_capture_stderr(["-i", str(src), "-af", f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json",
                                    "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", out, re.S)
    if not m:
        return f"loudnorm=I={target}:TP=-1.5:LRA=11"
    j = json.loads(m.group(0))
    return (f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:"
            f"measured_LRA={j['input_lra']}:measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true")


def chapters(video: Video, min_len: float = 12.0) -> list[dict]:
    out = []
    for sc in video.scenes:
        name = sc.visual.get("chapter") or sc.section.title()
        if not out or out[-1]["title"] != name:
            out.append({"title": name, "start": sc.start_s})
    out[0]["start"] = 0.0
    merged = [out[0]]
    for c in out[1:]:
        if c["start"] - merged[-1]["start"] < min_len:
            continue
        merged.append(c)
    if video.duration_s and video.duration_s - merged[-1]["start"] < min_len and len(merged) > 1:
        merged.pop()
    return merged


def run(db: Session, video: Video, stage_cb=None) -> None:
    vs = settings_store.get(db, "video")
    q = settings_store.get(db, "quality")
    T, fps = float(vs["transition_s"]), int(vs["fps"])
    is_short = video.kind == "short"
    set_canvas(1080, 1920) if is_short else set_canvas(1920, 1080)
    if is_short:
        T = min(T, 0.4)            # snappier cuts for Shorts (0 = hard cuts)
    d = video_dir(video.id)
    overlays = {}
    if vs.get("label_ai_visuals"):
        overlays["ai_label"] = procedural.render_text_overlay("Artistic reconstruction", d / "work" / "ai_label.png",
                                                              kind="ai_label")
    clips, durs = [], []
    if video.scenes and not (video.scenes[-1].alignment or {}).get("silent"):
        video.scenes[-1].visual = {**video.scenes[-1].visual, "end_hold": 0.9}
    for sc in video.scenes:
        p = render_scene(db, video, sc, T, fps, overlays)
        sc.clip_path = str(p)
        clips.append(p)
        durs.append(scene_seconds(sc, T))
    db.commit()
    emit(db, video, f"Rendered {len(clips)} scene clips")
    if stage_cb:
        stage_cb("rendering")
    starts, acc = [], 0.0
    for dd in durs:
        starts.append(acc)
        acc += dd - T
    total = acc + T
    picture, vdur = _xfade(clips, durs, T, vs.get("transition", "fade"), d / "work" / "picture.mp4", fps, final=True)
    total = min(total, vdur)
    mix, cues, words = build_audio(db, video, T, starts, total)
    srt = subtitles.write_srt(cues, d / "subtitles.srt")
    out = d / "final.mp4"
    vf = []
    if is_short:
        # Shorts: big word-by-word captions burned in (most Shorts are watched muted at first).
        ass = subtitles.write_ass_karaoke(words, d / "captions.ass")
        fonts_dir = (env.assets_dir / "fonts").as_posix()
        vf = ["-vf", f"ass={ass.as_posix()}:fontsdir={fonts_dir}", "-c:v", "libx264", "-preset", env.x264_preset,
              "-crf", str(env.x264_crf), "-pix_fmt", "yuv420p"]
    elif vs.get("burn_subtitles"):
        vf = ["-vf", f"subtitles={srt.as_posix()}:force_style='FontName=DejaVu Sans,FontSize=20,Outline=2,MarginV=40'",
              "-c:v", "libx264", "-preset", env.x264_preset, "-crf", str(env.x264_crf), "-pix_fmt", "yuv420p"]
    else:
        vf = ["-c:v", "copy"]
    media.run(["-i", str(picture), "-i", str(mix), "-map", "0:v", "-map", "1:a", *vf,
               "-af", loudnorm_filter(mix, q["target_lufs"]), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
               "-t", f"{total:.3f}", "-movflags", "+faststart", str(out)])
    video.output_path = str(out)
    video.subtitles_path = str(srt)
    video.duration_s = round(media.duration(out), 2)
    video.metadata_ = {**(video.metadata_ or {}), "chapters": [] if is_short else chapters(video),
                       "timeline_s": round(total, 3)}
    db.commit()
    emit(db, video, f"Final render: {video.duration_s:.1f}s → {out.name}")
