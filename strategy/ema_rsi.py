"""EMA/RSI trend strategy (one instance per symbol).

Rules (all evaluated on *closed* candles only):

* ``signal_mode = "crossover"`` (default): an entry needs a fresh EMA cross on
  this bar - fast crosses above slow (long) / below slow (short).
* ``signal_mode = "state"``: an entry only needs fast > slow (long) or
  fast < slow (short); duplicates are prevented by the position context.
* Long entry additionally needs ``RSI >= rsi_long_min``; short entry needs
  ``RSI <= rsi_short_max`` and ``enable_shorts``.
* Exit a long when fast < slow (state) / crosses below (crossover); vice versa
  for shorts. Exits are never blocked by the cooldown.
* Protective stop for entries: ``close -/+ atr_stop_multiple * ATR``.
* After any signal, new *entries* are suppressed for ``cooldown_bars`` bars.
* No signal is produced before ``warmup_bars`` closed candles have been seen.

No confidence score is emitted: there is no calibrated basis for one.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.config import StrategyConfig
from core.domain import Candle, Signal, SignalAction
from indicators.atr import ATR
from indicators.ema import EMA
from indicators.rsi import RSI

NAME = "ema_rsi"


@dataclass(frozen=True, slots=True)
class StrategyContext:
    position: str | None  # "LONG" | "SHORT" | None
    enable_shorts: bool
    allow_reversal: bool = False


@dataclass(frozen=True, slots=True)
class IndicatorValues:
    fast: float | None
    slow: float | None
    rsi: float | None
    atr: float | None


class EmaRsiStrategy:
    def __init__(self, symbol: str, params: StrategyConfig):
        self.symbol = symbol
        self.params = params
        self._fast = EMA(params.fast_period)
        self._slow = EMA(params.slow_period)
        self._rsi = RSI(params.rsi_period)
        self._atr = ATR(params.atr_period)
        self._prev_diff: float | None = None
        self._bars_seen = 0
        self._last_signal_bar: int | None = None
        self._last_candle_open: int | None = None

    @property
    def ready(self) -> bool:
        return self._bars_seen >= self.params.warmup_bars and all(
            i.ready for i in (self._fast, self._slow, self._rsi, self._atr)
        )

    @property
    def indicators(self) -> IndicatorValues:
        return IndicatorValues(self._fast.value, self._slow.value, self._rsi.value, self._atr.value)

    def generate_signals(self, candle: Candle, context: StrategyContext) -> list[Signal]:
        if candle.symbol != self.symbol:
            raise ValueError(f"strategy for {self.symbol} received candle for {candle.symbol}")
        if not candle.is_closed:
            raise ValueError("strategy only accepts closed candles")
        if self._last_candle_open is not None and candle.open_time <= self._last_candle_open:
            return []  # duplicate / out of order candle: ignore, never re-signal
        self._last_candle_open = candle.open_time

        fast = self._fast.update(candle.close)
        slow = self._slow.update(candle.close)
        rsi = self._rsi.update(candle.close)
        atr = self._atr.update(candle.high, candle.low, candle.close)
        self._bars_seen += 1

        prev_diff = self._prev_diff
        diff = None if fast is None or slow is None else fast - slow
        self._prev_diff = diff
        if not self.ready or diff is None or rsi is None or atr is None:
            return []

        p = self.params
        if p.signal_mode == "crossover":
            if prev_diff is None:
                return []
            bull = prev_diff <= 0 < diff
            bear = prev_diff >= 0 > diff
        else:
            bull = diff > 0
            bear = diff < 0

        signals: list[Signal] = []
        exit_long = context.position == "LONG" and diff < 0
        exit_short = context.position == "SHORT" and diff > 0
        if exit_long or exit_short:
            signals.append(
                self._signal(candle, SignalAction.EXIT, f"EMA{p.fast_period}/{p.slow_period} trend reversed")
            )
            if not context.allow_reversal:
                self._last_signal_bar = self._bars_seen
                return signals

        if self._in_cooldown():
            return signals
        flat_or_reversing = context.position is None or bool(signals)
        if not flat_or_reversing:
            return signals

        if bull and rsi >= p.rsi_long_min and context.position != "LONG":
            stop = candle.close - p.atr_stop_multiple * atr
            if stop > 0:
                signals.append(
                    self._signal(
                        candle,
                        SignalAction.ENTER_LONG,
                        f"EMA{p.fast_period}>EMA{p.slow_period} ({p.signal_mode}), RSI={rsi:.1f}>={p.rsi_long_min}",
                        stop,
                    )
                )
        elif bear and context.enable_shorts and rsi <= p.rsi_short_max and context.position != "SHORT":
            stop = candle.close + p.atr_stop_multiple * atr
            signals.append(
                self._signal(
                    candle,
                    SignalAction.ENTER_SHORT,
                    f"EMA{p.fast_period}<EMA{p.slow_period} ({p.signal_mode}), RSI={rsi:.1f}<={p.rsi_short_max}",
                    stop,
                )
            )
        if signals:
            self._last_signal_bar = self._bars_seen
        return signals

    def _in_cooldown(self) -> bool:
        if self._last_signal_bar is None or self.params.cooldown_bars == 0:
            return False
        return self._bars_seen - self._last_signal_bar <= self.params.cooldown_bars

    def _signal(self, candle: Candle, action: SignalAction, reason: str, stop: float | None = None) -> Signal:
        return Signal(
            symbol=candle.symbol,
            action=action,
            price=candle.close,
            timestamp=candle.close_time,
            strategy=NAME,
            reason=reason,
            stop_price=stop,
            signal_id=f"{NAME}:{candle.symbol}:{candle.close_time}:{action.value}",
        )
