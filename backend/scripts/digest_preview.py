"""Print the digest the demo portfolio would see for a window.

Usage: python scripts/digest_preview.py [days=7] [as_of=YYYY-MM-DD]
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finn.push.rank import build_digest  # noqa: E402
from finn.universe import PORTFOLIO  # noqa: E402

DEFAULT_CARE = ["results", "M&A", "management_change", "fund_raise", "litigation", "credit_rating", "pledging"]

days = float(sys.argv[1]) if len(sys.argv) > 1 else 7
until = (datetime.fromisoformat(sys.argv[2]).replace(tzinfo=timezone.utc) + timedelta(days=1)
         if len(sys.argv) > 2 else datetime.now(timezone.utc))
d = build_digest({h.symbol: h.weight for h in PORTFOLIO}, DEFAULT_CARE, since=until - timedelta(days=days), until=until)

c = d["counts"]
print(f"WINDOW {days:g}d -> {c['filings']} filings, {c['events']} events | "
      f"{c['matters']} matter | {c['routine_filings']} routine collapsed {d['routine_mix']}\n")
for e in d["matters"]:
    rel = f" (+{e['related']} related)" if e["related"] else ""
    print(f"{e['score']:>5.0f}  {e['symbol']:10} {e['label']:12} {e['filed_at'][:10]}{rel}")
    print(f"        {e['one_liner'] or e['headline']}")
    print(f"        why: {e['why']}")
