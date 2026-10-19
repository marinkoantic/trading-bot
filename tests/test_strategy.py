import pytest

from core.domain import SignalAction
from strategy.ema_rsi import EmaRsiStrategy, StrategyContext
from tests.helpers import candle, config, series

FLAT = StrategyContext(position=None, enable_shorts=False)


def _params(**kw):
    overrides = [f"strategy.{k}={v}" for k, v in kw.items()]
    return config(
        "strategy.fast_period=3",
        "strategy.slow_period=6",
        "strategy.rsi_period=3",
        "strategy.atr_period=3",
        "strategy.cooldown_bars=0",
        "market.warmup_candles=10",
        *overrides,
    ).strategy


def _run(strategy, candles, ctx=FLAT):
    out = []
    for c in candles:
        out.extend(strategy.generate_signals(c, ctx))
    return out


def down_then_up():
    return [100 - i for i in range(15)] + [86 + 2 * i for i in range(10)]


def test_no_signal_during_warmup():
    s = EmaRsiStrategy("BTCUSDT", _params())
    candles = series([100 + i for i in range(s.params.warmup_bars - 1)])
    assert _run(s, candles) == []
    assert not s.ready


def test_crossover_long_entry_with_atr_stop_once():
    s = EmaRsiStrategy("BTCUSDT", _params())
    signals = _run(s, series(down_then_up()))
    entries = [x for x in signals if x.action is SignalAction.ENTER_LONG]
    assert len(entries) == 1  # crossover happens once
    sig = entries[0]
    assert sig.stop_price is not None and 0 < sig.stop_price < sig.price
    assert sig.timestamp > 0 and sig.signal_id.endswith("ENTER_LONG")


def test_state_mode_signals_every_bar_while_flat():
    s = EmaRsiStrategy("BTCUSDT", _params(signal_mode="'state'"))
    signals = _run(s, series(down_then_up()))
    assert len([x for x in signals if x.action is SignalAction.ENTER_LONG]) > 1


def test_exit_when_long_and_trend_reverses_and_shorts_disabled():
    s = EmaRsiStrategy("BTCUSDT", _params())
    closes = [100 + 2 * i for i in range(15)] + [128 - 3 * i for i in range(10)]
    signals = _run(s, series(closes), StrategyContext(position="LONG", enable_shorts=False))
    assert signals and signals[0].action is SignalAction.EXIT
    assert not any(x.action is SignalAction.ENTER_SHORT for x in signals)


def test_short_entry_only_when_enabled():
    closes = [100 + 2 * i for i in range(15)] + [128 - 3 * i for i in range(10)]
    s = EmaRsiStrategy("BTCUSDT", _params())
    shorts = _run(s, series(closes), StrategyContext(position=None, enable_shorts=True))
    assert [x.action for x in shorts] == [SignalAction.ENTER_SHORT]
    assert shorts[0].stop_price > shorts[0].price


def test_cooldown_blocks_entries_not_exits():
    p = _params(cooldown_bars=50, signal_mode="'state'")
    s = EmaRsiStrategy("BTCUSDT", p)
    signals = _run(s, series(down_then_up()))
    assert len([x for x in signals if x.action is SignalAction.ENTER_LONG]) == 1


def test_duplicate_or_old_candles_are_ignored_and_symbols_isolated():
    s = EmaRsiStrategy("BTCUSDT", _params(signal_mode="'state'"))
    candles = series(down_then_up())
    _run(s, candles)
    assert s.generate_signals(candles[-1], FLAT) == []
    with pytest.raises(ValueError):
        s.generate_signals(candle(99, 10, symbol="ETHUSDT"), FLAT)
