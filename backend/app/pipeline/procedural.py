"""Procedurally rendered, geographically accurate motion graphics: maps, timelines, chapter cards.

Maps use Natural Earth (public domain) land and rivers only — no modern borders, so they
never show anachronistic countries. Positions come from real coordinates in the script.
"""
from __future__ import annotations

import json
import math
import random
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..config import env
from ..media import FramePipe

W, H = 1920, 1080
GEO = env.assets_dir / "geo"
FONTS = env.assets_dir / "fonts"
INK = (52, 36, 22)
SEA = (168, 186, 190)
LAND = (236, 222, 188)
SIDE = {"a": (165, 32, 38), "b": (34, 64, 120), None: (120, 30, 30)}


def set_canvas(w: int, h: int) -> None:
    """Switch output size (1920x1080 long-form, 1080x1920 Shorts). The worker renders one video at a time."""
    global W, H
    W, H = w, h


def fit_font(name: str, size: int, text: str, max_w: int, weight: str | None = None):
    f = font(name, size, weight)
    while size > 28 and f.getlength(text) > max_w:
        size -= 4
        f = font(name, size, weight)
    return f


def font(name: str, size: int, weight: str | None = None) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONTS / name), size)
    if weight:
        try:
            f.set_variation_by_name(weight)
        except Exception:
            pass
    return f


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def window(t: float, a: float, b: float) -> float:
    return ease((t - a) / max(1e-6, b - a))


def text_stroke(draw: ImageDraw.ImageDraw, xy, txt, fnt, fill, stroke=(245, 236, 215), sw=4, anchor="la"):
    draw.text(xy, txt, font=fnt, fill=fill, stroke_width=sw, stroke_fill=stroke, anchor=anchor)


@lru_cache(maxsize=4)
def _geo(name: str) -> list:
    data = json.loads((GEO / name).read_text())
    out = []
    for f in data["features"]:
        g = f["geometry"]
        if not g:
            continue
        if g["type"] in ("Polygon", "LineString"):
            out.append((g["type"], g["coordinates"]))
        elif g["type"] in ("MultiPolygon", "MultiLineString"):
            for c in g["coordinates"]:
                out.append((g["type"].replace("Multi", ""), c))
    return out


