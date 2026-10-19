"""Tick -> OHLCV candle aggregation with explicit closing and gap reporting.

Timestamps are milliseconds (UTC). A candle covers ``[open_time, close_time)``.
A candle is only emitted once a trade at or after its ``close_time`` arrives
(or :meth:`flush` is called at a known boundary), so consumers only ever see
closed candles. Missing intervals are *reported*, never fabricated - unless
``emit_empty=True`` and the caller knows no trade was lost (contiguous trade
ids): then an interval without trades becomes a flat zero-volume candle at the
previous close, exactly like an exchange kline without trades.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from core.domain import Candle


@dataclass
class AggregatorStats:
    trades: int = 0
    rejected_out_of_order: int = 0
    rejected_invalid: int = 0
    candles_closed: int = 0
    empty_intervals: int = 0
    missing_intervals: int = 0
    gaps: list[tuple[int, int]] = field(default_factory=list)  # (from_open_time, to_open_time) exclusive


class CandleAggregator:
    def __init__(self, symbol: str, timeframe: str, timeframe_ms: int, emit_empty: bool = False):
        self.symbol = symbol
        self.emit_empty = emit_empty
        self._last_close: float | None = None
        self.timeframe = timeframe
        self.timeframe_ms = timeframe_ms
        self.stats = AggregatorStats()
        self._open_time: int | None = None
        self._o = self._h = self._l = self._c = 0.0
        self._v = 0.0
        self._last_closed_open_time: int | None = None

    def seed_last_closed(self, open_time: int, close: float | None = None) -> None:
        """Tell the aggregator which candle was the last closed one (e.g. from warmup)."""
        self._last_closed_open_time = open_time
        self._last_close = close

    def bucket(self, ts_ms: int) -> int:
        return ts_ms - ts_ms % self.timeframe_ms

    def on_trade(self, price: float, quantity: float, ts_ms: int) -> list[Candle]:
        """Add a trade. Returns the candles that closed because of it (0 or 1)."""
        if not (math.isfinite(price) and math.isfinite(quantity)) or price <= 0 or quantity < 0:
            self.stats.rejected_invalid += 1
            return []
        bucket = self.bucket(ts_ms)
        if self._open_time is not None and bucket < self._open_time:
            self.stats.rejected_out_of_order += 1
            return []
        if self._last_closed_open_time is not None and bucket <= self._last_closed_open_time:
            self.stats.rejected_out_of_order += 1
            return []
        self.stats.trades += 1

        closed: list[Candle] = []
        if self._open_time is not None and bucket > self._open_time:
            closed.append(self._close_current())
        if self._open_time is None:
            closed.extend(self._start(bucket, price, quantity))
        else:
            self._h = max(self._h, price)
            self._l = min(self._l, price)
            self._c = price
            self._v += quantity
        return closed

    def flush(self, now_ms: int) -> list[Candle]:
        """Close the current candle if ``now_ms`` is past its end (no trade needed)."""
        if self._open_time is not None and now_ms >= self._open_time + self.timeframe_ms:
            return [self._close_current()]
        return []

    def _start(self, bucket: int, price: float, quantity: float) -> list[Candle]:
        empty: list[Candle] = []
        if self._last_closed_open_time is not None:
            expected = self._last_closed_open_time + self.timeframe_ms
            if bucket > expected:
                missing = (bucket - expected) // self.timeframe_ms
                if self.emit_empty and self._last_close is not None:
                    for k in range(missing):
                        start = expected + k * self.timeframe_ms
                        c = self._last_close
                        empty.append(
                            Candle(self.symbol, self.timeframe, start, start + self.timeframe_ms, c, c, c, c, 0.0, True)
                        )
                    self.stats.empty_intervals += missing
                    self._last_closed_open_time = bucket - self.timeframe_ms
                else:
                    self.stats.missing_intervals += missing
                    self.stats.gaps.append((expected, bucket))
        self._open_time = bucket
        self._o = self._h = self._l = self._c = price
        self._v = quantity
        return empty

    def _close_current(self) -> Candle:
        assert self._open_time is not None
        candle = Candle(
            symbol=self.symbol,
            timeframe=self.timeframe,
            open_time=self._open_time,
            close_time=self._open_time + self.timeframe_ms,
            open=self._o,
            high=self._h,
            low=self._l,
            close=self._c,
            volume=self._v,
            is_closed=True,
        )
        self._last_closed_open_time = self._open_time
        self._last_close = self._c
        self._open_time = None
        self.stats.candles_closed += 1
        return candle


def resample(candles: list[Candle], timeframe: str, timeframe_ms: int) -> list[Candle]:
    """Aggregate closed lower-timeframe candles into a higher timeframe.

    Only complete buckets (all sub-candles present) are returned, so a partial
    higher-timeframe candle can never leak into a signal.
    """
    if not candles:
        return []
    base_ms = candles[0].close_time - candles[0].open_time
    if timeframe_ms % base_ms:
        raise ValueError("target timeframe must be a multiple of the source timeframe")
    per_bucket = timeframe_ms // base_ms
    groups: dict[int, list[Candle]] = {}
    for c in candles:
        groups.setdefault(c.open_time - c.open_time % timeframe_ms, []).append(c)
    result = []
    for start in sorted(groups):
        group = sorted(groups[start], key=lambda c: c.open_time)
        if len(group) != per_bucket:
            continue
        result.append(
            Candle(
                symbol=group[0].symbol,
                timeframe=timeframe,
                open_time=start,
                close_time=start + timeframe_ms,
                open=group[0].open,
                high=max(c.high for c in group),
                low=min(c.low for c in group),
                close=group[-1].close,
                volume=sum(c.volume for c in group),
            )
        )
    return result


def validate_candle(candle: Candle) -> str | None:
    """Return a reason string if the candle is unusable, else None."""
    values = (candle.open, candle.high, candle.low, candle.close, candle.volume)
    if not all(math.isfinite(v) for v in values):
        return "non-finite value"
    if min(candle.open, candle.high, candle.low, candle.close) <= 0:
        return "non-positive price"
    if candle.volume < 0:
        return "negative volume"
    if candle.high < max(candle.open, candle.close) or candle.low > min(candle.open, candle.close):
        return "inconsistent OHLC"
    if candle.close_time <= candle.open_time:
        return "close_time <= open_time"
    if not candle.is_closed:
        return "candle not closed"
    return None
