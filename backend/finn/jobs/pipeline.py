"""The push pipeline the scheduler runs:
ingest -> classify -> results cards -> management bios -> alerts.

Usage: python -m finn.jobs.pipeline [SYMBOL ...]
Default universe = demo portfolio + research set + anything any user holds.
Each stage only processes what's new, so a run with nothing new makes no LLM calls.
"""
import sys
import time

from finn.db import cursor
from finn.jobs.ingest import main as ingest
from finn.push.alerts import run_alerts
from finn.push.bios import enrich_management_changes
from finn.push.classify import classify_pending
from finn.push.results import attach_results_cards
from finn.universe import all_symbols


def universe() -> list[str]:
    syms = list(all_symbols())
    with cursor(commit=False) as c:
        c.execute("select distinct symbol from public.holdings")
        for (s,) in c.fetchall():
            if s not in syms:
                syms.append(s)
    return syms


def run(symbols: list[str]) -> None:
    t0 = time.time()
    ingest(symbols)
    print("classify:", classify_pending())
    print("results cards:", attach_results_cards())
    print("bios:", enrich_management_changes())
    print("alerts:", run_alerts(lookback_days=3))
    print(f"pipeline done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    run(sys.argv[1:] or universe())
