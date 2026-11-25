"""Animated 'broadcast' backgrounds for charts: drifting team-colour glows, a slow light sweep,
rising particles, a faint perspective floor grid and a vignette. Subtle enough that numbers stay the hero.
numpy-composited so a 45 s Short renders in about a minute."""
from __future__ import annotations

import math
import random

import numpy as np
from PIL import Image, ImageDraw

W, H = 1080, 1920


def _glow(size: int, color: tuple, strength: float) -> np.ndarray:
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) / 2
    r = np.sqrt((x - c) ** 2 + (y - c) ** 2) / c
    a = np.clip(1 - r, 0, 1) ** 2.2 * strength
    return a[..., None] * np.array(color, np.float32)[None, None, :]


class DynBG:
    """Call .frame(i) for frame i. accent/second: RGB tuples (e.g. team colours)."""

    def __init__(self, nframes: int, fps: int = 30, accent=(255, 196, 0), second=(64, 120, 255), seed: int = 7,
                 watermark: str | None = None):
        self.n, self.fps = max(1, nframes), fps
        rnd = random.Random(seed)
        yy = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
        top, bot = np.array((14, 16, 30), np.float32), np.array((5, 6, 12), np.float32)
        self.base = np.broadcast_to(top * (1 - yy) + bot * yy, (H, W, 3)).copy()
        # perspective floor grid + optional giant watermark (e.g. a jersey number), baked once
        layer = Image.new("RGB", (W, H), (0, 0, 0))
        d = ImageDraw.Draw(layer)
        hy = 1180
        for i in range(-12, 13):
            d.line([(W / 2 + i * 40, hy), (W / 2 + i * 260, H)], fill=(22, 26, 44), width=2)
        for k in range(1, 12):
            y = hy + (H - hy) * (k / 11) ** 1.8
            d.line([(0, y), (W, y)], fill=(20, 24, 40), width=2)
        if watermark:
            from .procedural import font
            d.text((W - 40, 900), watermark, font=font("Anton-Regular.ttf", 900), anchor="rm", fill=(24, 28, 48))
        self.base = np.maximum(self.base, np.asarray(layer, np.float32))
        yv, xv = np.mgrid[0:H, 0:W].astype(np.float32)
        vig = np.sqrt(((xv - W / 2) / (W * 0.75)) ** 2 + ((yv - H / 2) / (H * 0.7)) ** 2)
        self.vig = np.clip(1.08 - vig * 0.55, 0.35, 1)[..., None]
        self.glows = [(_glow(1100, accent, 0.30), rnd.random() * 6.28, 0.10 + rnd.random() * 0.05),
                      (_glow(1300, second, 0.34), rnd.random() * 6.28, 0.07 + rnd.random() * 0.04),
                      (_glow(800, accent, 0.18), rnd.random() * 6.28, 0.13 + rnd.random() * 0.05)]
        self.parts = [(rnd.random() * W, rnd.random() * H, 0.6 + rnd.random() * 2.2, 18 + rnd.random() * 50,
                       rnd.choice([accent, (220, 226, 240), second])) for _ in range(70)]
        self.sweep = np.linspace(0, 1, W, dtype=np.float32)

    def frame(self, i: int) -> Image.Image:
        t = i / self.fps
        img = self.base.copy()
        for g, ph, sp in self.glows:
            s = g.shape[0]
            cx = W / 2 + math.sin(t * sp * 2 + ph) * W * 0.38
            cy = H * 0.42 + math.cos(t * sp * 1.6 + ph * 1.3) * H * 0.28
            x0, y0 = int(cx - s / 2), int(cy - s / 2)
            xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + s), min(H, y0 + s)
            if xa < xb and ya < yb:
                img[ya:yb, xa:xb] += g[ya - y0:yb - y0, xa - x0:xb - x0]
        # diagonal light sweep every ~6 s
        ph = (t % 6.0) / 6.0
        if ph < 0.35:
            pos = -0.3 + ph / 0.35 * 1.6
            yv = np.linspace(0, 0.5, H, dtype=np.float32)[:, None]
            band = np.exp(-(((self.sweep[None, :] + yv) - pos) / 0.05) ** 2) * 26
            img += band[..., None]
        img *= self.vig
        out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
        d = ImageDraw.Draw(out)
        for x, y, r, v, col in self.parts:
            yy = (y - t * v) % H
            xx = x + math.sin(t * 0.8 + y) * 12
            a = 0.35 + 0.35 * math.sin(t * 2 + x)
            c = tuple(int(10 + (cc - 10) * a) for cc in col)
            d.ellipse([xx - r, yy - r, xx + r, yy + r], fill=c)
        return out


_cfg: dict = {"on": False}


def configure(on: bool, accent=(255, 196, 0), second=(64, 120, 255), watermark: str | None = None) -> None:
    _cfg.update(on=on, accent=accent, second=second, watermark=watermark)


def make(nframes: int, fps: int, seed: int = 7):
    if not _cfg["on"]:
        return None
    return DynBG(nframes, fps, _cfg["accent"], _cfg["second"], seed, _cfg.get("watermark"))
