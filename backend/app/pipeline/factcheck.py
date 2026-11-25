"""Fact-checking stage.

1. Programmatic checks: every claim cites existing source ids; every quotation appears
   verbatim (normalised) in an excerpt of the cited source.
2. Independent model review of every claim against the cited excerpts.
3. Claims that remain unsupported get a fresh web-search cross-check.
Result: per-claim verdicts and a pass/fail gate used by QC.
"""
from __future__ import annotations

import re
import unicodedata

from sqlalchemy.orm import Session

from .. import settings_store
from ..events import emit
from ..models import Video
from ..providers import llm

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {"verdicts": {"type": "array", "items": {"type": "object", "properties": {
        "id": {"type": "string"},
        "verdict": {"type": "string", "enum": ["supported", "partially_supported", "unsupported", "contradicted",
                                               "needs_hedging"]},
        "reason": {"type": "string"},
        "fix": {"type": "string", "description": "Concrete correction or hedged wording, if needed"}},
        "required": ["id", "verdict", "reason"]}}},
    "required": ["verdicts"],
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", "", re.sub(r"\s+", " ", s)).strip()


def run(db: Session, video: Video) -> dict:
    script, bib = video.script, {s["id"]: s for s in video.research.get("bibliography", [])}
    claims, problems = [], []
    for si, scene in enumerate(script["scenes"]):
        for ci, c in enumerate(scene.get("claims", [])):
            cid = f"{si}.{ci}"
            missing = [x for x in c["source_ids"] if x not in bib or not bib[x].get("cited")]
            claims.append({"id": cid, "scene": si, **c, "missing_sources": missing})
            if not c["source_ids"] or len(missing) == len(c["source_ids"]):
                problems.append({"id": cid, "verdict": "unsupported", "reason": "No valid source cited.",
                                 "claim": c["claim"]})
        for q in scene.get("quotes", []) or []:
            src = bib.get(q.get("source_id", ""))
            found = src and any(_norm(q["text"]) in _norm(e) for e in src.get("excerpts", []))
            if not found:
                problems.append({"id": f"{si}.quote", "verdict": "unsupported", "claim": f'Quote: "{q["text"]}"',
                                 "reason": "Quotation not found verbatim in the cited source excerpt.",
                                 "fix": "Remove the quotation or paraphrase it with attribution."})
    # Narration with quotation marks but no registered quote is also suspicious.
    for si, scene in enumerate(script["scenes"]):
        if re.search(r"[\"“”]", scene["narration"]) and not scene.get("quotes"):
            problems.append({"id": f"{si}.quote", "verdict": "unsupported",
                             "claim": scene["narration"][:200], "reason": "Quoted words without a registered source.",
                             "fix": "Remove quotation marks or cite the verbatim source."})

    # Model review of claims vs excerpts, in batches.
    verdicts: dict[str, dict] = {}
    for i in range(0, len(claims), 60):
        batch = claims[i:i + 60]
        ctx_ids = sorted({x for c in batch for x in c["source_ids"] if x in bib})
        ctx = "\n".join(f"[{x}] {bib[x]['title']} ({bib[x]['url']}): " +
                        " | ".join(bib[x].get("excerpts", [])[:6 if x[:1] not in "PRD" else 60]) for x in ctx_ids)
        res = llm.structured(
            db, video_id=video.id, category="research", tool_name="submit_verdicts", schema=VERDICT_SCHEMA,
            est_usd=0.3, note="fact-check review",
            system=("You are a strict historical fact-checker. Judge each claim ONLY against the provided source "
                    "excerpts and the narration context. 'supported' requires the excerpts to clearly back the "
                    "specific dates, names, numbers and events. Use 'needs_hedging' when sources present it as "
                    "uncertain/disputed/legendary but the claim states it as fact."),
            prompt="SOURCES:\n" + ctx + "\n\nCLAIMS:\n" + "\n".join(
                f"{c['id']}: {c['claim']} (certainty stated: {c['certainty']}; cites {c['source_ids']}; "
                f"narration: \"{script['scenes'][c['scene']]['narration']}\")" for c in batch))
        for v in res["verdicts"]:
            verdicts[v["id"]] = v

    # Cross-check the doubtful ones with fresh searches.
    doubtful = [c for c in claims if verdicts.get(c["id"], {}).get("verdict") in ("unsupported", "partially_supported")]
    if doubtful:
        emit(db, video, f"Cross-checking {len(doubtful)} doubtful claims with new searches")
        r = llm.web_research(
            db, video_id=video.id, category="research", max_uses=min(10, 2 + len(doubtful)), est_usd=0.6,
            note="fact-check cross-check",
            system="You are a historical fact-checker. Verify each claim using reputable sources. Be precise.",
            prompt="Verify each claim; for each answer VERIFIED, FALSE, DISPUTED or UNVERIFIABLE with the correct "
                   "facts and sources:\n" + "\n".join(f"{c['id']}: {c['claim']}" for c in doubtful))
        res = llm.structured(
            db, video_id=video.id, category="research", tool_name="submit_verdicts", schema=VERDICT_SCHEMA,
            fast=True, est_usd=0.05, note="fact-check cross-check verdicts",
            system="Convert the fact-checker's findings into verdicts. VERIFIED→supported, FALSE→contradicted, "
                   "DISPUTED→needs_hedging, UNVERIFIABLE→unsupported.",
            prompt=r["text"][:30000])
        new_bib = video.research.setdefault("bibliography", [])
        known = {s["url"] for s in new_bib}
        for c in r["citations"]:
            if c["url"] not in known:
                new_bib.append({"id": f"S{len(new_bib) + 1}", "url": c["url"], "title": c["title"],
                                "excerpts": [c["cited_text"]], "cited": True, "tier": 3, "added_by": "fact-check"})
                known.add(c["url"])
        for v in res["verdicts"]:
            if v["id"] in verdicts:
                verdicts[v["id"]] = {**v, "cross_checked": True}

    for p in problems:
        verdicts[p["id"]] = {**verdicts.get(p["id"], {}), **p}
    total = max(1, len(claims))
    supported = sum(1 for c in claims if verdicts.get(c["id"], {}).get("verdict") == "supported")
    issues = [{"id": k, **v, "claim": v.get("claim") or next((c["claim"] for c in claims if c["id"] == k), "")}
              for k, v in verdicts.items() if v.get("verdict") != "supported"]
    blocking = [i for i in issues if i["verdict"] in ("unsupported", "contradicted", "needs_hedging")]
    ratio = supported / total if claims else 1.0     # pure jokes/hypotheticals make no factual claims
    q = settings_store.get(db, "quality")
    report = {"claims": len(claims), "supported": supported, "ratio": round(ratio, 3),
              "issues": issues, "blocking": len(blocking),
              "passed": ratio >= q["min_factcheck_supported_ratio"] and not any(
                  i["verdict"] == "contradicted" or i["id"].endswith("quote") for i in blocking)}
    return report


def revision_notes(report: dict) -> str:
    return "\n".join(f"- [{i['id']}] {i['verdict']}: {i.get('claim', '')} — {i.get('reason', '')}"
                     + (f" FIX: {i['fix']}" if i.get("fix") else "") for i in report["issues"])
