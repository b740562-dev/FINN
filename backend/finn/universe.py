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

PORTFOLIO: list[Holding] = [
    Holding("RELIANCE", "Conglomerate", "Large", 10.0),
    Holding("HDFCBANK", "Private bank", "Large", 10.0),
    Holding("INFY", "IT services", "Large", 8.0),
    Holding("ITC", "FMCG", "Large", 7.0),
    Holding("LT", "Capital goods", "Large", 7.0),
    Holding("BHARTIARTL", "Telecom", "Large", 7.0),
    Holding("SUNPHARMA", "Pharma", "Large", 5.0),
    Holding("MARUTI", "Auto", "Large", 5.0),
    Holding("TATASTEEL", "Metals", "Large", 5.0),
    Holding("BAJFINANCE", "NBFC", "Large", 5.0),
    Holding("ETERNAL", "Internet / delivery", "Large", 4.5),
    Holding("TRENT", "Retail", "Large", 5.0),
    Holding("DIXON", "Electronics manufacturing", "Mid", 4.0),
    Holding("POLYCAB", "Cables", "Mid", 4.0),
    Holding("PERSISTENT", "IT services", "Mid", 4.0),
    Holding("SUZLON", "Renewables", "Mid", 3.5),
    Holding("CDSL", "Capital markets", "Mid", 3.0),
    Holding("IEX", "Power exchange", "Small", 3.0),
]

# HAL was swapped for BEL (same sector): HAL had 1 transcript in 13 months and
# its Sep-2026 quarter was not yet reported at data-check time (11 Nov 2026).
RESEARCH_SET: list[str] = ["BEL", "TITAN", "ASIANPAINT", "KPITTECH"]

assert abs(sum(h.weight for h in PORTFOLIO) - 100.0) < 1e-6, "weights must sum to 100"


def all_symbols() -> list[str]:
    return [h.symbol for h in PORTFOLIO] + RESEARCH_SET
