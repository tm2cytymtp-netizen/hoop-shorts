"""Visual asset generation: consistent AI illustrations, selective AI motion, procedural graphics."""
from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy.orm import Session

from .. import costs, settings_store
from ..events import emit, video_dir
from ..models import Asset, Video
from ..providers import cfai, fal
from . import charts, procedural

NEGATIVE = ("text, letters, captions, watermark, signature, logo, modern objects, anachronism, photograph, "
            "photorealistic photo, deformed hands, extra fingers, duplicated faces, blurry")
LEAD_PAD = 0.0    # narration starts on the cut (no dead air)
TAIL_PAD = 0.35   # must be >= transition_s / 2


def breath(sc) -> float:
    """Gap after a line: a short breath at a sentence end, almost none mid-sentence, a beat before a question."""
    n = (sc.narration or "").rstrip()
    if (sc.alignment or {}).get("continues"):
        return 0.0                                 # mid-sentence cut: the take continues seamlessly
    if n.endswith("?"):
        return 0.32
    if n.endswith((".", "!")):
        return 0.2
    return 0.06


def scene_seconds(sc, transition_s: float) -> float:
    if (sc.alignment or {}).get("silent"):          # text-only beat: exactly the hold time
        return sc.audio_duration + transition_s
    return LEAD_PAD + sc.audio_duration + breath(sc) + transition_s + float(sc.visual.get("end_hold", 0))


def build_prompt(db: Session, video: Video, visual: dict) -> str:
    vs = settings_store.get(db, "video")
    bible = video.script.get("style_bible") or {}
    prompt = visual.get("prompt") or ""
    refs = []
    for c in bible.get("characters", []) + bible.get("locations", []):
        if c["name"] and re.search(rf"\b{re.escape(c['name'].split()[0])}", prompt, re.I):
            refs.append(f"{c['name']}: {c['look']}")
    parts = [prompt]
    if refs:
        parts.append("Consistent depiction — " + "; ".join(refs))
    parts.append(bible.get("art_direction", ""))
    style = vs["art_style"]
    if video.kind == "short":
        style = style.replace("16:9 widescreen composition", "") + ", vertical 9:16 composition, subject centred"
    parts.append(style)
    parts.append("fictional generic characters (not real people), no real team logos, no text, no letters")
    return ". ".join(p.strip().rstrip(".") for p in parts if p)


def _soften(prompt: str) -> str:
    # Retry wording for safety-filter hits: depict battle aftermath/violence without gore.
    return re.sub(r"\b(blood|bloody|gore|corpses?|dead bodies|severed|massacre|beheaded)\b", "", prompt, flags=re.I) \
        + ". Dramatic but not graphic; no gore."


AI_TYPES = ("meme", "reaction", "illustration", "ranking")


def _gen_image(db: Session, video: Video, sc, prompt: str, dest: Path, square: bool) -> dict:
    ai = settings_store.get(db, "ai")
    gen = cfai.generate_image if ai.get("image_provider", "cloudflare") == "cloudflare" else fal.generate_image
    size = {"width": 1024, "height": 1024} if square else settings_store.get(db, "shorts")["image_size"]
    last = None
    for attempt in range(3):
        try:
            return gen(db, video.id, prompt if attempt == 0 else _soften(prompt), dest,
                       seed=10_000 + video.id * 97 + sc.idx + attempt, negative=NEGATIVE, **size)
        except costs.BudgetExceeded:
            raise
        except (cfai.CFError, fal.FalError) as e:
            last = e
            emit(db, video, f"Image retry for scene {sc.idx}: {e}", level="warn")
    raise RuntimeError(f"Image generation failed for scene {sc.idx}: {last}")


