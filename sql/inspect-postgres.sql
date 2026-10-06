-- What DMS created on PostgreSQL by itself (DROP_AND_CREATE), compared with the source.
SELECT tablename AS table_name, COUNT(*) AS indexes
  FROM pg_indexes WHERE schemaname = 'ubuntu_retail' GROUP BY tablename ORDER BY 1;
SELECT COUNT(*) AS foreign_keys FROM information_schema.table_constraints
 WHERE constraint_schema = 'ubuntu_retail' AND constraint_type = 'FOREIGN KEY';
SELECT table_name, column_name, data_type, character_maximum_length AS len, column_default
  FROM information_schema.columns
 WHERE table_schema = 'ubuntu_retail' AND table_name = 'orders' ORDER BY ordinal_position;
SELECT 'orders' AS tbl, COUNT(*) AS row_count FROM ubuntu_retail.orders
UNION ALL SELECT 'order_items', COUNT(*) FROM ubuntu_retail.order_items;
-- The application's normal insert (no order_id: on MySQL, AUTO_INCREMENT supplies it):
INSERT INTO ubuntu_retail.orders (customer_id, status, total_zar) VALUES (1, 'NEW', 0);
