"""Integration: Candle -> Indicator -> Strategy -> Risk -> Execution -> Portfolio -> Store."""

from dataclasses import replace
from decimal import Decimal as D

import pytest

from app.engine import TradingEngine
from backtest.runner import run_backtest
from core.config import ConfigError
from core.domain import OrderStatus, OrderType
from persistence.store import Store, rebuild_ledger
from tests.helpers import MINUTE, config, series

FAST = (
    "run.symbols=['BTCUSDT']",
    "strategy.fast_period=3",
    "strategy.slow_period=6",
    "strategy.rsi_period=3",
    "strategy.atr_period=3",
    "strategy.cooldown_bars=0",
    "market.warmup_candles=10",
)


def wave(n_cycles=3):
    closes = []
    for _ in range(n_cycles):
        closes += [100 - i for i in range(12)] + [88 + 2 * i for i in range(12)] + [110 - 2 * i for i in range(12)]
    return closes


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


def test_backtest_end_to_end_books_consistently(store):
    cfg = config(*FAST)
    result = run_backtest(cfg, {"BTCUSDT": series(wave())}, store)
    e = result.engine
    assert e.counters["signals"] > 0 and e.counters["fills"] > 0 and e.counters["trades"] > 0
    e.ledger.check_invariants()
    # every booked fill is persisted exactly once and rebuilding gives the identical ledger
    rebuilt = rebuild_ledger(store, result.run_id, cfg.account.start_cash)
    assert rebuilt.cash == e.ledger.cash and rebuilt.realized_pnl == e.ledger.realized_pnl
    assert rebuilt.fees_paid == e.ledger.fees_paid
    assert store.count("fills", result.run_id) == e.counters["fills"]
    r = result.report
    assert r.trades == store.count("trades", result.run_id)
    assert D(r.fees) > 0
    assert r.warnings  # few trades -> warning


def test_no_lookahead_entry_fills_at_next_bar_open(store):
    cfg = config(*FAST)
    candles = series(wave(1))
    result = run_backtest(cfg, {"BTCUSDT": candles}, store)
    sig = store.conn.execute(
        "SELECT * FROM signals WHERE run_id=? AND action='ENTER_LONG' AND outcome='ORDER_ACCEPTED' ORDER BY ts LIMIT 1",
        (result.run_id,),
    ).fetchone()
    assert sig is not None
    fill = store.conn.execute("SELECT * FROM fills WHERE run_id=? ORDER BY seq LIMIT 1", (result.run_id,)).fetchone()
    next_bar = next(c for c in candles if c.open_time == sig["ts"])
    assert fill["ts"] == next_bar.open_time  # filled on the bar after the signal bar
    assert D(fill["reference_price"]) == D(str(next_bar.open))
    assert D(fill["price"]) > D(fill["reference_price"])  # costs applied


def test_backtest_is_reproducible(store):
    cfg = config(*FAST, "costs.random_slippage_bps=5")
    a = run_backtest(cfg, {"BTCUSDT": series(wave())}, store)
    b = run_backtest(cfg, {"BTCUSDT": series(wave())}, store)
    assert a.report.final_equity == b.report.final_equity and a.report.trades == b.report.trades


def test_every_position_gets_a_protective_stop(store):
    cfg = config(*FAST)
    result = run_backtest(cfg, {"BTCUSDT": series(wave())}, store)
    entries = store.conn.execute(
        "SELECT COUNT(*) FROM orders WHERE run_id=? AND reduce_only=0 AND filled_quantity!='0'", (result.run_id,)
    ).fetchone()[0]
    stops = store.conn.execute(
        "SELECT COUNT(*) FROM orders WHERE run_id=? AND order_type='STOP_MARKET'", (result.run_id,)
    ).fetchone()[0]
    assert entries > 0 and stops >= entries
    assert not store.events(result.run_id, "NO_PROTECTIVE_STOP")


def test_multi_symbol_states_are_isolated(store):
    cfg = config(*FAST, "run.symbols=['BTCUSDT','ETHUSDT']")
    btc = series(wave())
    eth = series([200.0] * len(btc), symbol="ETHUSDT")  # flat: must never trade
    result = run_backtest(cfg, {"BTCUSDT": btc, "ETHUSDT": eth}, store)
    symbols = {r["symbol"] for r in store.conn.execute("SELECT symbol FROM fills WHERE run_id=?", (result.run_id,))}
    assert symbols == {"BTCUSDT"}
    solo = run_backtest(config(*FAST), {"BTCUSDT": btc}, Store(":memory:"))
    assert solo.engine.counters["signals"] == result.engine.counters["signals"]


def test_data_gap_and_invalid_candles_are_reported_not_traded(store):
    cfg = config(*FAST)
    candles = series(wave(1))
    candles = candles[:20] + candles[25:]  # 5 missing bars
    candles[30] = replace(candles[30], high=candles[30].low / 2)  # inconsistent OHLC
    result = run_backtest(cfg, {"BTCUSDT": candles}, store)
    assert store.events(result.run_id, "DATA_GAP")
    assert store.events(result.run_id, "DATA_INVALID")
    assert result.quality["BTCUSDT"].missing == 5
    assert any("data quality" in w for w in result.report.warnings)


