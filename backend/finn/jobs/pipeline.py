"""The push pipeline the scheduler runs: ingest -> classify -> results cards.

Usage: python -m finn.jobs.pipeline [SYMBOL ...]
Each stage only processes what's new, so a run with nothing new costs no LLM calls.
"""
import sys
import time

from finn.jobs.ingest import main as ingest
from finn.push.classify import classify_pending
from finn.push.results import attach_results_cards
from finn.universe import all_symbols


def run(symbols: list[str]) -> None:
    t0 = time.time()
    ingest(symbols)
    print("classify:", classify_pending())
    print("results cards:", attach_results_cards())
    print(f"pipeline done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    run(sys.argv[1:] or all_symbols())
