"""Typed domain models for the paper-trading core.

All timestamps are integer milliseconds since the Unix epoch (UTC).
Money, prices and quantities that enter the accounting are ``Decimal``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum


def ms_to_utc(ts_ms: int) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000, tz=UTC)


def utc_iso(ts_ms: int) -> str:
    return ms_to_utc(ts_ms).isoformat()


def to_decimal(value: object) -> Decimal:
    """Convert a float/int/str to Decimal without binary float artefacts."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def sign(self) -> int:
        return 1 if self is Side.BUY else -1

    def opposite(self) -> Side:
        return Side.SELL if self is Side.BUY else Side.BUY


class OrderType(StrEnum):
    MARKET = "MARKET"
    STOP_MARKET = "STOP_MARKET"


class OrderStatus(StrEnum):
    NEW = "NEW"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"

    @property
    def is_terminal(self) -> bool:
        return self in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED)


class SignalAction(StrEnum):
    ENTER_LONG = "ENTER_LONG"
    ENTER_SHORT = "ENTER_SHORT"
    EXIT = "EXIT"


@dataclass(frozen=True, slots=True)
class Candle:
    symbol: str
    timeframe: str
    open_time: int  # ms, inclusive
    close_time: int  # ms, exclusive (open_time + timeframe)
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_closed: bool = True


@dataclass(frozen=True, slots=True)
class Signal:
    symbol: str
    action: SignalAction
    price: float  # close of the candle that produced the signal
    timestamp: int  # candle close_time; never wall-clock
    strategy: str
    reason: str
    stop_price: float | None = None
    signal_id: str = ""


@dataclass(slots=True)
class Order:
    order_id: str
    symbol: str
    side: Side
    order_type: OrderType
    quantity: Decimal
    created_at: int
    reason: str
    stop_price: Decimal | None = None
    reduce_only: bool = False
    signal_id: str = ""
    status: OrderStatus = OrderStatus.NEW
    filled_quantity: Decimal = Decimal("0")
    reject_reason: str = ""
    bars_open: int = 0

    @property
    def remaining(self) -> Decimal:
        return self.quantity - self.filled_quantity


@dataclass(frozen=True, slots=True)
class Fill:
    fill_id: str
    order_id: str
    symbol: str
    side: Side
    quantity: Decimal
    price: Decimal
    fee: Decimal
    timestamp: int
    reference_price: Decimal  # market price before spread/slippage
    liquidity: str = "TAKER"

    @property
    def notional(self) -> Decimal:
        return self.quantity * self.price

    @property
    def slippage_cost(self) -> Decimal:
        """Cost of spread + slippage versus the reference price (always >= 0)."""
        return (self.price - self.reference_price) * self.quantity * self.side.sign


@dataclass(frozen=True, slots=True)
class Trade:
    """One closing fill of a position (journal entry). Several entries with the same
    ``position_id`` form one round trip when a position is closed in parts."""

    trade_id: str
    symbol: str
    direction: str  # LONG | SHORT
    quantity: Decimal
    entry_price: Decimal
    exit_price: Decimal
    entry_time: int
    exit_time: int
    gross_pnl: Decimal
    fees: Decimal
    slippage_cost: Decimal
    entry_reason: str = ""
    exit_reason: str = ""
    position_id: str = ""  # groups partial closes of one position into a round trip

    @property
    def net_pnl(self) -> Decimal:
        return self.gross_pnl - self.fees


@dataclass(frozen=True, slots=True)
class EquitySnapshot:
    timestamp: int
    cash: Decimal
    equity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    fees: Decimal
    gross_exposure: Decimal
    open_positions: int


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    reason: str
    quantity: Decimal = Decimal("0")
    details: dict[str, str] = field(default_factory=dict)
