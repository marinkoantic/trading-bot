"""Deterministic fixtures shared by the tests."""

from __future__ import annotations

from dataclasses import replace

from core.config import AppConfig, load_config
from core.domain import Candle

MINUTE = 60_000
T0 = 1_700_000_000_000 - 1_700_000_000_000 % MINUTE  # aligned to a minute, UTC


def config(*overrides: str, profile: str = "backtest") -> AppConfig:
    return load_config(profile, list(overrides), environ={})


def candle(
    i: int, close: float, symbol: str = "BTCUSDT", *, open_=None, high=None, low=None, volume: float = 1_000_000.0
) -> Candle:
    o = close if open_ is None else open_
    h = max(o, close) if high is None else high
    lo = min(o, close) if low is None else low
    return Candle(symbol, "1m", T0 + i * MINUTE, T0 + (i + 1) * MINUTE, o, h, lo, close, volume)


def series(closes: list[float], symbol: str = "BTCUSDT", start: int = 0, volume: float = 1_000_000.0) -> list[Candle]:
    """Candles whose open equals the previous close (no gaps between bars)."""
    out: list[Candle] = []
    prev = closes[0]
    for k, c in enumerate(closes):
        hi, lo = max(prev, c) * 1.001, min(prev, c) * 0.999
        out.append(candle(start + k, c, symbol, open_=prev, high=hi, low=lo, volume=volume))
        prev = c
    return out


def shifted(c: Candle, **changes) -> Candle:
    return replace(c, **changes)
