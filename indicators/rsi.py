"""Relative Strength Index with Wilder smoothing (J. Welles Wilder, 1978).

The first average gain/loss is the simple mean of the first ``period`` price
changes; afterwards ``avg = (avg * (period - 1) + current) / period``.
Needs ``period + 1`` prices before the first value. A completely flat series
returns 50 (neutral) instead of 100.
"""

import math


class RSI:
    def __init__(self, period: int = 14):
        if period < 2:
            raise ValueError("RSI period must be >= 2")
        self.period = period
        self.value: float | None = None
        self._prev: float | None = None
        self._gains: list[float] = []
        self._losses: list[float] = []
        self._avg_gain: float | None = None
        self._avg_loss: float | None = None

    @property
    def ready(self) -> bool:
        return self.value is not None

    def update(self, price: float) -> float | None:
        if not math.isfinite(price):
            raise ValueError(f"RSI input must be finite, got {price!r}")
        if self._prev is None:
            self._prev = price
            return None
        delta = price - self._prev
        self._prev = price
        gain, loss = max(delta, 0.0), max(-delta, 0.0)

        if self._avg_gain is None:
            self._gains.append(gain)
            self._losses.append(loss)
            if len(self._gains) < self.period:
                return None
            self._avg_gain = sum(self._gains) / self.period
            self._avg_loss = sum(self._losses) / self.period
            self._gains, self._losses = [], []
        else:
            n = self.period
            self._avg_gain = (self._avg_gain * (n - 1) + gain) / n
            self._avg_loss = (self._avg_loss * (n - 1) + loss) / n

        self.value = _rsi_from_averages(self._avg_gain, self._avg_loss)
        return self.value


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 50.0 if avg_gain == 0 else 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def calculate_rsi(prices, period=14):
    """Batch helper kept for backwards compatibility. Returns None during warmup."""
    rsi = RSI(period)
    result = None
    for price in prices:
        result = rsi.update(price)
    return result
