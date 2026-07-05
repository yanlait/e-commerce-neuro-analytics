import re
import duckdb
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data/processed"

_BLOCKED = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|TRUNCATE|EXEC|EXECUTE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)
_UNBOUNDED_STAR = re.compile(r"SELECT\s+\*", re.IGNORECASE)
_REQUIRES_LIMIT = re.compile(r"\bFROM\s+(customers|orders|order_items|reviews|payments)\b", re.IGNORECASE)
# PII: row-level access to identity tables
_PII_TABLE = re.compile(r"\bFROM\s+(customers|sellers)\b", re.IGNORECASE)
_HAS_AGG = re.compile(r"\b(COUNT|SUM|AVG|MAX|MIN)\s*\(", re.IGNORECASE)
MAX_ROWS = 1000


class GuardrailError(ValueError):
    """Raised when SQL violates a security/PII policy."""


def check_guardrails(sql: str) -> None:
    """Policy checks. Raises GuardrailError on violation. Does not touch the DB."""
    if _BLOCKED.search(sql):
        raise GuardrailError(f"disallowed statement: {_BLOCKED.search(sql).group()}")
    if _UNBOUNDED_STAR.search(sql) and "LIMIT" not in sql.upper():
        raise GuardrailError("SELECT * without LIMIT is not allowed")
    has_agg = bool(_HAS_AGG.search(sql))
    has_group = "GROUP BY" in sql.upper()
    # PII tables: row-level access forbidden regardless of LIMIT — only aggregates allowed
    if _PII_TABLE.search(sql) and not has_agg and not has_group:
        raise GuardrailError("row-level access to identity tables (customers/sellers) is not allowed — use aggregation")
    if _REQUIRES_LIMIT.search(sql) and "LIMIT" not in sql.upper() and not has_group and not has_agg:
        raise GuardrailError("queries on raw tables require LIMIT, GROUP BY, or aggregation")


def _get_connection():
    con = duckdb.connect()
    for f in DATA_DIR.glob("*.parquet"):
        con.execute(f"CREATE VIEW {f.stem} AS SELECT * FROM read_parquet('{f}')")
    return con


def validate_sql(sql: str) -> tuple[bool, str | None]:
    """Dry-run validation: guardrails + EXPLAIN (binder/syntax) without executing.
    Returns (ok, error_message)."""
    try:
        check_guardrails(sql)
    except GuardrailError as e:
        return False, f"guardrail: {e}"
    con = _get_connection()
    try:
        con.execute(f"EXPLAIN {sql}")
        return True, None
    except Exception as e:
        return False, str(e).splitlines()[0] if str(e) else "unknown SQL error"
    finally:
        con.close()


def run_sql(sql: str) -> list[dict]:
    check_guardrails(sql)
    con = _get_connection()
    result = con.execute(sql).fetchdf()
    # hard row cap — defends against PII dumps that slip past static guards
    # (e.g. GROUP BY customer_unique_id returns one row per customer)
    if len(result) > MAX_ROWS:
        con.close()
        raise GuardrailError(
            f"result has {len(result)} rows (>{MAX_ROWS}) — likely a bulk/PII dump; narrow the query"
        )
    if "product_category_name" in result.columns:
        trans = con.execute("SELECT * FROM category_translation").fetchdf()
        result = result.merge(trans, on="product_category_name", how="left")
        result["product_category_name"] = result["product_category_name_english"].fillna(result["product_category_name"])
        result = result.drop(columns=["product_category_name_english"], errors="ignore")
    con.close()
    return result.to_dict(orient="records")
