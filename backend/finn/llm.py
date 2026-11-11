"""Single entry point for every LLM call.

- Model routing by tier: BULK (cheap, fast) vs REASON (stronger, thinks more).
- Structured JSON output against a JSON schema.
- Response cache in Postgres: identical (model, config, prompt) never runs twice.
- Every call (including cache hits) is logged to llm_calls for the cost meter.
"""
from __future__ import annotations

import hashlib
import json
import time

from google import genai
from google.genai import types

from finn import config
from finn.db import cursor

BULK = "gemini-3.5-flash-lite"     # classification, extraction, one-liners, verification
REASON = "gemini-3.8-flash"        # promise-vs-delivered, bull/bear, chat synthesis
EMBED = "gemini-embedding-2"
EMBED_DIM = 768

# USD per 1M tokens (input, output). Free tier costs ₹0; these let the cost
# meter show what the same work would cost at paid rates. Filled in from the
# published price list; None = unknown -> cost shown as tokens only.
PRICES_PER_M: dict[str, tuple[float, float] | None] = {
    BULK: None,
    REASON: None,
}

_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.env("GEMINI_API_KEY"))
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
    for attempt in range(retries):
        try:
            resp = client().models.generate_content(model=model, contents=prompt, config=cfg)
            data = json.loads(resp.text)
            u = resp.usage_metadata
            tin = (u.prompt_token_count or 0) if u else 0
            tout = ((u.candidates_token_count or 0) + (getattr(u, "thoughts_token_count", 0) or 0)) if u else 0
            with cursor() as c:
                c.execute(
                    "insert into public.llm_cache (key, model, response) values (%s, %s, %s::jsonb) "
                    "on conflict (key) do nothing",
                    (key, model, json.dumps(data)),
                )
            _log(task, model, tin, tout, False, ref_type, ref_id)
            return data
        except Exception as e:  # rate limits / transient errors / bad JSON
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"LLM call failed for task={task}") from last


def embed(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    resp = client().models.embed_content(
        model=EMBED,
        contents=texts,
        config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=EMBED_DIM),
    )
    return [e.values for e in resp.embeddings]
