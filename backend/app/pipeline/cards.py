"""Shorts-native graphics for basketball content (1080x1920): meme cards, reaction captions,
licensed photo cards, punchline text, and animated stat / comparison / scoreboard / ranking cards.
Every stat card prints its source and date on screen."""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from ..media import FramePipe
from .procedural import ease, font, window

W, H = 1080, 1920
ORANGE, GREEN, RED, WHITE = (255, 138, 0), (60, 220, 120), (240, 70, 70), (255, 255, 255)
NAVY = (14, 20, 38)


def wrap(text: str, fnt_name: str, max_w: int, size: int, min_size: int = 44, max_lines: int = 4):
    """Largest font size at which text wraps into <= max_lines lines within max_w."""
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    while True:
        f = font(fnt_name, size)
        words, lines, cur = text.split(), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if d.textlength(t, font=f) <= max_w:
                cur = t
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        if (len(lines) <= max_lines and all(d.textlength(l, font=f) <= max_w for l in lines)) or size <= min_size:
            return f, lines, size
        size -= 6


def meme_text(d: ImageDraw.ImageDraw, text: str, box: tuple[int, int, int, int], size: int = 110,
              fill=WHITE, stroke=(0, 0, 0)):
    x0, y0, x1, y1 = box
    f, lines, sz = wrap(text.upper(), "Anton-Regular.ttf", x1 - x0, size, max_lines=3)
    lh = int(sz * 1.08)
    y = y0 + ((y1 - y0) - lh * len(lines)) // 2
    for l in lines:
        d.text(((x0 + x1) // 2, y), l, font=f, fill=fill, anchor="ma", stroke_width=max(4, sz // 14),
               stroke_fill=stroke)
        y += lh


def court_bg(color=NAVY) -> Image.Image:
    img = Image.new("RGB", (W, H), color)
    g = Image.new("L", (W, H))
    gd = ImageDraw.Draw(g)
    for y in range(H):
        gd.line([(0, y), (W, y)], fill=int(90 * (y / H)))
    img = Image.composite(Image.new("RGB", (W, H), tuple(int(c * 0.45) for c in color)), img, g)
    d = ImageDraw.Draw(img)
    line = tuple(min(255, c + 28) for c in color)
    d.ellipse([W / 2 - 230, H / 2 - 230, W / 2 + 230, H / 2 + 230], outline=line, width=6)
    d.line([(0, H / 2), (W, H / 2)], fill=line, width=6)
    d.rectangle([W / 2 - 250, H - 560, W / 2 + 250, H + 10], outline=line, width=6)
    d.arc([W / 2 - 480, H - 1050, W / 2 + 480, H + 100], 180, 360, fill=line, width=6)
    return img


def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    return ImageOps.fit(img.convert("RGB"), (w, h), Image.LANCZOS)


def meme_card(img_path: str, top: str, bottom: str, out: Path) -> Path:
    """Classic top/bottom-text meme, vertical: text bands above and below a square image."""
    canvas = Image.new("RGB", (W, H), (0, 0, 0))
    img = _cover(Image.open(img_path), W, W)
    canvas.paste(img, (0, (H - W) // 2))
    d = ImageDraw.Draw(canvas)
    if top:
        meme_text(d, top, (40, 120, W - 40, (H - W) // 2 - 20))
    if bottom:
        meme_text(d, bottom, (40, (H + W) // 2 + 20, W - 40, H - 120))
    canvas.save(out)
    return out


def reaction_card(img_path: str, caption: str, out: Path) -> Path:
    """White caption box on top ('POV: …', 'When …') above the reaction image. Square/landscape art is shown
    whole (full width) over a blurred fill instead of being cropped."""
    src = Image.open(img_path).convert("RGB")
    f, lines, sz = wrap(caption, "DejaVuSans-Bold.ttf", W - 140, 64, min_size=40)
    box_h = 90 + len(lines) * int(sz * 1.25)
    if src.height / src.width < 1.4:
        canvas = Image.eval(_cover(src, W, H).filter(ImageFilter.GaussianBlur(40)), lambda v: int(v * 0.5))
        fg = ImageOps.contain(src, (W, H - 300), Image.LANCZOS)
        top = max(150 + box_h + 30, (H - fg.height) // 2)
        canvas.paste(fg, ((W - fg.width) // 2, top))
    else:
        canvas = _cover(src, W, H)
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle([40, 150, W - 40, 150 + box_h], radius=28, fill=WHITE)
    y = 150 + 45
    for l in lines:
        d.text((80, y), l, font=f, fill=(15, 15, 15))
        y += int(sz * 1.25)
    canvas.save(out)
    return out


def photo_card(img_path: str, caption: str, credit: str, out: Path) -> Path:
    src = Image.open(img_path).convert("RGB")
    bg = _cover(src, W, H).filter(ImageFilter.GaussianBlur(35))
    bg = Image.eval(bg, lambda v: int(v * 0.55))
    fg = ImageOps.contain(src, (W - 60, int(H * 0.62)), Image.LANCZOS)
    bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2 - 40))
    d = ImageDraw.Draw(bg)
    if caption:
        meme_text(d, caption, (50, 130, W - 50, 430), size=96)
    d.text((40, H - 70), credit[:90], font=font("DejaVuSans.ttf", 24), fill=(235, 235, 235), stroke_width=2,
           stroke_fill=(0, 0, 0))
    bg.save(out)
    return out


def big_text_card(text: str, out: Path, color=(255, 196, 0), bg_color=(18, 18, 18)) -> Path:
    img = court_bg(bg_color)
    d = ImageDraw.Draw(img)
    meme_text(d, text, (60, 300, W - 60, H - 300), size=150, fill=color)
    img.save(out)
    return out


def _fmt(v: float, like: str) -> str:
    if "." in like:
        return f"{v:.{len(like.split('.')[1])}f}"
    return f"{int(round(v)):,}"


def _num(s) -> float | None:
    try:
        return float(str(s).replace(",", "").replace("%", ""))
    except ValueError:
        return None


def render_stat_card(spec: dict, duration: float, out: Path, fps: int = 30) -> Path:
    """Player-vs-player comparison with rows revealing and numbers counting up. Higher value wins
    unless the row sets lower_is_better (e.g. turnovers)."""
    bg = court_bg()
    rows = spec.get("rows", [])[:4]            # 4 rows max: readable, and clear of spoken captions
    fT, fName, fLab, fVal = font("Anton-Regular.ttf", 92), font("Anton-Regular.ttf", 62), \
        font("DejaVuSans-Bold.ttf", 38), font("Anton-Regular.ttf", 84)
    pipe = FramePipe(out, W, H, fps)
    n = max(1, int(duration * fps))
    try:
        for fi in range(n):
            t = fi / max(1, n - 1)
            im = bg.copy()
            d = ImageDraw.Draw(im)
            k = window(t, 0, 0.1)
            meme_text(d, spec.get("title", ""), (50, 140, W - 50, 360), size=92, fill=(255, 196, 0))
            d.text((W * 0.27, 470 - 30 * (1 - k)), spec.get("left_name", "").upper(), font=fName, anchor="mm",
                   fill=WHITE + (int(255 * k),), stroke_width=4, stroke_fill=(0, 0, 0))
            d.text((W * 0.73, 470 - 30 * (1 - k)), spec.get("right_name", "").upper(), font=fName, anchor="mm",
                   fill=WHITE, stroke_width=4, stroke_fill=(0, 0, 0))
            d.text((W / 2, 470), "VS", font=fLab, anchor="mm", fill=ORANGE)
            for i, r in enumerate(rows):
                a, b = 0.08 + 0.7 * i / max(1, len(rows)), 0.18 + 0.7 * i / max(1, len(rows))
                rk = window(t, a, b)
                if rk <= 0:
                    continue
                y = 640 + i * 175
                d.rounded_rectangle([40, y - 70, W - 40, y + 70], radius=24, fill=(28, 36, 62),
                                    outline=(70, 80, 110), width=3)
                d.text((W / 2, y), r["label"].upper(), font=fLab, anchor="mm", fill=(200, 205, 220))
                lv, rv = _num(r.get("left")), _num(r.get("right"))
                lower = r.get("lower_is_better")
                for side, val, raw, x in (("l", lv, r.get("left", ""), W * 0.2), ("r", rv, r.get("right", ""), W * 0.8)):
                    shown = _fmt(val * rk, str(raw)) + ("%" if "%" in str(raw) else "") if val is not None else str(raw)
                    win = None
                    if lv is not None and rv is not None and lv != rv and rk >= 1:
                        win = (lv > rv) != bool(lower) if side == "l" else (rv > lv) != bool(lower)
                    col = GREEN if win else RED if win is False else WHITE
                    d.text((x, y), shown, font=fVal, anchor="mm", fill=col, stroke_width=3, stroke_fill=(0, 0, 0))
            d.text((40, H - 90), ("Source: " + spec.get("source", ""))[:80], font=font("DejaVuSans.ttf", 26),
                   fill=(190, 195, 210))
            pipe.write(im)
    finally:
        pipe.close()
    return out


def render_scoreboard(spec: dict, duration: float, out: Path, fps: int = 30) -> Path:
    bg = court_bg((30, 16, 8))
    fTeam, fScore, fSmall = font("Anton-Regular.ttf", 72), font("Anton-Regular.ttf", 210), font("DejaVuSans-Bold.ttf", 40)
    pipe = FramePipe(out, W, H, fps)
    n = max(1, int(duration * fps))
    hs, as_ = float(spec.get("home_score", 0)), float(spec.get("away_score", 0))
    try:
        for fi in range(n):
            t = fi / max(1, n - 1)
            k = ease(min(1, t / 0.55))
            im = bg.copy()
            d = ImageDraw.Draw(im)
            if spec.get("headline"):
                meme_text(d, spec["headline"], (50, 150, W - 50, 420), size=96, fill=(255, 196, 0))
            for j, (team, sc) in enumerate(((spec.get("away", ""), as_), (spec.get("home", ""), hs))):
                y = 560 + j * 420          # keep clear of the spoken-caption zone (~y 1300–1450)
                won = (sc > (hs if j == 0 else as_)) and k >= 1
                d.text((W / 2, y), team.upper(), font=fTeam, anchor="mm", fill=WHITE, stroke_width=4, stroke_fill=(0, 0, 0))
                d.text((W / 2, y + 190), str(int(sc * k)), font=fScore, anchor="mm", fill=GREEN if won else WHITE,
                       stroke_width=6, stroke_fill=(0, 0, 0))
            d.text((W / 2, 900), "FINAL" if k >= 1 else "", font=fSmall, anchor="mm", fill=ORANGE)
            d.text((40, H - 90), f"{spec.get('date', '')} · Source: {spec.get('source', '')}"[:80],
                   font=font("DejaVuSans.ttf", 26), fill=(200, 200, 200))
            pipe.write(im)
    finally:
        pipe.close()
    return out


def render_ranking(spec: dict, img_path: str | None, duration: float, out: Path, fps: int = 30) -> Path:
    base = _cover(Image.open(img_path), W, H) if img_path else court_bg()
    base = Image.eval(base, lambda v: int(v * 0.7))
    fRank = font("Anton-Regular.ttf", 380)
    pipe = FramePipe(out, W, H, fps)
    n = max(1, int(duration * fps))
    try:
        for fi in range(n):
            t = fi / max(1, n - 1)
            pk = window(t, 0, 0.12)
            scale = 1.6 - 0.6 * pk
            im = base.copy()
            d = ImageDraw.Draw(im)
            rank = f"#{spec.get('rank', '')}"
            layer = Image.new("RGBA", (W, 600), (0, 0, 0, 0))
            ImageDraw.Draw(layer).text((W / 2, 300), rank, font=fRank, anchor="mm", fill=(255, 196, 0, int(255 * pk)),
                                       stroke_width=12, stroke_fill=(0, 0, 0, int(255 * pk)))
            layer = layer.resize((int(W * scale), int(600 * scale)))
            im.paste(layer, ((W - layer.width) // 2, 420 - (layer.height - 600) // 2), layer)
            if window(t, 0.12, 0.25) > 0:
                meme_text(d, spec.get("item", ""), (50, 1150, W - 50, 1500), size=100)
            pipe.write(im)
    finally:
        pipe.close()
    return out
