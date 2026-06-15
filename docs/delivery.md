# Delivery Analytics

## Delivery Time
Average delivery time is **12.5 days** from purchase to customer receipt.
- Minimum: 0 days (same-day, very rare)
- Maximum: 210 days (extreme outlier)
- Column: `order_delivered_customer_date` minus `order_purchase_timestamp`
- Always CAST both columns to TIMESTAMP before date arithmetic

## On-Time Delivery Rate
**91.9%** of orders are delivered on or before the estimated delivery date.
- On-time = `order_delivered_customer_date <= order_estimated_delivery_date`
- Both columns can be NULL — use WHERE to filter
- Late deliveries correlate with lower review scores

## Delivery by State
Remote states (North and Northeast Brazil) have longer delivery times than São Paulo.
SP orders arrive in ~8 days on average; AM (Amazonas) can take 25+ days.

## SQL patterns for delivery analysis

```sql
-- Average delivery time in days
SELECT ROUND(AVG(DATEDIFF('day',
    CAST(order_purchase_timestamp AS TIMESTAMP),
    CAST(order_delivered_customer_date AS TIMESTAMP)
)), 1) as avg_days
FROM orders
WHERE order_delivered_customer_date IS NOT NULL;

-- On-time delivery rate
SELECT ROUND(100.0 * SUM(CASE WHEN order_delivered_customer_date <= order_estimated_delivery_date THEN 1 ELSE 0 END) / COUNT(*), 1) as on_time_pct
FROM orders
WHERE order_delivered_customer_date IS NOT NULL AND order_estimated_delivery_date IS NOT NULL;
```
