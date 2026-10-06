-- 5,000 customers, 500 products, 200,000 orders, 400,000 order lines. Deterministic, so every run is comparable.
USE ubuntu_retail;
SET SESSION cte_max_recursion_depth = 1000000;

INSERT INTO customers (email, full_name, province, loyalty_member, created_at)
WITH RECURSIVE seq (n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM seq WHERE n < 5000)
SELECT CONCAT('customer', n, '@example.co.za'), CONCAT('Customer ', n),
       ELT(1 + (n % 9), 'GP','WC','KZN','EC','FS','LP','MP','NW','NC'), n % 3 = 0,
       '2025-01-01 08:00:00' + INTERVAL n MINUTE
FROM seq;

INSERT INTO products (sku, name, price_zar)
WITH RECURSIVE seq (n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM seq WHERE n < 500)
SELECT CONCAT('UR-', LPAD(n, 5, '0')), CONCAT('Product ', n), 19.99 + (n % 200) * 5
FROM seq;

INSERT INTO orders (customer_id, status, total_zar, created_at, updated_at)
WITH RECURSIVE seq (n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM seq WHERE n < 200000)
SELECT 1 + (n * 7919) % 5000, ELT(1 + (n % 4), 'NEW','PAID','SHIPPED','CANCELLED'), 50 + (n * 37) % 5000,
       '2025-06-01 00:00:00.000' + INTERVAL n * 60 SECOND, '2025-06-01 00:00:00.000' + INTERVAL n * 60 SECOND
FROM seq;

INSERT INTO order_items (order_id, product_id, qty, price_zar)
WITH RECURSIVE seq (n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM seq WHERE n < 400000)
SELECT 1 + FLOOR((n - 1) / 2), 1 + (n * 31) % 500, 1 + n % 3, 19.99 + (n % 200) * 5
FROM seq;

SELECT 'customers' AS tbl, COUNT(*) AS row_count FROM customers
UNION ALL SELECT 'products', COUNT(*) FROM products
UNION ALL SELECT 'orders', COUNT(*) FROM orders
UNION ALL SELECT 'order_items', COUNT(*) FROM order_items;