def generate_images(db: Session, video: Video) -> None:
    """Build each scene's still: AI art for memes/reactions, licensed photos, text cards."""
    from ..models import Clip
    from ..providers import commons
    from . import cards
    d = video_dir(video.id) / "images"
    for sc in video.scenes:
        v = sc.visual
        t = v.get("type")
        if sc.image_path and Path(sc.image_path).exists():
            continue
        card = d / f"card_{sc.idx:03d}.png"
        if t in AI_TYPES and v.get("image_prompt"):
            raw = d / f"ai_{sc.idx:03d}.png"
            if not raw.exists():
                res = _gen_image(db, video, sc, build_prompt(db, video, {"prompt": v["image_prompt"]}), raw,
                                 square=(t == "meme"))
                db.add(Asset(video_id=video.id, kind="image", path=res["path"], source=str(res["model"]),
                             license="AI-generated (FLUX.1 schnell: Apache-2.0)" if "schnell" in str(res["model"])
                             else "AI-generated via fal.ai", commercial_use=True, ai_generated=True,
                             meta={"prompt": v["image_prompt"]}))
                db.commit()
            if t == "meme":
                cards.meme_card(str(raw), v.get("top_text", ""), v.get("bottom_text", ""), card)
            elif t == "reaction":
                cards.reaction_card(str(raw), v.get("caption", "") or v.get("top_text", ""), card)
            else:
                card = raw            # illustration / ranking background
            sc.image_path = str(card)
        elif t == "photo":
            ph = commons.find_photo(v.get("photo_query", ""), d / f"photo_{sc.idx:03d}.jpg")
            if ph:
                cards.photo_card(ph["path"], v.get("caption", ""), ph["credit"], card)
                db.add(Asset(video_id=video.id, kind="photo", path=ph["path"], source=ph["credit"],
                             license=f"{ph['license']} (Wikimedia Commons, attribution shown on screen)",
                             commercial_use=True, ai_generated=False, meta={"page": ph["page"]}))
                sc.visual = {**v, "credit": ph["credit"]}
            else:
                emit(db, video, f"No freely licensed photo for '{v.get('photo_query')}'; using a text card", level="warn")
                cards.big_text_card(v.get("caption") or v.get("photo_query", ""), card)
                sc.visual = {**v, "type": "big_text"}
            sc.image_path = str(card)
        elif t == "big_text" or (t in AI_TYPES and not v.get("image_prompt")):
            cards.big_text_card(v.get("text") or v.get("top_text") or v.get("caption") or "", card)
            sc.visual = {**v, "type": "big_text"} if t != "ranking" else v
            if t != "ranking":
                sc.image_path = str(card)
        elif t == "clip":
            c = db.get(Clip, int((v.get("clip") or {}).get("clip_id") or 0))
            if not (c and c.attested_by_user and Path(c.path).exists()):
                emit(db, video, f"Scene {sc.idx}: clip unavailable; using a text card", level="warn")
                cards.big_text_card(v.get("caption") or "…", card)
                sc.visual = {**v, "type": "big_text"}
                sc.image_path = str(card)
            else:
                sc.motion_path = c.path
                db.add(Asset(video_id=video.id, kind="video", path=c.path, source=c.source, license=c.license,
                             commercial_use=True, ai_generated=False, meta={"clip_id": c.id, "user_attested": True}))
        db.commit()
    emit(db, video, "Visuals ready")


