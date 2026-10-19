from decimal import Decimal as D

from core.domain import Fill, Side, Signal, SignalAction
from portfolio.ledger import Ledger
from risk.risk_engine import DAY_MS, RiskEngine
from tests.helpers import T0, config


def sig(action=SignalAction.ENTER_LONG, price=100.0, stop=98.0, symbol="BTCUSDT", ts=T0):
    return Signal(symbol, action, price, ts, "test", "r", stop, "s1")


def zero_cost(*extra):
    return config("costs.taker_fee_rate=0", "costs.half_spread_bps=0", "costs.slippage_bps=0", *extra)


def test_stop_based_sizing_uses_stop_distance_not_entry_price():
    engine = RiskEngine(zero_cost())
    d = engine.evaluate(sig(price=100.0, stop=98.0), Ledger(D("1000")))
    # risk budget 1% of 1000 = 10; per unit risk 2 -> 5 units (notional 500 -> capped by 25% = 250 -> 2.5)
    assert d.approved
    assert d.quantity == D("2.5")
    assert d.details["binding_cap"] == "position_notional"
    d2 = engine.evaluate(sig(price=100.0, stop=60.0), Ledger(D("1000")))
    assert d2.quantity == D("0.25") and d2.details["binding_cap"] == "risk"  # 10 / 40


def test_costs_reduce_size():
    plain = RiskEngine(zero_cost()).evaluate(sig(stop=60.0), Ledger(D("1000"))).quantity
    costly = RiskEngine(config()).evaluate(sig(stop=60.0), Ledger(D("1000"))).quantity
    assert costly < plain


def test_min_notional_never_bumps_size():
    engine = RiskEngine(zero_cost())
    d = engine.evaluate(sig(price=100.0, stop=1.0), Ledger(D("100")))  # budget 1 / 99 -> notional ~1 < 5
    assert not d.approved and d.reason.startswith("BELOW_MIN")


def test_rejections_fail_closed():
    engine = RiskEngine(zero_cost())
    lg = Ledger(D("1000"))
    assert engine.evaluate(sig(stop=None), lg).reason == "MISSING_STOP"
    assert engine.evaluate(sig(stop=101.0), lg).reason == "STOP_ON_WRONG_SIDE"
    assert engine.evaluate(sig(price=float("nan")), lg).reason == "INVALID_PRICE"
    assert engine.evaluate(sig(action=SignalAction.ENTER_SHORT, stop=102.0), lg).reason == "SHORTS_DISABLED"
    assert engine.evaluate(sig(symbol="XRPUSDT"), lg).reason == "UNKNOWN_SYMBOL"
    assert engine.evaluate(sig(action=SignalAction.EXIT, stop=None), lg).approved


def test_position_and_exposure_limits():
    engine = RiskEngine(zero_cost("risk.max_open_positions=1"))
    lg = Ledger(D("1000"))
    lg.apply_fill(Fill("f", "o", "ETHUSDT", Side.BUY, D("1"), D("100"), D("0"), T0, D("100")))
    assert engine.evaluate(sig(), lg).reason == "MAX_OPEN_POSITIONS"
    lg2 = Ledger(D("1000"))
    lg2.apply_fill(Fill("f", "o", "BTCUSDT", Side.BUY, D("1"), D("100"), D("0"), T0, D("100")))
    assert RiskEngine(zero_cost()).evaluate(sig(), lg2).reason == "POSITION_ALREADY_OPEN"
    lg3 = Ledger(D("1000"))
    lg3.apply_fill(Fill("f", "o", "ETHUSDT", Side.BUY, D("4.9"), D("100"), D("0"), T0, D("100")))
    d = RiskEngine(zero_cost()).evaluate(sig(), lg3)  # 490 used of 500 total exposure -> room 10 -> 0.1 units
    assert d.approved and d.quantity == D("0.1") and d.details["binding_cap"] == "total_exposure"


def test_kill_switch_drawdown_latches_until_reset():
    engine = RiskEngine(zero_cost())
    assert engine.update_equity(T0, D("1000")) is None
    reason = engine.update_equity(T0 + 1, D("790"))
    assert reason and reason.startswith("MAX_DRAWDOWN")
    assert engine.evaluate(sig(ts=T0 + 2), Ledger(D("790"))).reason.startswith("KILL_SWITCH")
    assert engine.update_equity(T0 + 5 * DAY_MS, D("2000")) is None
    assert engine.entries_blocked(T0 + 5 * DAY_MS)  # still latched on a new day
    engine.reset_kill_switch()
    assert engine.entries_blocked(T0 + 5 * DAY_MS) is None


def test_daily_loss_blocks_until_next_utc_day():
    engine = RiskEngine(zero_cost())
    day_start = T0 - T0 % DAY_MS
    engine.update_equity(day_start + 1, D("1000"))
    assert engine.update_equity(day_start + 2, D("969")).startswith("MAX_DAILY_LOSS")
    assert engine.entries_blocked(day_start + 3) == "DAILY_LOSS_LIMIT"
    engine.update_equity(day_start + DAY_MS, D("969"))
    assert engine.entries_blocked(day_start + DAY_MS) is None
