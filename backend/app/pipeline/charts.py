"""Animated stat charts for vertical Shorts (hoopgraphs-style). All values come from parsed data
tables — the script only says WHICH player/stat/seasons to show, never the numbers themselves.
Layout keeps y≈1300–1480 clear for the spoken captions."""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

from ..media import FramePipe
from .cards import meme_text
from .procedural import ease, font, window

W, H = 1080, 1920
# every data-chart visual type (rendered straight to video by visuals.render_procedural)
CHART_TYPES = ("season_bars", "line_compare", "big_number", "leaderboard", "comeback_card", "slope",
               "head_to_head", "tally", "hype_text", "all_time_rank")
BG = (11, 14, 24)
GRID = (36, 42, 60)
BAR = (70, 110, 220)
GOLD = (255, 196, 0)
TEXT = (235, 238, 245)
MUTED = (140, 148, 170)
PALETTE = [(255, 196, 0), (64, 170, 255), (255, 92, 92), (90, 220, 140)]


def _bg(seed: int = 7):
    """Static dark background, or an animated DynBG when dynamic backgrounds are on (settings video.dynamic_bg)."""
    from . import dynbg
    dyn = dynbg.make(1, 30, seed)
    if dyn is not None:
        return dyn
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    for y in range(H):
        if y % 4 == 0:
            d.line([(0, y), (W, y)], fill=(13, 17, 29))
    return img


def _bgf(base, fi: int) -> Image.Image:
    return base.frame(fi) if hasattr(base, "frame") else base.copy()


def _header(d: ImageDraw.ImageDraw, title: str, subtitle: str, k: float = 1.0) -> None:
    meme_text(d, title, (50, 80, W - 50, 250), size=80, fill=GOLD)
    if subtitle:
        d.text((W / 2, 290), subtitle, font=font("DejaVuSans-Bold.ttf", 32), anchor="mm", fill=MUTED)


def _footer(d: ImageDraw.ImageDraw, source: str) -> None:
    if source:
        d.text((40, H - 80), source[:95], font=font("DejaVuSans.ttf", 25), fill=MUTED)


def render_season_bars(spec: dict, rows: list[dict], duration: float, out: Path, fps: int = 30) -> Path:
    """Horizontal bars, one per season. spec: title, subtitle, stat, unit, reveal_from, reveal_to (indexes),
    highlight (list of season labels), show_average (value or None), source, legend."""
    stat = spec["stat"]
    vals = [r[stat] for r in rows]
    vmax = max(v for v in vals if v is not None) or 1
    n = len(rows)
    top, bottom = 420, 1240
    rh = (bottom - top) / max(n, 1)
    bar_h = min(46, rh * 0.72)
    label_w, x0, x1 = 170, 200, W - 150
    f_lab = font("DejaVuSans-Bold.ttf", int(min(30, rh * 0.55)))
    f_val = font("Anton-Regular.ttf", int(min(40, rh * 0.8)))
    r_from, r_to = spec.get("reveal_from", 0), spec.get("reveal_to", n - 1)
    hi = set(spec.get("highlight", []))
    nframes = max(1, int(duration * fps))
    base = _bg()
    pipe = FramePipe(out, W, H, fps)
    try:
        for fi in range(nframes):
            t = fi / max(1, nframes - 1)
            im = _bgf(base, fi)
            d = ImageDraw.Draw(im)
            _header(d, spec.get("title", ""), spec.get("subtitle", ""))
            for g in range(0, int(vmax) + 1, 10 if vmax > 25 else 5):
                gx = x0 + (x1 - x0) * g / vmax
                d.line([(gx, top - 20), (gx, bottom)], fill=GRID, width=2)
                d.text((gx, bottom + 18), str(g), font=font("DejaVuSans.ttf", 24), anchor="mm", fill=MUTED)
            span = max(1, r_to - r_from + 1)
            for i, r in enumerate(rows):
                if i > r_to:
                    break
                if i < r_from:
                    k = 1.0
                else:
                    a = 0.05 + 0.75 * (i - r_from) / span
                    k = ease((t - a) / (0.75 / span + 0.12))
                    if k <= 0:
                        continue
                y = top + i * rh + (rh - bar_h) / 2
                v = r[stat]
                is_hi = r["season"] in hi
                d.text((label_w, y + bar_h / 2), r["season"], font=f_lab, anchor="rm",
                       fill=GOLD if is_hi else TEXT)
                if v is None:
                    continue
                w = (x1 - x0) * (v / vmax) * min(1, k * 1.15)
                col = GOLD if is_hi else BAR
                d.rounded_rectangle([x0, y, x0 + max(4, w), y + bar_h], radius=int(bar_h / 3), fill=col)
                if r.get("champion"):
                    d.ellipse([x0 + w - bar_h * 0.5 - 6, y + bar_h * 0.25, x0 + w - 6, y + bar_h * 0.75],
                              fill=(255, 255, 255))
                dec = int(spec.get("decimals", 1))
                shown = f"{v * min(1, k * 1.15):.{dec}f}" if k < 0.87 else f"{v:.{dec}f}"
                d.text((x0 + w + 14, y + bar_h / 2), shown, font=f_val, anchor="lm", fill=GOLD if is_hi else TEXT)
                if r.get("note") and k >= 0.87 and w > 160:      # tag sits inside the bar, never off-screen
                    d.text((x0 + w - (bar_h * 0.7 if r.get("champion") else 0) - 14, y + bar_h / 2), r["note"],
                           font=font("DejaVuSans-Bold.ttf", int(bar_h * 0.5)), anchor="rm", fill=(20, 20, 30))
            avg = spec.get("show_average")
            if avg:
                ak = window(t, 0.15, 0.6)
                ax = x0 + (x1 - x0) * avg / vmax
                d.line([(ax, top - 30), (ax, top - 30 + (bottom - top + 30) * ak)], fill=(255, 92, 92), width=5)
                if ak > 0.3:
                    d.text((ax, top - 22), f"CAREER AVG {avg:.1f}", font=font("Anton-Regular.ttf", 34), anchor="ms",
                           fill=(255, 92, 92))
            if spec.get("legend"):
                d.text((W / 2, 338), spec["legend"], font=font("DejaVuSans.ttf", 26), anchor="mm", fill=MUTED)
            _footer(d, spec.get("source", ""))
            pipe.write(im)
    finally:
        pipe.close()
    return out


