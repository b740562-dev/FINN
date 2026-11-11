"""Request auth: the app sends the Supabase access token as a Bearer token;
we confirm it with Supabase Auth (GET /auth/v1/user) and cache the answer
briefly so most requests don't make the extra round trip."""
from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import dataclass

import requests
from fastapi import Header, HTTPException, Request

from finn import config

TTL = 300  # seconds a verified token is trusted without re-checking
_cache: dict[str, tuple[float, "User"]] = {}
_lock = threading.Lock()


@dataclass(frozen=True)
class User:
    id: str
    is_anonymous: bool
    email: str | None

    @property
    def is_admin(self) -> bool:
        """Admins see internals (model routing, usage & cost). A verified,
        non-guest email on ADMIN_EMAILS, or the local demo user when
        FINN_DEV_ADMIN=1 is also set (development only)."""
        if self.id == DEV_USER_ID:
            return os.getenv("FINN_DEV_AUTH") == "1" and os.getenv("FINN_DEV_ADMIN") == "1"
        return (not self.is_anonymous and bool(self.email)
                and self.email.lower() in config.ADMIN_EMAILS)


def require_admin(user: "User") -> None:
    if not user.is_admin:
        raise HTTPException(403, "Admins only")


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


# ---- Local demo mode (development only) ------------------------------------
# For demoing on a network that blocks *.supabase.co. Accepted ONLY when
# FINN_DEV_AUTH=1 is set in the server's environment AND the request comes
# from this machine. Never set FINN_DEV_AUTH in a deployed environment.
DEV_TOKEN = "dev-local-demo"
DEV_USER_ID = "00000000-0000-4000-8000-00000000f1a0"
_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _dev_user(request: Request, token: str) -> User | None:
    if os.getenv("FINN_DEV_AUTH") != "1" or token != DEV_TOKEN:
        return None
    if not request.client or request.client.host not in _LOCAL_HOSTS:
        raise HTTPException(401, "Dev demo token is only accepted from localhost")
    return User(id=DEV_USER_ID, is_anonymous=True, email=None)


def current_user(request: Request, authorization: str | None = Header(default=None)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if dev := _dev_user(request, token):
        return dev
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
