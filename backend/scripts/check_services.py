"""Smoke-test external services: Gemini key + model list, Supabase Postgres.
Never prints secrets."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finn import config  # noqa: E402


def check_gemini() -> None:
    from google import genai
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    names = []
    for m in client.models.list():
        actions = getattr(m, "supported_actions", None) or []
        names.append((m.name.replace("models/", ""), ",".join(a for a in actions if a in ("generateContent", "embedContent"))))
    print(f"Gemini OK: {len(names)} models visible")
    for n, a in sorted(names):
        if any(k in n for k in ("flash", "pro", "embed")) and a:
            print(f"   {n:45s} {a}")
    # tiny live calls on the models we plan to route to
    for pick in ("gemini-3.5-flash-lite", "gemini-3.8-flash"):
        try:
            r = client.models.generate_content(model=pick, contents="Reply with exactly: pong")
            u = r.usage_metadata
            print(f"   live {pick}: {r.text.strip()!r}  tokens in/out={u.prompt_token_count}/{u.candidates_token_count}")
        except Exception as e:
            print(f"   live {pick}: FAILED {str(e)[:160]}")
    try:
        e = client.models.embed_content(model="gemini-embedding-2", contents=["hello"])
        print(f"   embed gemini-embedding-2: dim={len(e.embeddings[0].values)}")
    except Exception as ex:
        print(f"   embed gemini-embedding-2: FAILED {str(ex)[:160]}")


def check_db() -> None:
    from finn.db import cursor
    with cursor(commit=False) as cur:
        cur.execute("select version()")
        print("Postgres OK:", cur.fetchone()[0].split(",")[0])
        cur.execute("select name, default_version, installed_version from pg_available_extensions where name = 'vector'")
        print("   pgvector:", cur.fetchone())


if __name__ == "__main__":
    for fn in (check_gemini, check_db):
        try:
            fn()
        except Exception as e:
            print(f"{fn.__name__} FAILED: {type(e).__name__}: {str(e)[:300]}")