def render_line_compare(spec: dict, series: dict[str, list[float | None]], duration: float, out: Path,
                        fps: int = 30) -> Path:
    """Career arcs: stat by season number for 2–4 players; lines draw on together."""
    names = list(series)[:4]
    longest = max(len(v) for v in series.values())
    vals = [x for v in series.values() for x in v if x is not None]
    vmax = max(vals) * 1.1 if vals else 1
    left, right, top, bottom = 120, W - 60, 380, 1120
    nframes = max(1, int(duration * fps))
    base = _bg()
    pipe = FramePipe(out, W, H, fps)

    def P(i, v):
        return left + (right - left) * i / max(1, longest - 1), bottom - (bottom - top) * v / vmax
    try:
        for fi in range(nframes):
            t = fi / max(1, nframes - 1)
            prog = ease(min(1, t / 0.8)) * (longest - 1)
            im = _bgf(base, fi)
            d = ImageDraw.Draw(im)
            _header(d, spec.get("title", ""), spec.get("subtitle", ""))
            step = 10 if vmax > 25 else 5
            for g in range(0, int(vmax) + 1, step):
                y = P(0, g)[1]
                d.line([(left, y), (right, y)], fill=GRID, width=2)
                d.text((left - 16, y), str(g), font=font("DejaVuSans.ttf", 24), anchor="rm", fill=MUTED)
            for s in range(0, longest, 2 if longest > 10 else 1):
                d.text((P(s, 0)[0], bottom + 24), str(s + 1), font=font("DejaVuSans.ttf", 22), anchor="mm", fill=MUTED)
            d.text(((left + right) / 2, bottom + 58), "SEASON IN THE LEAGUE", font=font("DejaVuSans-Bold.ttf", 24),
                   anchor="mm", fill=MUTED)
            for ni, name in enumerate(names):
                col = PALETTE[ni]
                pts = [P(i, v) for i, v in enumerate(series[name]) if v is not None and i <= prog]
                if len(pts) >= 2:
                    d.line(pts, fill=col, width=8, joint="curve")
                if pts:
                    x, y = pts[-1]
                    d.ellipse([x - 11, y - 11, x + 11, y + 11], fill=col)
                    last_i = max(i for i, v in enumerate(series[name]) if v is not None and i <= prog)
                    d.text((x + 16 if x < right - 200 else x - 16, y - 30), f"{series[name][last_i]:.1f}",
                           font=font("Anton-Regular.ttf", 38), anchor="lm" if x < right - 200 else "rm", fill=col)
                d.rounded_rectangle([60 + ni * 250, 1230, 90 + ni * 250, 1260], radius=6, fill=col)
                d.text((100 + ni * 250, 1246), name.split()[-1].upper(), font=font("Anton-Regular.ttf", 34),
                       anchor="lm", fill=TEXT)
            _footer(d, spec.get("source", ""))
            pipe.write(im)
    finally:
        pipe.close()
    return out


def _photo_disc(photo: str, size: int, ring) -> Image.Image:
    from PIL import ImageFilter, ImageOps
    pad = 60
    out = Image.new("RGBA", (size + 2 * pad, size + 2 * pad), (0, 0, 0, 0))
    glow = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([pad - 18, pad - 18, pad + size + 18, pad + size + 18], fill=tuple(ring) + (200,))
    out = Image.alpha_composite(out, glow.filter(ImageFilter.GaussianBlur(28)))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    ph = ImageOps.fit(Image.open(photo).convert("RGB"), (size, size), Image.LANCZOS, centering=(0.5, 0.28))
    out.paste(ph, (pad, pad), mask)
    ImageDraw.Draw(out).ellipse([pad, pad, pad + size - 1, pad + size - 1], outline=tuple(ring), width=10)
    return out


