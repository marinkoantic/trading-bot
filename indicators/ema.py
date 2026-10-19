"""Exponential moving average.

Seeded with the simple average of the first ``period`` values (the common
TA-Lib / TradingView convention). No value is produced before ``period``
inputs have been seen.
"""

import math


class EMA:
    def __init__(self, period: int):
        if period < 1:
            raise ValueError("EMA period must be >= 1")
        self.period = period
        self.alpha = 2 / (period + 1)
        self.value: float | None = None
        self._seed: list[float] = []

    @property
    def ready(self) -> bool:
        return self.value is not None

    def update(self, price: float) -> float | None:
        if not math.isfinite(price):
            raise ValueError(f"EMA input must be finite, got {price!r}")
        if self.value is None:
            self._seed.append(price)
            if len(self._seed) == self.period:
                self.value = sum(self._seed) / self.period
                self._seed = []
            return self.value
        self.value = self.value + self.alpha * (price - self.value)
        return self.value


def calculate_ema(prices, period):
    """Batch helper kept for backwards compatibility. Returns None during warmup."""
    ema = EMA(period)
    result = None
    for price in prices:
        result = ema.update(price)
    return result
