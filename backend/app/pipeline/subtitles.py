"""SRT (for YouTube caption tracks / burn-in) and ASS karaoke captions (Shorts) from TTS word timings."""
from __future__ import annotations

from pathlib import Path


def _ts(t: float, sep: str = ",") -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}{sep}{int(round((s - int(s)) * 1000)):03d}"


def cues(words: list[dict], max_chars: int = 42, max_dur: float = 6.0) -> list[dict]:
    """Group timed words into readable cues, breaking at punctuation where possible."""
    out, cur = [], []
    for w in words:
        cur.append(w)
        text = " ".join(x["word"] for x in cur)
        end_punct = w["word"][-1:] in ".?!;:,"
        if len(text) >= max_chars or (cur[-1]["end"] - cur[0]["start"]) >= max_dur or \
                (end_punct and len(text) > max_chars * 0.55) or w["word"][-1:] in ".?!":
            out.append({"start": cur[0]["start"], "end": cur[-1]["end"], "text": text})
            cur = []
    if cur:
        out.append({"start": cur[0]["start"], "end": cur[-1]["end"], "text": " ".join(x["word"] for x in cur)})
    for a, b in zip(out, out[1:]):           # never overlap
        a["end"] = min(a["end"] + 0.25, b["start"] - 0.02)
    return out


def write_srt(all_cues: list[dict], path: Path) -> Path:
    lines = []
    for i, c in enumerate(all_cues, 1):
        lines += [str(i), f"{_ts(c['start'])} --> {_ts(c['end'])}", c["text"], ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_ass_karaoke(words: list[dict], path: Path, w: int = 1080, h: int = 1920, font: str = "Anton") -> Path:
    """Big centred word-by-word captions for vertical Shorts (current word highlighted)."""
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},96,&H00FFFFFF,&H0000D7FF,&H00000000,&H64000000,0,0,0,0,100,100,1,0,1,7,3,2,60,60,560,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    group: list[dict] = []
    groups = []
    for wd in words:
        group.append(wd)
        if len(group) == 3 or wd["word"][-1:] in ".?!,;":
            groups.append(group)
            group = []
    if group:
        groups.append(group)
    for gi, g in enumerate(groups):
        nxt = groups[gi + 1][0]["start"] if gi + 1 < len(groups) else None
        for i, cur in enumerate(g):
            start = cur["start"]
            end = g[i + 1]["start"] if i + 1 < len(g) else cur["end"] + 0.15
            if nxt is not None:
                end = min(end, nxt - 0.01)      # never show two caption groups at once
            if end <= start:
                end = start + 0.05
            txt = " ".join(("{\\c&H00D7FF&\\fscx110\\fscy110}" + x["word"].upper() + "{\\r}") if x is cur
                           else x["word"].upper() for x in g)
            ev.append(f"Dialogue: 0,{_ts(start, '.')[:-1]},{_ts(end, '.')[:-1]},Cap,,0,0,0,,{txt}")
    path.write_text(head + "\n".join(ev) + "\n", encoding="utf-8")
    return path
