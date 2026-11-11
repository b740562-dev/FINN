"""Apply backend/sql/*.sql in order, once each, tracked in public.schema_migrations.

Usage:  python scripts/migrate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finn.db import connect  # noqa: E402

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def split_sql(sql: str) -> list[str]:
    """Split on ';' outside quotes, dollar-quoted bodies and comments."""
    out, buf, i, n = [], [], 0, len(sql)
    in_single, dollar_tag = False, None
    while i < n:
        c = sql[i]
        if dollar_tag:
            if sql.startswith(dollar_tag, i):
                buf.append(dollar_tag); i += len(dollar_tag); dollar_tag = None; continue
            buf.append(c); i += 1; continue
        if in_single:
            buf.append(c)
            if c == "'":
                in_single = False
            i += 1; continue
        if sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j == -1 else j + 1
            buf.append("\n"); continue
        if c == "'":
            in_single = True; buf.append(c); i += 1; continue
        if c == "$":
            j = sql.find("$", i + 1)
            tag = sql[i:j + 1] if j != -1 else ""
            if tag and all(ch.isalnum() or ch == "_" for ch in tag[1:-1]):
                dollar_tag = tag; buf.append(tag); i = j + 1; continue
        if c == ";":
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []; i += 1; continue
        buf.append(c); i += 1
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def main() -> None:
    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute("create table if not exists public.schema_migrations "
                "(name text primary key, applied_at timestamptz not null default now())")
    conn.commit()
    cur.execute("select name from public.schema_migrations")
    done = {r[0] for r in cur.fetchall()}
    for f in sorted(SQL_DIR.glob("*.sql")):
        if f.name in done:
            print(f"skip   {f.name}")
            continue
        stmts = split_sql(f.read_text(encoding="utf-8"))
        try:
            for s in stmts:
                cur.execute(s)
            cur.execute("insert into public.schema_migrations (name) values (%s)", (f.name,))
            conn.commit()
            print(f"apply  {f.name}  ({len(stmts)} statements)")
        except Exception as e:
            conn.rollback()
            print(f"FAILED {f.name}: {e}")
            raise SystemExit(1)
    conn.close()


if __name__ == "__main__":
    main()