def render_big_number(spec: dict, duration: float, out: Path, fps: int = 30) -> Path:
    """One verified number counting up, with a label and context line. With spec['photo'] (a licensed
    player photo) the photo pops in above the number inside a team-colour ring."""
    value = float(spec["value"])
    decimals = int(spec.get("decimals", 1))
    nframes = max(1, int(duration * fps))
    base = _bg()
    disc = None
    if spec.get("photo"):
        disc = _photo_disc(spec["photo"], 400, team_colors(spec.get("team", ""))[1])
    pipe = FramePipe(out, W, H, fps)
    try:
        for fi in range(nframes):
            t = fi / max(1, nframes - 1)
            k = ease(min(1, t / 0.45))
            im = _bgf(base, fi)
            if disc is not None:
                kp = ease(min(1, (fi / fps) / 0.35))
                sz = max(1, int(disc.width * (0.7 + 0.3 * kp)))
                dd = disc.resize((sz, sz), Image.BILINEAR)
                dd.putalpha(dd.getchannel("A").point(lambda a: int(a * kp)))
                im.paste(dd, (int(W / 2 - sz / 2), int(450 - sz / 2)), dd)
            d = ImageDraw.Draw(im)
            ty, ny, ly, cy = (690, 900, 1090, 1140) if disc is not None else (220, 760, 990, 1060)
            if spec.get("title"):
                if disc is not None:
                    d.text((W / 2, ty + 40), spec["title"].upper(), font=font("Anton-Regular.ttf", 76), anchor="mm",
                           fill=TEXT, stroke_width=3, stroke_fill=(0, 0, 0))
                else:
                    meme_text(d, spec["title"], (50, 220, W - 50, 480), size=90, fill=TEXT)
            num = f"{value * k:,.{decimals}f}"
            d.text((W / 2, ny), num, font=font("Anton-Regular.ttf", 260 if disc is not None else 330), anchor="mm",
                   fill=GOLD, stroke_width=6, stroke_fill=(0, 0, 0))
            if spec.get("label"):
                d.text((W / 2, ly), spec["label"].upper(), font=font("Anton-Regular.ttf", 58), anchor="mm", fill=TEXT)
            if spec.get("context") and t > 0.4:
                meme_text(d, spec["context"], (60, cy, W - 60, cy + 130 if disc is not None else 1240), size=48,
                          fill=MUTED)
            _footer(d, spec.get("source", ""))
            pipe.write(im)
    finally:
        pipe.close()
    return out


# ---------------------------------------------------------------- comeback / before-after infographics
TEAM_COLORS = {  # primary, secondary — colours only (no logos)
    "atlanta": ((225, 68, 52), (38, 40, 42)), "boston": ((0, 122, 51), (186, 150, 83)),
    "brooklyn": ((30, 30, 30), (255, 255, 255)), "charlotte": ((29, 17, 96), (0, 120, 140)),
    "chicago": ((206, 17, 65), (6, 25, 34)), "cleveland": ((134, 0, 56), (253, 187, 48)),
    "dallas": ((0, 83, 188), (0, 43, 92)), "denver": ((13, 34, 64), (255, 198, 39)),
    "detroit": ((200, 16, 46), (29, 66, 138)), "golden state": ((29, 66, 138), (255, 199, 44)),
    "houston": ((206, 17, 65), (6, 25, 34)), "indiana": ((0, 45, 98), (253, 187, 48)),
    "clippers": ((200, 16, 46), (29, 66, 148)), "lakers": ((85, 37, 130), (253, 185, 39)),
    "memphis": ((93, 118, 169), (18, 23, 63)), "miami": ((152, 0, 46), (249, 160, 27)),
    "milwaukee": ((0, 71, 27), (240, 235, 210)), "minnesota": ((12, 35, 64), (35, 97, 146)),
    "new orleans": ((0, 22, 65), (225, 58, 62)), "new york": ((0, 107, 182), (245, 132, 38)),
    "oklahoma city": ((0, 125, 195), (239, 59, 36)), "orlando": ((0, 125, 197), (196, 206, 211)),
    "philadelphia": ((0, 107, 182), (237, 23, 76)), "phoenix": ((29, 17, 96), (229, 95, 32)),
    "portland": ((224, 58, 62), (6, 25, 34)), "sacramento": ((91, 43, 130), (99, 113, 122)),
    "san antonio": ((196, 206, 211), (6, 25, 34)), "toronto": ((206, 17, 65), (6, 25, 34)),
    "utah": ((0, 43, 92), (249, 160, 27)), "washington": ((0, 43, 92), (227, 24, 55)),
    "seattle": ((0, 101, 58), (255, 194, 32)),
}


def team_colors(team: str) -> tuple:
    t = (team or "").lower()
    for k, v in TEAM_COLORS.items():
        if k in t:
            return v
    return (70, 110, 220), (255, 196, 0)


