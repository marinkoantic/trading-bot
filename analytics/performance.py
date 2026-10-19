"""Performance metrics and reports (Markdown + CSV), computed from the store.

Definitions. A *round trip* is one position from opening to (complete or
partial) closing; positions closed by several partial fills are grouped by
``position_id``. Trade ratios use round trips, not individual closing fills:

* total_return_pct     = (final_equity - start_cash) / start_cash * 100
* max_drawdown_pct     = max over the equity curve of (peak - equity) / peak * 100
* win_rate_pct         = round trips with net_pnl > 0 / all round trips * 100
* profit_factor        = sum(net_pnl > 0) / |sum(net_pnl < 0)|; ``None`` without losing trades
* avg_win / avg_loss   = mean net_pnl of winning / losing trades
* expectancy           = mean net_pnl per trade
* fees                 = all fees paid (including still-open positions)
* slippage_cost        = spread + slippage cost of closed trades versus reference prices
* exposure_pct         = share of equity snapshots with at least one open position
* buy_and_hold_pct     = per symbol: (last close / first open - 1) * 100 minus a
  round trip of taker fees, over the same period (equal weight across symbols)

With fewer than ``MIN_TRADES_FOR_STATS`` closed trades a warning is added: the
ratios are reported but are not statistically meaningful.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path

from core.config import AppConfig
from core.domain import utc_iso
from persistence.store import Store

MIN_TRADES_FOR_STATS = 30


@dataclass
class PerformanceReport:
    run_id: str
    mode: str
    config_hash: str
    status: str
    period_start: str | None
    period_end: str | None
    start_cash: str
    final_equity: str
    total_return_pct: float
    max_drawdown_pct: float
    trades: int  # round trips
    closing_fills: int
    win_rate_pct: float | None
    profit_factor: float | None
    avg_win: float | None
    avg_loss: float | None
    expectancy: float | None
    fees: str
    slippage_cost: str
    exposure_pct: float | None
    open_positions: int
    buy_and_hold_pct: float | None = None
    warnings: list[str] = field(default_factory=list)


def round_trips(trades) -> list[dict]:
    """Group journal entries (closing fills) into round trips by position_id."""
    groups: dict[str, dict] = {}
    for t in trades:
        key = t["position_id"] or t["trade_id"]
        g = groups.get(key)
        if g is None:
            g = groups[key] = {
                "position_id": key,
                "symbol": t["symbol"],
                "direction": t["direction"],
                "entry_time": t["entry_time"],
                "exit_time": t["exit_time"],
                "quantity": Decimal("0"),
                "gross_pnl": Decimal("0"),
                "fees": Decimal("0"),
                "slippage_cost": Decimal("0"),
                "net_pnl": Decimal("0"),
                "fills": 0,
                "entry_reason": t["entry_reason"],
                "exit_reason": t["exit_reason"],
            }
        g["exit_time"] = max(g["exit_time"], t["exit_time"])
        g["fills"] += 1
        g["exit_reason"] = t["exit_reason"]
        for field_name in ("quantity", "gross_pnl", "fees", "slippage_cost", "net_pnl"):
            g[field_name] += Decimal(t[field_name])
    return sorted(groups.values(), key=lambda g: (g["exit_time"], g["position_id"]))


def max_drawdown_pct(equity: list[Decimal]) -> float:
    peak, worst = None, Decimal("0")
    for value in equity:
        if peak is None or value > peak:
            peak = value
        if peak and peak > 0:
            worst = max(worst, (peak - value) / peak)
    return float(worst * 100)


def build_report(store: Store, run_id: str, cfg: AppConfig, buy_and_hold_pct: float | None = None) -> PerformanceReport:
    run = store.get_run(run_id)
    meta = json.loads(run["meta_json"])
    start_cash = Decimal(json.loads(run["config_json"])["account"]["start_cash"])
    curve = store.equity_curve(run_id)
    trades = store.trades(run_id)
    trips = round_trips(trades)
    equity = [Decimal(r["equity"]) for r in curve]
    final = equity[-1] if equity else start_cash
    nets = [t["net_pnl"] for t in trips]
    wins = [n for n in nets if n > 0]
    losses = [n for n in nets if n < 0]
    warnings: list[str] = []
    if not curve:
        warnings.append("no equity snapshots recorded")
    if len(trips) < MIN_TRADES_FOR_STATS:
        warnings.append(
            f"only {len(trips)} round trip(s): ratios are not statistically meaningful (< {MIN_TRADES_FOR_STATS})"
        )
    last = curve[-1] if curve else None
    if last is not None and last["open_positions"]:
        warnings.append(f"{last['open_positions']} position(s) still open; final equity includes unrealized PnL")
    quality = meta.get("data_quality", {})
    for symbol, q in quality.items():
        if q.get("missing") or q.get("duplicates") or q.get("invalid"):
            warnings.append(f"data quality {symbol}: {q}")
    gaps = store.events(run_id, "DATA_GAP")
    if gaps:
        warnings.append(f"{len(gaps)} data gap event(s) during the run")
    kills = store.events(run_id, "KILL_SWITCH")
    if kills:
        warnings.append(f"kill switch triggered: {kills[0]['message']}")
    period = meta.get("period", {})
    p_start = period.get("start", curve[0]["ts"] if curve else None)
    p_end = period.get("end", curve[-1]["ts"] if curve else None)

    return PerformanceReport(
        run_id=run_id,
        mode=run["mode"],
        config_hash=run["config_hash"],
        status=run["status"],
        period_start=utc_iso(p_start) if p_start else None,
        period_end=utc_iso(p_end) if p_end else None,
        start_cash=str(start_cash),
        final_equity=f"{final:.8f}",
        total_return_pct=float((final - start_cash) / start_cash * 100),
        max_drawdown_pct=max_drawdown_pct([start_cash, *equity]),
        trades=len(trips),
        closing_fills=len(trades),
        win_rate_pct=len(wins) / len(nets) * 100 if nets else None,
        profit_factor=float(sum(wins) / abs(sum(losses))) if losses else None,
        avg_win=float(sum(wins) / len(wins)) if wins else None,
        avg_loss=float(sum(losses) / len(losses)) if losses else None,
        expectancy=float(sum(nets) / len(nets)) if nets else None,
        fees=f"{Decimal(last['fees']) if last else Decimal('0'):.8f}",
        slippage_cost=f"{sum((Decimal(t['slippage_cost']) for t in trades), Decimal('0')):.8f}",
        exposure_pct=sum(1 for r in curve if r["open_positions"]) / len(curve) * 100 if curve else None,
        open_positions=last["open_positions"] if last else 0,
        buy_and_hold_pct=buy_and_hold_pct if buy_and_hold_pct is not None else meta.get("buy_and_hold_pct"),
        warnings=warnings,
    )


def buy_and_hold_pct(first_open: dict[str, float], last_close: dict[str, float], fee_rate: Decimal) -> float | None:
    if not first_open:
        return None
    fee = float(fee_rate)
    returns = [(last_close[s] * (1 - fee)) / (first_open[s] * (1 + fee)) - 1 for s in first_open]
    return sum(returns) / len(returns) * 100


def _fmt(value: float | None, suffix: str = "", digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}{suffix}"


def to_markdown(report: PerformanceReport) -> str:
    r = report
    rows = [
        ("Run", r.run_id),
        ("Mode", r.mode),
        ("Status", r.status),
        ("Config hash", r.config_hash),
        ("Period (UTC)", f"{r.period_start} → {r.period_end}"),
        ("Start cash", r.start_cash),
        ("Final equity", r.final_equity),
        ("Total return", _fmt(r.total_return_pct, " %")),
        ("Buy & hold (after fees)", _fmt(r.buy_and_hold_pct, " %")),
        ("Max drawdown", _fmt(r.max_drawdown_pct, " %")),
        ("Round trips", str(r.trades)),
        ("Closing fills (journal entries)", str(r.closing_fills)),
        ("Win rate", _fmt(r.win_rate_pct, " %")),
        ("Profit factor", _fmt(r.profit_factor)),
        ("Avg win", _fmt(r.avg_win, digits=6)),
        ("Avg loss", _fmt(r.avg_loss, digits=6)),
        ("Expectancy / trade", _fmt(r.expectancy, digits=6)),
        ("Fees paid", r.fees),
        ("Spread + slippage (closed trades)", r.slippage_cost),
        ("Time in market", _fmt(r.exposure_pct, " %")),
        ("Open positions at end", str(r.open_positions)),
    ]
    lines = [
        f"# Report {r.run_id}",
        "",
        "PAPER_ONLY simulation - no real orders were sent.",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    lines += [f"| {k} | {v} |" for k, v in rows]
    if r.warnings:
        lines += ["", "## Warnings", ""] + [f"- {w}" for w in r.warnings]
    return "\n".join(lines) + "\n"


def write_report(store: Store, report: PerformanceReport, out_dir: str | Path) -> Path:
    out = Path(out_dir) / report.run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(to_markdown(report), encoding="utf-8")
    (out / "report.json").write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    trades = store.trades(report.run_id)
    with (out / "trades.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "trade_id",
                "position_id",
                "symbol",
                "direction",
                "quantity",
                "entry_time_utc",
                "exit_time_utc",
                "entry_price",
                "exit_price",
                "gross_pnl",
                "fees",
                "slippage_cost",
                "net_pnl",
                "entry_reason",
                "exit_reason",
            ]
        )
        for t in trades:
            writer.writerow(
                [
                    t["trade_id"],
                    t["position_id"],
                    t["symbol"],
                    t["direction"],
                    t["quantity"],
                    utc_iso(t["entry_time"]),
                    utc_iso(t["exit_time"]),
                    t["entry_price"],
                    t["exit_price"],
                    t["gross_pnl"],
                    t["fees"],
                    t["slippage_cost"],
                    t["net_pnl"],
                    t["entry_reason"],
                    t["exit_reason"],
                ]
            )
    with (out / "round_trips.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        cols = [
            "position_id",
            "symbol",
            "direction",
            "quantity",
            "entry_time_utc",
            "exit_time_utc",
            "gross_pnl",
            "fees",
            "slippage_cost",
            "net_pnl",
            "fills",
            "entry_reason",
            "exit_reason",
        ]
        writer.writerow(cols)
        for g in round_trips(trades):
            writer.writerow(
                [
                    g["position_id"],
                    g["symbol"],
                    g["direction"],
                    g["quantity"],
                    utc_iso(g["entry_time"]),
                    utc_iso(g["exit_time"]),
                    g["gross_pnl"],
                    g["fees"],
                    g["slippage_cost"],
                    g["net_pnl"],
                    g["fills"],
                    g["entry_reason"],
                    g["exit_reason"],
                ]
            )
    with (out / "equity.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(
            ["time_utc", "cash", "equity", "realized_pnl", "unrealized_pnl", "fees", "gross_exposure", "open_positions"]
        )
        for e in store.equity_curve(report.run_id):
            writer.writerow(
                [
                    utc_iso(e["ts"]),
                    e["cash"],
                    e["equity"],
                    e["realized_pnl"],
                    e["unrealized_pnl"],
                    e["fees"],
                    e["gross_exposure"],
                    e["open_positions"],
                ]
            )
    return out