def paper(w: int, h: int, base=(236, 224, 196), seed: int = 1) -> Image.Image:
    rnd = random.Random(seed)
    small = Image.new("L", (w // 8, h // 8))
    small.putdata([rnd.randint(0, 255) for _ in range((w // 8) * (h // 8))])
    noise = small.resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(6))
    img = Image.new("RGB", (w, h), base)
    dark = Image.new("RGB", (w, h), tuple(int(c * 0.9) for c in base))
    img = Image.composite(dark, img, noise.point(lambda v: int(v * 0.5)))
    # vignette
    vig = Image.new("L", (w, h), 0)
    vd = ImageDraw.Draw(vig)
    for i in range(40):
        a = int(255 * (1 - i / 40) ** 2)
        vd.rectangle([i * w / 80, i * h / 80, w - i * w / 80, h - i * h / 80], outline=255 - a)
    vig = vig.filter(ImageFilter.GaussianBlur(60))
    vig = vig.point(lambda v: int(140 + v * 115 / 255))
    return Image.composite(img, Image.new("RGB", (w, h), tuple(int(c * 0.7) for c in base)), vig)


class Projection:
    """Equirectangular with cos(lat) correction, fitted to 16:9 around the requested bbox."""

    def __init__(self, bbox, w: int, h: int, pad: float = 0.08):
        west, south, east, north = bbox
        if east < west:
            east += 360
        self.lat0 = math.radians((south + north) / 2)
        k = math.cos(self.lat0)
        bw, bh = (east - west) * k, (north - south)
        bw, bh = bw * (1 + 2 * pad), bh * (1 + 2 * pad)
        if bw / bh < w / h:
            bw = bh * w / h
        else:
            bh = bw * h / w
        self.cx, self.cy = (west + east) / 2 * k, (south + north) / 2
        self.scale = w / bw
        self.w, self.h, self.k = w, h, k

    def __call__(self, lon: float, lat: float) -> tuple[float, float]:
        x = (lon * self.k - self.cx) * self.scale + self.w / 2
        y = (self.cy - lat) * self.scale + self.h / 2
        return x, y

    def km(self, km: float) -> float:
        return km / 111.0 * self.scale


def _base_map(spec: dict, w: int, h: int, seed: int) -> tuple[Image.Image, Projection]:
    proj = Projection(spec["bbox"], w, h)
    img = paper(w, h, SEA, seed)
    land = Image.new("L", (w, h), 0)
    ld = ImageDraw.Draw(land)
    for kind, coords in _geo("coast.geojson"):
        if kind != "Polygon":
            continue
        ring = [proj(lon, lat) for lon, lat in coords[0]]
        xs, ys = [p[0] for p in ring], [p[1] for p in ring]
        if max(xs) < -50 or min(xs) > w + 50 or max(ys) < -50 or min(ys) > h + 50:
            continue
        ld.polygon(ring, fill=255)
        for hole in coords[1:]:
            ld.polygon([proj(lon, lat) for lon, lat in hole], fill=0)
    land_tex = paper(w, h, LAND, seed + 1)
    shadow = land.filter(ImageFilter.GaussianBlur(10)).point(lambda v: int(v * 0.35))
    img = Image.composite(Image.new("RGB", (w, h), (150, 160, 150)), img, shadow)
    img = Image.composite(land_tex, img, land)
    edge = land.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(3))
    img = Image.composite(Image.new("RGB", (w, h), INK), img, edge.point(lambda v: int(v * 0.7)))
    d = ImageDraw.Draw(img)
    rw = max(1, int(w / 1400))
    for kind, coords in _geo("rivers.geojson"):
        if kind != "LineString":
            continue
        pts = [proj(lon, lat) for lon, lat in coords]
        if any(-10 < x < w + 10 and -10 < y < h + 10 for x, y in pts):
            d.line(pts, fill=(118, 140, 150), width=rw)
    return img, proj


def _bezier(p0, p2, t, bend=0.18):
    mx, my = (p0[0] + p2[0]) / 2, (p0[1] + p2[1]) / 2
    dx, dy = p2[0] - p0[0], p2[1] - p0[1]
    p1 = (mx - dy * bend, my + dx * bend)
    return ((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
            (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1])


def _route(points: list, samples: int = 120) -> list:
    """Smooth path through waypoints (Catmull-Rom); a gentle arc when only two points."""
    if len(points) == 2:
        return [_bezier(points[0], points[1], i / samples) for i in range(samples + 1)]
    pts = [points[0]] + points + [points[-1]]
    out = []
    per = max(4, samples // (len(points) - 1))
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for s_ in range(per):
            t = s_ / per
            out.append(tuple(0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t * t
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t ** 3) for j in (0, 1)))
    out.append(points[-1])
    return out


def render_map(spec: dict, duration: float, out: Path, fps: int = 30, seed: int = 7, preset: str = "veryfast") -> Path:
    zoom_max = 1.08
    bw, bh = int(W * zoom_max), int(H * zoom_max)
    base, proj = _base_map(spec, bw, bh, seed)
    f_title, f_label, f_arrow = font("Cinzel.ttf", 58, "Bold"), font("PlayfairDisplay.ttf", 34, "Bold"), \
        font("PlayfairDisplay.ttf", 28, "Bold")
    markers = spec.get("markers") or []
    arrows = spec.get("arrows") or []
    areas = spec.get("areas") or []
    n = max(1, int(duration * fps))
    pipe = FramePipe(out, W, H, fps, preset=preset)
    try:
        for fi in range(n):
            t = fi / max(1, n - 1)
            z = 1 + (zoom_max - 1) * ease(t)                     # slow push-in
            cw, ch = bw / z, bh / z
            ox, oy = (bw - cw) / 2, (bh - ch) / 2
            frame = base.crop((int(ox), int(oy), int(ox + cw), int(oy + ch))).resize((W, H), Image.BILINEAR)
            sx = W / cw

            def P(lat, lon):
                x, y = proj(lon, lat)
                return (x - ox) * sx, (y - oy) * sx

            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(ov)
            for i, a in enumerate(areas):
                k = window(t, 0.1 + 0.1 * i, 0.5 + 0.1 * i)
                if k <= 0:
                    continue
                cx, cy = P(a["lat"], a["lon"])
                r = proj.km(a["radius_km"]) * sx * (0.6 + 0.4 * k)
                col = SIDE.get(a.get("side"))
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (int(70 * k),), outline=col + (int(180 * k),),
                          width=4)
                if a.get("label"):
                    text_stroke(d, (cx, cy), a["label"].upper(), f_arrow, col + (int(255 * k),), anchor="mm")
            for i, m in enumerate(markers):
                k = window(t, 0.05 + 0.35 * i / max(1, len(markers)), 0.15 + 0.35 * i / max(1, len(markers)))
                if k <= 0:
                    continue
                x, y = P(m["lat"], m["lon"])
                r = 9 + 6 * (1 - k)
                d.ellipse([x - r, y - r, x + r, y + r], fill=(130, 20, 20, int(255 * k)),
                          outline=(245, 236, 215, int(255 * k)), width=3)
                text_stroke(d, (x + 18, y - 4), m["name"], f_label, INK + (int(255 * k),), anchor="lm")
            for i, a in enumerate(arrows):
                k = window(t, 0.3 + 0.12 * i, 0.75 + 0.08 * i)
                if k <= 0:
                    continue
                path = _route([P(*a["from"])] + [P(*v) for v in a.get("via") or []] + [P(*a["to"])])
                pts = path[:max(2, int(len(path) * k))]
                col = SIDE.get(a.get("side"))
                d.line(pts, fill=col + (235,), width=10, joint="curve")
                (x1, y1), (x2, y2) = pts[-2], pts[-1]
                ang = math.atan2(y2 - y1, x2 - x1)
                hl = 30
                d.polygon([(x2 + math.cos(ang) * 10, y2 + math.sin(ang) * 10),
                           (x2 - hl * math.cos(ang - 0.5), y2 - hl * math.sin(ang - 0.5)),
                           (x2 - hl * math.cos(ang + 0.5), y2 - hl * math.sin(ang + 0.5))], fill=col + (255,))
                if a.get("label") and k > 0.5:
                    lx, ly = path[len(path) // 2]
                    text_stroke(d, (lx, ly - 26), a["label"], f_arrow, col + (int(255 * (k - 0.5) * 2),), anchor="mm")
            if spec.get("title"):
                k = window(t, 0.0, 0.12)
                ft = fit_font("Cinzel.ttf", 58, spec["title"].upper(), W - 180, "Bold")
                text_stroke(d, (90, 80 if W > H else 260), spec["title"].upper(), ft, INK + (int(255 * k),), sw=6)
                ty = 150 if W > H else 330
                d.line([(90, ty), (90 + min(520, W - 180) * k, ty)], fill=INK + (int(200 * k),), width=3)
            frame = Image.alpha_composite(frame.convert("RGBA"), ov).convert("RGB")
            pipe.write(frame)
    finally:
        pipe.close()
    return out


def _wrap(text: str, fnt, max_w: int, draw) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        test = (cur + " " + w_).strip()
        if draw.textlength(test, font=fnt) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines[:3]


def render_timeline(spec: dict, duration: float, out: Path, fps: int = 30, seed: int = 3, preset: str = "veryfast") -> Path:
    events = (spec.get("events") or [])[:12]
    hi = spec.get("highlight")
    ne = max(1, len(events))
    spacing = min(380, (W - 440) / max(1, ne - 1)) if ne > 1 else 0
    if ne > 1 and spacing < 280:
        spacing = 300
    total_w = int(max(W, 440 + spacing * (ne - 1)))
    left = 220 if total_w > W else (W - spacing * (ne - 1)) / 2
    base = paper(total_w, H, (233, 220, 190), seed)
    f_date, f_lab = font("Cinzel.ttf", 48, "Bold"), font("PlayfairDisplay.ttf", 30)
    n = max(1, int(duration * fps))
    pipe = FramePipe(out, W, H, fps, preset=preset)
    y = H // 2 + 20
    try:
        for fi in range(n):
            t = fi / max(1, n - 1)
            pan = (total_w - W) * ease(t)
            frame = base.crop((int(pan), 0, int(pan) + W, H)).convert("RGBA")
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(ov)
            line_k = window(t, 0.0, 0.25)
            d.line([(0, y), (W * line_k + (total_w - W) * line_k, y)], fill=INK + (230,), width=5)
            for i, e in enumerate(events):
                x = left + spacing * i - pan
                k = window(t, 0.08 + 0.75 * i / max(1, len(events)), 0.18 + 0.75 * i / max(1, len(events)))
                if k <= 0 or x < -200 or x > W + 200:
                    continue
                big = hi is not None and i == hi
                col = (150, 30, 30) if big else INK
                r = (18 if big else 12) * (0.5 + 0.5 * k)
                d.ellipse([x - r, y - r, x + r, y + r], fill=col + (int(255 * k),), outline=(245, 236, 215, 255), width=3)
                text_stroke(d, (x, y - 50 - 20 * (1 - k)), e["date"], f_date, col + (int(255 * k),), anchor="ms")
                for li, line in enumerate(_wrap(e["label"], f_lab, int(max(spacing, 320) - 40), d)):
                    text_stroke(d, (x, y + 60 + li * 38), line, f_lab, INK + (int(255 * k),), anchor="ma", sw=3)
            pipe.write(Image.alpha_composite(frame, ov).convert("RGB"))
    finally:
        pipe.close()
    return out


def render_title_card(title: str, subtitle: str, duration: float, out: Path, fps: int = 30, preset: str = "veryfast") -> Path:
    bg = paper(W, H, (28, 24, 20), 11)
    f_t, f_s = fit_font("Cinzel.ttf", 96, title.upper(), W - 120, "Bold"), font("PlayfairDisplay.ttf", 40)
    n = max(1, int(duration * fps))
    pipe = FramePipe(out, W, H, fps, preset=preset)
    gold = (214, 178, 106)
    try:
        for fi in range(n):
            t = fi / max(1, n - 1)
            k = window(t, 0.05, 0.35) * (1 - window(t, 0.85, 1.0))
            frame = bg.copy().convert("RGBA")
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(ov)
            half = 420 * window(t, 0.0, 0.4)
            d.line([(W / 2 - half, H / 2 + 70), (W / 2 + half, H / 2 + 70)], fill=gold + (int(255 * k),), width=3)
            d.text((W / 2, H / 2 - 10 + 12 * (1 - k)), title.upper(), font=f_t, fill=(240, 228, 200, int(255 * k)),
                   anchor="ms")
            if subtitle:
                d.text((W / 2, H / 2 + 130), subtitle, font=f_s, fill=gold + (int(255 * k),), anchor="ms")
            pipe.write(Image.alpha_composite(frame, ov).convert("RGB"))
    finally:
        pipe.close()
    return out


def render_text_overlay(text: str, out: Path, kind: str = "lower_third") -> Path:
    """Transparent PNG overlay for on-screen captions (place/date/name) or the AI-visual label."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if kind == "lower_third":
        f = fit_font("Cinzel.ttf", 46, text, W - 220, "Bold")
        tw = d.textlength(text, font=f)
        x, y = 110, (H - 210) if W > H else 470    # Shorts: below map titles, clear of captions & UI
        grad = Image.new("RGBA", (int(tw + 160), 90), (0, 0, 0, 0))
        gd = ImageDraw.Draw(grad)
        for i in range(grad.width):
            gd.line([(i, 0), (i, 90)], fill=(10, 8, 6, int(170 * (1 - i / grad.width) ** 0.6)))
        img.alpha_composite(grad, (x - 40, y - 20))
        d.line([(x, y + 62), (x + min(tw, 600), y + 62)], fill=(214, 178, 106, 255), width=3)
        d.text((x, y), text, font=f, fill=(245, 236, 215, 255))
    elif kind == "credit":   # museum artwork credit
        f = font("DejaVuSans.ttf", 22 if W > H else 26)
        lines = _wrap(text, f, W - 120, d) if W < H else [text]
        y0 = H - 60 - 34 * len(lines) if W > H else 150
        for i, line in enumerate(lines):
            d.text((50, y0 + i * 34), line, font=f, fill=(255, 255, 255, 190), stroke_width=2,
                   stroke_fill=(0, 0, 0, 150))
    else:  # ai label
        f = font("DejaVuSans.ttf", 22)
        d.text((W - 40, 36), text, font=f, fill=(255, 255, 255, 150), anchor="ra",
               stroke_width=2, stroke_fill=(0, 0, 0, 120))
    img.save(out)
    return out
