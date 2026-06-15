# Customer Behavior

## Repeat Purchase Rate
Only **3.12%** of customers place more than one order — Olist is dominated by one-time buyers.
This is typical for Brazilian marketplace dynamics in 2016–2018.

## customer_id vs customer_unique_id
This is a critical gotcha in the dataset:
- `customer_id` in the orders table is **order-scoped** — a new ID is generated per order
- `customer_unique_id` in the customers table is the **actual persistent user identifier**
- To find repeat buyers, always JOIN customers and GROUP BY `customer_unique_id`, not `customer_id`

```sql
-- Correct way to count repeat buyers
SELECT customer_unique_id, COUNT(*) as order_count
FROM customers c JOIN orders o ON c.customer_id = o.customer_id
GROUP BY customer_unique_id
HAVING COUNT(*) > 1;
```

## Geographic Distribution
Top states by order volume:
- SP (São Paulo): 41,746 orders — 42% of all orders
- RJ (Rio de Janeiro): 12,852
- MG (Minas Gerais): 11,635
- RS, PR, SC: 5,000–5,500 each

São Paulo dominates due to population size and proximity to sellers.

## Review Behavior
- 57% of customers give 5-star reviews
- 11% give 1-star (strong bimodal distribution — customers either love or hate)
- Score 1 often correlates with late delivery or damaged product
- Not all orders receive reviews — use LEFT JOIN when combining
