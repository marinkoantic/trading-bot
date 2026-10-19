import json
import threading
import time
from decimal import Decimal as D

import pytest

import cli
from app.paper_runner import run_paper
from core.config import ConfigError
from market.live_feed import LiveFeed, backoff_delay, parse_agg_trade
from persistence.store import Store
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


def agg_msg(symbol, price, qty, ts, agg_id):
    return json.dumps(
        {
            "stream": f"{symbol.lower()}@aggTrade",
            "data": {"e": "aggTrade", "s": symbol, "p": str(price), "q": str(qty), "T": ts, "a": agg_id},
        }
    )


class FakeFeed:
    """Stands in for LiveFeed: replays scripted messages through the real message handler."""

    def __init__(self, messages):
        self.messages = messages

    def __call__(self, ws_url, symbols, on_trade, max_backoff):
        self.real = LiveFeed(ws_url, symbols, on_trade, max_backoff, ws_factory=lambda **kw: None)
        self.status = self.real.status
        self.stopped = threading.Event()
        return self

    def seconds_since_last_message(self):
        return self.real.seconds_since_last_message()

    def run(self):
        for raw in self.messages:
            if self.stopped.is_set():
                return
            self.real.handle_message(raw)
        self.stopped.wait(5)

    def stop(self):
        self.stopped.set()


def test_parse_agg_trade_and_reject_bad_values():
    tick = parse_agg_trade(agg_msg("BTCUSDT", "100.5", "0.1", 1000, 7))
    assert tick.symbol == "BTCUSDT" and tick.price == D("100.5") and tick.agg_id == 7
    assert parse_agg_trade(json.dumps({"result": None, "id": 1})) is None
    with pytest.raises(ValueError):
        parse_agg_trade(agg_msg("BTCUSDT", "-1", "1", 1, 1))


def test_feed_detects_sequence_gaps_and_duplicates():
    got = []
    feed = LiveFeed("wss://x", ("BTCUSDT",), got.append, ws_factory=lambda **kw: None)
    for agg_id in (1, 2, 2, 5):
        feed.handle_message(agg_msg("BTCUSDT", 1, 1, agg_id, agg_id))
    feed.handle_message("not json{")
    feed.handle_message(agg_msg("ETHUSDT", 1, 1, 9, 9))  # not subscribed
    assert [t.agg_id for t in got] == [1, 2, 5]
    assert feed.status.sequence_gaps == 1 and feed.status.parse_errors == 1


def test_backoff_is_capped_and_jittered():
    import random

    rng = random.Random(3)
    delays = [backoff_delay(a, 60, rng) for a in range(12)]
    assert all(0 <= d <= 60 for d in delays)
    assert len(set(delays)) == len(delays)


def test_feed_reconnects_until_stopped():
    class FakeWS:
        runs = 0

        def __init__(self, **kw):
            self.kw = kw

        def run_forever(self, **kw):
            FakeWS.runs += 1
            if FakeWS.runs == 3:
                feed.stop()

        def close(self):
            pass

    feed = LiveFeed("wss://x", ("BTCUSDT",), lambda t: None, max_backoff=0.01, ws_factory=FakeWS)
    t = threading.Thread(target=feed.run)
    t.start()
    t.join(5)
    assert not t.is_alive() and FakeWS.runs == 3 and feed.status.reconnects == 2