def render_procedural(db: Session, video: Video, transition_s: float, fps: int) -> None:
    """Animated data cards. Scoreboard numbers are taken from the data source, never from the script."""
    from . import cards
    d = video_dir(video.id) / "clips"
    procedural.set_canvas(1080, 1920)
    bib = {s["id"]: s for s in (video.research or {}).get("bibliography", [])}
    reveal_state: dict = {}
    photo_cache = _player_photos(db, video, bib)
    from . import dynbg
    vset = settings_store.get(db, "video")
    look = (video.script or {}).get("look") or {}
    prim, sec = charts.team_colors(look.get("team", ""))
    dynbg.configure(bool(vset.get("dynamic_bg", True)), accent=tuple(look.get("accent") or sec),
                    second=tuple(look.get("second") or prim), watermark=look.get("watermark"))
    for sc in video.scenes:
        v = sc.visual
        t = v.get("type")
        if t in charts.CHART_TYPES:
            out = d / f"proc_{sc.idx:03d}.mp4"
            if not out.exists():
                _render_chart(sc, bib, scene_seconds(sc, transition_s), out, fps, reveal_state,
                              footer=settings_store.get(db, "video").get("show_data_footer", False),
                              photos=photo_cache)
            sc.motion_path = str(out)
            db.add(Asset(video_id=video.id, kind="graphic", path=str(out), source="Chart rendered by this app from "
                         "cited data", license="Original graphic", commercial_use=True, ai_generated=False))
            db.commit()
            continue
        if t not in ("stat_card", "scoreboard", "ranking"):
            continue
        out = d / f"proc_{sc.idx:03d}.mp4"
        if out.exists():
            sc.motion_path = str(out)
            continue
        dur = scene_seconds(sc, transition_s)
        if t == "stat_card":
            st = v.get("stat") or {}
            srcs = [bib[i] for i in st.get("source_ids", []) if i in bib]
            label = "; ".join(s["title"].split(" (")[0] for s in srcs[:2]) or "see description"
            cards.render_stat_card({**st, "source": label}, dur, out, fps)
        elif t == "scoreboard":
            sid = (v.get("scoreboard") or {}).get("game_source_id", "")
            g = (bib.get(sid) or {}).get("data")
            if not g:
                raise RuntimeError(f"Scene {sc.idx}: scoreboard references '{sid}', which is not real game data.")
            cards.render_scoreboard({"headline": (v.get("scoreboard") or {}).get("headline", ""), "home": g["home"],
                                     "away": g["away"], "home_score": g["home_score"], "away_score": g["away_score"],
                                     "date": g["date"], "source": "BALLDONTLIE NBA API"}, dur, out, fps)
        else:
            cards.render_ranking(v.get("ranking") or {}, sc.image_path or None, dur, out, fps)
        sc.motion_path = str(out)
        db.add(Asset(video_id=video.id, kind="graphic", path=str(out), source="Rendered by this app (OFL fonts)",
                     license="Original graphic", commercial_use=True, ai_generated=False))
        db.commit()


def animate(db: Session, video: Video) -> None:
    """AI image-to-video for the scenes marked 'animated', within the per-video request cap."""
    d = video_dir(video.id) / "motion"
    if settings_store.get(db, "ai").get("image_provider") != "fal" or not __import__("app.config", fromlist=["env"]).env.fal_key:
        # Free mode: no image-to-video service; animated scenes use camera moves on the still instead.
        for s in video.scenes:
            if s.visual.get("type") == "animated":
                s.visual = {**s.visual, "type": "illustration"}
        db.commit()
        return
    cap = settings_store.get(db, "budget")["max_video_requests_per_video"]
    if video.kind == "short":
        cap = min(cap, int(settings_store.get(db, "shorts")["animated_scenes"]))
    used = costs.count(db, video.id, "video")
    todo = [s for s in video.scenes if s.visual.get("type") == "animated"
            and not (s.motion_path and Path(s.motion_path).exists())]
    if len(todo) > cap - used:
        # Prioritise the climax and hook, demote the rest to camera-move illustrations.
        rank = {"climax": 0, "hook": 1, "story": 2, "details": 3, "introduction": 4, "conclusion": 5, "ending": 6}
        todo.sort(key=lambda s: rank.get(s.section, 9))
        for s in todo[max(0, cap - used):]:
            s.visual = {**s.visual, "type": "illustration", "demoted": "video request cap"}
        todo = todo[:max(0, cap - used)]
        db.commit()
    emit(db, video, f"Animating {len(todo)} scenes with image-to-video")
    for sc in todo:
        motion = sc.visual.get("motion_prompt") or "subtle natural motion, drifting smoke and dust, slow camera push"
        try:
            res = fal.animate_image(db, video.id, Path(sc.image_path), sc.visual.get("image_url"),
                                    motion + ", cinematic, smooth, stable", d / f"scene_{sc.idx:03d}.mp4")
        except costs.BudgetExceeded:
            raise
        except fal.FalError as e:
            emit(db, video, f"Animation failed for scene {sc.idx}, using camera move instead: {e}", level="warn")
            sc.visual = {**sc.visual, "type": "illustration", "demoted": str(e)[:200]}
            db.commit()
            continue
        sc.motion_path = res["path"]
        db.add(Asset(video_id=video.id, kind="video", path=res["path"], source=f"fal.ai {res['model']}",
                     license="AI-generated via fal.ai (commercial use per model licence)", commercial_use=True,
                     ai_generated=True, meta={"prompt": motion}))
        db.commit()


