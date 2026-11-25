"""Free player stats: the 'NBA career statistics → Regular season / Playoffs' tables on Wikipedia
(CC BY-SA; the tables are sourced from Basketball-Reference / NBA.com). Parsed from the rendered HTML so
column names come from the table itself. Markers: † = won the championship, * = led the league."""
from __future__ import annotations

import re
from html.parser import HTMLParser

import httpx

API = "https://en.wikipedia.org/w/api.php"
UA = {"User-Agent": "HoopsShorts/1.0 (self-hosted stats video tool)"}
ALIASES = {"G": "GP", "PTS": "PPG", "REB": "RPG", "AST": "APG", "STL": "SPG", "BLK": "BPG", "MIN": "MPG"}


class _P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.h = {2: "", 3: "", 4: ""}
        self.tables, self.t, self.row, self.cell = [], None, None, None
        self.cur_h, self.htxt, self.skip = None, "", 0

    def handle_starttag(self, tag, a):
        a = dict(a)
        if tag in ("h2", "h3", "h4"):
            self.cur_h, self.htxt = int(tag[1]), ""
        elif tag == "table" and "wikitable" in (a.get("class") or ""):
            self.t = {"h2": self.h[2], "h3": self.h[3], "h4": self.h[4], "rows": []}
        elif self.t is not None and tag == "tr":
            self.row = []
        elif self.t is not None and self.row is not None and tag in ("td", "th"):
            self.cell = {"tag": tag, "text": "", "colspan": int(a.get("colspan", "1") or 1),
                         "rowspan": int(a.get("rowspan", "1") or 1)}
        elif tag in ("sup", "style") and self.cell is not None:
            self.skip += 1            # footnote markers like [a]

    def handle_endtag(self, tag):
        if tag in ("h2", "h3", "h4") and self.cur_h:
            self.h[self.cur_h] = self.htxt.strip()
            for lvl in range(self.cur_h + 1, 5):
                self.h[lvl] = ""
            self.cur_h = None
        elif tag in ("sup", "style") and self.skip:
            self.skip -= 1
        elif tag in ("td", "th") and self.cell is not None:
            self.cell["text"] = re.sub(r"\s+", " ", self.cell["text"]).strip()
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.t["rows"].append(self.row)
            self.row = None
        elif tag == "table" and self.t is not None:
            self.tables.append(self.t)
            self.t = None

    def handle_data(self, data):
        if self.cur_h:
            self.htxt += data
        if self.cell is not None and not self.skip:
            self.cell["text"] += data


def _num(s: str):
    s = s.replace(",", "").replace("−", "-").strip().rstrip("*†‡#^")
    if s in ("", "—", "-", "–"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_tables(html: str, section: str = "Regular season") -> dict | None:
    p = _P()
    p.feed(html)
    cand = [t for t in p.tables
            if ("career statistics" in t["h2"].lower() or "statistics" in t["h2"].lower())
            and (t["h3"].lower().startswith(section.lower()) or t["h4"].lower().startswith(section.lower()))
            and t["rows"] and any(c["text"] in ("GP", "G", "PPG", "PTS") for c in t["rows"][0])]
    nba = [t for t in cand if "nba" in (t["h2"] + t["h3"]).lower()] or cand
    if not nba:
        return None
    t = nba[0]
    header = [ALIASES.get(c["text"].upper(), c["text"].upper().replace("YEAR", "SEASON")) for c in t["rows"][0]]
    rows, career, carry = [], None, {}
    for r in t["rows"][1:]:
        cells = []
        for c in r:
            cells += [c] * c["colspan"]
        # rowspan carry (traded mid-season: season cell spans several team rows)
        if len(cells) < len(header) and carry.get("season"):
            cells = [carry["season"]] + cells
        if cells and cells[0]["rowspan"] > 1:
            carry["season"] = dict(cells[0], rowspan=1)
        elif cells and len(cells) >= len(header):
            carry = {}
        first = cells[0]["text"] if cells else ""
        if first.lower().startswith("career") or first.lower().startswith("all-star"):
            if first.lower().startswith("career"):
                career = {h: _num(c["text"]) for h, c in zip(header, cells) if h not in ("SEASON", "TEAM")}
            continue
        if len(cells) != len(header):
            continue
        row = {"season": re.sub(r"[†*‡#^]", "", first).strip(), "champion": "†" in first}
        led = {}
        for h, c in zip(header[1:], cells[1:]):
            if h == "TEAM":
                row["team"] = c["text"]
            else:
                row[h] = _num(c["text"])
                if c["text"].strip().endswith("*"):
                    led[h] = True
        row["led_league"] = led
        rows.append(row)
    return {"columns": header, "rows": merge_traded(rows), "career": career}


def merge_traded(rows: list[dict]) -> list[dict]:
    """One row per season. Split seasons are combined with GP-weighted averages (marked as computed)."""
    out: list[dict] = []
    for r in rows:
        if out and out[-1]["season"] == r["season"]:
            a, b = out[-1], r
            ga, gb = a.get("GP") or 0, b.get("GP") or 0
            m = {"season": a["season"], "team": f"{a.get('team', '')} / {b.get('team', '')}", "GP": ga + gb,
                 "champion": a["champion"] or b["champion"], "led_league": {}, "computed": True}
            for k in a:
                if k in m or not isinstance(a.get(k), (int, float)) or isinstance(a.get(k), bool):
                    continue
                if a.get(k) is not None and b.get(k) is not None and ga + gb:
                    m[k] = round((a[k] * ga + b[k] * gb) / (ga + gb), 3 if a[k] < 1 else 1)
            out[-1] = m
        else:
            out.append(r)
    return out


def player_stats(name: str, section: str = "Regular season") -> dict | None:
    r = httpx.get(API, headers=UA, timeout=30, params={"action": "parse", "page": name, "prop": "text|revid",
                                                        "format": "json", "formatversion": 2, "redirects": 1})
    j = r.json()
    if "error" in j:
        return None
    data = parse_tables(j["parse"]["text"], section)
    if not data:
        return None
    title = j["parse"]["title"]
    data.update(player=title, url=f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                revid=j["parse"].get("revid"),
                permalink=f"https://en.wikipedia.org/w/index.php?title={title.replace(' ', '_')}&oldid={j['parse'].get('revid')}")
    return data


def as_source(stats: dict, sid: str, fetched: str) -> dict:
    """Bibliography entry: one excerpt line per season so the fact-checker can verify every number."""
    lines = []
    for r in stats["rows"]:
        nums = ", ".join(f"{k} {v}" for k, v in r.items() if k not in ("season", "team", "champion", "led_league",
                                                                         "computed") and v is not None)
        marks = (" [won championship]" if r["champion"] else "") + \
            (f" [led league in {', '.join(r['led_league'])}]" if r["led_league"] else "") + \
            (" [split season, combined]" if r.get("computed") else "")
        lines.append(f"{stats['player']} {r['season']} ({r.get('team', '')}): {nums}{marks}")
    if stats.get("career"):
        lines.append(f"{stats['player']} career regular season: " +
                     ", ".join(f"{k} {v}" for k, v in stats["career"].items() if v is not None))
    return {"id": sid, "url": stats["permalink"], "title": f"{stats['player']} — NBA career statistics (Wikipedia, "
            f"revision {stats['revid']}, fetched {fetched})", "excerpts": lines, "cited": True, "tier": 2,
            "player_stats": stats, "fetched": fetched}