def test_paper_session_end_to_end_with_scripted_feed(tmp_path):
    cfg = config(*FAST, f"run.database='{tmp_path / 'p.db'}'", profile="paper")
    history = series([100.0 - i for i in range(16)])  # falling: the EMA cross happens live, not in warmup
    last = history[-1]
    msgs, agg_id = [], 1
    price = last.close
    for k in range(8):  # rising trades, one per minute plus one mid-minute
        for offset in (1_000, 30_000):
            price += 2
            msgs.append(agg_msg("BTCUSDT", price, 5, last.close_time + k * MINUTE + offset, agg_id))
            agg_id += 1
    feed = FakeFeed(msgs)
    store = Store(cfg.run.database)
    stop = threading.Event()
    threading.Timer(1.5, stop.set).start()
    backfills = []

    def fetch_range(rest, symbol, tf, tf_ms, start, end):
        backfills.append((start, end))
        return [c for c in series([84.0 + 2 * i for i in range(20)], start=16) if start <= c.open_time < end]

    run_id = run_paper(
        cfg, store, stop_event=stop, fetch=lambda *a, **k: history, fetch_range=fetch_range, feed_factory=feed
    )
    assert backfills == [(last.close_time, last.close_time + MINUTE)]  # first live candle replaced
    run = store.get_run(run_id)
    assert run["status"] == "stopped" and run["mode"] == "paper"
    assert store.count("signals", run_id) >= 1
    assert store.count("fills", run_id) >= 1
    fill = store.load_fills(run_id)[0][0]
    sig = store.conn.execute("SELECT ts FROM signals WHERE run_id=? ORDER BY ts LIMIT 1", (run_id,)).fetchone()
    assert fill.timestamp >= sig["ts"]  # filled on a trade after the signal candle closed
    status = cli._status(store, run_id)
    assert status["fills"] >= 1 and status["status"] == "stopped"
    store.close()


def test_paper_refuses_incomplete_warmup(tmp_path):
    from data.klines import DataError

    cfg = config(*FAST, f"run.database='{tmp_path / 'p.db'}'", profile="paper")
    store = Store(cfg.run.database)
    with pytest.raises(DataError, match="warmup"):
        run_paper(cfg, store, fetch=lambda *a, **k: series([1.0, 2.0]), feed_factory=FakeFeed([]))
    assert store.list_runs()[0]["status"] == "failed"


def test_paper_refuses_backtest_mode(tmp_path):
    with pytest.raises(ConfigError):
        run_paper(config(*FAST), Store(":memory:"))


def test_cli_exit_codes_and_backtest(tmp_path, capsys):
    from data.klines import write_csv

    closes = []
    for _ in range(3):
        closes += [100 - i for i in range(12)] + [88 + 2 * i for i in range(12)] + [110 - 2 * i for i in range(12)]
    csv_path = tmp_path / "btc.csv"
    write_csv(csv_path, series(closes))
    db = tmp_path / "bt.db"
    common = [
        *sum((["--set", o] for o in FAST), []),
        "--set",
        f"run.database='{db}'",
        "--set",
        f"run.log_dir='{tmp_path / 'logs'}'",
        "--set",
        f"run.report_dir='{tmp_path / 'rep'}'",
    ]
    assert cli.main(["backtest", "--csv", str(csv_path), *common]) == 0
    out = capsys.readouterr().out
    assert "MODE: BACKTEST" in out and "PAPER_ONLY=True" in out and "Total return" in out
    assert cli.main(["status", *common, "--profile", "backtest"]) == 0
    assert cli.main(["report", *common, "--profile", "backtest"]) == 0
    assert list((tmp_path / "rep").glob("*/trades.csv"))
    assert cli.main(["config", "--set", "run.mode=live"]) == cli.EXIT_CONFIG
    assert cli.main(["backtest", "--csv", str(tmp_path / "missing.csv"), *common]) == cli.EXIT_DATA
    assert cli.main(["paper", "--profile", "backtest", *common]) == cli.EXIT_CONFIG


def test_logs_redact_secrets(tmp_path):
    import logging

    from utils.log_setup import configure_logging, redact

    assert redact("api_key=abc123 secret: xyz") == "api_key=*** secret: ***"
    path = configure_logging(tmp_path, console=False)
    logging.getLogger("t").warning("token=SuperSecret value", extra={"symbol": "BTCUSDT"})
    for h in logging.getLogger().handlers:
        h.flush()
    line = json.loads(path.read_text().strip().splitlines()[-1])
    assert "SuperSecret" not in line["msg"] and line["symbol"] == "BTCUSDT" and line["ts"].endswith("+00:00")