class ChartDataError(RuntimeError):
    pass


def _src_label(src: dict) -> str:
    if src.get("player_stats"):
        return f"Data: Wikipedia NBA career statistics · fetched {src.get('fetched', '')}"
    return "Data: " + src["title"].split(" (")[0]


def _player_photos(db, video, bib: dict) -> dict:
    """Freely licensed photos (Wikimedia Commons) for every player the video shows: P# sources, L# leaderboard
    rows and hype_text `players`. Also fetches licensed b-roll for hype_text `broll` queries. Keys: player name,
    plus "broll:<query>" for clips. Every file used is recorded as an Asset with its credit."""
    from ..providers import commons
    out: dict = {}
    d = video_dir(video.id) / "images"
    names: list[str] = []
    for sid, src in bib.items():
        if src.get("player_stats") and not src.get("no_photo"):   # no_photo: derived/joke figures, not a person
            names.append(src["player_stats"]["player"])
        for r in src.get("leaders") or []:
            names.append(r["player"])
    brolls: list[str] = []
    for sc in video.scenes:
        c = (sc.visual or {}).get("chart") or {}
        for p in c.get("players") or []:
            names.append(p["name"] if isinstance(p, dict) else p)
        if c.get("broll"):
            brolls.append(c["broll"])
    for i, name in enumerate(dict.fromkeys(names)):
        try:
            ph = commons.find_photo(name, d / f"player_{i}.jpg")
        except Exception:
            ph = None
        if ph:
            out[name] = ph["path"]
            db.add(Asset(video_id=video.id, kind="photo", path=ph["path"], source=ph["credit"],
                         license=f"{ph['license']} (Wikimedia Commons; credited in description)", commercial_use=True,
                         ai_generated=False, meta={"page": ph["page"], "player": name}))
    for j, q in enumerate(dict.fromkeys(brolls)):
        try:
            cl = commons.find_clip(q, d / f"broll_{j}.video")
        except Exception:
            cl = None
        if cl:
            out[f"broll:{q}"] = cl["path"]
            db.add(Asset(video_id=video.id, kind="clip", path=cl["path"], source=cl["credit"],
                         license=f"{cl['license']} (Wikimedia Commons; credited in description)", commercial_use=True,
                         ai_generated=False, meta={"page": cl["page"], "query": q}))
    db.commit()
    return out


def _team_of(bib: dict, name: str) -> str:
    for src in bib.values():
        st = src.get("player_stats")
        if st and st.get("player") == name:
            return st.get("team") or ""
        for r in src.get("leaders") or []:
            if r["player"] == name:
                return r.get("team", "")
    return ""


def _season_row(st: dict, label: str | None) -> dict | None:
    if not label or label == "?":
        return None
    if label.lower() == "career":
        return st.get("career") or None
    norm = label.replace("-", "–")
    return next((r for r in st["rows"] if r["season"] == norm), None)


