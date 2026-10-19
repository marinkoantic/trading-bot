"""Command line interface. PAPER_ONLY - there is no command that trades live.

    python cli.py config   [--profile P] [--set section.key=value ...]
    python cli.py fetch-data --symbol BTCUSDT --days 7 --out data/BTCUSDT_1m.csv
    python cli.py backtest --csv data/BTCUSDT_1m.csv [--csv ...]
    python cli.py paper    [--duration 24h] [--resume RUN_ID]
    python cli.py status   [--run-id RUN_ID]
    python cli.py report   [--run-id RUN_ID] [--out DIR]
    python cli.py runs
    python cli.py reset-kill-switch --run-id RUN_ID

Exit codes: 0 ok, 1 runtime error, 2 configuration/usage error, 3 data error.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
import time
from pathlib import Path

from core.config import PAPER_ONLY, AppConfig, ConfigError, TradingMode, load_config

EXIT_OK, EXIT_RUNTIME, EXIT_CONFIG, EXIT_DATA = 0, 1, 2, 3
log = logging.getLogger("cli")


def _duration(text: str) -> float:
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    try:
        if text[-1].lower() in units:
            value = float(text[:-1]) * units[text[-1].lower()]
        else:
            value = float(text)
    except (ValueError, IndexError) as exc:
        raise argparse.ArgumentTypeError(f"invalid duration {text!r} (e.g. 90s, 30m, 24h)") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError("duration must be > 0")
    return value


def summary(cfg: AppConfig) -> str:
    r, k = cfg.run, cfg.risk
    return "\n".join(
        [
            "=" * 60,
            f" MODE: {r.mode.value.upper()}   (PAPER_ONLY={PAPER_ONLY} - no real orders can be sent)",
            f" profile={cfg.profile}  config_hash={cfg.config_hash()}",
            f" symbols={','.join(r.symbols)}  timeframe={r.timeframe}  start_cash={cfg.account.start_cash}",
            f" strategy={cfg.strategy.name} ({cfg.strategy.signal_mode}) EMA{cfg.strategy.fast_period}/"
            f"{cfg.strategy.slow_period} RSI{cfg.strategy.rsi_period} ATRx{cfg.strategy.atr_stop_multiple}",
            f" risk/trade={k.risk_per_trade_pct}%  max_pos={k.max_open_positions}  "
            f"pos_cap={k.max_position_notional_pct}%  exposure_cap={k.max_total_exposure_pct}%",
            f" daily_loss_halt={k.max_daily_loss_pct}%  max_drawdown_kill={k.max_drawdown_pct}%  "
            f"shorts={k.enable_shorts}",
            f" costs: taker={cfg.costs.taker_fee_rate} spread={cfg.costs.half_spread_bps}bps "
            f"slippage={cfg.costs.slippage_bps}bps(+{cfg.costs.random_slippage_bps} random)",
            f" database={r.database}",
            "=" * 60,
        ]
    )


def _store(cfg: AppConfig):
    from persistence.store import Store

    return Store(cfg.run.database)


def cmd_config(cfg: AppConfig, args) -> int:
    print(summary(cfg))
    print(json.dumps(cfg.to_dict(), indent=2))
    return EXIT_OK


def cmd_fetch(cfg: AppConfig, args) -> int:
    from data.klines import data_quality, fetch_klines, write_csv

    symbol = args.symbol.upper()
    if symbol not in cfg.symbols:
        raise ConfigError(f"no [symbols.{symbol}] rules configured")
    end = int(time.time() * 1000)
    end -= end % cfg.timeframe_ms
    start = end - int(args.days * 86_400_000)
    candles = fetch_klines(cfg.market.rest_url, symbol, cfg.run.timeframe, cfg.timeframe_ms, start, end)
    write_csv(args.out, candles)
    q = data_quality(symbol, candles, cfg.timeframe_ms)
    print(
        f"wrote {len(candles)} closed {cfg.run.timeframe} candles to {args.out} "
        f"(missing={q.missing}, duplicates={q.duplicates}, invalid={q.invalid})"
    )
    return EXIT_OK


def cmd_backtest(cfg: AppConfig, args) -> int:
    from analytics.performance import to_markdown, write_report
    from backtest.runner import run_backtest
    from data.klines import read_csv

    if cfg.run.mode is not TradingMode.BACKTEST:
        raise ConfigError("backtest needs run.mode='backtest' - use --profile backtest")
    data: dict[str, list] = {}
    for path in args.csv:
        for candle in read_csv(path, cfg.run.timeframe):
            data.setdefault(candle.symbol, []).append(candle)
    print(summary(cfg))
    store = _store(cfg)
    try:
        result = run_backtest(cfg, data, store, {"data_files": [str(Path(p)) for p in args.csv]})
        out = write_report(store, result.report, cfg.run.report_dir)
    finally:
        store.close()
    print(to_markdown(result.report))
    print(f"report written to {out}")
    return EXIT_OK


def cmd_paper(cfg: AppConfig, args) -> int:
    from app.paper_runner import run_paper

    if cfg.run.mode is not TradingMode.PAPER:
        raise ConfigError("paper needs run.mode='paper'")
    print(summary(cfg))
    stop = threading.Event()

    def handle(signum, _frame):
        log.warning("signal %s received - shutting down", signum)
        stop.set()

    signal.signal(signal.SIGINT, handle)
    signal.signal(signal.SIGTERM, handle)
    store = _store(cfg)
    try:
        run_id = run_paper(
            cfg,
            store,
            stop_event=stop,
            duration_s=args.duration,
            resume_run_id=args.resume,
            on_started=lambda e: print(f"paper session {e.run_id} running - Ctrl+C to stop"),
        )
        print(json.dumps(_status(store, run_id), indent=2))
    finally:
        store.close()
    return EXIT_OK


def _status(store, run_id: str) -> dict:
    run = store.get_run(run_id)
    curve = store.equity_curve(run_id)
    last = curve[-1] if curve else None
    return {
        "run_id": run_id,
        "mode": run["mode"],
        "status": run["status"],
        "config_hash": run["config_hash"],
        "equity": last["equity"] if last else None,
        "realized_pnl": last["realized_pnl"] if last else None,
        "unrealized_pnl": last["unrealized_pnl"] if last else None,
        "fees": last["fees"] if last else None,
        "open_positions": last["open_positions"] if last else 0,
        "orders": store.count("orders", run_id),
        "fills": store.count("fills", run_id),
        "trades": store.count("trades", run_id),
        "risk_rejections": len(store.events(run_id, "RISK_REJECT")),
        "kill_switch": store.get_state(run_id, "risk", {}).get("reason") or None,
        "health": store.get_state(run_id, "health"),
    }


def _run_id(store, args) -> str:
    run_id = args.run_id or store.latest_run_id()
    if run_id is None:
        raise ConfigError(f"no runs in {store.path}")
    return run_id


def cmd_status(cfg: AppConfig, args) -> int:
    store = _store(cfg)
    try:
        print(json.dumps(_status(store, _run_id(store, args)), indent=2, default=str))
    finally:
        store.close()
    return EXIT_OK


def cmd_runs(cfg: AppConfig, args) -> int:
    store = _store(cfg)
    try:
        for r in store.list_runs():
            print(f"{r['run_id']}  {r['mode']:8} {r['status']:9} config={r['config_hash']}")
    finally:
        store.close()
    return EXIT_OK


def cmd_report(cfg: AppConfig, args) -> int:
    from analytics.performance import build_report, to_markdown, write_report

    store = _store(cfg)
    try:
        report = build_report(store, _run_id(store, args), cfg)
        out = write_report(store, report, args.out or cfg.run.report_dir)
    finally:
        store.close()
    print(to_markdown(report))
    print(f"report written to {out}")
    return EXIT_OK


def cmd_reset_kill_switch(cfg: AppConfig, args) -> int:
    from app.engine import _risk_state_from_json, _risk_state_to_json
    from risk.risk_engine import RiskEngine

    store = _store(cfg)
    try:
        state = _risk_state_from_json(store.get_state(args.run_id, "risk"))
        engine = RiskEngine(cfg, state)
        engine.reset_kill_switch()
        with store.transaction():
            store.set_state(args.run_id, "risk", _risk_state_to_json(engine.state))
            store.log_event(args.run_id, int(time.time() * 1000), "KILL_SWITCH_RESET", "manual reset via CLI")
    finally:
        store.close()
    print(f"kill switch reset for {args.run_id}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--profile", help="config profile (config/profiles/<name>.toml)")
    common.add_argument(
        "--set", action="append", default=[], metavar="SECTION.KEY=VALUE", help="validated config override (repeatable)"
    )
    common.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser = argparse.ArgumentParser(prog="trading-bot", description="PAPER-ONLY trading and backtesting")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("config", parents=[common], help="show validated configuration")
    p = sub.add_parser("fetch-data", parents=[common], help="download closed candles (public REST) to CSV")
    p.add_argument("--symbol", required=True)
    p.add_argument("--days", type=float, default=7)
    p.add_argument("--out", required=True)
    p = sub.add_parser("backtest", parents=[common], help="run a backtest on CSV candles")
    p.add_argument("--csv", action="append", required=True)
    p = sub.add_parser("paper", parents=[common], help="run a paper-trading session on live public data")
    p.add_argument("--duration", type=_duration, help="stop after e.g. 30m, 24h")
    p.add_argument("--resume", metavar="RUN_ID", help="continue an earlier paper run")
    for name, help_text in (("status", "show run status"), ("report", "write Markdown/CSV report")):
        p = sub.add_parser(name, parents=[common], help=help_text)
        p.add_argument("--run-id")
        if name == "report":
            p.add_argument("--out")
    sub.add_parser("runs", parents=[common], help="list runs")
    p = sub.add_parser("reset-kill-switch", parents=[common], help="clear a latched kill switch")
    p.add_argument("--run-id", required=True)
    return parser


COMMANDS = {
    "config": cmd_config,
    "fetch-data": cmd_fetch,
    "backtest": cmd_backtest,
    "paper": cmd_paper,
    "status": cmd_status,
    "report": cmd_report,
    "runs": cmd_runs,
    "reset-kill-switch": cmd_reset_kill_switch,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    profile = args.profile or ("backtest" if args.command == "backtest" else None)
    try:
        cfg = load_config(profile, args.set)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    from utils.log_setup import configure_logging

    configure_logging(cfg.run.log_dir, args.log_level)
    from data.klines import DataError

    try:
        return COMMANDS[args.command](cfg, args)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except DataError as exc:
        print(f"data error: {exc}", file=sys.stderr)
        return EXIT_DATA
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except Exception:  # noqa: BLE001 - top-level guard: log with traceback, return a clear exit code
        log.exception("unhandled error")
        print("runtime error - see logs/tradingbot.jsonl", file=sys.stderr)
        return EXIT_RUNTIME


if __name__ == "__main__":
    sys.exit(main())
