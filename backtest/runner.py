"""Backtest runner: replays closed candles through the same engine as paper trading.

Bars of all symbols are merged in time order ``(open_time, symbol)``. For each
bar, pending orders are matched at the bar's open (and stops intrabar), then the
bar's close is processed - so a signal from bar *t* can only fill on bar *t+1*.
Costs (fees, spread, slippage) are always applied. Randomness uses
``run.seed``, making runs reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass

from analytics.performance import PerformanceReport, build_report, buy_and_hold_pct
from app.engine import TradingEngine
from core.config import AppConfig, ConfigError, TradingMode
from core.domain import Candle
from data.klines import DataError, DataQuality, data_quality, dedupe_sorted
from persistence.store import Store


@dataclass
class BacktestResult:
    run_id: str
    engine: TradingEngine
    report: PerformanceReport
    quality: dict[str, DataQuality]


def run_backtest(
    cfg: AppConfig, candles_by_symbol: dict[str, list[Candle]], store: Store, meta: dict | None = None
) -> BacktestResult:
    if cfg.run.mode is not TradingMode.BACKTEST:
        raise ConfigError("run_backtest requires run.mode = 'backtest' (use --profile backtest)")
    missing = set(cfg.run.symbols) - set(candles_by_symbol)
    if missing:
        raise DataError(f"no data for configured symbol(s): {sorted(missing)}")
    quality = {}
    bars: list[Candle] = []
    for symbol in cfg.run.symbols:
        candles = [c for c in candles_by_symbol[symbol] if c.symbol == symbol]
        wrong_tf = [c for c in candles if c.close_time - c.open_time != cfg.timeframe_ms]
        if wrong_tf:
            raise DataError(f"{symbol}: {len(wrong_tf)} candle(s) do not match timeframe {cfg.run.timeframe}")
        quality[symbol] = data_quality(symbol, candles, cfg.timeframe_ms)
        bars.extend(dedupe_sorted(candles))
    if not bars:
        raise DataError("no candles to backtest")
    bars.sort(key=lambda c: (c.open_time, c.symbol))

    run_meta = {
        "period": {"start": bars[0].open_time, "end": bars[-1].close_time},
        "bars": len(bars),
        "data_quality": {
            s: {"candles": q.candles, "missing": q.missing, "duplicates": q.duplicates, "invalid": q.invalid}
            for s, q in quality.items()
        },
        **(meta or {}),
    }
    run_id = store.create_run(cfg, run_meta)
    engine = TradingEngine(cfg, store, run_id)
    try:
        for candle in bars:
            engine.on_bar(candle)
        engine.ledger.check_invariants()
    except BaseException:
        store.finish_run(run_id, "failed")
        raise
    first_open = {s: next(c.open for c in bars if c.symbol == s) for s in cfg.run.symbols}
    last_close = {s: next(c.close for c in reversed(bars) if c.symbol == s) for s in cfg.run.symbols}
    bh = buy_and_hold_pct(first_open, last_close, cfg.costs.taker_fee_rate)
    store.finish_run(run_id, "completed", {"counters": dict(engine.counters), "buy_and_hold_pct": bh})
    report = build_report(store, run_id, cfg)
    return BacktestResult(run_id, engine, report, quality)
