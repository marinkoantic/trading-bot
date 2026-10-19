"""Simulated (paper) broker. Never talks to an exchange.

Order lifecycle: ``NEW -> ACCEPTED -> (PARTIALLY_FILLED)* -> FILLED | CANCELED``
or ``NEW -> REJECTED``.

Execution rules (no lookahead):

* Orders are only matched in :meth:`on_market`, which is called with the
  *next* market data after the order was submitted - the next bar's open in a
  backtest, the next trade in paper mode. A market order created at a bar's
  close therefore fills at the following bar's open.
* MARKET orders fill at ``reference_price`` (bar open / trade price).
* STOP_MARKET orders (protective, reduce-only) trigger when the bar's
  low <= stop (sell) or high >= stop (buy); the reference price is the stop, or
  the open if the market gapped through it.
* Fill price = reference worsened by half spread + slippage (+ optional seeded
  random slippage), rounded to the tick size *against* the trader.
* Liquidity: with a bar volume, at most ``max_volume_participation`` of it is
  filled per bar (shared by all orders of the symbol); the rest stays open
  until ``order_timeout_bars`` is reached, then it is CANCELED (entries only;
  reduce-only exits keep working until the position is flat). Trades from the
  live feed carry no reliable liquidity information, so paper mode passes
  ``volume=None`` (no participation cap).
* Fills are booked into the :class:`Ledger` immediately.
* Opening/increasing exposure needs ``available_funds``; if funds are short
  the quantity is reduced, or the order canceled (INSUFFICIENT_FUNDS).
* Reduce-only orders never exceed (or flip) the current position.
* Only MARKET and STOP_MARKET are supported; LIMIT orders are not implemented.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_DOWN, Decimal

from core.config import AppConfig
from core.domain import Fill, Order, OrderStatus, OrderType, Side, Trade
from portfolio.ledger import Ledger
from risk.risk_engine import BPS, round_step

FEE_QUANT = Decimal("0.0000000001")


@dataclass(frozen=True, slots=True)
class OrderUpdate:
    order: Order
    fill: Fill | None = None
    trades: tuple[Trade, ...] = ()


class PaperBroker:
    def __init__(
        self,
        cfg: AppConfig,
        ledger: Ledger,
        rng: random.Random | None = None,
        on_update: Callable[[OrderUpdate], None] | None = None,
    ):
        self.cfg = cfg
        self.ledger = ledger
        self.rng = rng or random.Random(cfg.run.seed)
        self.on_update = on_update
        self.orders: dict[str, Order] = {}
        self._open: list[str] = []
        self._fill_seq: dict[str, int] = {}

    # ------------------------------------------------------------- orders
    def open_orders(self, symbol: str | None = None) -> list[Order]:
        orders = [self.orders[o] for o in self._open]
        return [o for o in orders if symbol is None or o.symbol == symbol]

    def submit(self, order: Order) -> Order:
        if order.order_id in self.orders:
            return self.orders[order.order_id]  # idempotent resubmission
        self.orders[order.order_id] = order
        reason = self._validate(order)
        if reason:
            order.status, order.reject_reason = OrderStatus.REJECTED, reason
        else:
            order.status = OrderStatus.ACCEPTED
            self._open.append(order.order_id)
        self._emit(order)
        return order

    def cancel(self, order_id: str, reason: str = "CANCELED") -> None:
        order = self.orders.get(order_id)
        if order is None or order.status.is_terminal:
            return
        order.status, order.reject_reason = OrderStatus.CANCELED, reason
        self._open.remove(order_id)
        self._emit(order)

    def cancel_all(self, symbol: str, reason: str, order_type: OrderType | None = None) -> None:
        for order in self.open_orders(symbol):
            if order_type is None or order.order_type is order_type:
                self.cancel(order.order_id, reason)

    def _validate(self, order: Order) -> str:
        if order.symbol not in self.cfg.symbols:
            return "UNKNOWN_SYMBOL"
        if order.order_type not in (OrderType.MARKET, OrderType.STOP_MARKET):
            return "UNSUPPORTED_ORDER_TYPE"
        rules = self.cfg.rules_for(order.symbol)
        if not order.quantity.is_finite() or order.quantity <= 0:
            return "INVALID_QUANTITY"
        if order.quantity % rules.step_size != 0:
            return "QUANTITY_NOT_MULTIPLE_OF_STEP"
        if order.quantity < rules.min_qty:
            return "BELOW_MIN_QTY"
        if order.quantity > rules.max_qty:
            return "ABOVE_MAX_QTY"
        if order.order_type is OrderType.STOP_MARKET:
            if order.stop_price is None or order.stop_price <= 0:
                return "INVALID_STOP_PRICE"
            if not order.reduce_only:
                return "STOP_ORDERS_MUST_BE_REDUCE_ONLY"
        if order.reduce_only and self._reduce_room(order) <= 0:
            return "REDUCE_ONLY_WITHOUT_POSITION"
        return ""

    # ------------------------------------------------------------- matching
    def on_market(
        self,
        symbol: str,
        open_: Decimal,
        high: Decimal,
        low: Decimal,
        ts: int,
        volume: Decimal | None = None,
        new_bar: bool = True,
    ) -> list[Fill]:
        """Match open orders of ``symbol`` against new market data."""
        rules = self.cfg.rules_for(symbol)
        liquidity = (
            None
            if volume is None
            else round_step(volume * self.cfg.execution.max_volume_participation, rules.step_size)
        )
        fills: list[Fill] = []
        seen: set[str] = set()
        while True:
            # Orders created while matching (e.g. a protective stop right after an entry fill)
            # are matched against the same bar: a resting stop could have been hit later in it.
            pending = [o for o in self.open_orders(symbol) if o.order_id not in seen]
            if not pending:
                break
            for order in pending:
                seen.add(order.order_id)
                if not order.status.is_terminal:
                    liquidity = self._match(order, open_, high, low, ts, liquidity, new_bar, fills)
        return fills

    def _match(
        self,
        order: Order,
        open_: Decimal,
        high: Decimal,
        low: Decimal,
        ts: int,
        liquidity: Decimal | None,
        new_bar: bool,
        fills: list[Fill],
    ) -> Decimal | None:
        rules = self.cfg.rules_for(order.symbol)
        if order.order_type is OrderType.STOP_MARKET:
            ref = self._stop_reference(order, open_, high, low)
            if ref is None:
                return liquidity
        else:
            ref = open_
        qty = order.remaining
        if order.reduce_only:
            room = self._reduce_room(order)
            if room <= 0:
                self.cancel(order.order_id, "POSITION_ALREADY_FLAT")
                return liquidity
            qty = min(qty, room)
        if liquidity is not None:
            qty = min(qty, liquidity)
        price = self._execution_price(order.side, ref, rules.tick_size)
        if not order.reduce_only:
            affordable = self._affordable(order, price, rules.step_size)
            if affordable < rules.min_qty:
                self.cancel(order.order_id, "INSUFFICIENT_FUNDS")
                return liquidity
            qty = min(qty, affordable)
        # Non-reduce fills below min_notional would be rejected by the exchange: wait instead.
        if qty > 0 and (order.reduce_only or qty * price >= rules.min_notional):
            fill = self._fill(order, qty, price, ref, ts)
            fills.append(fill)
            if liquidity is not None:
                liquidity -= qty
        # Entries time out; risk-reducing orders keep working until the position is flat.
        if not order.status.is_terminal and new_bar and order.order_type is OrderType.MARKET and not order.reduce_only:
            order.bars_open += 1
            if order.bars_open >= self.cfg.execution.order_timeout_bars:
                self.cancel(order.order_id, "TIMEOUT_UNFILLED_REMAINDER")
        return liquidity

    def _stop_reference(self, order: Order, open_: Decimal, high: Decimal, low: Decimal) -> Decimal | None:
        stop = order.stop_price
        if order.side is Side.SELL:
            if low > stop:
                return None
            return min(open_, stop)  # gap down -> open is worse than the stop
        if high < stop:
            return None
        return max(open_, stop)

    def _execution_price(self, side: Side, ref: Decimal, tick: Decimal) -> Decimal:
        c = self.cfg.costs
        bps = c.half_spread_bps + c.slippage_bps
        if c.random_slippage_bps > 0:
            bps += Decimal(str(round(self.rng.random(), 6))) * c.random_slippage_bps
        raw = ref * (1 + side.sign * bps / BPS)
        rounding = ROUND_CEILING if side is Side.BUY else ROUND_DOWN
        price = (raw / tick).to_integral_value(rounding=rounding) * tick
        return max(price, tick)

    def _reduce_room(self, order: Order) -> Decimal:
        pos = self.ledger.position_qty(order.symbol)
        if pos == 0 or (pos > 0) == (order.side is Side.BUY):
            return Decimal("0")
        return abs(pos)

    def _affordable(self, order: Order, price: Decimal, step: Decimal) -> Decimal:
        pos = self.ledger.position_qty(order.symbol)
        reducing = Decimal("0")
        if pos != 0 and (pos > 0) != (order.side is Side.BUY):
            reducing = abs(pos)  # closing part needs no funds and frees collateral
        rate = self.cfg.costs.taker_fee_rate
        funds = self.ledger.available_funds() + reducing * price
        new_exposure = max(funds, Decimal("0")) / (price * (1 + rate))
        return round_step(reducing + new_exposure, step)

    def _fill(self, order: Order, qty: Decimal, price: Decimal, ref: Decimal, ts: int) -> Fill:
        seq = self._fill_seq.get(order.order_id, 0) + 1
        self._fill_seq[order.order_id] = seq
        fee = (qty * price * self.cfg.costs.taker_fee_rate).quantize(FEE_QUANT, rounding=ROUND_CEILING)
        fill = Fill(
            fill_id=f"{order.order_id}-F{seq}",
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=qty,
            price=price,
            fee=fee,
            timestamp=ts,
            reference_price=ref,
        )
        order.filled_quantity += qty
        if order.remaining <= 0:
            order.status = OrderStatus.FILLED
            self._open.remove(order.order_id)
        else:
            order.status = OrderStatus.PARTIALLY_FILLED
        # Book immediately so later orders in the same step see the new position and funds.
        trades = self.ledger.apply_fill(fill, order.reason) or []
        self._emit(order, fill, tuple(trades))
        return fill

    def _emit(self, order: Order, fill: Fill | None = None, trades: tuple[Trade, ...] = ()) -> None:
        if self.on_update:
            self.on_update(OrderUpdate(order, fill, trades))
