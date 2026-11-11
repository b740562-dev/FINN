"""Postgres access via pg8000 (pure Python, so there's no native DLL for
Windows Smart App Control to block, and nothing to compile on Render)."""
from __future__ import annotations

import ssl
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


@contextmanager
def cursor(commit: bool = True):
    conn = connect()
    try:
        cur = conn.cursor()
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
