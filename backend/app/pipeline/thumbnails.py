"""Three thumbnail concepts → AI base art → graded composite with short bold text → scored."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageStat
from sqlalchemy.orm import Session

from .. import settings_store
from ..events import emit, video_dir
from ..models import Asset, Video
from ..providers import fal, llm
from . import procedural

CONCEPT_SCHEMA = {
    "type": "object",
    "properties": {"concepts": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "object", "properties": {
        "idea": {"type": "string"},
        "image_prompt": {"type": "string", "description": "ONE clear focal subject, large in frame, dramatic "
                         "lighting, strong contrast, simple background, leave negative space on the "
                         "{side} third for text; painted illustration, no text"},
        "text": {"type": "string", "description": "0-4 punchy words, ALL CAPS, honest to the video"},
        "text_side": {"type": "string", "enum": ["left", "right"]},
        "accent": {"type": "string", "enum": ["gold", "red", "white"]}},
        "required": ["idea", "image_prompt", "text", "text_side", "accent"]}}},
    "required": ["concepts"],
}
SCORE_SCHEMA = {
    "type": "object",
    "properties": {"scores": {"type": "array", "items": {"type": "object", "properties": {
        "index": {"type": "integer"}, "focal_clarity": {"type": "number"}, "contrast": {"type": "number"},
        "mobile_readability": {"type": "number"}, "relevance": {"type": "number"}, "artifacts": {"type": "number",
        "description": "10 = no AI artefacts (bad hands, faces, garbled details)"}, "comment": {"type": "string"}},
        "required": ["index", "focal_clarity", "contrast", "mobile_readability", "relevance", "artifacts"]}}},
    "required": ["scores"],
}
ACCENT = {"gold": (255, 196, 64), "red": (230, 40, 40), "white": (255, 255, 255)}


def compose(base: Path, text: str, side: str, accent: str, out: Path) -> Path:
    img = Image.open(base).convert("RGB")
    img = img.resize((1280, int(img.height * 1280 / img.width)), Image.LANCZOS)
    img = img.crop((0, (img.height - 720) // 2, 1280, (img.height - 720) // 2 + 720)) if img.height >= 720 \
        else img.resize((1280, 720))
    img = ImageEnhance.Contrast(img).enhance(1.18)
    img = ImageEnhance.Color(img).enhance(1.12)
    img = ImageEnhance.Sharpness(img).enhance(1.3)
    # side darkening gradient for text legibility + vignette
    grad = Image.new("L", (1280, 720), 0)
    gd = ImageDraw.Draw(grad)
    for x in range(1280):
        f = (1 - x / 760) if side == "left" else (x - 520) / 760
        gd.line([(x, 0), (x, 720)], fill=int(max(0, min(1, f)) * 190))
    img = Image.composite(Image.new("RGB", img.size, (8, 6, 4)), img, grad)
    if text:
        d = ImageDraw.Draw(img)
        words = text.upper().split()
        lines = [" ".join(words[:2]), " ".join(words[2:])] if len(words) > 2 else [" ".join(words)]
        size = 150 if max(len(l) for l in lines) <= 8 else 120
        f = procedural.font("Anton-Regular.ttf", size)
        y = 360 - len(lines) * size * 0.55
        for i, line in enumerate(lines):
            x = 60 if side == "left" else 1220
            fill = ACCENT[accent] if i == len(lines) - 1 else (255, 255, 255)
            shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
            ImageDraw.Draw(shadow).text((x + 6, y + 8), line, font=f, fill=(0, 0, 0, 200),
                                        anchor="la" if side == "left" else "ra")
            img.paste(shadow.filter(ImageFilter.GaussianBlur(6)), (0, 0), shadow.filter(ImageFilter.GaussianBlur(6)))
            d.text((x, y), line, font=f, fill=fill, stroke_width=6, stroke_fill=(0, 0, 0),
                   anchor="la" if side == "left" else "ra")
            y += size * 1.05
    img.save(out, "JPEG", quality=90, optimize=True)
    q = 90
    while out.stat().st_size > 1_900_000 and q > 60:
        q -= 8
        img.save(out, "JPEG", quality=q, optimize=True)
    return out


def contrast_metric(path: Path) -> float:
    st = ImageStat.Stat(Image.open(path).convert("L"))
    return round(min(10.0, st.stddev[0] / 7.0), 2)


def run(db: Session, video: Video) -> None:
    d = video_dir(video.id) / "thumbs"
    vs = settings_store.get(db, "video")
    title = (video.metadata_ or {}).get("title") or video.working_title
    c = llm.structured(
        db, video_id=video.id, category="image", tool_name="submit_concepts", schema=CONCEPT_SCHEMA, fast=True,
        est_usd=0.05, note="thumbnail concepts",
        system="You design high-CTR but honest YouTube thumbnails for history documentaries.",
        prompt=(f"Video title: {title}\nLogline: {video.script.get('logline')}\nStyle bible: "
                f"{llm.to_json(video.script.get('style_bible'))}\nGive 3 distinct concepts (e.g. a face/figure "
                "close-up with emotion, a dramatic object or place, a striking moment). No misleading imagery."))
    thumbs = []
    for i, con in enumerate(c["concepts"]):
        prompt = (f"{con['image_prompt']}. Composition leaves empty space on the {con['text_side']} third. "
                  f"{vs['art_style']}. Bold contrast, cinematic, single focal subject, no text.")
        base = d / f"base_{i}.png"
        if not base.exists():
            fal.generate_image(db, video.id, prompt, base, width=1344, height=768, seed=500 + i)
        out = compose(base, con["text"], con["text_side"], con["accent"], d / f"thumb_{i}.jpg")
        thumbs.append({"path": str(out), "concept": con, "contrast": contrast_metric(out)})
        db.add(Asset(video_id=video.id, kind="thumbnail", path=str(out), source="fal.ai + Anton (OFL)",
                     license="AI-generated; font SIL OFL", commercial_use=True, ai_generated=True))
    sc = llm.structured(
        db, video_id=video.id, category="image", tool_name="submit_scores", schema=SCORE_SCHEMA, est_usd=0.1,
        images=[Path(t["path"]) for t in thumbs], note="thumbnail scoring",
        system="Rate YouTube thumbnails 0-10 as they appear at small mobile size. Be critical.",
        prompt=f"Video: {title}. Score images in order (index 0,1,2).")
    for s in sc["scores"]:
        if 0 <= s["index"] < len(thumbs):
            t = thumbs[s["index"]]
            t["review"] = s
            t["score"] = round(0.25 * s["focal_clarity"] + 0.15 * s["contrast"] + 0.2 * s["mobile_readability"] +
                               0.25 * s["relevance"] + 0.15 * s["artifacts"], 2)
    video.thumbnails = thumbs
    video.selected_thumbnail = max(range(len(thumbs)), key=lambda i: thumbs[i].get("score", 0))
    db.commit()
    emit(db, video, f"3 thumbnails created; auto-selected #{video.selected_thumbnail + 1} "
                    f"(score {thumbs[video.selected_thumbnail].get('score')})")
