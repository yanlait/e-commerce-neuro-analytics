import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data/query_log.db"

_COLUMNS = {
    "model": "TEXT",
    "cost_usd": "REAL",
    "input_tokens": "INTEGER",
    "output_tokens": "INTEGER",
    "llm_latency_ms": "REAL",
}


def _conn():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS query_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            question TEXT NOT NULL,
            sql TEXT,
            rows_returned INTEGER,
            latency_ms REAL,
            error TEXT,
            answer_type TEXT
        )
    """)
    # migrate: add columns if missing
    existing = {row[1] for row in con.execute("PRAGMA table_info(query_log)")}
    for col, col_type in _COLUMNS.items():
        if col not in existing:
            con.execute(f"ALTER TABLE query_log ADD COLUMN {col} {col_type}")
    con.commit()
    return con


def log(question, sql, rows, latency_ms, error=None, answer_type="sql",
        model=None, cost_usd=None, input_tokens=None, output_tokens=None, llm_latency_ms=None):
    con = _conn()
    con.execute(
        """INSERT INTO query_log
           (ts, question, sql, rows_returned, latency_ms, error, answer_type,
            model, cost_usd, input_tokens, output_tokens, llm_latency_ms)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (datetime.now(timezone.utc).isoformat(), question, sql, rows, round(latency_ms, 2),
         error, answer_type, model, cost_usd, input_tokens, output_tokens, llm_latency_ms),
    )
    con.commit()
    con.close()
