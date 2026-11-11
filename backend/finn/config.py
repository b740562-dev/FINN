"""Environment config, loaded once from backend/.env."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def env(name: str, required: bool = True) -> str:
    val = (os.getenv(name) or "").strip()
    if required and not val:
        raise RuntimeError(f"Missing {name} in backend/.env")
    return val


GEMINI_API_KEY = env("GEMINI_API_KEY", required=False)
# Accept the project URL with or without a pasted '/rest/v1/' suffix.
SUPABASE_URL = env("SUPABASE_URL", required=False).rstrip("/").removesuffix("/rest/v1")
SUPABASE_ANON_KEY = env("SUPABASE_ANON_KEY", required=False)
SUPABASE_SERVICE_ROLE_KEY = env("SUPABASE_SERVICE_ROLE_KEY", required=False)
DATABASE_URL = env("DATABASE_URL", required=False)
TAVILY_API_KEY = env("TAVILY_API_KEY", required=False)

# Accounts allowed to see internals (model routing, LLM usage & cost).
# Comma-separated emails, set per deployment (never committed).
ADMIN_EMAILS = {e.strip().lower() for e in env("ADMIN_EMAILS", required=False).split(",") if e.strip()}
