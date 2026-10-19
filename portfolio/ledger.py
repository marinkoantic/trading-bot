"""Portfolio ledger: the single source of truth for cash, positions and PnL.

Accounting model (cash accounting, one net position per symbol):

* BUY  fill: ``cash -= qty * price + fee``
* SELL fill: ``cash += qty * price - fee``
* Position quantity is signed (long > 0, short < 0). Increasing a position
  updates the volume-weighted average entry price; reducing it realises
  ``(exit - avg_entry) * closed_qty * direction``. A fill larger than the open
  position closes it and opens the remainder in the opposite direction at the
  fill price (reverse).
* Fees are booked exactly once, at fill time, into ``fees_paid``. Realised PnL
  is *gross* (before fees); a closed :class:`Trade` carries its share of entry
  and exit fees so ``trade.net_pnl`` is after fees.
* Equity = cash + sum(qty * mark price). Invariant (tested):
  ``equity == start_cash + realized_pnl + unrealized_pnl - fees_paid``.
* ``available_funds = equity - gross_exposure`` (1x collateral; no leverage).
* Every fill carries a unique ``fill_id``; re-applying a known fill is a no-op.

All arithmetic uses ``Decimal`` without intermediate rounding; values are only
quantised for display/persistence (see ``MONEY_QUANT``).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from core.domain import EquitySnapshot, Fill, Side, Trade

ZERO = Decimal("0")
MONEY_QUANT = Decimal("0.00000001")
# The only inexact operation is the average-price division (28 significant digits).
INVARIANT_TOLERANCE = Decimal("1e-12")


@dataclass
class Position:
    symbol: str
    quantity: Decimal  # signed
    avg_price: Decimal
    opened_at: int
    entry_fees: Decimal  # fees of the still-open quantity
    entry_slippage: Decimal
    entry_reason: str = ""
    position_id: str = ""

    @property
    def direction(self) -> str:
        return "LONG" if self.quantity > 0 else "SHORT"


class Ledger:
    def __init__(self, start_cash: Decimal):
        if start_cash <= 0:
            raise ValueError("start_cash must be > 0")
        self.start_cash = start_cash
        self.cash = start_cash
        self.positions: dict[str, Position] = {}
        self.marks: dict[str, Decimal] = {}
        self.realized_pnl = ZERO
        self.fees_paid = ZERO
        self.trades: list[Trade] = []
        self._fill_ids: set[str] = set()
        self._trade_seq = 0

    # ------------------------------------------------------------------ queries
    def has_fill(self, fill_id: str) -> bool:
        return fill_id in self._fill_ids

    def position_qty(self, symbol: str) -> Decimal:
        pos = self.positions.get(symbol)
        return pos.quantity if pos else ZERO

    def direction(self, symbol: str) -> str | None:
        pos = self.positions.get(symbol)
        return pos.direction if pos else None

    def mark_price(self, symbol: str) -> Decimal | None:
        if symbol in self.marks:
            return self.marks[symbol]
        pos = self.positions.get(symbol)
        return pos.avg_price if pos else None

    def unrealized_pnl(self) -> Decimal:
        total = ZERO
        for pos in self.positions.values():
            total += (self.mark_price(pos.symbol) - pos.avg_price) * pos.quantity
        return total

    def exposure(self, symbol: str) -> Decimal:
        pos = self.positions.get(symbol)
        return abs(pos.quantity) * self.mark_price(symbol) if pos else ZERO

    def gross_exposure(self) -> Decimal:
        return sum((self.exposure(s) for s in self.positions), ZERO)

    def equity(self) -> Decimal:
        return self.cash + sum((p.quantity * self.mark_price(s) for s, p in self.positions.items()), ZERO)

    def available_funds(self) -> Decimal:
        return self.equity() - self.gross_exposure()

    def snapshot(self, ts: int) -> EquitySnapshot:
        return EquitySnapshot(
            timestamp=ts,
            cash=self.cash,
            equity=self.equity(),
            realized_pnl=self.realized_pnl,
            unrealized_pnl=self.unrealized_pnl(),
            fees=self.fees_paid,
            gross_exposure=self.gross_exposure(),
            open_positions=len(self.positions),
        )

    def check_invariants(self) -> None:
        expected = self.start_cash + self.realized_pnl + self.unrealized_pnl() - self.fees_paid
        if abs(self.equity() - expected) > INVARIANT_TOLERANCE:
            raise AssertionError(f"ledger invariant violated: equity {self.equity()} != {expected}")
        for pos in self.positions.values():
            if pos.quantity == 0 or pos.avg_price <= 0:
                raise AssertionError(f"invalid position state {pos}")

    # ------------------------------------------------------------------ updates
    def mark(self, symbol: str, price: Decimal) -> None:
        if price <= 0:
            raise ValueError(f"mark price must be > 0, got {price}")
        self.marks[symbol] = price

    def apply_fill(self, fill: Fill, reason: str = "") -> list[Trade] | None:
        """Book a fill. Returns closed trades, or ``None`` if the fill was already booked."""
        if fill.fill_id in self._fill_ids:
            return None
        if fill.quantity <= 0 or fill.price <= 0 or fill.fee < 0:
            raise ValueError(f"invalid fill {fill}")
        self._fill_ids.add(fill.fill_id)

        qty, price, sign = fill.quantity, fill.price, fill.side.sign
        self.cash -= sign * qty * price + fill.fee
        self.fees_paid += fill.fee
        self.marks.setdefault(fill.symbol, price)

        pos = self.positions.get(fill.symbol)
        trades: list[Trade] = []
        if pos is None:
            self._open(fill, qty, fill.fee, fill.slippage_cost, reason)
        elif (pos.quantity > 0) == (fill.side is Side.BUY):
            new_abs = abs(pos.quantity) + qty
            pos.avg_price = (abs(pos.quantity) * pos.avg_price + qty * price) / new_abs
            pos.quantity += sign * qty
            pos.entry_fees += fill.fee
            pos.entry_slippage += fill.slippage_cost
        else:
            close_qty = min(abs(pos.quantity), qty)
            exit_fee = fill.fee * close_qty / qty
            exit_slip = fill.slippage_cost * close_qty / qty
            share = close_qty / abs(pos.quantity)
            entry_fee = pos.entry_fees * share
            entry_slip = pos.entry_slippage * share
            direction = 1 if pos.quantity > 0 else -1
            gross = (price - pos.avg_price) * close_qty * direction
            self.realized_pnl += gross
            self._trade_seq += 1
            trades.append(
                Trade(
                    trade_id=f"{fill.fill_id}:T{self._trade_seq}",
                    symbol=fill.symbol,
                    direction=pos.direction,
                    quantity=close_qty,
                    entry_price=pos.avg_price,
                    exit_price=price,
                    entry_time=pos.opened_at,
                    exit_time=fill.timestamp,
                    gross_pnl=gross,
                    fees=entry_fee + exit_fee,
                    slippage_cost=entry_slip + exit_slip,
                    entry_reason=pos.entry_reason,
                    exit_reason=reason,
                    position_id=pos.position_id,
                )
            )
            pos.quantity += sign * close_qty
            pos.entry_fees -= entry_fee
            pos.entry_slippage -= entry_slip
            if pos.quantity == 0:
                del self.positions[fill.symbol]
            remainder = qty - close_qty
            if remainder > 0:
                self._open(fill, remainder, fill.fee - exit_fee, fill.slippage_cost - exit_slip, reason)
        self.trades.extend(trades)
        return trades

    def _open(self, fill: Fill, qty: Decimal, fee: Decimal, slip: Decimal, reason: str) -> None:
        self.positions[fill.symbol] = Position(
            symbol=fill.symbol,
            quantity=fill.side.sign * qty,
            avg_price=fill.price,
            opened_at=fill.timestamp,
            entry_fees=fee,
            entry_slippage=slip,
            entry_reason=reason,
            position_id=f"{fill.symbol}:{fill.fill_id}",
        )
