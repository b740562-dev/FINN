"""Postgres access via pg8000 (pure Python, so there's no native DLL for
Windows Smart App Control to block, and nothing to compile on Render)."""
from __future__ import annotations

import queue
import ssl
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import unquote, urlparse

import pg8000.dbapi

from finn import config


# Supabase signs its Postgres TLS certs with its own CA. Download it from
# Project Settings -> Database -> SSL Configuration -> "Download certificate"
# and save it as backend/supabase-ca.crt. Connections are always fully verified.
SUPABASE_CA = Path(__file__).resolve().parent.parent / "supabase-ca.crt"


def _ssl_context() -> ssl.SSLContext:
    if not SUPABASE_CA.exists():
        raise RuntimeError(
            "backend/supabase-ca.crt is missing. Download it from Supabase: Project Settings -> "
            "Database -> SSL Configuration -> Download certificate."
        )
    return ssl.create_default_context(cafile=str(SUPABASE_CA))


def _conn_kwargs(url: str) -> dict:
    u = urlparse(url)
    return dict(
        user=unquote(u.username or ""),
        password=unquote(u.password or ""),
        host=u.hostname,
        port=u.port or 5432,
        database=(u.path or "/postgres").lstrip("/") or "postgres",
        ssl_context=_ssl_context(),
        timeout=30,
    )


def connect():
    return pg8000.dbapi.connect(**_conn_kwargs(config.env("DATABASE_URL")))


# Small pool: a TLS handshake to the Mumbai pooler costs ~0.5s, so reuse
# connections across requests. pg8000 connections are not thread-safe, so a
# connection is checked out by exactly one caller at a time.
_POOL: queue.LifoQueue = queue.LifoQueue(maxsize=8)


def _checkout():
    while True:
        try:
            conn, born = _POOL.get_nowait()
        except queue.Empty:
            return connect(), time.monotonic()
        if time.monotonic() - born < 240:   # recycle before the pooler's idle timeout
            return conn, born
        try:
            conn.close()
        except Exception:
            pass


def _checkin(conn, born) -> None:
    try:
        _POOL.put_nowait((conn, born))
    except queue.Full:
        conn.close()


@contextmanager
def cursor(commit: bool = True):
    conn, born = _checkout()
    healthy = True
    try:
        cur = conn.cursor()
        yield cur
        if commit:
            conn.commit()
        else:
            conn.rollback()  # end the read transaction before returning to the pool
    except pg8000.dbapi.InterfaceError:
        healthy = False      # broken socket: drop it
        raise
    except Exception:
        try:
            conn.rollback()
        except Exception:
            healthy = False
        raise
    finally:
        if healthy:
            _checkin(conn, born)
        else:
            try:
                conn.close()
            except Exception:
                pass
