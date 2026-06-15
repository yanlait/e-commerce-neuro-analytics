# Payments

## Payment Method Distribution
- **Credit card**: 74% of transactions (avg 3.5 installments)
- **Boleto**: 19% (always 1 installment — upfront payment)
- **Voucher**: 6% (gift cards, promotions)
- **Debit card**: 1.5%

## Installments
Brazilian credit card culture allows splitting purchases into monthly payments (parcelas).
- Average installments: 3.5 for credit card
- High-value orders often use 10–12 installments
- `payment_installments = 1` means paid in full

## Multiple Payment Rows per Order
One order can have multiple rows in the payments table:
- Split payment (e.g. part voucher + part credit card)
- Different installment sequences

Always use `SUM(payment_value)` grouped by `order_id` to get total order payment.
Never JOIN payments 1:1 with orders — it will cause row duplication.

```sql
-- Correct: total payment per order
SELECT order_id, SUM(payment_value) as total_paid
FROM payments
GROUP BY order_id;

-- Payment method breakdown
SELECT payment_type,
       COUNT(*) as transactions,
       ROUND(AVG(payment_value), 2) as avg_value,
       ROUND(AVG(payment_installments), 1) as avg_installments
FROM payments
GROUP BY payment_type
ORDER BY transactions DESC;
```

## Boleto
Boleto bancário is a Brazilian payment slip — customers print or pay digitally at a bank.
Common among unbanked population or those avoiding credit.
Boleto orders sometimes go unpaid (pending status) if customer changes mind.
