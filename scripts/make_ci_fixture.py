"""
Build a small, referentially-consistent fixture for the CI eval gate.

Samples ~3000 orders and keeps only the related rows across all tables so that
JOINs still return data. The fixture (a few MB) is committed to the repo, so CI
can run structural/safety gates without the full 38MB dataset or raw CSVs.

Numeric ground-truth checks are NOT meaningful on this sample — those run locally
against the full dataset. See backend/evals/thresholds.ci.json.

Usage: python scripts/make_ci_fixture.py
"""
import pandas as pd
from pathlib import Path

FULL = Path("data/processed")
OUT = Path("backend/evals/fixtures")
OUT.mkdir(parents=True, exist_ok=True)

N_ORDERS = 3000


def load(name):
    return pd.read_parquet(FULL / f"{name}.parquet")


def main():
    orders = load("orders").head(N_ORDERS)
    oids = set(orders.order_id)
    cids = set(orders.customer_id)

    order_items = load("order_items")
    order_items = order_items[order_items.order_id.isin(oids)]
    pids = set(order_items.product_id)
    sids = set(order_items.seller_id)

    products = load("products")
    products = products[products.product_id.isin(pids)]

    customers = load("customers")
    customers = customers[customers.customer_id.isin(cids)]

    sellers = load("sellers")
    sellers = sellers[sellers.seller_id.isin(sids)]

    reviews = load("reviews")
    reviews = reviews[reviews.order_id.isin(oids)]

    payments = load("payments")
    payments = payments[payments.order_id.isin(oids)]

    category_translation = load("category_translation")  # tiny, keep full

    tables = {
        "orders": orders,
        "order_items": order_items,
        "products": products,
        "customers": customers,
        "sellers": sellers,
        "reviews": reviews,
        "payments": payments,
        "category_translation": category_translation,
    }

    total = 0
    for name, df in tables.items():
        path = OUT / f"{name}.parquet"
        df.to_parquet(path, index=False)
        size = path.stat().st_size
        total += size
        print(f"  {name:22} {len(df):6} rows  {size/1024:6.0f} KB")
    print(f"\nFixture total: {total/1024/1024:.1f} MB → {OUT}")


if __name__ == "__main__":
    main()
