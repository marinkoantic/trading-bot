"""Pre-trade risk checks, stop-based position sizing and kill switch.

Every *entry* goes through :meth:`RiskEngine.evaluate` before an order is
created. Anything that cannot be validated is rejected (fail closed), and every
rejection carries a machine-readable reason.

Sizing (stop based)::

    risk_budget    = equity * risk_per_trade_pct / 100
    per_unit_risk  = |entry - stop| + estimated round-trip costs per unit
    qty            = risk_budget / per_unit_risk
    qty            = min(qty, position-notional cap, total-exposure cap, available funds)
    qty            = round down to step_size

If the result is below ``min_qty`` or ``min_notional`` the entry is rejected;
the size is never bumped up to the exchange minimum (that would exceed the
risk budget).

Kill switch:

* Daily loss (UTC day, measured from the first equity of the day) >=
  ``max_daily_loss_pct``: new entries blocked until the next UTC day.
* Drawdown from peak equity >= ``max_drawdown_pct``: latched halt. New entries
  are blocked and the engine flattens all positions. Only an explicit
  :meth:`reset_kill_switch` (CLI ``reset-kill-switch``) clears it.

Exits are never blocked by the risk engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from core.config import AppConfig
from core.domain import RiskDecision, Signal, SignalAction, to_decimal
from portfolio.ledger import Ledger

BPS = Decimal("10000")
DAY_MS = 86_400_000


@dataclass
class KillSwitchState:
    halted: bool = False
    reason: str = ""
    since: int | None = None
    peak_equity: Decimal | None = None
    day: int | None = None
    day_start_equity: Decimal | None = None
    daily_halt_day: int | None = None


def round_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


class RiskEngine:
    def __init__(self, cfg: AppConfig, state: KillSwitchState | None = None):
        self.cfg = cfg
        self.state = state or KillSwitchState()

    # ---------------------------------------------------------- kill switch
    def update_equity(self, ts: int, equity: Decimal) -> str | None:
        """Track peak/daily equity. Returns a kill reason if a limit was newly breached."""
        s, r = self.state, self.cfg.risk
        day = ts // DAY_MS
        if s.day != day:
            s.day, s.day_start_equity = day, equity
        if s.peak_equity is None or equity > s.peak_equity:
            s.peak_equity = equity

        if not s.halted and s.peak_equity > 0:
            drawdown = (s.peak_equity - equity) / s.peak_equity * 100
            if drawdown >= r.max_drawdown_pct:
                s.halted, s.since = True, ts
                s.reason = f"MAX_DRAWDOWN {drawdown:.2f}% >= {r.max_drawdown_pct}%"
                return s.reason
        if s.daily_halt_day != day and s.day_start_equity and s.day_start_equity > 0:
            daily_loss = (s.day_start_equity - equity) / s.day_start_equity * 100
            if daily_loss >= r.max_daily_loss_pct:
                s.daily_halt_day = day
                return f"MAX_DAILY_LOSS {daily_loss:.2f}% >= {r.max_daily_loss_pct}%"
        return None

    def entries_blocked(self, ts: int) -> str | None:
        if self.state.halted:
            return f"KILL_SWITCH: {self.state.reason}"
        if self.state.daily_halt_day == ts // DAY_MS:
            return "DAILY_LOSS_LIMIT"
        return None

    def reset_kill_switch(self) -> None:
        self.state.halted, self.state.reason, self.state.since = False, "", None
        self.state.peak_equity = None

    # ---------------------------------------------------------- sizing
    def estimated_cost_rate(self) -> Decimal:
        """Expected one-way cost as a fraction of price (fee + half spread + slippage)."""
        c = self.cfg.costs
        return c.taker_fee_rate + (c.half_spread_bps + c.slippage_bps + c.random_slippage_bps) / BPS

    def evaluate(
        self, signal: Signal, ledger: Ledger, open_orders: int = 0, replacing_position: bool = False
    ) -> RiskDecision:
        if signal.action is SignalAction.EXIT:
            return RiskDecision(True, "EXIT_ALLOWED")
        r = self.cfg.risk
        blocked = self.entries_blocked(signal.timestamp)
        if blocked:
            return RiskDecision(False, blocked)
        if signal.action is SignalAction.ENTER_SHORT and not r.enable_shorts:
            return RiskDecision(False, "SHORTS_DISABLED")
        if signal.symbol not in self.cfg.symbols:
            return RiskDecision(False, "UNKNOWN_SYMBOL")
        if signal.stop_price is None:
            return RiskDecision(False, "MISSING_STOP")
        try:
            entry, stop = to_decimal(signal.price), to_decimal(signal.stop_price)
        except ArithmeticError:
            return RiskDecision(False, "INVALID_PRICE")
        if not (entry.is_finite() and stop.is_finite()) or entry <= 0 or stop <= 0:
            return RiskDecision(False, "INVALID_PRICE")
        is_long = signal.action is SignalAction.ENTER_LONG
        if (is_long and stop >= entry) or (not is_long and stop <= entry):
            return RiskDecision(False, "STOP_ON_WRONG_SIDE")

        current = ledger.position_qty(signal.symbol)
        if current != 0 and not replacing_position:
            return RiskDecision(False, "POSITION_ALREADY_OPEN")
        open_positions = len(ledger.positions) - (1 if replacing_position and current != 0 else 0)
        if open_positions + open_orders >= r.max_open_positions:
            return RiskDecision(False, "MAX_OPEN_POSITIONS")

        equity = ledger.equity()
        if equity <= 0:
            return RiskDecision(False, "NON_POSITIVE_EQUITY")
        rules = self.cfg.rules_for(signal.symbol)
        cost_rate = self.estimated_cost_rate()
        risk_budget = equity * r.risk_per_trade_pct / 100
        per_unit_risk = abs(entry - stop) + 2 * cost_rate * entry
        qty_risk = risk_budget / per_unit_risk

        own_exposure = ledger.exposure(signal.symbol) if replacing_position else Decimal("0")
        exposure_room = equity * r.max_total_exposure_pct / 100 - (ledger.gross_exposure() - own_exposure)
        funds = ledger.available_funds() + own_exposure  # closing the old position frees its collateral
        caps = {
            "risk": qty_risk,
            "position_notional": equity * r.max_position_notional_pct / 100 / entry,
            "total_exposure": max(exposure_room, Decimal("0")) / entry,
            "available_funds": max(funds, Decimal("0")) / (entry * (1 + cost_rate)),
            "max_qty": rules.max_qty,
        }
        binding = min(caps, key=caps.get)
        qty = round_step(caps[binding], rules.step_size)
        details = {
            "equity": f"{equity:.8f}",
            "risk_budget": f"{risk_budget:.8f}",
            "per_unit_risk": f"{per_unit_risk:.10f}",
            "binding_cap": binding,
            **{f"cap_{k}": f"{v:.8f}" for k, v in caps.items()},
        }
        if qty <= 0 or qty < rules.min_qty:
            return RiskDecision(False, f"BELOW_MIN_QTY (limited by {binding})", qty, details)
        if qty * entry < rules.min_notional:
            return RiskDecision(False, f"BELOW_MIN_NOTIONAL (limited by {binding})", qty, details)
        return RiskDecision(True, "APPROVED", qty, details)