def test_no_live_order_endpoint_anywhere():
    """PAPER_ONLY guard: no code may reference authenticated/order endpoints."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    forbidden = ("/api/v3/order", "/fapi/", "/sapi/", "X-MBX-APIKEY", "signature=", "hmac")
    offenders = []
    for path in root.rglob("*.py"):
        if "venv" in path.parts or path.name == "test_paper_and_cli.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        offenders += [f"{path.relative_to(root)}: {f}" for f in forbidden if f in text]
    assert offenders == []


def test_klines_pagination_drops_unclosed_and_handles_rate_limit(monkeypatch):
    from data import klines

    monkeypatch.setattr(klines.time, "sleep", lambda s: None)
    start, now = 0, 2500 * MINUTE + 30_000  # candle 2500 still forming

    class Resp:
        def __init__(self, code, rows=None):
            self.status_code, self._rows, self.headers, self.text = code, rows, {"Retry-After": "0"}, ""

        def json(self):
            return self._rows

    calls = []

    def get(url, params, timeout):
        calls.append(params["startTime"])
        if len(calls) == 2:
            return Resp(429)
        s = params["startTime"] // MINUTE
        rows = [[i * MINUTE, "1", "2", "0.5", "1.5", "10", (i + 1) * MINUTE - 1] for i in range(s, min(s + 1000, 2501))]
        return Resp(200, rows)

    candles = klines.fetch_klines("https://x", "BTCUSDT", "1m", MINUTE, start, 2501 * MINUTE, get, now_ms=now)
    assert len(candles) == 2500 and candles[-1].open_time == 2499 * MINUTE
    assert candles[0].close_time == MINUTE  # exclusive close time
    assert calls[1] == calls[2]  # retried the same page after 429
    assert klines.data_quality("BTCUSDT", candles, MINUTE).ok


def test_csv_roundtrip(tmp_path):
    from data.klines import read_csv, write_csv

    candles = series([1.0, 2.0, 3.0])
    write_csv(tmp_path / "c.csv", candles)
    assert read_csv(tmp_path / "c.csv", "1m") == candles


def test_shutdown_is_bounded(tmp_path):
    cfg = config(*FAST, f"run.database='{tmp_path / 'p.db'}'", profile="paper")
    history = series([100 - i for i in range(12)] + [88 + 2 * i for i in range(4)])
    stop = threading.Event()
    stop.set()
    t0 = time.monotonic()
    run_id = run_paper(
        cfg, Store(cfg.run.database), stop_event=stop, fetch=lambda *a, **k: history, feed_factory=FakeFeed([])
    )
    assert time.monotonic() - t0 < 5 and run_id


def test_empty_minutes_become_zero_volume_candles_only_without_sequence_gap():
    from candles.aggregator import CandleAggregator

    agg = CandleAggregator("BTCUSDT", "1m", MINUTE, emit_empty=True)
    agg.seed_last_closed(0, 10.0)
    agg.on_trade(11, 1, MINUTE)
    closed = agg.on_trade(12, 1, 4 * MINUTE)  # minutes 2 and 3 had no trades
    assert [(c.open_time, c.volume, c.close) for c in closed] == [
        (MINUTE, 1, 11),
        (2 * MINUTE, 0.0, 11),
        (3 * MINUTE, 0.0, 11),
    ]
    assert agg.stats.empty_intervals == 2 and agg.stats.missing_intervals == 0
    agg.emit_empty = False  # e.g. after a trade-id gap
    agg.on_trade(13, 1, 7 * MINUTE)
    assert agg.stats.missing_intervals == 2


def test_feed_marks_tick_after_sequence_gap():
    got = []
    feed = LiveFeed("wss://x", ("BTCUSDT",), got.append, ws_factory=lambda **kw: None)
    for agg_id in (1, 2, 5):
        feed.handle_message(agg_msg("BTCUSDT", 1, 1, agg_id, agg_id))
    assert [t.after_gap for t in got] == [False, False, True]


def test_runtime_does_not_import_legacy_pipelines():
    import subprocess
    import sys

    code = (
        "import sys, cli, app.paper_runner, backtest.runner;"
        "bad = ('core.events', 'core.models', 'core.eventing', 'candles.candle_engine', 'config.settings',"
        " 'portfolio.portfolio', 'portfolio.portfolio_manager', 'simulation.execution_engine',"
        " 'simulation.execution_simulator', 'strategy.demo_strategy', 'strategy.strategy_engine');"
        "print([m for m in sys.modules if m.startswith(bad)])"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "[]"