def test_kill_switch_flattens_and_blocks_entries(store):
    cfg = config(*FAST, "risk.max_drawdown_pct=0.5", "risk.risk_per_trade_pct=5", "risk.max_position_notional_pct=50")
    closes = wave(1)[:30] + [110 - 5 * i for i in range(15)] + wave(2)
    result = run_backtest(cfg, {"BTCUSDT": series(closes)}, store)
    kills = store.events(result.run_id, "KILL_SWITCH")
    assert kills and "MAX_DRAWDOWN" in kills[0]["message"]
    kill_ts = kills[0]["ts"]
    late_entries = store.conn.execute(
        "SELECT COUNT(*) FROM orders WHERE run_id=? AND reduce_only=0 AND created_at>?", (result.run_id, kill_ts)
    ).fetchone()[0]
    assert late_entries == 0
    rejected = store.conn.execute(
        "SELECT outcome FROM signals WHERE run_id=? AND ts>? AND action LIKE 'ENTER%'", (result.run_id, kill_ts)
    ).fetchall()
    assert all("KILL_SWITCH" in r["outcome"] for r in rejected)
    assert not result.engine.ledger.positions


def test_resume_rebuilds_state_and_ignores_duplicates(tmp_path):
    cfg = config(*FAST)
    candles = series(wave())
    db = tmp_path / "run.db"
    store = Store(db)
    run_id = store.create_run(cfg)
    engine = TradingEngine(cfg, store, run_id)
    stop_at = None
    for i, c in enumerate(candles):
        engine.on_bar(c)
        if engine.ledger.positions:
            stop_at = i + 1
            break
    assert engine.ledger.positions, "test needs an open position at the crash point"
    before = (engine.ledger.cash, engine.ledger.position_qty("BTCUSDT"), engine.ledger.fees_paid)
    store.close()  # simulated crash: process gone, only the database survives

    store2 = Store(db)
    resumed = TradingEngine.resume(cfg, store2, run_id)
    assert (resumed.ledger.cash, resumed.ledger.position_qty("BTCUSDT"), resumed.ledger.fees_paid) == before
    stops = [o for o in resumed.broker.open_orders("BTCUSDT") if o.order_type is OrderType.STOP_MARKET]
    assert len(stops) == 1 and stops[0].quantity == abs(before[1])
    # re-delivering an already booked fill must not change anything
    fill, reason = store2.load_fills(run_id)[0]
    assert store2.save_fill(run_id, fill, reason) is False
    assert resumed.ledger.apply_fill(fill) is None
    resumed.warmup(candles[:stop_at])
    for c in candles[stop_at:]:
        resumed.on_bar(c)
    resumed.ledger.check_invariants()
    assert rebuild_ledger(store2, run_id, cfg.account.start_cash).cash == resumed.ledger.cash
    with pytest.raises(ConfigError):
        TradingEngine.resume(config(*FAST, "risk.max_open_positions=1"), store2, run_id)


def test_rejected_orders_are_logged_with_reason(store):
    cfg = config(*FAST, "account.start_cash=10")  # too little for min notional with 1% risk
    result = run_backtest(cfg, {"BTCUSDT": series(wave())}, store)
    rejects = store.events(result.run_id, "RISK_REJECT")
    assert rejects and all(r["message"] for r in rejects)
    assert store.count("fills", result.run_id) == 0
    assert all(
        o["status"] != OrderStatus.FILLED.value
        for o in store.conn.execute("SELECT status FROM orders WHERE run_id=?", (result.run_id,))
    )


def test_backtest_requires_backtest_mode(store):
    with pytest.raises(ConfigError):
        run_backtest(config(*FAST, profile="paper"), {"BTCUSDT": series(wave())}, store)


def test_timeframe_mismatch_rejected(store):
    from data.klines import DataError

    bad = [replace(c, close_time=c.open_time + 5 * MINUTE) for c in series(wave(1))]
    with pytest.raises(DataError):
        run_backtest(config(*FAST), {"BTCUSDT": bad}, store)


def test_partial_closes_are_grouped_into_round_trips(store):
    from analytics.performance import round_trips

    # tiny volume -> entries and exits are filled in several parts
    cfg = config(*FAST, "execution.max_volume_participation=0.5", "execution.order_timeout_bars=20")
    result = run_backtest(cfg, {"BTCUSDT": series(wave(), volume=3.0)}, store)
    journal = store.trades(result.run_id)
    trips = round_trips(journal)
    assert len(journal) > len(trips) >= 1
    assert result.report.trades == len(trips) and result.report.closing_fills == len(journal)
    assert sum(t["net_pnl"] for t in trips) == sum(D(t["net_pnl"]) for t in journal)


def test_exit_orders_do_not_time_out(store):
    cfg = config(*FAST, "execution.max_volume_participation=0.5", "execution.order_timeout_bars=1")
    result = run_backtest(cfg, {"BTCUSDT": series(wave(), volume=3.0)}, store)
    timed_out_exits = store.conn.execute(
        "SELECT COUNT(*) FROM orders WHERE run_id=? AND reduce_only=1 AND reject_reason='TIMEOUT_UNFILLED_REMAINDER'",
        (result.run_id,),
    ).fetchone()[0]
    assert timed_out_exits == 0
