"""Claude API wrapper: structured (tool-forced) output, and web-search-grounded research.

Every source this system ever cites comes from a real `web_search_tool_result` or
citation returned by the API — the model is never asked to produce URLs from memory.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import anthropic
from sqlalchemy.orm import Session

from .. import costs, settings_store
from ..config import env


class LLMError(Exception):
    pass


def _client() -> anthropic.Anthropic:
    if not env.anthropic_api_key:
        raise LLMError("ANTHROPIC_API_KEY is not configured (see README → Connect your accounts).")
    return anthropic.Anthropic(api_key=env.anthropic_api_key, max_retries=4, timeout=900)


def _record(db: Session, video_id, category: str, model: str, usage, fast: bool, note: str) -> float:
    searches = 0
    stu = getattr(usage, "server_tool_use", None)
    if stu is not None:
        searches = getattr(stu, "web_search_requests", 0) or 0
    usd = costs.llm_cost(db, usage.input_tokens, usage.output_tokens, fast=fast, searches=searches)
    costs.record(db, video_id, category, f"anthropic:{model}", usage.input_tokens + usage.output_tokens,
                 "tokens", usd, note + (f" ({searches} searches)" if searches else ""))
    return usd


def provider(db: Session) -> str:
    return settings_store.get(db, "ai").get("llm_provider", "gemini")


def structured(db: Session, *, video_id: int | None, category: str, system: str, prompt: str,
               schema: dict, tool_name: str = "submit", fast: bool = False, max_tokens: int = 16000,
               images: list[Path] | None = None, est_usd: float = 0.3, note: str = "") -> dict:
    """Ask the model for output that must match `schema` (Claude: forced tool call; Gemini: JSON schema)."""
    if provider(db) == "gemini":
        from . import gemini
        return gemini.generate(db, video_id=video_id, category=category, system=system, prompt=prompt,
                               schema=schema, fast=fast, images=images, max_tokens=max_tokens,
                               note=note or tool_name)
    ai = settings_store.get(db, "ai")
    model = ai["llm_model_fast"] if fast else ai["llm_model"]
    costs.guard(db, video_id, category, est_usd)
    content: list = []
    for img in images or []:
        media = "image/png" if str(img).endswith(".png") else "image/jpeg"
        content.append({"type": "image", "source": {"type": "base64", "media_type": media,
                                                    "data": base64.b64encode(Path(img).read_bytes()).decode()}})
    content.append({"type": "text", "text": prompt})
    with _client().messages.stream(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": content}],
        tools=[{"name": tool_name, "description": "Submit the result.", "input_schema": schema}],
        tool_choice={"type": "tool", "name": tool_name},
    ) as stream:
        resp = stream.get_final_message()
    _record(db, video_id, category, model, resp.usage, fast, note or tool_name)
    for block in resp.content:
        if block.type == "tool_use":
            return block.input
    raise LLMError("Model did not return structured output.")


def web_research(db: Session, *, video_id: int | None, category: str, system: str, prompt: str,
                 max_uses: int | None = None, est_usd: float = 1.0, note: str = "") -> dict:
    """Run a web-search-grounded research turn.

    Returns {"text": str, "citations": [{url,title,cited_text}], "results": [{url,title,page_age}]}
    """
    if provider(db) == "gemini":
        return free_research(db, video_id=video_id, category=category, system=system, prompt=prompt, note=note)
    ai = settings_store.get(db, "ai")
    model = ai["llm_model"]
    costs.guard(db, video_id, category, est_usd)
    tool = {"type": ai.get("web_search_tool", "web_search_20250305"), "name": "web_search",
            "max_uses": max_uses or ai["web_search_max_uses"]}
    if ai.get("blocked_domains"):
        tool["blocked_domains"] = ai["blocked_domains"]
    messages: list = [{"role": "user", "content": prompt}]
    text_parts, citations, results = [], [], {}
    client = _client()
    for _ in range(6):  # continue through `pause_turn` for long research turns
        with client.messages.stream(model=model, max_tokens=16000, system=system,
                                    messages=messages, tools=[tool]) as stream:
            resp = stream.get_final_message()
        _record(db, video_id, category, model, resp.usage, False, note or "web research")
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
                for c in getattr(block, "citations", None) or []:
                    url = getattr(c, "url", None)
                    if url:
                        citations.append({"url": url, "title": getattr(c, "title", "") or "",
                                          "cited_text": getattr(c, "cited_text", "") or ""})
            elif block.type == "web_search_tool_result":
                items = block.content if isinstance(block.content, list) else []
                for r in items:
                    url = getattr(r, "url", None)
                    if url:
                        results[url] = {"url": url, "title": getattr(r, "title", "") or "",
                                        "page_age": getattr(r, "page_age", "") or ""}
        if resp.stop_reason != "pause_turn":
            break
        messages = messages + [{"role": "assistant", "content": resp.content}]
    return {"text": "".join(text_parts), "citations": citations, "results": list(results.values())}


def to_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1)


QUERY_SCHEMA = {"type": "object", "properties": {"queries": {"type": "array", "items": {"type": "string"}}},
                "required": ["queries"]}


def free_research(db: Session, *, video_id, category: str, system: str, prompt: str, note: str = "") -> dict:
    """Free research: Wikipedia articles chosen by the model, answered ONLY from numbered excerpts.
    Citations are the excerpts the answer actually cites, so nothing is invented."""
    import re

    from . import gemini, wiki
    q = gemini.generate(db, video_id=video_id, category=category, schema=QUERY_SCHEMA, fast=True,
                        note=(note or "research") + ": queries",
                        system="You plan Wikipedia research for a history video.",
                        prompt=f"Give 3-5 short Wikipedia search queries (specific article subjects) to research:\n{prompt}")
    titles: list[str] = []
    for query in q.get("queries", [])[:5]:
        try:
            for t in wiki.search(query, 3):
                if t not in titles:
                    titles.append(t)
        except Exception:
            continue
    arts, paras = [], []
    for t in titles[:7]:
        try:
            a = wiki.article(t)
        except Exception:
            a = None
        if not a:
            continue
        arts.append(a)
        for i, p in enumerate(a["paragraphs"]):
            paras.append({**p, "i": i, "title": a["title"], "url": a["url"]})
    if not paras:
        return {"text": "No sources found.", "citations": [], "results": []}
    chosen = wiki.relevant(paras, prompt + " " + " ".join(q.get("queries", [])), k=28)
    numbered = "\n\n".join(f"[{n}] ({c['title']} — {c['section'] or 'intro'}) {c['text'][:1500]}"
                            for n, c in enumerate(chosen, 1))
    answer = gemini.generate(
        db, video_id=video_id, category=category, note=note or "research",
        system=system + "\n\nUse ONLY the numbered excerpts provided. Put the excerpt number in square brackets "
                        "after every fact, e.g. [3]. If the excerpts don't cover something, say so plainly. "
                        "Never add facts, dates or quotations from memory.",
        prompt=f"TASK:\n{prompt}\n\nEXCERPTS:\n{numbered}")
    cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer) if 0 < int(n) <= len(chosen)})
    citations = [{"url": chosen[n - 1]["url"], "title": f"{chosen[n - 1]['title']} (Wikipedia)",
                  "cited_text": chosen[n - 1]["text"]} for n in cited]
    # Rewrite [n] markers so the downstream text names the article rather than a local number.
    text = re.sub(r"\[(\d+)\]", lambda m: f"[{chosen[int(m.group(1)) - 1]['title']}]"
                  if 0 < int(m.group(1)) <= len(chosen) else "", answer)
    return {"text": text, "citations": citations,
            "results": [{"url": a["url"], "title": f"{a['title']} (Wikipedia)", "page_age": ""} for a in arts]}
