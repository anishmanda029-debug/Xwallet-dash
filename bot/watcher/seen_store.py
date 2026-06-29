"""
The watcher needs to remember which tx hashes it already reported, so a
restart doesn't re-report old payments. Lives on the watcher's own
machine/process — deliberately separate from the main bot's database.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "seen.db"


def init_db():
    with get_conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS seen_txs (
                symbol TEXT NOT NULL,
                tx_hash TEXT NOT NULL,
                PRIMARY KEY (symbol, tx_hash)
            )"""
        )


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def is_seen(symbol: str, tx_hash: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM seen_txs WHERE symbol = ? AND tx_hash = ?",
            (symbol, tx_hash),
        ).fetchone()
        return row is not None


def mark_seen(symbol: str, tx_hash: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO seen_txs (symbol, tx_hash) VALUES (?, ?)",
            (symbol, tx_hash),
        )
