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

# 20 companies across 18 sectors and all three sizes (market caps from screener,
# 14 Nov 2026): a large-cap core of household names, plus mid and small caps
# that move differently and file differently. Weighted by size tier, not pure
# market cap, so the smaller names still matter to the book.
PORTFOLIO: list[Holding] = [
    Holding("RELIANCE", "Conglomerate", "Large", 11.0),
    Holding("HDFCBANK", "Private bank", "Large", 10.0),
    Holding("BHARTIARTL", "Telecom", "Large", 8.0),
    Holding("ICICIBANK", "Private bank", "Large", 8.0),
    Holding("TCS", "IT services", "Large", 7.0),
    Holding("SBIN", "PSU bank", "Large", 6.0),
    Holding("ITC", "FMCG", "Large", 5.0),
    Holding("LT", "Capital goods", "Large", 5.0),
    Holding("BAJFINANCE", "NBFC", "Large", 5.0),
    Holding("SUNPHARMA", "Pharma", "Large", 4.0),
    Holding("MARUTI", "Auto", "Large", 4.0),
    Holding("ETERNAL", "Internet / delivery", "Large", 4.0),
    Holding("TRENT", "Retail", "Large", 4.0),
    Holding("TATASTEEL", "Metals", "Large", 3.0),
    Holding("POLYCAB", "Cables", "Large", 3.0),
    Holding("DIXON", "Electronics manufacturing", "Mid", 3.0),
    Holding("PERSISTENT", "IT services", "Mid", 3.0),
    Holding("SUZLON", "Renewables", "Mid", 3.0),
    Holding("CDSL", "Capital markets", "Small", 2.0),
    Holding("IEX", "Power exchange", "Small", 2.0),
]

# HAL was swapped for BEL (same sector): HAL had 1 transcript in 13 months and
# its Sep-2026 quarter was not yet reported at data-check time (11 Nov 2026).
RESEARCH_SET: list[str] = ["BEL", "TITAN", "ASIANPAINT", "KPITTECH"]

assert abs(sum(h.weight for h in PORTFOLIO) - 100.0) < 1e-6, "weights must sum to 100"


def all_symbols() -> list[str]:
    return [h.symbol for h in PORTFOLIO] + RESEARCH_SET