def player_icon(name: str, team: str, size: int, photo: str | None = None) -> Image.Image:
    """Circular player icon: licensed photo if available, otherwise team-colour badge with initials."""
    from PIL import ImageOps
    prim, sec = team_colors(team)
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    if photo:
        ph = ImageOps.fit(Image.open(photo).convert("RGB"), (size, size), Image.LANCZOS, centering=(0.5, 0.3))
        icon.paste(ph, (0, 0), mask)
    else:
        face = Image.new("RGB", (size, size), prim)
        d = ImageDraw.Draw(face)
        d.ellipse([size * 0.06, size * 0.06, size * 0.94, size * 0.94], outline=sec, width=max(4, size // 22))
        initials = "".join(p[0] for p in name.replace(".", "").split()[:2]).upper()
        d.text((size / 2, size / 2), initials, font=font("Anton-Regular.ttf", int(size * 0.42)), anchor="mm",
               fill=sec if sum(sec) > 200 else (255, 255, 255))
        icon.paste(face, (0, 0), mask)
    ring = ImageDraw.Draw(icon)
    ring.ellipse([2, 2, size - 3, size - 3], outline=sec, width=max(5, size // 18))
    return icon


def _fmt_stat(stat: str, v) -> str:
    if v is None:
        return "?"
    if isinstance(v, str):
        return v
    if stat in ("FG%", "3P%", "FT%"):
        return f"{v:.3f}".lstrip("0")
    if stat in ("GP", "G"):
        return f"{int(v)}"
    return f"{v:.1f}"


def _delta(stat: str, a, b) -> tuple[str, tuple] | None:
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return None
    dv = b - a
    if stat in ("GP", "G"):
        return None
    txt = (f"{dv:+.3f}".replace("0.", ".") if stat in ("FG%", "3P%", "FT%") else f"{dv:+.1f}")
    return txt, ((60, 210, 120) if dv > 0 else (240, 80, 80) if dv < 0 else MUTED)


def _timeline(d: ImageDraw.ImageDraw, marks: list, current, k: float) -> None:
    if not marks:
        return
    y, x0, x1 = 120, 90, W - 90
    lo, hi = min(m for m in marks), max(m for m in marks)
    span = max(1, hi - lo)
    d.line([(x0, y), (x1, y)], fill=GRID, width=4)
    for m in marks:
        x = x0 + (x1 - x0) * (m - lo) / span
        on = m == current
        r = 14 if on else 8
        d.ellipse([x - r, y - r, x + r, y + r], fill=GOLD if on else (90, 98, 120))
        if on or m in (lo, hi):
            d.text((x, y + 38), str(m), font=font("Anton-Regular.ttf", 34 if on else 26), anchor="mm",
                   fill=GOLD if on else MUTED)


def render_comeback_card(spec: dict, duration: float, out: Path, fps: int = 30) -> Path:
    """Before vs first-full-season-after for one player. spec: name, team, photo, injury, when (label),
    year (int, for the timeline), timeline (list of years), before {label, stats{}}, after {label, stats{}},
    stats (ordered list of stat keys), source."""
    stats = spec["stats"]
    nframes = max(1, int(duration * fps))
    base = _bg()
    icon = player_icon(spec["name"], spec.get("team", ""), 190, spec.get("photo"))
    prim, sec = team_colors(spec.get("team", ""))
    pipe = FramePipe(out, W, H, fps)
    xb, xa, xd = 470, 760, 975
    try:
        for fi in range(nframes):
            t = fi / max(1, nframes - 1)
            im = _bgf(base, fi)
            d = ImageDraw.Draw(im)
            d.rectangle([0, 0, 14, H], fill=prim)
            _timeline(d, spec.get("timeline", []), spec.get("year"), 1)
            k1 = window(t, 0.0, 0.12)
            im.paste(icon, (60, 230 - int(30 * (1 - k1))), icon)
            d = ImageDraw.Draw(im)
            nm_font = font("Anton-Regular.ttf", 86)
            name = spec["name"].upper()
            while nm_font.getlength(name) > W - 310 and nm_font.size > 50:
                nm_font = font("Anton-Regular.ttf", nm_font.size - 4)
            d.text((280, 290), name, font=nm_font, anchor="lm", fill=TEXT)
            d.text((282, 370), spec.get("subtitle", ""), font=font("DejaVuSans-Bold.ttf", 30), anchor="lm", fill=MUTED)
            k2 = window(t, 0.08, 0.2)
            if k2 > 0:
                inj = f"{spec['injury'].upper()}  ·  {spec['when'].upper()}"
                f_inj = font("DejaVuSans-Bold.ttf", 34)
                while f_inj.getlength(inj) > W - 140 and f_inj.size > 22:
                    f_inj = font("DejaVuSans-Bold.ttf", f_inj.size - 2)
                tw = f_inj.getlength(inj)
                good = spec.get("tone") == "positive"      # gold tag for awards/breakouts, red for injuries
                d.rounded_rectangle([60, 470, 60 + (tw + 60) * k2, 545], radius=36,
                                    fill=GOLD if good else (150, 28, 36))
                if k2 > 0.6:
                    d.text((90, 508), inj, font=f_inj, anchor="lm", fill=(20, 16, 4) if good else (255, 235, 235))
            # column headers
            hk = window(t, 0.15, 0.28)
            if hk > 0:
                for x, lab, sub, col in ((xb, spec.get("before_head", "BEFORE"), spec["before"]["label"], TEXT),
                                         (xa, spec.get("after_head", "AFTER"), spec["after"]["label"], GOLD)):
                    d.text((x, 630), lab.upper(), font=font("Anton-Regular.ttf", 46), anchor="mm", fill=col)
                    d.text((x, 682), sub, font=font("DejaVuSans-Bold.ttf", 26), anchor="mm", fill=MUTED)
                d.line([(60, 715), (W - 60, 715)], fill=GRID, width=3)
            for i, st in enumerate(stats):
                y = 830 + i * 160
                rk_b = window(t, 0.22 + i * 0.06, 0.42 + i * 0.06)
                rk_a = window(t, 0.45 + i * 0.07, 0.68 + i * 0.07)
                if rk_b <= 0:
                    continue
                d.text((70, y), {"PPG": "POINTS / GAME", "RPG": "REBOUNDS", "APG": "ASSISTS", "FG%": "FG %",
                                 "3P%": "3PT %", "GP": "GAMES PLAYED", "MPG": "MINUTES"}.get(st, st),
                       font=font("DejaVuSans-Bold.ttf", 28), anchor="lm", fill=MUTED)
                bv, av = spec["before"]["stats"].get(st), spec["after"]["stats"].get(st)
                show_b = bv * rk_b if isinstance(bv, (int, float)) and rk_b < 1 else bv
                d.text((xb, y), _fmt_stat(st, show_b), font=font("Anton-Regular.ttf", 92), anchor="mm", fill=TEXT)
                if rk_a > 0:
                    show_a = av * rk_a if isinstance(av, (int, float)) and rk_a < 1 else av
                    d.text((xa, y), _fmt_stat(st, show_a), font=font("Anton-Regular.ttf", 92), anchor="mm",
                           fill=GOLD)
                dl = _delta(st, bv, av)
                if dl and rk_a >= 1:
                    txt, col = dl
                    d.rounded_rectangle([xd - 85, y - 34, xd + 85, y + 34], radius=34, fill=col)
                    d.text((xd, y), txt, font=font("Anton-Regular.ttf", 44), anchor="mm", fill=(12, 14, 22))
            if spec.get("source"):
                _footer(d, spec["source"])
            pipe.write(im)
    finally:
        pipe.close()
    return out


def render_slope(spec: dict, items: list[dict], duration: float, out: Path, fps: int = 30) -> Path:
    """Before → after for several players on one chart. items: {name, team, before, after, photo?}."""
    vals = [v for it in items for v in (it["before"], it["after"])]
    vmin, vmax = min(vals) - 3, max(vals) + 3
    xl, xr, top, bottom = 190, 600, 420, 1180
    nframes = max(1, int(duration * fps))
    base = _bg()
    icons = [player_icon(it["name"], it.get("team", ""), 84, it.get("photo")) for it in items]
    pipe = FramePipe(out, W, H, fps)

    def Y(v):
        return bottom - (bottom - top) * (v - vmin) / (vmax - vmin)
    try:
        for fi in range(nframes):
            t = fi / max(1, nframes - 1)
            im = _bgf(base, fi)
            d = ImageDraw.Draw(im)
            _header(d, spec.get("title", ""), spec.get("subtitle", ""))
            for x, lab in ((xl, spec.get("left_label", "BEFORE")), (xr, spec.get("right_label", "AFTER"))):
                d.line([(x, top - 20), (x, bottom + 20)], fill=GRID, width=4)
                d.text((x, bottom + 60), lab, font=font("Anton-Regular.ttf", 40), anchor="mm", fill=MUTED)
            placed, placed_l = [], []
            for i, it in enumerate(items):
                k = window(t, 0.05 + i * 0.12, 0.35 + i * 0.12)
                if k <= 0:
                    continue
                prim, sec = team_colors(it.get("team", ""))
                col = (60, 210, 120) if it["after"] > it["before"] else (240, 80, 80)
                y0, y1 = Y(it["before"]), Y(it["after"])
                xe = xl + (xr - xl) * k
                ye = y0 + (y1 - y0) * k
                d.line([(xl, y0), (xe, ye)], fill=col, width=9)
                d.ellipse([xl - 12, y0 - 12, xl + 12, y0 + 12], fill=TEXT)
                d.ellipse([xe - 14, ye - 14, xe + 14, ye + 14], fill=col)
                lyl = y0
                for p in placed_l:
                    if abs(lyl - p) < 46:
                        lyl = p + 46 if lyl >= p else p - 46
                placed_l.append(lyl)
                d.text((xl - 30, lyl), f"{it['before']:.1f}", font=font("Anton-Regular.ttf", 40), anchor="rm", fill=TEXT)
                if k >= 1:
                    d.text((xr + 30, y1), f"{it['after']:.1f}", font=font("Anton-Regular.ttf", 44), anchor="lm", fill=col)
                    ly = y1
                    for p in placed:
                        if abs(ly - p) < 90:
                            ly = p + 90
                    placed.append(ly)
                    im.paste(icons[i], (xr + 135, int(ly - 42)), icons[i])
                    d = ImageDraw.Draw(im)
                    d.text((xr + 232, ly), it["name"].split()[-1].upper(), font=font("Anton-Regular.ttf", 40),
                           anchor="lm", fill=TEXT)
            if spec.get("source"):
                _footer(d, spec["source"])
            pipe.write(im)
    finally:
        pipe.close()
    return out


# ---------------------------------------------------------------- GOAT-debate comparisons
def _winners(vals: list, higher_is_better: bool = True) -> set[int]:
    nums = [v for v in vals if isinstance(v, (int, float))]
    if not nums:
        return set()
    best = max(nums) if higher_is_better else min(nums)
    return {i for i, v in enumerate(vals) if v == best}


def _fmt_num(v, decimals: int) -> str:
    return "?" if v is None else f"{v:,.{decimals}f}"


def render_head_to_head(spec: dict, players: list[dict], duration: float, out: Path, fps: int = 30) -> Path:
    """One stat, up to 5 players, horizontal bars racing out. players: [{name, team, photo, value, losses?,
    display?}]. If `losses` is given the bar is a W–L split (wins gold/green, losses red). Leaders get a crown;
    ties crown everyone tied. spec: title, subtitle, decimals, higher_is_better, note."""
    n = len(players)
    dec = int(spec.get("decimals", 0))
    vals = [p.get("rank", p.get("value")) for p in players]   # rank = what decides the leader (e.g. win %)
    win = _winners(vals, spec.get("higher_is_better", True))
    tie = len(win) > 1
    has_l = any(p.get("losses") is not None for p in players)
    top = max((p.get("value") or 0) + (p.get("losses") or 0) for p in players) or 1
    row_h = 230 if n <= 3 else 190 if n == 4 else 165
    isz = min(150, row_h - 30)
    icons = [player_icon(p["name"], p.get("team", ""), isz, p.get("photo")) for p in players]
    nframes = max(1, int(duration * fps))
    base = _bg()
    pipe = FramePipe(out, W, H, fps)
    x0, x1 = 230, W - 70
    y_top = 430
    try:
        for fi in range(nframes):
            t = fi / max(1, nframes - 1)
            im = _bgf(base, fi)
            d = ImageDraw.Draw(im)
            _header(d, spec.get("title", ""), spec.get("subtitle", ""))
            for i, p in enumerate(players):
                k = ease(window(t, 0.04 + 0.08 * i, 0.42 + 0.08 * i))
                y = y_top + i * row_h
                im.paste(icons[i], (45, int(y)), icons[i])
                d.text((x0, y + 18), p["name"].upper(), font=font("Anton-Regular.ttf", 46), anchor="lm", fill=TEXT)
                bar_y0, bar_y1 = y + 58, y + 132
                d.rounded_rectangle([x0, bar_y0, x1, bar_y1], radius=14, fill=GRID)
                v = (p.get("value") or 0) * k
                lead = i in win and t > 0.55
                col = GOLD if lead else (90, 200, 130) if has_l else BAR
                wx = x0 + (x1 - x0) * v / top
                if wx > x0 + 6:
                    d.rounded_rectangle([x0, bar_y0, wx, bar_y1], radius=14, fill=col)
                if has_l and p.get("losses"):
                    lx = wx + (x1 - x0) * p["losses"] * k / top
                    if lx > wx + 6:
                        d.rounded_rectangle([wx, bar_y0, lx, bar_y1], radius=14, fill=(230, 72, 72))
                    wx = lx
                label = p.get("display") if (p.get("display") and k > 0.98) else _fmt_num(v, dec)
                lf = font("Anton-Regular.ttf", 58)
                tw = d.textlength(label, font=lf)
                inside = wx - x0 > tw + 50
                tx = wx - 22 if inside else wx + 18
                d.text((tx, (bar_y0 + bar_y1) / 2), label, font=lf, anchor="rm" if inside else "lm",
                       fill=(10, 12, 20) if inside else TEXT, stroke_width=0 if inside else 3, stroke_fill=(0, 0, 0))
                if lead:
                    tag = "TIE" if tie else "LEADS"
                    d.text((x1, y + 18), f"♛ {tag}", font=font("DejaVuSans-Bold.ttf", 36), anchor="rm", fill=GOLD)
            if has_l:
                ly = y_top + n * row_h - 40
                d.rounded_rectangle([x0, ly, x0 + 34, ly + 34], radius=6, fill=(90, 200, 130))
                d.text((x0 + 48, ly + 17), "WINS", font=font("DejaVuSans-Bold.ttf", 30), anchor="lm", fill=MUTED)
                d.rounded_rectangle([x0 + 200, ly, x0 + 234, ly + 34], radius=6, fill=(230, 72, 72))
                d.text((x0 + 248, ly + 17), "LOSSES", font=font("DejaVuSans-Bold.ttf", 30), anchor="lm", fill=MUTED)
            if spec.get("note") and t > 0.5:      # under the subtitle: the caption band below stays clear
                d.text((W / 2, 345), spec["note"], font=font("DejaVuSans-Bold.ttf", 30), anchor="mm", fill=MUTED)
            pipe.write(im)
    finally:
        pipe.close()
    return out


def render_tally(spec: dict, players: list[dict], cats: list[dict], duration: float, out: Path, fps: int = 30) -> Path:
    """Category scoreboard: players as columns, categories as rows revealed one by one; the leader's cell is
    gold, and the bottom row counts categories won (ties count for everyone tied).
    players: [{name, team, photo}], cats: [{label, values:[...], display:[...]?, decimals, higher_is_better}]."""
    n = len(players)
    icons = [player_icon(p["name"], p.get("team", ""), 130, p.get("photo")) for p in players]
    lab_w = 300
    cw = (W - 60 - lab_w) / n
    cx = [60 + lab_w + cw * (i + 0.5) for i in range(n)]
    rows = [(c, _winners(c.get("rank") or c["values"], c.get("higher_is_better", True))) for c in cats]
    nframes = max(1, int(duration * fps))
    base = _bg()
    pipe = FramePipe(out, W, H, fps)
    y0, rh = 560, 92
    try:
        for fi in range(nframes):
            t = fi / max(1, nframes - 1)
            im = _bgf(base, fi)
            d = ImageDraw.Draw(im)
            _header(d, spec.get("title", "THE SCORECARD"), spec.get("subtitle", ""))
            for i, p in enumerate(players):
                im.paste(icons[i], (int(cx[i] - 65), 345), icons[i])
                d.text((cx[i], 500), p["name"].split()[-1].upper(), font=font("Anton-Regular.ttf", 38),
                       anchor="mm", fill=TEXT)
            shown = [0] * n
            for r, (c, win) in enumerate(rows):
                k = window(t, 0.05 + 0.09 * r, 0.12 + 0.09 * r)
                if k <= 0:
                    continue
                y = y0 + r * rh
                d.rounded_rectangle([50, y, W - 50, y + rh - 12], radius=12, fill=(20, 25, 40))
                d.text((70, y + (rh - 12) / 2), c["label"].upper(), font=font("Anton-Regular.ttf", 36),
                       anchor="lm", fill=MUTED)
                dec = int(c.get("decimals", 0))
                for i in range(n):
                    txt = (c.get("display") or [None] * n)[i] or _fmt_num(c["values"][i], dec)
                    lead = i in win and k >= 1
                    if lead:
                        d.rounded_rectangle([cx[i] - cw / 2 + 10, y + 6, cx[i] + cw / 2 - 10, y + rh - 18],
                                            radius=10, fill=GOLD)
                        shown[i] += 1
                    d.text((cx[i], y + (rh - 12) / 2), txt, font=font("Anton-Regular.ttf", 44), anchor="mm",
                           fill=(10, 12, 20) if lead else TEXT)
            if t > 0.05 + 0.09 * len(rows) + 0.06:
                y = y0 + len(rows) * rh + 10
                d.text((70, y + 40), "CATEGORIES WON", font=font("Anton-Regular.ttf", 36), anchor="lm", fill=GOLD)
                best = max(shown)
                for i in range(n):
                    d.text((cx[i], y + 40), str(shown[i]), font=font("Anton-Regular.ttf", 78), anchor="mm",
                           fill=GOLD if shown[i] == best else TEXT, stroke_width=3, stroke_fill=(0, 0, 0))
            pipe.write(im)
    finally:
        pipe.close()
    return out


# ---------------------------------------------------------------- flashy-but-professional pieces
def render_hype_text(spec: dict, duration: float, out: Path, fps: int = 30) -> Path:
    """Kinetic title card: kicker line slides in, headline punches in with a glow, accent bar wipes under it.
    spec: text, kicker, accent(rgb)."""
    from PIL import ImageFilter
    from .cards import wrap
    nframes = max(1, int(duration * fps))
    base = _bg(seed=11)
    broll = BrollReader(spec["broll"], fps) if spec.get("broll") else None
    acc = tuple(spec.get("accent") or GOLD)
    faces = [player_icon(n, tm, 190, ph) for n, tm, ph in (spec.get("faces") or [])[:4]]
    f, lines, size = wrap(spec["text"].upper(), "Anton-Regular.ttf", W - 140, 150, min_size=80, max_lines=4)
    lh = int(size * 1.08)
    y0 = 760 - (len(lines) * lh) / 2
    # pre-render headline + glow once
    txt = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    td = ImageDraw.Draw(txt)
    for i, ln in enumerate(lines):
        td.text((W / 2, y0 + i * lh), ln, font=f, anchor="mt", fill=TEXT, stroke_width=4, stroke_fill=(0, 0, 0))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for i, ln in enumerate(lines):
        gd.text((W / 2, y0 + i * lh), ln, font=f, anchor="mt", fill=acc + (200,))
    glow = glow.filter(ImageFilter.GaussianBlur(26))
    pipe = FramePipe(out, W, H, fps)
    try:
        for fi in range(nframes):
            t = fi / fps
            im = (broll.frame() if broll else _bgf(base, fi)).convert("RGBA")
            k = ease(min(1, t / 0.35))
            sc = 1.18 - 0.18 * k
            pulse = 0.75 + 0.25 * math.sin(t * 3.2)
            g = glow.copy()
            g.putalpha(g.getchannel("A").point(lambda a: int(a * k * pulse)))
            layer = Image.alpha_composite(g, txt) if k > 0 else txt
            if abs(sc - 1) > 0.002:
                lw, lhh = int(W * sc), int(H * sc)
                layer = layer.resize((lw, lhh), Image.BILINEAR).crop(((lw - W) // 2, (lhh - H) // 2,
                                                                     (lw - W) // 2 + W, (lhh - H) // 2 + H))
            layer.putalpha(layer.getchannel("A").point(lambda a: int(a * k)))
            im = Image.alpha_composite(im, layer)
            d = ImageDraw.Draw(im)
            if spec.get("kicker"):
                kk = ease(window(t / max(duration, 0.1), 0.0, 0.15))
                kx = W / 2 - (1 - kk) * 200
                kf = font("DejaVuSans-Bold.ttf", 40)
                tw = d.textlength(spec["kicker"].upper(), font=kf)
                d.rounded_rectangle([kx - tw / 2 - 30, y0 - 130, kx + tw / 2 + 30, y0 - 60], radius=35,
                                    fill=acc + (255,))
                d.text((kx, y0 - 95), spec["kicker"].upper(), font=kf, anchor="mm", fill=(12, 12, 20))
            bw = (W - 300) * ease(window(t / max(duration, 0.1), 0.08, 0.3))
            by = y0 + len(lines) * lh + 40
            d.rounded_rectangle([W / 2 - bw / 2, by, W / 2 + bw / 2, by + 12], radius=6, fill=acc + (255,))
            if faces:
                n = len(faces)
                gap = 30
                tot = n * 190 + (n - 1) * gap
                for i, fc in enumerate(faces):
                    kf = ease(window(t / max(duration, 0.1), 0.12 + 0.07 * i, 0.3 + 0.07 * i))
                    if kf <= 0:
                        continue
                    x = int(W / 2 - tot / 2 + i * (190 + gap))
                    y = int(by + 50 + (1 - kf) * 60)
                    f2 = fc.copy()
                    f2.putalpha(f2.getchannel("A").point(lambda a: int(a * kf)))
                    im.paste(f2, (x, y), f2)
            pipe.write(im.convert("RGB"))
    finally:
        pipe.close()
        if broll:
            broll.close()
    return out


class BrollReader:
    """Streams a licensed b-roll clip as blurred, darkened 1080x1920 background frames (looped)."""

    def __init__(self, path: str, fps: int = 30):
        import subprocess
        self.w, self.h = 540, 960
        self.proc = subprocess.Popen(
            ["ffmpeg", "-loglevel", "error", "-stream_loop", "-1", "-i", path, "-an", "-vf",
             f"fps={fps},scale={self.w}:{self.h}:force_original_aspect_ratio=increase,crop={self.w}:{self.h},"
             "boxblur=6:2,eq=brightness=-0.22:saturation=0.75", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdout=subprocess.PIPE)
        self.last = Image.new("RGB", (W, H), BG)

    def frame(self) -> Image.Image:
        buf = self.proc.stdout.read(self.w * self.h * 3)
        if len(buf) == self.w * self.h * 3:
            img = Image.frombytes("RGB", (self.w, self.h), buf).resize((W, H), Image.BILINEAR)
            dark = Image.new("RGB", (W, H), (8, 10, 18))
            self.last = Image.blend(img, dark, 0.5)
        return self.last.copy()

    def close(self) -> None:
        try:
            self.proc.kill()
        except Exception:
            pass


def render_all_time_rank(spec: dict, rows: list[dict], duration: float, out: Path, fps: int = 30) -> Path:
    """All-time leaderboard: rank, badge, player, season, value bar. Rows reveal bottom-up like a countdown;
    the highlighted row (this season) pulses in gold. rows: [{rank, player, season, value, team, highlight}]."""
    n = len(rows)
    nframes = max(1, int(duration * fps))
    base = _bg(seed=5)
    dec = int(spec.get("decimals", 1))
    vmax = max(r["value"] for r in rows)
    vmin = spec.get("axis_min", min(r["value"] for r in rows) * 0.8)
    row_h = min(118, int(820 / max(1, n)))
    y_top = 400
    icons = [player_icon(r["player"], r.get("team", ""), row_h - 26, r.get("photo")) for r in rows]
    x0, x1 = 330, W - 60
    pipe = FramePipe(out, W, H, fps)
    try:
        for fi in range(nframes):
            t = fi / max(1, nframes - 1)
            ts = fi / fps
            im = _bgf(base, fi)
            d = ImageDraw.Draw(im)
            _header(d, spec.get("title", ""), spec.get("subtitle", ""))
            for j in range(n):
                i = n - 1 - j                       # countdown: bottom row first
                k = ease(window(t, 0.03 + 0.07 * j, 0.2 + 0.07 * j))
                if k <= 0:
                    continue
                r = rows[i]
                y = y_top + i * row_h
                hl = r.get("highlight")
                if hl:
                    a = 0.6 + 0.4 * math.sin(ts * 4)
                    d.rounded_rectangle([30, y - 4, W - 30, y + row_h - 10], radius=18,
                                        fill=(int(60 * a), int(46 * a), 0), outline=GOLD, width=4)
                d.text((70, y + (row_h - 14) / 2), f"{r['rank']}", font=font("Anton-Regular.ttf", 54), anchor="mm",
                       fill=GOLD if hl else MUTED)
                im.paste(icons[i], (112, int(y + 6)), icons[i])
                d.text((x0 - 120 + row_h, y + 10), "", font=font("DejaVuSans.ttf", 10))
                d.text((x0 - 105 + row_h - 100, y + 6), r["player"].upper(), font=font("Anton-Regular.ttf", 36),
                       anchor="la", fill=TEXT)
                d.text((x0 - 105 + row_h - 100, y + 48), r["season"], font=font("DejaVuSans-Bold.ttf", 24),
                       anchor="la", fill=GOLD if hl else MUTED)
                bx0 = 640
                bw = (x1 - bx0) * (r["value"] - vmin) / (vmax - vmin) * k
                d.rounded_rectangle([bx0, y + 20, bx0 + max(bw, 8), y + row_h - 34], radius=10,
                                    fill=GOLD if hl else BAR)
                d.text((bx0 + max(bw, 8) - 12, y + (row_h - 14) / 2), f"{r['value'] * min(1, k * 1.05):.{dec}f}",
                       font=font("Anton-Regular.ttf", 40), anchor="rm", fill=(12, 12, 20) if hl else TEXT)
            if spec.get("note") and t > 0.4:
                d.text((W / 2, 345), spec["note"], font=font("DejaVuSans-Bold.ttf", 30), anchor="mm", fill=MUTED)
            pipe.write(im)
    finally:
        pipe.close()
    return out
