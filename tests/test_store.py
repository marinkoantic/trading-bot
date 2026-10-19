import sqlite3

import pytest

from persistence.store import MIGRATIONS, Store
from tests.helpers import config


def test_migrates_v1_database_forward(tmp_path):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATIONS[0] + "; PRAGMA user_version = 1;")
    conn.close()
    store = Store(db)
    assert store.conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    cols = {r[1] for r in store.conn.execute("PRAGMA table_info(trades)")}
    assert "position_id" in cols


def test_refuses_newer_schema(tmp_path):
    db = tmp_path / "new.db"
    conn = sqlite3.connect(db)
    conn.execute(f"PRAGMA user_version = {len(MIGRATIONS) + 1}")
    conn.close()
    with pytest.raises(RuntimeError, match="newer"):
        Store(db)


def test_transaction_rolls_back_on_error():
    store = Store(":memory:")
    run_id = store.create_run(config())
    with pytest.raises(ZeroDivisionError):
        with store.transaction():
            store.log_event(run_id, 1, "X", "will be rolled back")
            raise ZeroDivisionError
    assert store.count("events", run_id) == 0
