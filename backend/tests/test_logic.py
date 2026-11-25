"""Logic tests for research → script → fact-check (with revision loop), budget pause and scheduling.
Paid APIs are replaced with deterministic stand-ins; the orchestration code under test is real.

Run:  cd backend && python -m pytest -q tests/test_logic.py
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="hc_logic_"))
os.environ["DATABASE_URL"] = f"sqlite:///{TMP / 't.db'}"
os.environ["DATA_DIR"] = str(TMP / "data")

from app import costs, orchestrator, settings_store  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import CostEntry, Job, Topic, Video  # noqa: E402
from app.pipeline import factcheck, narration, publish  # noqa: E402
from app.providers import llm  # noqa: E402

CALLS: list[str] = []


def fake_web_research(db, *, video_id, category, system, prompt, max_uses=None, est_usd=1.0, note=""):
    costs.guard(db, video_id, category, est_usd)
    costs.record(db, video_id, category, "anthropic:test", 1000, "tokens", 0.05, note)
    CALLS.append(note)
    return {"text": "Hannibal won at Cannae in 216 BC [cited].",
            "citations": [{"url": "https://uni.edu/cannae", "title": "Cannae — University", "cited_text":
                           "At Cannae in 216 BC Hannibal encircled the Roman army. Livy wrote: \"never before\""},
                          {"url": "https://museum.org/punic", "title": "Punic Wars", "cited_text": "Carthage vs Rome"},
                          {"url": "https://archive.org/polybius", "title": "Polybius", "cited_text": "Polybius 3.117"},
                          {"url": "https://britannica.com/cannae", "title": "Cannae", "cited_text": "August 216 BC"},
                          {"url": "https://jstor.org/x", "title": "Journal", "cited_text": "double envelopment"}],
            "results": [{"url": "https://reddit.com/r/x", "title": "forum"}]}


def script_with(quote: str, claim_src: str):
    return {"title": "Cannae", "logline": "l", "mood": "tense", "pronunciations": {},
            "style_bible": {"art_direction": "", "characters": [], "locations": []},
            "scenes": [{"section": "hook", "chapter": "A", "narration": f"In 216 BC Hannibal said {quote}.",
                        "visual": {"type": "illustration", "camera": "push_in", "prompt": "x"},
                        "claims": [{"claim": "Cannae was fought in 216 BC", "source_ids": [claim_src],
                                    "certainty": "established"}],
                        "quotes": [{"text": quote.strip('"'), "speaker": "Livy", "source_id": "S1"}]}]}


def fake_structured(db, *, video_id=None, category="script", tool_name="", prompt="", **kw):
    costs.record(db, video_id, category, "anthropic:test", 1000, "tokens", 0.02, tool_name)
    CALLS.append(tool_name)
    if tool_name == "submit_script":
        if "FACT-CHECK ISSUES" in prompt:   # revision: a verbatim quote and a valid source
            return script_with('"never before"', "S1")
        return script_with('"I came, I saw"', "S99")   # invented quote + bogus source
    if tool_name == "submit_verdicts":
        return {"verdicts": [{"id": "0.0", "verdict": "supported", "reason": "matches S1"}]}
    raise AssertionError(tool_name)


def setup_module(_):
    llm.web_research = fake_web_research
    llm.structured = fake_structured
    init_db()


def test_bibliography_is_only_real_search_results_and_ranked():
    from app.pipeline import research
    db = SessionLocal()
    t = Topic(title="Cannae", format="fact", main_event="battle")
    db.add(t)
    db.commit()
    v = Video(working_title="Cannae", topic_id=t.id)
    db.add(v)
    db.commit()
    r = research.run(db, v)
    urls = [s["url"] for s in r["bibliography"]]
    assert "https://uni.edu/cannae" in urls and all(u.startswith("https://") for u in urls)
    cited = [s for s in r["bibliography"] if s["cited"]]
    assert cited[0]["tier"] == 1


def test_factcheck_rejects_invented_quote_then_revision_passes():
    db = SessionLocal()
    t = Topic(title="Cannae", format="fact", main_event="battle", period="216 BC", target_minutes=10)
    db.add(t)
    db.commit()
    v = orchestrator.new_video(db, t)
    narration.run = lambda db, video: (_ for _ in ()).throw(RuntimeError("stop-after-factcheck"))
    try:
        orchestrator.produce(db, v)
    except RuntimeError as e:
        assert "stop-after-factcheck" in str(e)
    db.refresh(v)
    assert v.fact_check["passed"], v.fact_check
    assert CALLS.count("submit_script") == 2, "first draft must be revised"
    assert '"never before"' in v.scenes[0].narration
    assert v.status == "narrating"


def test_factcheck_detects_bad_sources_and_quotes_directly():
    db = SessionLocal()
    v = Video(working_title="x", research={"bibliography": [
        {"id": "S1", "url": "u", "title": "t", "cited": True, "excerpts": ["Livy wrote: never before"]}]},
        script=script_with('"I came, I saw"', "S99"))
    db.add(v)
    db.commit()
    rep = factcheck.run(db, v)
    ids = {i["id"]: i for i in rep["issues"]}
    assert not rep["passed"] and "0.0" in ids and "0.quote" in ids


def test_budget_exceeded_pauses_before_spending():
    db = SessionLocal()
    # Paid providers (the free stack estimates $0 and can't exceed a budget).
    settings_store.update(db, "ai", {"llm_provider": "anthropic", "image_provider": "fal"})
    settings_store.update(db, "voice", {"provider": "elevenlabs"})
    settings_store.update(db, "shorts", {"animated_scenes": 1})
    settings_store.update(db, "budget", {"max_per_video_usd": 1.0})
    t = Topic(title="Expensive", format="fact", target_minutes=15)
    db.add(t)
    db.commit()
    v = orchestrator.new_video(db, t)
    before = db.query(CostEntry).filter(CostEntry.video_id == v.id).count()
    try:
        orchestrator.produce(db, v)
        raise AssertionError("should have paused")
    except costs.BudgetExceeded as e:
        assert "exceeds the per-video limit" in str(e)
    assert db.query(CostEntry).filter(CostEntry.video_id == v.id).count() == before == 0
    settings_store.update(db, "budget", {"max_per_video_usd": 25.0})
    settings_store.update(db, "ai", {"llm_provider": "gemini", "image_provider": "cloudflare"})
    settings_store.update(db, "voice", {"provider": "kokoro"})


def test_worker_marks_budget_pause_and_notifies():
    from app import worker
    db = SessionLocal()
    settings_store.update(db, "budget", {"max_monthly_usd": 0.01})
    t = Topic(title="Monthly cap", format="fact", target_minutes=8)
    db.add(t)
    db.commit()
    v = orchestrator.new_video(db, t)
    db.query(Job).filter(Job.video_id != v.id).update({"status": "done"})
    db.commit()
    assert worker.process_one()
    db.expire_all()
    assert db.get(Video, v.id).status == "paused_budget"
    assert db.query(Job).filter(Job.video_id == v.id).one().status == "paused"
    settings_store.update(db, "budget", {"max_monthly_usd": 300})


def test_schedule_slots_and_upload_guard():
    db = SessionLocal()
    settings_store.update(db, "schedule", {"days": ["mon", "wed", "fri"], "time": "15:00",
                                           "timezone": "America/New_York"})
    slots = publish.upcoming_slots(db, 6, kind="long")
    assert len(slots) == 6
    from zoneinfo import ZoneInfo
    assert {s.astimezone(ZoneInfo("America/New_York")).strftime("%a %H:%M") for s in slots} <= \
        {"Mon 15:00", "Wed 15:00", "Fri 15:00"}
    shorts = publish.upcoming_slots(db, 6, kind="short")     # default: daily at 11:00, 15:00, 19:00
    assert {s.astimezone(ZoneInfo("America/New_York")).strftime("%H:%M") for s in shorts} == {"11:00", "15:00", "19:00"}
    v = Video(working_title="not approved", status="awaiting_approval")
    db.add(v)
    db.commit()
    try:
        publish.upload(db, v)
        raise AssertionError("must refuse")
    except RuntimeError as e:
        assert "not approved" in str(e)
    v.status = "approved"
    v.qc_report = {"passed": False}
    db.commit()
    try:
        publish.upload(db, v)
        raise AssertionError("must refuse")
    except RuntimeError as e:
        assert "Quality checks" in str(e)
