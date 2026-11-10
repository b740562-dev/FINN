"""Shared HTTP helpers: browser-like headers, retries, polite pacing, and an
optional on-disk cache so development runs don't re-hit public sites."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import requests

# Honest client identity. We only use sources that serve plain clients; we do
# not imitate browsers to get past bot protection.
UA = "FINN-prototype/0.1 (personal research project; low-volume EOD fetches)"

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "http"


def make_session(extra_headers: dict | None = None) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/json,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    if extra_headers:
        s.headers.update(extra_headers)
    return s


def get(
    session: requests.Session,
    url: str,
    *,
    params: dict | None = None,
    retries: int = 3,
    timeout: int = 20,
    backoff: float = 1.5,
    cache_ttl: int | None = None,
) -> requests.Response:
    """GET with retries. If cache_ttl (seconds) is set, text responses are
    cached on disk keyed by URL + params."""
    cache_file = None
    if cache_ttl:
        key = hashlib.sha1((url + json.dumps(params or {}, sort_keys=True)).encode()).hexdigest()
        cache_file = CACHE_DIR / f"{key}.json"
        if cache_file.exists() and time.time() - cache_file.stat().st_mtime < cache_ttl:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            resp = requests.Response()
            resp.status_code = data["status"]
            resp._content = data["body"].encode("utf-8")
            resp.encoding = "utf-8"
            resp.url = url
            return resp

    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = session.get(url, params=params, timeout=timeout)
            if resp.status_code in (429, 503):
                raise requests.HTTPError(f"{resp.status_code} rate-limited", response=resp)
            if cache_file and resp.ok:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(
                    json.dumps({"status": resp.status_code, "body": resp.text}), encoding="utf-8"
                )
            return resp
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
            last_exc = e
            time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"GET failed after {retries} attempts: {url}") from last_exc
