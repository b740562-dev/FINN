"""Single entry point for every LLM call.

- Model routing by tier: BULK (cheap, fast) vs REASON (stronger, thinks more).
- Structured JSON output against a JSON schema.
- Response cache in Postgres: identical (model, config, prompt) never runs twice.
- Every call (including cache hits) is logged to llm_calls for the cost meter.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time

from google import genai
from google.genai import types

from finn import config
from finn.db import cursor

BULK = "gemini-3.5-flash-lite"     # classification, extraction, one-liners, verification
# promise-vs-delivered, bull/bear, chat synthesis. gemini-3.8-flash is the
# stronger model but on 11 Nov 2026 it returned 504s / multi-minute latencies
# on our free-tier key. gemini-3.5-flash is deprecated and Google routes it to
# gemini-3.6-flash, so we name 3.6-flash directly. Override with
# FINN_REASON_MODEL=gemini-3.8-flash when it is healthy.
REASON = os.getenv("FINN_REASON_MODEL", "gemini-3.6-flash")
EMBED = "gemini-embedding-2"
EMBED_DIM = 768

# Paid-tier list prices, USD per 1M tokens (input, output incl. thinking),
# from https://ai.google.dev/gemini-api/docs/pricing as read on 11 Nov 2026.
# 3.6/3.8-flash prices double on 1 Jan 2027. FINN runs on the free tier
# (billed ₹0); the meter shows what the same work would cost at paid rates.
PRICES_PER_M: dict[str, tuple[float, float] | None] = {
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.6-flash": (0.75, 3.75),
    "gemini-3.5-flash": (0.75, 3.75),   # deprecated alias, served by 3.6-flash
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-embedding-2": (0.20, 0.0),
}
PRICES_AS_OF = "2026-11-11"

# When the primary model is overloaded (503) or too slow, fall back once to a
# sibling model rather than leaving the user waiting minutes.
FALLBACK = {REASON: "gemini-3.5-flash-lite" if REASON != "gemini-3.5-flash-lite" else "gemini-3.1-flash-lite",
            BULK: "gemini-3.1-flash-lite"}
TIMEOUT_MS = 75_000

_client: genai.Client | None = None
_client_lock = threading.Lock()


def client() -> genai.Client:
    """One shared client. Locked: two threads racing here would each build a
    Client and the loser gets garbage-collected (closed) mid-request."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = genai.Client(api_key=config.env("GEMINI_API_KEY"),
                                       http_options=types.HttpOptions(timeout=TIMEOUT_MS))
    return _client


def _cost(model: str, tin: int, tout: int) -> float | None:
    p = PRICES_PER_M.get(model)
    return None if not p else round((tin * p[0] + tout * p[1]) / 1e6, 6)


def _log(task: str, model: str, tin: int, tout: int, cache_hit: bool, ref_type=None, ref_id=None) -> None:
    with cursor() as c:
        c.execute(
            "insert into public.llm_calls (task, model, tokens_in, tokens_out, cost_usd, cache_hit, ref_type, ref_id) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s)",
            (task, model, tin, tout, None if cache_hit else _cost(model, tin, tout), cache_hit, ref_type, ref_id),
        )


def generate_json(
    task: str,
    prompt: str,
    schema: dict,
    *,
    model: str = BULK,
    system: str | None = None,
    thinking: str = "low",
    temperature: float = 0.2,
    ref_type: str | None = None,
    ref_id: str | None = None,
    retries: int = 3,
):
    """Return parsed JSON matching `schema`. Cached + logged."""
    key = hashlib.sha256(
        json.dumps([model, system, prompt, schema, thinking, temperature], sort_keys=True).encode()
    ).hexdigest()
    with cursor(commit=False) as c:
        c.execute("select response from public.llm_cache where key = %s", (key,))
        hit = c.fetchone()
    if hit:
        _log(task, model, 0, 0, True, ref_type, ref_id)
        return hit[0] if not isinstance(hit[0], str) else json.loads(hit[0])

    cfg = types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        response_mime_type="application/json",
        response_json_schema=schema,
        thinking_config=types.ThinkingConfig(thinking_level=thinking),
    )
    last: Exception | None = None
    use = model
    for attempt in range(retries):
        try:
            resp = client().models.generate_content(model=use, contents=prompt, config=cfg)
            data = json.loads(resp.text)
            u = resp.usage_metadata
            tin = (u.prompt_token_count or 0) if u else 0
            tout = ((u.candidates_token_count or 0) + (getattr(u, "thoughts_token_count", 0) or 0)) if u else 0
            with cursor() as c:
                c.execute(
                    "insert into public.llm_cache (key, model, response) values (%s, %s, %s::jsonb) "
                    "on conflict (key) do nothing",
                    (key, use, json.dumps(data)),
                )
            _log(task, use, tin, tout, False, ref_type, ref_id)
            return data
        except Exception as e:  # rate limits / overload / timeouts / bad JSON
            last = e
            msg = str(e)
            overloaded = any(s in msg for s in ("503", "504", "UNAVAILABLE", "DEADLINE_EXCEEDED", "overloaded",
                                                "high demand", "timed out", "Timeout", "429", "RESOURCE_EXHAUSTED"))
            if overloaded and use == model and FALLBACK.get(model):
                use = FALLBACK[model]           # switch model straight away instead of waiting
                continue
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"LLM call failed for task={task}") from last


TRANSCRIBE_PROMPT = (
    "Transcribe this voice note exactly as spoken. It is an investor asking a question, often about Indian "
    "listed companies (e.g. HDFC Bank, Reliance, TCS, BEL), financial terms (EBITDA, NIM, concall, order book) "
    "and rupee amounts (lakh, crore). Keep the language that was spoken; write company names and tickers in "
    "their usual spelling. Return only the transcript, no quotes or commentary. If there is no speech, return "
    "an empty string."
)


def transcribe(audio: bytes, mime_type: str, *, ref_id: str | None = None) -> str:
    """Speech -> text with the bulk model (audio input). Not cached: every
    recording is different. Logged like any other call."""
    use, last = BULK, None
    for attempt in range(3):
        try:
            resp = client().models.generate_content(
                model=use,
                contents=[types.Part.from_bytes(data=audio, mime_type=mime_type), TRANSCRIBE_PROMPT],
                config=types.GenerateContentConfig(temperature=0.0,
                                                   thinking_config=types.ThinkingConfig(thinking_level="low")),
            )
            u = resp.usage_metadata
            tin = (u.prompt_token_count or 0) if u else 0
            tout = ((u.candidates_token_count or 0) + (getattr(u, "thoughts_token_count", 0) or 0)) if u else 0
            _log("transcribe", use, tin, tout, False, "voice", ref_id)
            return (resp.text or "").strip().strip('"').strip()
        except Exception as e:
            last = e
            if any(s in str(e) for s in ("503", "504", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "overloaded")) \
                    and use == BULK and FALLBACK.get(BULK):
                use = FALLBACK[BULK]
                continue
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("Transcription failed") from last


def embed(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    resp = client().models.embed_content(
        model=EMBED,
        contents=texts,
        config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=EMBED_DIM),
    )
    # The embed API doesn't return token counts; estimate ~4 chars per token so
    # embeddings show up in the cost meter instead of being invisible.
    try:
        est = sum(len(t) for t in texts) // 4
        _log("embed_documents" if task_type == "RETRIEVAL_DOCUMENT" else "embed_query", EMBED, est, 0, False)
    except Exception:
        pass
    return [e.values for e in resp.embeddings]
