"""End-of-day price & volume from Yahoo Finance (yfinance), plus the signals
the alert engine watches: day move %, volume vs N-day average."""
from __future__ import annotations

from dataclasses import dataclass, asdict

import pandas as pd
import yfinance as yf


def yahoo_symbol(nse_symbol: str) -> str:
    # Yahoo uses the NSE symbol + .NS; '&' is kept (e.g. M&M.NS), '-' is kept.
    return f"{nse_symbol}.NS"


def fetch_eod(symbols: list[str], period: str = "6mo") -> dict[str, pd.DataFrame]:
    """Daily OHLCV per NSE symbol. Missing/failed symbols are omitted."""
    tickers = [yahoo_symbol(s) for s in symbols]
    raw = yf.download(
        tickers, period=period, interval="1d", group_by="ticker",
        auto_adjust=False, progress=False, threads=True,
    )
    out: dict[str, pd.DataFrame] = {}
    for sym, tk in zip(symbols, tickers):
        try:
            # group_by="ticker" yields (ticker, field) MultiIndex columns, even for a single ticker
            df = raw[tk] if isinstance(raw.columns, pd.MultiIndex) else raw
        except KeyError:
            continue
        if "Close" not in df.columns:
            continue
        df = df.dropna(subset=["Close"])
        if not df.empty:
            out[sym] = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    return out


@dataclass
class EodSignal:
    symbol: str
    date: str
    close: float
    prev_close: float
    change_pct: float
    volume: int
    avg_volume: float       # mean of the previous `window` sessions (excludes today)
    volume_ratio: float     # today's volume / avg_volume

    def to_dict(self) -> dict:
        return asdict(self)


def compute_signal(symbol: str, df: pd.DataFrame, window: int = 20) -> EodSignal | None:
    if len(df) < window + 2:
        return None
    last, prev = df.iloc[-1], df.iloc[-2]
    avg_vol = float(df["Volume"].iloc[-(window + 1):-1].mean())
    return EodSignal(
        symbol=symbol,
        date=df.index[-1].strftime("%Y-%m-%d"),
        close=round(float(last["Close"]), 2),
        prev_close=round(float(prev["Close"]), 2),
        change_pct=round((float(last["Close"]) / float(prev["Close"]) - 1) * 100, 2),
        volume=int(last["Volume"]),
        avg_volume=round(avg_vol, 0),
        volume_ratio=round(float(last["Volume"]) / avg_vol, 2) if avg_vol else 0.0,
    )
