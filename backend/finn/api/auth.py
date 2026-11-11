"""Request auth: the app sends the Supabase access token as a Bearer token;
we confirm it with Supabase Auth (GET /auth/v1/user) and cache the answer
briefly so most requests don't make the extra round trip."""
from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass

import requests
from fastapi import Header, HTTPException

from finn import config

TTL = 300  # seconds a verified token is trusted without re-checking
_cache: dict[str, tuple[float, "User"]] = {}
_lock = threading.Lock()


@dataclass(frozen=True)
class User:
    id: str
    is_anonymous: bool
    email: str | None


def _verify(token: str) -> User:
    r = requests.get(
        f"{config.SUPABASE_URL}/auth/v1/user",
        headers={"apikey": config.SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if r.status_code != 200:
        raise HTTPException(401, "Invalid or expired session")
    u = r.json()
    return User(id=u["id"], is_anonymous=bool(u.get("is_anonymous")), email=u.get("email"))


def current_user(authorization: str | None = Header(default=None)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    key = hashlib.sha256(token.encode()).hexdigest()
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
    user = _verify(token)
    with _lock:
        _cache[key] = (now + TTL, user)
        if len(_cache) > 5000:  # crude bound
            for k in [k for k, (exp, _) in _cache.items() if exp <= now]:
                _cache.pop(k, None)
    return user
