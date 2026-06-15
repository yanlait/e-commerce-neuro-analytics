# Business Metrics

## Revenue
Total revenue is the sum of all `price` values in `order_items`. It excludes freight costs.
Freight is stored separately in `freight_value` and represents shipping cost paid by the customer.

## Average Order Value (AOV)
AOV = total revenue / number of distinct orders.
Calculated as: `SUM(price) / COUNT(DISTINCT order_id)` from `order_items`.

## Order Status
Orders go through these statuses: created → approved → processing → shipped → delivered.
Canceled and unavailable are terminal failure states.
Use `status = 'delivered'` to count only completed orders.

## Review Score
Customers rate orders 1–5 in the `reviews` table. Score 5 is best.
Average review score is a proxy for customer satisfaction.
Not every order has a review — use LEFT JOIN when combining with orders.

## Freight Rate
Freight rate = `freight_value / price` per item. High freight rate may indicate heavy or remote deliveries.
