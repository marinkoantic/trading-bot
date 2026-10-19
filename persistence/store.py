"""SQLite persistence for runs, orders, fills, trades, signals, equity and risk events.

Design:

* Fills are the source of truth for accounting. On restart the ledger is
  rebuilt by replaying the stored fills in order (:func:`rebuild_ledger`), so a
  restored state is exactly the state that was booked - no separate snapshot
  that could drift.
* ``fills.fill_id`` is the primary key and inserts use ``INSERT OR IGNORE``:
  a duplicate fill can never be stored twice.
* A fill, its order update and resulting trades are written in one transaction.
* Decimals are stored as TEXT to keep exact precision.
* Schema changes go through ``MIGRATIONS`` (append-only, versioned via
  ``PRAGMA user_version``).
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

from core.config import AppConfig
from core.domain import EquitySnapshot, Fill, Order, Side, Signal, Trade
from portfolio.ledger import Ledger

MIGRATIONS: list[str] = [
    """
    CREATE TABLE runs (
        run_id TEXT PRIMARY KEY,
        mode TEXT NOT NULL,
        profile TEXT NOT NULL,
        status TEXT NOT NULL,
        started_at INTEGER NOT NULL,
        ended_at INTEGER,
        config_hash TEXT NOT NULL,
        config_json TEXT NOT NULL,
        meta_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE TABLE orders (
        order_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        order_type TEXT NOT NULL,
        quantity TEXT NOT NULL,
        stop_price TEXT,
        reduce_only INTEGER NOT NULL,
        status TEXT NOT NULL,
        filled_quantity TEXT NOT NULL,
        reason TEXT NOT NULL,
        reject_reason TEXT NOT NULL,
        signal_id TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
    );
    CREATE TABLE fills (
        fill_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        order_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        quantity TEXT NOT NULL,
        price TEXT NOT NULL,
        fee TEXT NOT NULL,
        reference_price TEXT NOT NULL,
        reason TEXT NOT NULL,
        ts INTEGER NOT NULL,
        seq INTEGER NOT NULL
    );
    CREATE INDEX fills_run_seq ON fills(run_id, seq);
    CREATE TABLE trades (
        trade_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        symbol TEXT NOT NULL,
        direction TEXT NOT NULL,
        quantity TEXT NOT NULL,
        entry_price TEXT NOT NULL,
        exit_price TEXT NOT NULL,
        entry_time INTEGER NOT NULL,
        exit_time INTEGER NOT NULL,
        gross_pnl TEXT NOT NULL,
        fees TEXT NOT NULL,
        slippage_cost TEXT NOT NULL,
        net_pnl TEXT NOT NULL,
        entry_reason TEXT NOT NULL,
        exit_reason TEXT NOT NULL
    );
    CREATE TABLE signals (
        signal_id TEXT NOT NULL,
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        symbol TEXT NOT NULL,
        action TEXT NOT NULL,
        price REAL NOT NULL,
        stop_price REAL,
        ts INTEGER NOT NULL,
        reason TEXT NOT NULL,
        outcome TEXT NOT NULL,
        PRIMARY KEY (run_id, signal_id)
    );
    CREATE TABLE equity (
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        ts INTEGER NOT NULL,
        cash TEXT NOT NULL,
        equity TEXT NOT NULL,
        realized_pnl TEXT NOT NULL,
        unrealized_pnl TEXT NOT NULL,
        fees TEXT NOT NULL,
        gross_exposure TEXT NOT NULL,
        open_positions INTEGER NOT NULL,
        PRIMARY KEY (run_id, ts)
    );
    CREATE TABLE events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        ts INTEGER NOT NULL,
        kind TEXT NOT NULL,
        symbol TEXT,
        message TEXT NOT NULL,
        details_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE TABLE state (
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        key TEXT NOT NULL,
        value_json TEXT NOT NULL,
        PRIMARY KEY (run_id, key)
    );
    """,
    # v2: round-trip grouping for partially closed positions
    """
    ALTER TABLE trades ADD COLUMN position_id TEXT NOT NULL DEFAULT '';
    CREATE INDEX trades_position ON trades(run_id, position_id);
    """,
]


def _d(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        if str(path) != ":memory:":
            self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.execute("PRAGMA synchronous = NORMAL")
        self._in_tx = False
        self._migrate()

    def close(self) -> None:
        self.conn.close()

    def _migrate(self) -> None:
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version > len(MIGRATIONS):
            raise RuntimeError(f"database schema v{version} is newer than this code (v{len(MIGRATIONS)})")
        for index in range(version, len(MIGRATIONS)):
            with self.transaction():
                for statement in MIGRATIONS[index].split(";"):
                    if statement.strip():
                        self.conn.execute(statement)
                self.conn.execute(f"PRAGMA user_version = {index + 1}")

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self._in_tx:  # nested: join the outer transaction
            yield
            return
        self.conn.execute("BEGIN IMMEDIATE")
        self._in_tx = True
        try:
            yield
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        else:
            self.conn.execute("COMMIT")
        finally:
            self._in_tx = False

    # ------------------------------------------------------------ runs
    def create_run(self, cfg: AppConfig, meta: dict[str, Any] | None = None) -> str:
        run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:6]
        self.conn.execute(
            "INSERT INTO runs (run_id, mode, profile, status, started_at, config_hash, config_json, meta_json)"
            " VALUES (?, ?, ?, 'running', ?, ?, ?, ?)",
            (
                run_id,
                cfg.run.mode.value,
                cfg.profile,
                int(time.time() * 1000),
                cfg.config_hash(),
                json.dumps(cfg.to_dict(), sort_keys=True),
                json.dumps(meta or {}, sort_keys=True),
            ),
        )
        return run_id

    def finish_run(self, run_id: str, status: str, meta: dict[str, Any] | None = None) -> None:
        with self.transaction():
            if meta is not None:
                current = json.loads(self.get_run(run_id)["meta_json"])
                current.update(meta)
                self.conn.execute(
                    "UPDATE runs SET meta_json = ? WHERE run_id = ?", (json.dumps(current, sort_keys=True), run_id)
                )
            self.conn.execute(
                "UPDATE runs SET status = ?, ended_at = ? WHERE run_id = ?", (status, int(time.time() * 1000), run_id)
            )

    def reopen_run(self, run_id: str) -> None:
        self.conn.execute("UPDATE runs SET status = 'running', ended_at = NULL WHERE run_id = ?", (run_id,))

    def get_run(self, run_id: str) -> sqlite3.Row:
        row = self.conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown run {run_id}")
        return row

    def latest_run_id(self) -> str | None:
        row = self.conn.execute("SELECT run_id FROM runs ORDER BY started_at DESC, rowid DESC LIMIT 1").fetchone()
        return row["run_id"] if row else None

    def list_runs(self, limit: int = 20) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM runs ORDER BY started_at DESC, rowid DESC LIMIT ?", (limit,)).fetchall()

    # ------------------------------------------------------------ writes
    def save_order(self, run_id: str, order: Order, ts: int) -> None:
        self.conn.execute(
            """INSERT INTO orders (order_id, run_id, symbol, side, order_type, quantity, stop_price, reduce_only,
                   status, filled_quantity, reason, reject_reason, signal_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(order_id) DO UPDATE SET status = excluded.status,
                   filled_quantity = excluded.filled_quantity, reject_reason = excluded.reject_reason,
                   updated_at = excluded.updated_at""",
            (
                order.order_id,
                run_id,
                order.symbol,
                order.side.value,
                order.order_type.value,
                str(order.quantity),
                None if order.stop_price is None else str(order.stop_price),
                int(order.reduce_only),
                order.status.value,
                str(order.filled_quantity),
                order.reason,
                order.reject_reason,
                order.signal_id,
                order.created_at,
                ts,
            ),
        )

    def save_fill(self, run_id: str, fill: Fill, reason: str) -> bool:
        """Insert a fill; returns False if it was already stored (duplicate)."""
        seq = self.conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM fills WHERE run_id = ?", (run_id,)).fetchone()[0]
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO fills (fill_id, run_id, order_id, symbol, side, quantity, price, fee,
                   reference_price, reason, ts, seq) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fill.fill_id,
                run_id,
                fill.order_id,
                fill.symbol,
                fill.side.value,
                str(fill.quantity),
                str(fill.price),
                str(fill.fee),
                str(fill.reference_price),
                reason,
                fill.timestamp,
                seq,
            ),
        )
        return cur.rowcount == 1

    def save_trade(self, run_id: str, trade: Trade) -> None:
        self.conn.execute(
            """INSERT OR IGNORE INTO trades (trade_id, run_id, symbol, direction, quantity, entry_price, exit_price,
                   entry_time, exit_time, gross_pnl, fees, slippage_cost, net_pnl, entry_reason, exit_reason,
                   position_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trade.trade_id,
                run_id,
                trade.symbol,
                trade.direction,
                str(trade.quantity),
                str(trade.entry_price),
                str(trade.exit_price),
                trade.entry_time,
                trade.exit_time,
                str(trade.gross_pnl),
                str(trade.fees),
                str(trade.slippage_cost),
                str(trade.net_pnl),
                trade.entry_reason,
                trade.exit_reason,
                trade.position_id,
            ),
        )

    def save_signal(self, run_id: str, signal: Signal, outcome: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                signal.signal_id,
                run_id,
                signal.symbol,
                signal.action.value,
                signal.price,
                signal.stop_price,
                signal.timestamp,
                signal.reason,
                outcome,
            ),
        )

    def save_equity(self, run_id: str, snap: EquitySnapshot) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO equity VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                snap.timestamp,
                str(snap.cash),
                str(snap.equity),
                str(snap.realized_pnl),
                str(snap.unrealized_pnl),
                str(snap.fees),
                str(snap.gross_exposure),
                snap.open_positions,
            ),
        )

    def log_event(
        self,
        run_id: str,
        ts: int,
        kind: str,
        message: str,
        symbol: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO events (run_id, ts, kind, symbol, message, details_json) VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, ts, kind, symbol, message, json.dumps(details or {}, sort_keys=True, default=str)),
        )

    def set_state(self, run_id: str, key: str, value: Any) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO state VALUES (?, ?, ?)",
            (run_id, key, json.dumps(value, sort_keys=True, default=str)),
        )

    def get_state(self, run_id: str, key: str, default: Any = None) -> Any:
        row = self.conn.execute("SELECT value_json FROM state WHERE run_id = ? AND key = ?", (run_id, key)).fetchone()
        return default if row is None else json.loads(row["value_json"])

    # ------------------------------------------------------------ reads
    def load_fills(self, run_id: str) -> list[tuple[Fill, str]]:
        rows = self.conn.execute("SELECT * FROM fills WHERE run_id = ? ORDER BY seq", (run_id,)).fetchall()
        return [
            (
                Fill(
                    r["fill_id"],
                    r["order_id"],
                    r["symbol"],
                    Side(r["side"]),
                    Decimal(r["quantity"]),
                    Decimal(r["price"]),
                    Decimal(r["fee"]),
                    r["ts"],
                    Decimal(r["reference_price"]),
                ),
                r["reason"],
            )
            for r in rows
        ]

    def open_orders(self, run_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM orders WHERE run_id = ? AND status IN ('NEW', 'ACCEPTED', 'PARTIALLY_FILLED')", (run_id,)
        ).fetchall()

    def trades(self, run_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM trades WHERE run_id = ? ORDER BY exit_time, rowid", (run_id,)
        ).fetchall()

    def equity_curve(self, run_id: str) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM equity WHERE run_id = ? ORDER BY ts", (run_id,)).fetchall()

    def events(self, run_id: str, kind: str | None = None) -> list[sqlite3.Row]:
        if kind:
            return self.conn.execute(
                "SELECT * FROM events WHERE run_id = ? AND kind = ? ORDER BY id", (run_id, kind)
            ).fetchall()
        return self.conn.execute("SELECT * FROM events WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()

    def count(self, table: str, run_id: str) -> int:
        if table not in {"orders", "fills", "trades", "signals", "equity", "events"}:
            raise ValueError(table)
        return self.conn.execute(f"SELECT COUNT(*) FROM {table} WHERE run_id = ?", (run_id,)).fetchone()[0]


def rebuild_ledger(store: Store, run_id: str, start_cash: Decimal) -> Ledger:
    """Reconstruct the ledger of a run by replaying its stored fills."""
    ledger = Ledger(start_cash)
    last_price: dict[str, Decimal] = {}
    for fill, reason in store.load_fills(run_id):
        ledger.apply_fill(fill, reason)
        last_price[fill.symbol] = fill.reference_price
    for symbol, price in last_price.items():
        ledger.mark(symbol, price)  # best known market price until fresh data arrives
    ledger.check_invariants()
    return ledger
