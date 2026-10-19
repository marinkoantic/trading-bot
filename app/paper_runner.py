"""Paper-trading session: live public market data -> engine. PAPER_ONLY.

Threads:
* ``feed`` - WebSocket client, pushes trades into a bounded queue.
* main/consumer - the only thread that touches the engine (no shared mutable
  state between threads besides the queue).

Candle integrity: the first live candle of each symbol is incomplete (the
session connected in the middle of it), so it is never used - it and any
candle missed between warmup and connect are back-filled from the public REST
klines once closed. A minute without trades becomes a zero-volume candle
(like an exchange kline) only if the trade-id sequence proves nothing was
missed; after a sequence gap the interval is reported as DATA_GAP instead.

Backpressure: if the queue is full for 1 s the trade is dropped, counted and
recorded as a DATA_GAP event, because a silently missing trade would corrupt
the candle.

Shutdown (stop event, SIGINT/SIGTERM or ``duration`` reached): stop the feed,
join it with a timeout, process what is still queued (bounded), write a final
equity snapshot and mark the run ``stopped``. Open positions stay open and are
restored with ``paper --resume <run_id>``.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import asdict

from app.engine import TradingEngine
from candles.aggregator import CandleAggregator
from core.config import AppConfig, ConfigError, TradingMode
from data.klines import DataError, data_quality, fetch_klines, fetch_recent
from market.live_feed import LiveFeed, TradeTick
from persistence.store import Store

log = logging.getLogger("paper")

HEALTH_INTERVAL_S = 60
DRAIN_TIMEOUT_S = 5
JOIN_TIMEOUT_S = 10


def run_paper(
    cfg: AppConfig,
    store: Store,
    *,
    stop_event: threading.Event | None = None,
    duration_s: float | None = None,
    resume_run_id: str | None = None,
    fetch: Callable = fetch_recent,
    fetch_range: Callable = fetch_klines,
    feed_factory: Callable = LiveFeed,
    on_started: Callable[[TradingEngine], None] | None = None,
) -> str:
    if cfg.run.mode is not TradingMode.PAPER:
        raise ConfigError("paper sessions require run.mode = 'paper'")
    stop = stop_event or threading.Event()

    if resume_run_id:
        engine = TradingEngine.resume(cfg, store, resume_run_id)
    else:
        engine = TradingEngine(cfg, store, store.create_run(cfg, {"kind": "paper", "duration_s": duration_s}))
    run_id = engine.run_id
    status = "failed"
    feed = None
    feed_thread = None
    try:
        aggregators = _warmup(cfg, engine, fetch)
        trades: queue.Queue[TradeTick] = queue.Queue(maxsize=cfg.market.queue_size)
        dropped = 0

        def on_trade(tick: TradeTick) -> None:
            nonlocal dropped
            try:
                trades.put(tick, timeout=1)
            except queue.Full:
                dropped += 1
                log.error("trade queue full - dropping trade (%d dropped)", dropped, extra={"symbol": tick.symbol})

        feed = feed_factory(
            cfg.market.ws_url, cfg.run.symbols, on_trade, max_backoff=cfg.market.reconnect_max_backoff_seconds
        )
        feed_thread = threading.Thread(target=feed.run, name="feed", daemon=True)
        feed_thread.start()
        if on_started:
            on_started(engine)
        deadline = None if duration_s is None else time.monotonic() + duration_s
        next_health = time.monotonic() + HEALTH_INTERVAL_S
        reported_drops = 0
        log.info("paper session %s started for %s", run_id, ",".join(cfg.run.symbols), extra={"run_id": run_id})

        while not stop.is_set():
            if deadline is not None and time.monotonic() >= deadline:
                log.info("duration reached", extra={"run_id": run_id})
                break
            try:
                tick = trades.get(timeout=0.5)
            except queue.Empty:
                tick = None
            if tick is not None:
                _process(cfg, engine, aggregators, tick, fetch_range)
            if dropped > reported_drops:
                with store.transaction():
                    store.log_event(
                        run_id,
                        engine._now,
                        "DATA_GAP",
                        f"{dropped - reported_drops} trade(s) dropped (queue full)",
                        None,
                        {"total_dropped": dropped},
                    )
                reported_drops = dropped
            if time.monotonic() >= next_health:
                next_health = time.monotonic() + HEALTH_INTERVAL_S
                _health(cfg, engine, feed, aggregators, trades.qsize(), dropped)
        status = "stopped"
    finally:
        if feed is not None:
            feed.stop()
        if feed_thread is not None:
            feed_thread.join(JOIN_TIMEOUT_S)
            if feed_thread.is_alive():
                log.error("feed thread did not stop within %ss", JOIN_TIMEOUT_S)
        if status == "stopped":
            drain_until = time.monotonic() + DRAIN_TIMEOUT_S
            while time.monotonic() < drain_until:
                try:
                    _process(cfg, engine, aggregators, trades.get_nowait(), fetch_range)
                except queue.Empty:
                    break
        with store.transaction():
            store.save_equity(run_id, engine.ledger.snapshot(max(engine._now, 1)))
            engine._persist_state()
            if feed is not None:
                store.set_state(
                    run_id, "feed", {k: v for k, v in asdict(feed.status).items() if k != "last_message_monotonic"}
                )
        store.finish_run(run_id, status, {"counters": dict(engine.counters)})
        log.info("paper session %s %s", run_id, status, extra={"run_id": run_id})
    return run_id


def _warmup(cfg: AppConfig, engine: TradingEngine, fetch: Callable) -> dict[str, CandleAggregator]:
    candles = []
    aggregators = {}
    for symbol in cfg.run.symbols:
        history = fetch(cfg.market.rest_url, symbol, cfg.run.timeframe, cfg.timeframe_ms, cfg.market.warmup_candles)
        quality = data_quality(symbol, history, cfg.timeframe_ms)
        if quality.candles < cfg.strategy.warmup_bars:
            raise DataError(
                f"{symbol}: only {quality.candles} warmup candles, need {cfg.strategy.warmup_bars}; "
                "refusing to trade without a complete warmup"
            )
        if not quality.ok:
            log.warning("warmup data quality issue for %s: %s", symbol, quality)
        agg = CandleAggregator(symbol, cfg.run.timeframe, cfg.timeframe_ms, emit_empty=True)
        agg.seed_last_closed(history[-1].open_time, history[-1].close)
        agg.needs_backfill = True  # type: ignore[attr-defined]
        aggregators[symbol] = agg
        candles.extend(history)
    candles.sort(key=lambda c: (c.open_time, c.symbol))
    engine.warmup(candles)
    for symbol in cfg.run.symbols:
        if not engine.strategies[symbol].ready:
            raise DataError(f"{symbol}: strategy not ready after warmup")
    return aggregators


def _process(
    cfg: AppConfig,
    engine: TradingEngine,
    aggregators: dict[str, CandleAggregator],
    tick: TradeTick,
    fetch_range: Callable,
) -> None:
    agg = aggregators.get(tick.symbol)
    if agg is None:
        return
    if tick.after_gap:
        with engine.store.transaction():
            engine.store.log_event(
                engine.run_id,
                tick.ts,
                "DATA_GAP",
                "trade-id sequence gap in live feed",
                tick.symbol,
                {"agg_id": tick.agg_id},
            )
    agg.emit_empty = not tick.after_gap  # never invent empty candles when trades were lost
    last_closed = agg._last_closed_open_time
    closed = agg.on_trade(float(tick.price), float(tick.quantity), tick.ts)
    if closed and getattr(agg, "needs_backfill", False):
        agg.needs_backfill = False  # type: ignore[attr-defined]
        closed = _backfill(cfg, engine, tick.symbol, last_closed + cfg.timeframe_ms, closed[-1].close_time, fetch_range)
    # Close the previous candle first: its signals can then fill on this (later) trade.
    for candle in closed:
        engine.on_candle_closed(candle)
    engine.on_trade(tick.symbol, tick.price, tick.ts)


def _backfill(cfg: AppConfig, engine: TradingEngine, symbol: str, start: int, end: int, fetch_range: Callable):
    """Replace the first (partial) live candle(s) with closed exchange klines."""
    try:
        candles = fetch_range(cfg.market.rest_url, symbol, cfg.run.timeframe, cfg.timeframe_ms, start, end)
    except Exception as exc:  # noqa: BLE001 - backfill is best effort; the gap is recorded instead
        log.warning("backfill failed for %s: %s", symbol, exc, extra={"symbol": symbol})
        candles = []
    candles = [c for c in candles if start <= c.open_time < end]
    expected = (end - start) // cfg.timeframe_ms
    if len(candles) < expected:
        with engine.store.transaction():
            engine.store.log_event(
                engine.run_id,
                end,
                "DATA_GAP",
                f"backfill returned {len(candles)}/{expected} candle(s); partial live candle discarded",
                symbol,
                {"from": start, "to": end},
            )
    return candles


def _health(cfg: AppConfig, engine: TradingEngine, feed, aggregators, queue_size: int, dropped: int) -> None:
    age = feed.seconds_since_last_message()
    stale = age is None or age > cfg.market.stale_after_seconds
    health = {
        "feed_connected": feed.status.connected,
        "seconds_since_last_message": None if age is None else round(age, 1),
        "stale": stale,
        "reconnects": feed.status.reconnects,
        "sequence_gaps": feed.status.sequence_gaps,
        "queue_size": queue_size,
        "dropped_trades": dropped,
        "candle_gaps": {s: a.stats.missing_intervals for s, a in aggregators.items()},
        **engine.status(),
    }
    with engine.store.transaction():
        engine.store.set_state(engine.run_id, "health", health)
        if stale:
            engine.store.log_event(
                engine.run_id, engine._now, "STALE_FEED", f"no market data for {health['seconds_since_last_message']}s"
            )
    level = logging.WARNING if stale else logging.INFO
    log.log(
        level,
        "health equity=%s positions=%s stale=%s",
        health["equity"],
        health["positions"],
        stale,
        extra={"run_id": engine.run_id},
    )
