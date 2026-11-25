"""BALLDONTLIE NBA API — free account key (app.balldontlie.io). Free tier: teams, players, games
(scores), 5 requests/minute. Every number used in a video is stored with source + fetch date."""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone

import httpx

from ..config import env

BASES = ["https://api.balldontlie.io/v1", "https://api.balldontlie.io/nba/v1"]
_last = [0.0]


class BDLError(Exception):
    pass


def _get(path: str, params: dict) -> dict:
    if not env.balldontlie_api_key:
        raise BDLError("BALLDONTLIE_API_KEY not configured (free key at app.balldontlie.io).")
    for base in BASES:
        for attempt in range(4):
            wait = 12.5 - (time.time() - _last[0])        # free tier: 5 requests/minute
            if wait > 0:
                time.sleep(wait)
            _last[0] = time.time()
            r = httpx.get(f"{base}/{path}", params=params, headers={"Authorization": env.balldontlie_api_key},
                          timeout=30)
            if r.status_code == 429:
                time.sleep(20)
                continue
            break
        if r.status_code == 404:
            continue
        if r.status_code >= 400:
            raise BDLError(f"balldontlie {r.status_code}: {r.text[:200]}")
        return r.json()
    raise BDLError("balldontlie endpoint not found")


def recent_games(days: int = 2) -> list[dict]:
    today = datetime.now(timezone.utc).date()
    dates = [(today - timedelta(days=i)).isoformat() for i in range(days, -1, -1)]
    res = _get("games", {"dates[]": dates, "per_page": 100})
    out = []
    for g in res.get("data", []):
        out.append({
            "id": g["id"], "date": g["date"][:10], "status": g.get("status", ""),
            "home": g["home_team"]["full_name"], "home_abbr": g["home_team"]["abbreviation"],
            "away": g["visitor_team"]["full_name"], "away_abbr": g["visitor_team"]["abbreviation"],
            "home_score": g.get("home_team_score"), "away_score": g.get("visitor_team_score"),
            "postseason": g.get("postseason", False),
        })
    return out


def final_games(days: int = 2) -> list[dict]:
    return [g for g in recent_games(days) if str(g["status"]).lower().startswith("final") and g["home_score"]]


def player_lines(day: str) -> list[dict]:
    """Per-game player stats for one date — needs the ALL-STAR plan ($9.99/mo)."""
    out, cursor = [], None
    for _ in range(10):
        params = {"dates[]": [day], "per_page": 100}
        if cursor:
            params["cursor"] = cursor
        res = _get("stats", params)
        for s in res.get("data", []):
            mins = str(s.get("min") or "0")
            if mins in ("0", "00", "", "0:00"):
                continue
            p, t = s["player"], s["team"]
            out.append({"player": f"{p['first_name']} {p['last_name']}", "team": t["abbreviation"],
                        "pts": s.get("pts"), "reb": s.get("reb"), "ast": s.get("ast"), "stl": s.get("stl"),
                        "blk": s.get("blk"), "fg3m": s.get("fg3m"), "min": mins, "game_id": s["game"]["id"]})
        cursor = (res.get("meta") or {}).get("next_cursor")
        if not cursor:
            break
    return out


def recap_source(day: str, lines: list[dict], sid: str = "R1") -> dict:
    top = sorted(lines, key=lambda x: -(x["pts"] or 0))[:12]
    return {"id": sid, "url": f"https://www.balldontlie.io/#stats-{day}", "cited": True, "tier": 2,
            "title": f"BALLDONTLIE NBA API — player game stats {day}",
            "excerpts": [f"{day} {l['player']} ({l['team']}): {l['pts']} pts, {l['reb']} reb, {l['ast']} ast, "
                         f"{l['fg3m']} 3PM in {l['min']} min" for l in top], "recap": {"date": day, "lines": top}}


def as_source(g: dict, fetched: date | None = None) -> dict:
    """A bibliography entry whose excerpt is the exact data used."""
    fetched = fetched or datetime.now(timezone.utc).date()
    line = (f"{g['date']}: {g['away']} {g['away_score']} at {g['home']} {g['home_score']} "
            f"({'playoffs' if g['postseason'] else 'regular season'}, status {g['status']})")
    return {"url": f"https://www.balldontlie.io/#game-{g['id']}", "title": f"BALLDONTLIE NBA API — game {g['id']} "
            f"(fetched {fetched.isoformat()})", "excerpts": [line], "cited": True, "tier": 2, "data": g}