def _render_chart(sc, bib: dict, dur: float, out: Path, fps: int, reveal_state: dict, footer: bool = False,
                  photos: dict | None = None) -> None:
    """Every number drawn here is read from a cited data source — never from the script."""
    from . import charts
    photos = photos or {}
    v = sc.visual
    c = v.get("chart") or {}
    t = v["type"]
    _lbl = _src_label
    globals()["_src_label"] = (lambda src: _lbl(src)) if footer else (lambda src: "")
    try:
        _render_chart_inner(sc, bib, dur, out, fps, reveal_state, photos, charts, v, c, t)
    finally:
        globals()["_src_label"] = _lbl


def _render_chart_inner(sc, bib, dur, out, fps, reveal_state, photos, charts, v, c, t) -> None:
    if t == "comeback_card":
        src = bib.get(c.get("source_id", ""))
        if not src or not src.get("player_stats"):
            raise ChartDataError(f"Scene {sc.idx}: comeback_card needs a P# player-stats source")
        st = src["player_stats"]
        stats = (c.get("stats") or ["PPG", "FG%", "RPG"])[:3]
        before = _season_row(st, c.get("before_season"))
        after = _season_row(st, c.get("after_season"))
        if before is None:
            raise ChartDataError(f"Scene {sc.idx}: season '{c.get('before_season')}' not in {st['player']}'s data")
        if c.get("after_season") not in (None, "?") and after is None:
            raise ChartDataError(f"Scene {sc.idx}: season '{c.get('after_season')}' not in {st['player']}'s data")
        team = c.get("team") or (before.get("team") if isinstance(before, dict) else "") or st["rows"][-1].get("team", "")
        charts.render_comeback_card({
            "name": st["player"], "team": team, "photo": photos.get(st["player"]),
            "subtitle": c.get("subtitle", team), "injury": c.get("event", ""), "when": c.get("when", ""),
            "tone": c.get("tone", "injury"), "before_head": c.get("before_head", "BEFORE"),
            "after_head": c.get("after_head", "AFTER"),
            "year": c.get("year"), "timeline": c.get("timeline", []), "stats": stats,
            "before": {"label": c.get("before_label") or c.get("before_season"), "stats": {k: before.get(k) for k in stats}},
            "after": {"label": c.get("after_label") or c.get("after_season") or "after return",
                      "stats": {k: (after.get(k) if after else "?") for k in stats}},
            "source": _src_label(src)}, dur, out, fps)
        return
    if t == "slope":
        items = []
        stat = c.get("stat", "PPG")
        for it in c.get("items", [])[:6]:
            src = bib.get(it.get("source_id", ""))
            if not src or not src.get("player_stats"):
                raise ChartDataError(f"Scene {sc.idx}: slope item needs a P# source ({it})")
            st = src["player_stats"]
            b, a = _season_row(st, it.get("before_season")), _season_row(st, it.get("after_season"))
            if not b or not a or b.get(stat) is None or a.get(stat) is None:
                raise ChartDataError(f"Scene {sc.idx}: missing {stat} for {st['player']} {it}")
            items.append({"name": st["player"], "team": a.get("team", ""), "before": b[stat], "after": a[stat],
                          "photo": photos.get(st["player"])})
        charts.render_slope({"title": c.get("title") or stat, "subtitle": c.get("subtitle", ""),
                             "left_label": c.get("before_label", "BEFORE"), "right_label": c.get("after_label", "AFTER"),
                             "source": ""}, items, dur, out, fps)
        return
    if t == "season_bars":
        src = bib.get(c.get("source_id", ""))
        if not src or not src.get("player_stats"):
            raise ChartDataError(f"Scene {sc.idx}: season_bars needs a P# player-stats source, got {c.get('source_id')}")
        st = src["player_stats"]
        stat = c.get("stat", "PPG")
        rows = [r for r in st["rows"] if r.get(stat) is not None]
        if not rows:
            raise ChartDataError(f"Scene {sc.idx}: no '{stat}' column for {st['player']}")
        labels = [r["season"] for r in rows]
        key = (c.get("source_id"), stat)
        r_from = reveal_state.get(key, -1) + 1
        r_to = labels.index(c["reveal_to_season"]) if c.get("reveal_to_season") in labels else len(rows) - 1
        r_to = max(r_to, min(r_from, len(rows) - 1))
        reveal_state[key] = r_to
        hi = [h for h in c.get("highlight", []) if h in labels]
        led = [r["season"] for r in rows if stat in (r.get("led_league") or {})]
        for r in rows:
            r["note"] = "LED NBA" if stat in (r.get("led_league") or {}) else ""
        avg = (st.get("career") or {}).get(stat) if c.get("show_career_average") else None
        legend = "● = won the championship" if any(r["champion"] for r in rows) else ""
        charts.render_season_bars({"title": c.get("title") or f"{st['player']}: {stat}",
                                   "subtitle": c.get("subtitle") or f"Every regular season, {labels[0]} to {labels[-1]}",
                                   "stat": stat, "reveal_from": 0 if r_from > r_to else r_from, "reveal_to": r_to,
                                   "highlight": hi or [], "show_average": avg, "legend": legend,
                                   "source": _src_label(src)}, rows, dur, out, fps)
        sc.visual = {**v, "resolved": {"seasons": labels[: r_to + 1], "led": led}}
    elif t == "line_compare":
        series, label_src = {}, None
        stat = c.get("stat", "PPG")
        for sid in c.get("source_ids", [])[:4]:
            src = bib.get(sid)
            if src and src.get("player_stats"):
                series[src["player_stats"]["player"]] = [r.get(stat) for r in src["player_stats"]["rows"]]
                label_src = src
        if len(series) < 2:
            raise ChartDataError(f"Scene {sc.idx}: line_compare needs 2+ P# sources")
        charts.render_line_compare({"title": c.get("title") or f"{stat} by season", "subtitle": c.get("subtitle", ""),
                                    "source": "Data: Wikipedia NBA career statistics"}, series, dur, out, fps)
    elif t == "big_number":
        src = bib.get(c.get("source_id", ""))
        stat = c.get("stat", "PPG")
        val = None
        if src and src.get("player_stats"):
            st = src["player_stats"]
            if (c.get("season") or "career").lower() == "career":
                val = (st.get("career") or {}).get(stat)
            else:
                row = next((r for r in st["rows"] if r["season"] == c.get("season")), None)
                val = row.get(stat) if row else None
        elif src and src.get("recap"):
            row = next((l for l in src["recap"]["lines"] if l["player"].lower() in (c.get("title", "") +
                        c.get("label", "")).lower()), src["recap"]["lines"][0])
            val = row.get(stat.lower())
        if val is None:
            raise ChartDataError(f"Scene {sc.idx}: big_number value not found in data ({c})")
        dec = 3 if val < 1 else (1 if stat.upper() in ("PPG", "RPG", "APG", "SPG", "BPG", "MPG") else 0)
        who = (src.get("player_stats") or {}).get("player") if src else None
        charts.render_big_number({"title": c.get("title", ""), "value": val, "decimals": dec,
                                  "label": c.get("label") or stat, "context": c.get("context", ""),
                                  "source": _src_label(src), "photo": photos.get(who) if who else None,
                                  "team": (src.get("player_stats") or {}).get("team", "") if src else ""},
                                 dur, out, fps)
    elif t == "hype_text":
        faces = []
        for p in c.get("players") or []:
            nm = p["name"] if isinstance(p, dict) else p
            tm = (p.get("team") if isinstance(p, dict) else None) or _team_of(bib, nm)
            faces.append((nm, tm, photos.get(nm)))
        charts.render_hype_text({"text": v.get("text", ""), "kicker": v.get("kicker", ""),
                                 "accent": c.get("accent"), "faces": faces,
                                 "broll": photos.get(f"broll:{c['broll']}") if c.get("broll") else None},
                                dur, out, fps)
    elif t == "all_time_rank":
        src = bib.get(c.get("source_id", ""))
        if not src or not src.get("leaders"):
            raise ChartDataError(f"Scene {sc.idx}: all_time_rank needs a leaderboard source (L#), got {c.get('source_id')}")
        hl = c.get("highlight") or {}
        rows = [{**r, "highlight": r["player"] == hl.get("player") and r["season"] == hl.get("season"),
                 "photo": photos.get(r["player"])}
                for r in src["leaders"][: int(c.get("top", 8))]]
        charts.render_all_time_rank({"title": c.get("title", ""), "subtitle": c.get("subtitle", ""),
                                     "note": c.get("note", ""), "decimals": c.get("decimals", 1)}, rows, dur, out, fps)
    elif t in ("head_to_head", "tally"):
        sts = []
        for sid in c.get("source_ids", [])[:5]:
            src = bib.get(sid)
            if not src or not src.get("player_stats") or not (src["player_stats"].get("career") or c.get("season")):
                raise ChartDataError(f"Scene {sc.idx}: {t} needs P# sources with career totals, got {sid}")
            sts.append(src["player_stats"])
        players = [{"name": st["player"], "team": st.get("team") or st["rows"][-1].get("team", ""),
                    "photo": photos.get(st["player"])} for st in sts]

        def cat(stat, loss=None):
            vals, rank, disp = [], [], []
            for st in sts:
                car = _season_row(st, c["season"]) if c.get("season") else st["career"]   # one season or career
                if not car or car.get(stat) is None:
                    raise ChartDataError(f"Scene {sc.idx}: '{stat}' missing for {st['player']}")
                w = car[stat]
                vals.append(w)
                if loss:
                    l = car.get(loss, 0)
                    rank.append(w / (w + l) if (w + l) else 0)
                    disp.append(f"{w}-{l}")
                else:
                    rank.append(w)
                    disp.append(None)
            return vals, rank, disp

        if t == "head_to_head":
            stat, loss = c.get("stat", "PPG"), c.get("loss_stat")
            vals, rank, disp = cat(stat, loss)
            for i, p in enumerate(players):
                p.update(value=vals[i], rank=rank[i], display=disp[i],
                         losses=sts[i]["career"].get(loss) if loss else None)
            dec = c.get("decimals", 1 if any(isinstance(x, float) and x != int(x) for x in vals) else 0)
            charts.render_head_to_head({"title": c.get("title") or stat, "subtitle": c.get("subtitle", ""),
                                        "decimals": dec, "note": c.get("note", "")}, players, dur, out, fps)
        else:
            cats = []
            for k in c.get("categories", []):
                vals, rank, disp = cat(k["stat"], k.get("loss_stat"))
                dec = k.get("decimals", 1 if any(isinstance(x, float) and x != int(x) for x in vals) else 0)
                cats.append({"label": k.get("label") or k["stat"], "values": vals, "rank": rank,
                             "display": disp if k.get("loss_stat") else None, "decimals": dec})
            charts.render_tally({"title": c.get("title", "THE SCORECARD"), "subtitle": c.get("subtitle", "")},
                                players, cats, dur, out, fps)
    elif t == "leaderboard":
        src = bib.get(c.get("source_id", "R1"))
        if not src or not src.get("recap"):
            raise ChartDataError(f"Scene {sc.idx}: leaderboard needs recap data (BALLDONTLIE ALL-STAR plan)")
        stat = (c.get("stat") or "pts").lower()
        lines = sorted(src["recap"]["lines"], key=lambda l: -(l.get(stat) or 0))[:8]
        rows = [{"season": l["player"].split()[-1][:11], "VAL": float(l.get(stat) or 0), "champion": False,
                 "note": l["team"]} for l in lines]
        charts.render_season_bars({"title": c.get("title") or f"Last night's top {stat.upper()}",
                                   "subtitle": src["recap"]["date"], "stat": "VAL", "highlight": [rows[0]["season"]], "decimals": 0,
                                   "source": _src_label(src)}, rows, dur, out, fps)
