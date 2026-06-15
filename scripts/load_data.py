"""Download and convert Olist CSV files to parquet."""
import pandas as pd
from pathlib import Path

RAW = Path("data/raw")
OUT = Path("data/processed")
OUT.mkdir(exist_ok=True)

FILES = [
    "olist_orders_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_products_dataset.csv",
    "olist_customers_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_sellers_dataset.csv",
    "product_category_name_translation.csv",
]

RENAME = {
    "olist_orders_dataset": "orders",
    "olist_order_items_dataset": "order_items",
    "olist_products_dataset": "products",
    "olist_customers_dataset": "customers",
    "olist_order_reviews_dataset": "reviews",
    "olist_order_payments_dataset": "payments",
    "olist_sellers_dataset": "sellers",
    "product_category_name_translation": "category_translation",
}

for fname in FILES:
    src = RAW / fname
    if not src.exists():
        print(f"Missing: {src} — download from Kaggle first")
        continue
    stem = fname.replace(".csv", "")
    name = RENAME.get(stem, stem)
    df = pd.read_csv(src)
    out = OUT / f"{name}.parquet"
    df.to_parquet(out, index=False)
    print(f"Saved {out} ({len(df)} rows)")
