"""Trading engine: Candle -> Indicators/Strategy -> Risk -> Paper broker -> Ledger -> Store.

The same engine runs backtests and paper sessions. It is single-threaded and
deterministic for a given input sequence and seed; the paper runner feeds it
from one consumer thread.

Per-symbol policy: at most one net position per symbol. Entry signals while a
position (or an entry order) exists are blocked; with ``risk.allow_reversal``
an opposite entry is executed as exit + new entry.

Market-data contract:
* ``market_step`` - new prices (next bar open/high/low, or a live trade). This
  is the only place where orders are matched.
* ``on_candle_closed`` - a closed candle. Marks positions, checks the kill
  switch, runs the strategy and submits orders. Orders therefore fill on the
  *next* market step, never at the price that produced the signal.
"""

from __future__ import annotations

import logging
import random
from collections import Counter
from decimal import ROUND_CEILING, ROUND_DOWN, Decimal

from candles.aggregator import validate_candle
from core.config import AppConfig, ConfigError
from core.domain import Candle, Order, OrderStatus, OrderType, Side, Signal, SignalAction, to_decimal
from persistence.store import Store, rebuild_ledger
from portfolio.ledger import Ledger
from risk.risk_engine import KillSwitchState, RiskEngine
from simulation.paper_broker import OrderUpdate, PaperBroker
from strategy.ema_rsi import EmaRsiStrategy, StrategyContext

log = logging.getLogger("engine")


def _risk_state_to_json(s: KillSwitchState) -> dict:
    return {
        "halted": s.halted,
        "reason": s.reason,
        "since": s.since,
        "peak_equity": None if s.peak_equity is None else str(s.peak_equity),
        "day": s.day,
        "day_start_equity": None if s.day_start_equity is None else str(s.day_start_equity),
        "daily_halt_day": s.daily_halt_day,
    }


def _risk_state_from_json(d: dict | None) -> KillSwitchState:
    if not d:
        return KillSwitchState()
    return KillSwitchState(
        halted=d["halted"],
        reason=d["reason"],
        since=d["since"],
        peak_equity=None if d["peak_equity"] is None else Decimal(d["peak_equity"]),
        day=d["day"],
        day_start_equity=None if d["day_start_equity"] is None else Decimal(d["day_start_equity"]),
        daily_halt_day=d["daily_halt_day"],
    )


