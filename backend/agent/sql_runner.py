import re
import duckdb
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data/processed"

_BLOCKED = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|TRUNCATE|EXEC|EXECUTE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)
# SELECT * without LIMIT risks dumping entire tables
_UNBOUNDED_STAR = re.compile(r"SELECT\s+\*", re.IGNORECASE)
# any query without LIMIT that touches raw customer/order tables risks data dump
_REQUIRES_LIMIT = re.compile(r"\bFROM\s+(customers|orders|order_items|reviews|payments)\b", re.IGNORECASE)
MAX_ROWS = 1000


def _get_connection():
    con = duckdb.connect()
    for f in DATA_DIR.glob("*.parquet"):
        con.execute(f"CREATE VIEW {f.stem} AS SELECT * FROM read_parquet('{f}')")
    return con


def run_sql(sql: str) -> list[dict]:
    if _BLOCKED.search(sql):
        raise ValueError(f"SQL contains disallowed statement: {_BLOCKED.search(sql).group()}")
    if _UNBOUNDED_STAR.search(sql) and "LIMIT" not in sql.upper():
        raise ValueError("SELECT * without LIMIT is not allowed")
    if _REQUIRES_LIMIT.search(sql) and "LIMIT" not in sql.upper() and "GROUP BY" not in sql.upper():
        raise ValueError("Queries on raw tables require LIMIT or GROUP BY")
    con = _get_connection()
    result = con.execute(sql).fetchdf()
    # translate portuguese category names if column present
    if "product_category_name" in result.columns:
        trans = con.execute("SELECT * FROM category_translation").fetchdf()
        result = result.merge(trans, on="product_category_name", how="left")
        result["product_category_name"] = result["product_category_name_english"].fillna(result["product_category_name"])
        result = result.drop(columns=["product_category_name_english"], errors="ignore")
    return result.to_dict(orient="records")
