"""Demo universe: the seeded portfolio and the pre-warmed research set.

Nothing in the engine depends on this list. Every source works on any NSE
symbol; this is only what new accounts are seeded with and what we pre-warm.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Holding:
    symbol: str      # NSE symbol, as on nseindia.com
    sector: str
    size: str        # Large / Mid / Small
    weight: float    # % of notional book


NOTIONAL_BOOK_INR = 50_00_000  # ₹50L

# India's seven largest listed companies by market value (screener market caps,
# 12 Nov 2026): the household names. Weighted by market cap, like an index.
PORTFOLIO: list[Holding] = [
    Holding("RELIANCE", "Conglomerate", "Large", 22.5),
    Holding("BHARTIARTL", "Telecom", "Large", 16.5),
    Holding("HDFCBANK", "Private bank", "Large", 15.5),
    Holding("ICICIBANK", "Private bank", "Large", 14.0),
    Holding("SBIN", "PSU bank", "Large", 12.0),
    Holding("TCS", "IT services", "Large", 11.0),
    Holding("BAJFINANCE", "NBFC", "Large", 8.5),
]

# HAL was swapped for BEL (same sector): HAL had 1 transcript in 13 months and
# its Sep-2026 quarter was not yet reported at data-check time (11 Nov 2026).
RESEARCH_SET: list[str] = ["BEL", "TITAN", "ASIANPAINT", "KPITTECH"]

assert abs(sum(h.weight for h in PORTFOLIO) - 100.0) < 1e-6, "weights must sum to 100"


def all_symbols() -> list[str]:
    return [h.symbol for h in PORTFOLIO] + RESEARCH_SET