class TradingEngine:
    def __init__(
        self,
        cfg: AppConfig,
        store: Store,
        run_id: str,
        *,
        ledger: Ledger | None = None,
        risk_state: KillSwitchState | None = None,
        order_seq: int = 0,
    ):
        self.cfg = cfg
        self.store = store
        self.run_id = run_id
        self.ledger = ledger or Ledger(cfg.account.start_cash)
        self.risk = RiskEngine(cfg, risk_state)
        self.broker = PaperBroker(cfg, self.ledger, random.Random(cfg.run.seed), self._on_order_update)
        self.strategies = {s: EmaRsiStrategy(s, cfg.strategy) for s in cfg.run.symbols}
        self.stops: dict[str, Decimal] = {}
        self._entry_stops: dict[str, Decimal] = {}
        self.last_candle: dict[str, Candle] = {}
        self.counters: Counter[str] = Counter()
        self.warming_up = False
        self._order_seq = order_seq
        self._bars_since_snapshot = 0
        self._now = 0

    # ------------------------------------------------------------------ lifecycle
    @classmethod
    def resume(cls, cfg: AppConfig, store: Store, run_id: str) -> TradingEngine:
        """Rebuild a run from the database (fills are the source of truth)."""
        run = store.get_run(run_id)
        if run["config_hash"] != cfg.config_hash():
            raise ConfigError(
                f"run {run_id} was created with config {run['config_hash']}, current config is "
                f"{cfg.config_hash()}; refusing to resume with different parameters"
            )
        ledger = rebuild_ledger(store, run_id, cfg.account.start_cash)
        engine = cls(
            cfg,
            store,
            run_id,
            ledger=ledger,
            risk_state=_risk_state_from_json(store.get_state(run_id, "risk")),
            order_seq=store.count("orders", run_id),
        )
        engine.stops = {k: Decimal(v) for k, v in store.get_state(run_id, "stops", {}).items()}
        with store.transaction():
            for row in store.open_orders(run_id):
                store.conn.execute(
                    "UPDATE orders SET status = 'CANCELED', reject_reason = 'CANCELED_ON_RESTART' WHERE order_id = ?",
                    (row["order_id"],),
                )
            store.reopen_run(run_id)
            store.log_event(
                run_id,
                0,
                "RECOVERY",
                f"rebuilt ledger from {store.count('fills', run_id)} fills",
                details={"equity": str(ledger.equity()), "positions": len(ledger.positions)},
            )
        for symbol in list(ledger.positions):
            engine._sync_stop(symbol, 0)
        return engine

    def warmup(self, candles: list[Candle]) -> None:
        """Feed historical closed candles to the strategies without trading."""
        self.warming_up = True
        try:
            for candle in candles:
                self.on_candle_closed(candle)
        finally:
            self.warming_up = False

    # ------------------------------------------------------------------ market data
    def on_bar(self, candle: Candle) -> None:
        """Backtest step: match pending orders against this bar, then process its close."""
        if validate_candle(candle) is None and not self._is_old(candle):
            self.market_step(
                candle.symbol,
                to_decimal(candle.open),
                to_decimal(candle.high),
                to_decimal(candle.low),
                candle.open_time,
                to_decimal(candle.volume),
            )
        self.on_candle_closed(candle)

    def market_step(
        self,
        symbol: str,
        open_: Decimal,
        high: Decimal,
        low: Decimal,
        ts: int,
        volume: Decimal | None = None,
        new_bar: bool = True,
    ) -> None:
        if symbol not in self.strategies:
            return
        self._now = max(self._now, ts)
        self.broker.on_market(symbol, open_, high, low, ts, volume, new_bar)
        self.ledger.mark(symbol, open_)

    def on_trade(self, symbol: str, price: Decimal, ts: int) -> None:
        """Paper mode: a live trade is the next tradable price for pending orders."""
        self.market_step(symbol, price, price, price, ts, None, new_bar=False)

    def on_candle_closed(self, candle: Candle) -> None:
        symbol, ts = candle.symbol, candle.close_time
        if symbol not in self.strategies:
            self.counters["candles_unknown_symbol"] += 1
            return
        problem = validate_candle(candle)
        if problem:
            self.counters["candles_invalid"] += 1
            self._event(ts, "DATA_INVALID", f"{problem}: {candle}", symbol)
            return
        if self._is_old(candle):
            self.counters["candles_duplicate"] += 1
            self._event(ts, "DATA_DUPLICATE", f"candle {candle.open_time} already processed", symbol)
            return
        last = self.last_candle.get(symbol)
        if last is not None and candle.open_time > last.close_time:
            missing = (candle.open_time - last.close_time) // self.cfg.timeframe_ms
            self.counters["missing_candles"] += missing
            self._event(
                ts,
                "DATA_GAP",
                f"{missing} candle(s) missing before {candle.open_time}",
                symbol,
                {"from": last.close_time, "to": candle.open_time},
            )
        self.last_candle[symbol] = candle
        self._now = max(self._now, ts)
        self.counters["candles"] += 1
        self.ledger.mark(symbol, to_decimal(candle.close))

        if not self.warming_up:
            self._check_kill_switch(ts)

        ctx = StrategyContext(self.ledger.direction(symbol), self.cfg.risk.enable_shorts, self.cfg.risk.allow_reversal)
        signals = self.strategies[symbol].generate_signals(candle, ctx)
        if self.warming_up:
            return
        with self.store.transaction():
            for signal in signals:
                self._route(signal)
            self._bars_since_snapshot += 1
            if self._bars_since_snapshot >= self.cfg.run.equity_snapshot_every_bars:
                self._bars_since_snapshot = 0
                self.store.save_equity(self.run_id, self.ledger.snapshot(ts))
            self._persist_state()

    def _is_old(self, candle: Candle) -> bool:
        last = self.last_candle.get(candle.symbol)
        return last is not None and candle.open_time <= last.open_time

    # ------------------------------------------------------------------ routing
    def _route(self, signal: Signal) -> None:
        self.counters["signals"] += 1
        symbol, pos = signal.symbol, self.ledger.position_qty(signal.symbol)
        pending = [o for o in self.broker.open_orders(symbol) if o.order_type is OrderType.MARKET]

        if signal.action is SignalAction.EXIT:
            if pos == 0:
                outcome = "IGNORED_NO_POSITION"
            elif any(o.reduce_only for o in pending):
                outcome = "IGNORED_EXIT_PENDING"
            else:
                order = self._submit(symbol, Side.SELL if pos > 0 else Side.BUY, abs(pos), signal, reduce_only=True)
                outcome = f"ORDER_{order.status.value}"
            self.store.save_signal(self.run_id, signal, outcome)
            return

        want_long = signal.action is SignalAction.ENTER_LONG
        exit_pending = any(o.reduce_only for o in pending)
        entry_pending = [o for o in pending if not o.reduce_only]
        replacing = pos != 0 and (pos > 0) != want_long and self.cfg.risk.allow_reversal and exit_pending
        if entry_pending:
            outcome = "BLOCKED_ENTRY_ORDER_PENDING"
        elif pos != 0 and not replacing:
            outcome = "BLOCKED_POSITION_OPEN"
        else:
            other_pending = len(
                {
                    o.symbol
                    for o in self.broker.open_orders()
                    if o.order_type is OrderType.MARKET and not o.reduce_only and o.symbol != symbol
                }
            )
            decision = self.risk.evaluate(signal, self.ledger, open_orders=other_pending, replacing_position=replacing)
            if not decision.approved:
                outcome = f"RISK_REJECTED:{decision.reason}"
                self.counters["risk_rejections"] += 1
                self._event(signal.timestamp, "RISK_REJECT", decision.reason, symbol, decision.details)
            else:
                order = self._submit(symbol, Side.BUY if want_long else Side.SELL, decision.quantity, signal)
                if order.status is OrderStatus.ACCEPTED:
                    self._entry_stops[order.order_id] = self._normalize_stop(symbol, signal.stop_price, want_long)
                outcome = f"ORDER_{order.status.value}"
        self.store.save_signal(self.run_id, signal, outcome)

    def _submit(
        self,
        symbol: str,
        side: Side,
        qty: Decimal,
        signal: Signal | None,
        *,
        reduce_only: bool = False,
        order_type: OrderType = OrderType.MARKET,
        stop: Decimal | None = None,
        reason: str = "",
    ) -> Order:
        self._order_seq += 1
        order = Order(
            order_id=f"{self.run_id}-O{self._order_seq}",
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=qty,
            created_at=signal.timestamp if signal else self._now,
            reason=reason or (signal.reason if signal else ""),
            stop_price=stop,
            reduce_only=reduce_only,
            signal_id=signal.signal_id if signal else "",
        )
        self.counters["orders"] += 1
        return self.broker.submit(order)

    def _normalize_stop(self, symbol: str, stop: float | None, is_long: bool) -> Decimal:
        tick = self.cfg.rules_for(symbol).tick_size
        rounding = ROUND_DOWN if is_long else ROUND_CEILING  # never tighter than the strategy asked for
        return (to_decimal(stop) / tick).to_integral_value(rounding=rounding) * tick

    def _sync_stop(self, symbol: str, ts: int) -> None:
        """Keep exactly one protective reduce-only stop matching the open position."""
        qty = self.ledger.position_qty(symbol)
        stops = [o for o in self.broker.open_orders(symbol) if o.order_type is OrderType.STOP_MARKET]
        if qty == 0:
            for o in stops:
                self.broker.cancel(o.order_id, "POSITION_CLOSED")
            self.stops.pop(symbol, None)
            return
        price = self.stops.get(symbol)
        if price is None:
            self._event(ts, "NO_PROTECTIVE_STOP", "open position without stop price", symbol)
            return
        side = Side.SELL if qty > 0 else Side.BUY
        if (
            len(stops) == 1
            and stops[0].remaining == abs(qty)
            and stops[0].side is side
            and stops[0].stop_price == price
        ):
            return
        for o in stops:
            self.broker.cancel(o.order_id, "STOP_REPLACED")
        self._submit(
            symbol,
            side,
            abs(qty),
            None,
            reduce_only=True,
            order_type=OrderType.STOP_MARKET,
            stop=price,
            reason=f"protective stop @ {price}",
        )

    # ------------------------------------------------------------------ callbacks
    def _on_order_update(self, update: OrderUpdate) -> None:
        order, fill = update.order, update.fill
        ts = fill.timestamp if fill else self._now
        with self.store.transaction():
            self.store.save_order(self.run_id, order, ts)
            if order.status is OrderStatus.REJECTED:
                self.counters["orders_rejected"] += 1
                self._event(ts, "ORDER_REJECTED", order.reject_reason, order.symbol, {"order_id": order.order_id})
            elif order.status is OrderStatus.CANCELED:
                self._event(ts, "ORDER_CANCELED", order.reject_reason, order.symbol, {"order_id": order.order_id})
            if fill is None:
                return
            if not self.store.save_fill(self.run_id, fill, order.reason):
                self._event(ts, "DUPLICATE_FILL", fill.fill_id, fill.symbol)
                return
            self.counters["fills"] += 1
            for trade in update.trades:
                self.store.save_trade(self.run_id, trade)
                self.counters["trades"] += 1
            if not order.reduce_only and order.order_id in self._entry_stops:
                self.stops[order.symbol] = self._entry_stops[order.order_id]
                if order.status.is_terminal:
                    del self._entry_stops[order.order_id]
            log.info(
                "fill %s %s %s @ %s fee=%s",
                fill.symbol,
                fill.side.value,
                fill.quantity,
                fill.price,
                fill.fee,
                extra={"run_id": self.run_id, "order_id": order.order_id, "symbol": fill.symbol},
            )
            self._sync_stop(order.symbol, ts)
            self._persist_state()

    # ------------------------------------------------------------------ risk
    def _check_kill_switch(self, ts: int) -> None:
        reason = self.risk.update_equity(ts, self.ledger.equity())
        if reason is None:
            return
        with self.store.transaction():
            self._event(ts, "KILL_SWITCH", reason, None, {"equity": str(self.ledger.equity())})
            log.warning("kill switch: %s", reason, extra={"run_id": self.run_id})
            if self.risk.state.halted:
                for symbol in list(self.ledger.positions):
                    pending = self.broker.open_orders(symbol)
                    if any(o.reduce_only and o.order_type is OrderType.MARKET for o in pending):
                        continue
                    for o in pending:
                        if not o.reduce_only:
                            self.broker.cancel(o.order_id, "KILL_SWITCH")
                    pos = self.ledger.position_qty(symbol)
                    self._submit(
                        symbol,
                        Side.SELL if pos > 0 else Side.BUY,
                        abs(pos),
                        None,
                        reduce_only=True,
                        reason="KILL_SWITCH flatten",
                    )
            self._persist_state()

    def reset_kill_switch(self) -> None:
        self.risk.reset_kill_switch()
        with self.store.transaction():
            self._event(self._now, "KILL_SWITCH_RESET", "manual reset", None)
            self._persist_state()

    # ------------------------------------------------------------------ helpers
    def _persist_state(self) -> None:
        self.store.set_state(self.run_id, "risk", _risk_state_to_json(self.risk.state))
        self.store.set_state(self.run_id, "stops", {k: str(v) for k, v in self.stops.items()})
        self.store.set_state(self.run_id, "counters", dict(self.counters))

    def _event(self, ts: int, kind: str, message: str, symbol: str | None, details: dict | None = None) -> None:
        self.store.log_event(self.run_id, ts, kind, message, symbol, details)
        level = (
            logging.WARNING
            if kind in {"KILL_SWITCH", "DATA_GAP", "DATA_INVALID", "NO_PROTECTIVE_STOP"}
            else logging.INFO
        )
        log.log(level, "%s %s", kind, message, extra={"run_id": self.run_id, "symbol": symbol or "-"})

    def status(self) -> dict:
        snap = self.ledger.snapshot(self._now)
        return {
            "run_id": self.run_id,
            "mode": self.cfg.run.mode.value,
            "equity": str(snap.equity),
            "cash": str(snap.cash),
            "realized_pnl": str(snap.realized_pnl),
            "unrealized_pnl": str(snap.unrealized_pnl),
            "fees": str(snap.fees),
            "positions": {s: str(p.quantity) for s, p in self.ledger.positions.items()},
            "kill_switch": self.risk.state.reason if self.risk.state.halted else None,
            "counters": dict(self.counters),
        }
