"""Title, description (with chapters, sources and AI disclosure), tags, hashtags, playlist."""
from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from ..models import Video
from ..providers import llm

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "<= 60 chars. Short, intriguing, funny, never misleading"},
        "alt_titles": {"type": "array", "items": {"type": "string"}, "description": "2 more title variations"},
        "platform_captions": {"type": "object", "properties": {
            "tiktok": {"type": "string"}, "instagram": {"type": "string"}, "facebook": {"type": "string"}},
            "description": "Native caption for each platform (hashtags included, platform-appropriate length)"},
        "summary": {"type": "string", "description": "2-3 short paragraphs for the description; first 150 "
                    "characters must hook and include the main keyword"},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "10-20 tags, total < 400 chars"},
        "hashtags": {"type": "array", "items": {"type": "string"}, "description": "3 hashtags with #"},
        "playlist": {"type": "string", "description": "Playlist name: the content category, e.g. 'Ancient Rome'"},
    },
    "required": ["title", "alt_titles", "summary", "keywords", "tags", "hashtags", "playlist"],
}


def _ts(s: float) -> str:
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def build_description(summary: str, chapters: list[dict], bibliography: list[dict], hashtags: list[str],
                      music_credits: list[str], synthetic: bool) -> str:
    parts = [summary.strip(), ""]
    if len(chapters) >= 3:
        parts += ["CHAPTERS"] + [f"{_ts(c['start'])} {c['title']}" for c in chapters] + [""]
    if synthetic:
        parts += ["Visuals in this documentary are artistic reconstructions created with AI tools and "
                  "procedural maps; they are not historical photographs or archival footage. Narration is "
                  "AI-generated from a researched, fact-checked script.", ""]
    srcs = [s for s in bibliography if s.get("cited")]
    srcs.sort(key=lambda s: s.get("tier", 3))
    if srcs:
        parts.append("SOURCES & FURTHER READING")
        for s in srcs:
            line = f"• {s['title'][:90]} — {s['url']}"
            if len("\n".join(parts + [line]).encode()) > 4300:
                parts.append("• (full bibliography available on request)")
                break
            parts.append(line)
        parts.append("")
    if music_credits:
        parts += ["MUSIC"] + [f"• {m}" for m in music_credits] + [""]
    parts.append(" ".join(hashtags[:3]))
    text = "\n".join(parts).replace("<", "‹").replace(">", "›")
    return text.encode()[:5000].decode(errors="ignore")


def run(db: Session, video: Video, music_credits: list[str]) -> dict:
    res = llm.structured(
        db, video_id=video.id, category="script", tool_name="submit_metadata", schema=SCHEMA, fast=True,
        est_usd=0.05, note="metadata",
        system=("You write metadata for a basketball meme/Shorts channel: short, funny, searchable, honest. "
                "Never claim something the video doesn't show; no fake news framing; no clickbait lies."),
        prompt=(f"Working title: {video.working_title}\nLogline: {video.script.get('logline')}\n"
                f"Category: {video.topic.category if video.topic else ''}\nScript:\n" +
                "\n".join(s.narration for s in video.scenes)[:20000]))
    tags, total = [], 0
    for t in res["tags"]:
        t = t.replace("<", "").replace(">", "").strip()
        cost = len(t) + (2 if " " in t else 0) + 1
        if t and total + cost <= 480:
            tags.append(t)
            total += cost
    md = video.metadata_ or {}
    synthetic = True   # AI illustrations of realistic-looking historical scenes → disclose
    if video.kind == "short":
        tags_h = [h for h in res["hashtags"] if h.lower() not in ("#shorts", "#nba")][:2] + ["#NBA", "#Shorts"]
        srcs = sorted([s for s in video.research.get("bibliography", []) if s.get("cited")],
                      key=lambda s: s.get("tier", 3))[:3]
        q = video.script.get("engagement_question") or ""
        desc = "\n".join([res["summary"].split("\n")[0].strip()] + ([q] if q else []) +
                         ([""] + [" ".join(x for x in (
                             "Cartoon images feature fictional players." if any(
                                 sc.visual.get("type") in ("meme", "reaction", "illustration") for sc in video.scenes)
                             else "", "Stats and facts: sources below." if srcs else "") if x)]) +
                         (["", "Sources:"] + [f"• {s['url']}" for s in srcs] if srcs else []) +
                         ([""] + ["Credits:"] + [f"• {m}" for m in music_credits] if music_credits else []) +
                         ["", " ".join(tags_h)]).replace("<", "‹").replace(">", "›")
        res["hashtags"] = tags_h
    else:
        desc = build_description(res["summary"], md.get("chapters", []), video.research.get("bibliography", []),
                                 res["hashtags"], music_credits, synthetic)
    md.update({"title": res["title"][:100].replace("<", "").replace(">", ""), "alt_titles": res["alt_titles"][:2],
               "platform_captions": res.get("platform_captions", {}),
               "trending_sound_fit": bool(video.script.get("trending_sound_fit")),
               "description": desc, "tags": tags, "keywords": res["keywords"], "hashtags": res["hashtags"],
               "playlist": res["playlist"], "category_id": "17",  # Sports
               "contains_synthetic_media": synthetic, "made_for_kids": False})
    video.metadata_ = md
    flag_modified(video, "metadata_")
    db.commit()
    return md
