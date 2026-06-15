import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data/query_log.db"


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
    con.commit()
    return con


def log(question: str, sql: str | None, rows: int, latency_ms: float, error: str | None = None, answer_type: str = "sql"):
    con = _conn()
    con.execute(
        "INSERT INTO query_log (ts, question, sql, rows_returned, latency_ms, error, answer_type) VALUES (?,?,?,?,?,?,?)",
        (datetime.utcnow().isoformat(), question, sql, rows, round(latency_ms, 2), error, answer_type),
    )
    con.commit()
    con.close()
