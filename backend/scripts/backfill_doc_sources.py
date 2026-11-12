"""Record where each pre-loaded document came from.

docs_inbox/download-map.json (written by doc_downloads.py) maps every file we
asked the user to download to its BSE link. This stores that link on the
matching documents row (source='bse'), so Surya's "Verified" line can point
to the original filing. Safe to re-run; never overwrites a source a user gave.

  python scripts/backfill_doc_sources.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finn.db import cursor  # noqa: E402

MAP = Path(__file__).resolve().parent.parent / "docs_inbox" / "download-map.json"


def backfill() -> int:
    if not MAP.exists():
        return 0
    entries = json.loads(MAP.read_text(encoding="utf-8"))
    n = 0
    with cursor() as c:
        for e in entries:
            c.execute("""update public.documents set source = 'bse', source_url = %s
                         where symbol = %s and filename = %s and source_url is null""",
                      (e["url"], e["symbol"], e["target"]))
            n += c.rowcount
    return n


if __name__ == "__main__":
    print("documents linked to their BSE source:", backfill())
