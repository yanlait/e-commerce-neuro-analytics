# Olist Dataset Overview

## Source
Brazilian e-commerce public dataset by Olist, available on Kaggle.
Contains ~100k orders from 2016 to 2018 made at Olist marketplace.

## Tables
- **orders** — one row per order, tracks status and timestamps
- **order_items** — one row per item in an order; an order can have multiple items
- **products** — product catalog; category names are in Portuguese
- **customers** — one row per customer; customer_id is anonymized
- **reviews** — customer reviews after delivery; not every order has one
- **payments** — payment transactions; one order can have multiple payment rows (split payments)
- **sellers** — sellers registered on the Olist platform
- **category_translation** — maps Portuguese category names to English

## Important gotchas
- `customer_id` in orders is NOT the same as a persistent user ID — each order gets a new customer_id
- To analyze repeat buyers, join on `customer_unique_id` from the customers table
- Payments table can have multiple rows per order (installments or split payment types)
- Some orders have items from multiple sellers
- Timestamps are in Brazil timezone (BRT, UTC-3)
