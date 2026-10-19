"""Average True Range with Wilder smoothing.

True range needs the previous close, so the first bar only primes the
indicator; the first ATR is the mean of the next ``period`` true ranges.
"""

import math


class ATR:
    def __init__(self, period: int = 14):
        if period < 1:
            raise ValueError("ATR period must be >= 1")
        self.period = period
        self.value: float | None = None
        self._prev_close: float | None = None
        self._seed: list[float] = []

    @property
    def ready(self) -> bool:
        return self.value is not None

    def update(self, high: float, low: float, close: float) -> float | None:
        if not all(math.isfinite(v) for v in (high, low, close)):
            raise ValueError("ATR inputs must be finite")
        if high < low:
            raise ValueError(f"ATR: high {high} < low {low}")
        prev, self._prev_close = self._prev_close, close
        if prev is None:
            return None
        tr = max(high - low, abs(high - prev), abs(low - prev))
        if self.value is None:
            self._seed.append(tr)
            if len(self._seed) == self.period:
                self.value = sum(self._seed) / self.period
                self._seed = []
            return self.value
        self.value = (self.value * (self.period - 1) + tr) / self.period
        return self.value
