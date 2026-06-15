# Sellers

## Overview
3,095 unique sellers on the Olist platform.
Sellers are concentrated in São Paulo state — same geographic pattern as customers.

## Seller Performance Metrics
Key metrics for evaluating sellers:
- **Revenue**: SUM(price) from order_items for their seller_id
- **Order count**: COUNT(DISTINCT order_id) from order_items
- **Avg review score**: JOIN reviews through orders
- **On-time rate**: % of orders delivered before estimated date
- **Avg items per order**: AVG(order_item_id) — order_item_id is a sequence number per order

## SQL patterns

```sql
-- Top sellers by revenue
SELECT oi.seller_id,
       s.seller_state,
       COUNT(DISTINCT oi.order_id) as orders,
       ROUND(SUM(oi.price), 2) as revenue,
       ROUND(AVG(r.review_score), 2) as avg_score
FROM order_items oi
JOIN sellers s ON oi.seller_id = s.seller_id
LEFT JOIN orders o ON oi.order_id = o.order_id
LEFT JOIN reviews r ON o.order_id = r.order_id
GROUP BY oi.seller_id, s.seller_state
ORDER BY revenue DESC
LIMIT 10;
```

## Multi-seller Orders
A single order can contain items from multiple sellers.
Each seller ships their items independently — this affects delivery time.
`order_item_id` is a sequence number within an order (1, 2, 3...) not a global ID.
