"""Google Gemini API (free tier) for structured output. Key: https://aistudio.google.com/apikey
Free-tier prompts may be used by Google to improve its products — fine for public history scripts,
don't send private data. Free-tier rate limits are low, so 429s are retried with backoff."""
from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from .. import costs, settings_store
from ..config import env

API = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiError(Exception):
    pass


def _post(model: str, body: dict) -> httpx.Response:
    if not env.gemini_api_key:
        raise GeminiError("GEMINI_API_KEY is not configured (free key: https://aistudio.google.com/apikey).")
    r = None
    for attempt in range(7):
        r = httpx.post(f"{API}/{model}:generateContent", json=body, timeout=300,
                       headers={"x-goog-api-key": env.gemini_api_key})
        if r.status_code in (429, 500, 503):
            time.sleep(min(90, 15 * (attempt + 1)))      # free tier: a few requests per minute
            continue
        return r
    return r


def _text(resp: dict) -> str:
    try:
        parts = resp["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError):
        raise GeminiError(f"Gemini returned no content: {str(resp)[:400]}")
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def parse_json(text: str):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=0)
    return json.loads(text[start:])


def generate(db: Session, *, video_id, category: str, system: str, prompt: str, schema: dict | None = None,
             fast: bool = False, images: list[Path] | None = None, max_tokens: int = 16000, note: str = "") -> dict | str:
    ai = settings_store.get(db, "ai")
    model = ai["gemini_model_fast"] if fast else ai["gemini_model"]
    costs.guard(db, video_id, category, 0)
    parts: list = []
    for img in images or []:
        parts.append({"inline_data": {"mime_type": "image/png" if str(img).endswith(".png") else "image/jpeg",
                                      "data": base64.b64encode(Path(img).read_bytes()).decode()}})
    parts.append({"text": prompt})
    base = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": parts}]}
    cfg = {"maxOutputTokens": max_tokens, "temperature": 0.7}
    variants = [None]
    if schema is not None:
        variants = [
            {**cfg, "responseMimeType": "application/json", "responseJsonSchema": schema},
            {**cfg, "responseFormat": {"text": {"mimeType": "application/json", "schema": schema}}},
            {**cfg, "responseMimeType": "application/json"},   # last resort: schema in the prompt
        ]
    r = None
    for i, gc in enumerate(variants):
        body = dict(base, generationConfig=gc or cfg)
        if schema is not None and i == 2:
            body["contents"][0]["parts"][-1] = {"text": prompt + "\n\nReturn ONLY JSON matching this JSON Schema:\n"
                                                + json.dumps(schema)}
        r = _post(model, body)
        if r.status_code == 400 and schema is not None and i < 2:
            continue
        break
    if r.status_code >= 400:
        raise GeminiError(f"Gemini error {r.status_code}: {r.text[:500]}")
    data = r.json()
    u = data.get("usageMetadata", {})
    costs.record(db, video_id, category, f"gemini:{model} (free tier)",
                 u.get("promptTokenCount", 0) + u.get("candidatesTokenCount", 0), "tokens", 0.0, note)
    text = _text(data)
    if schema is None:
        return text
    try:
        return parse_json(text)
    except json.JSONDecodeError as e:
        raise GeminiError(f"Gemini returned invalid JSON ({e}): {text[:300]}")
