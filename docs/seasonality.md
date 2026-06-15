# Seasonality and Growth

## Dataset Period
Orders span from **September 2016 to August 2018**.
- September–October 2018 data is incomplete (only 20 orders) — exclude from trend analysis
- 2016 data is sparse (Q4 only) — use 2017–2018 for reliable trends

## Black Friday Effect
November 2017 shows a sharp spike: **7,544 orders** vs 4,631 in October (+63%).
This is the single largest month-over-month jump in the dataset.
When analyzing November, always consider Black Friday as a confounding factor.

## Year-over-Year Growth
Olist grew significantly from 2017 to 2018:
- Q1 2017: ~5,000 orders/month average
- Q1 2018: ~7,000 orders/month average
- Growth rate: ~40% YoY

## Seasonality Patterns
- Peaks: November (Black Friday), January (post-holiday)
- Dip: relative slowdown in June–July
- No strong weekly seasonality visible in this dataset

## SQL for time-based analysis

```sql
-- Monthly order trend (exclude incomplete 2018 tail)
SELECT DATE_TRUNC('month', CAST(order_purchase_timestamp AS TIMESTAMP)) as month,
       COUNT(*) as orders,
       SUM(oi.price) as revenue
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE CAST(order_purchase_timestamp AS TIMESTAMP) < '2018-09-01'
GROUP BY 1 ORDER BY 1;
```
