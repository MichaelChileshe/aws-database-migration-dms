-- Run at cutover, after validation: adding the constraints checks every existing row.
USE ubuntu_retail;
ALTER TABLE orders      ADD CONSTRAINT fk_orders_customer FOREIGN KEY (customer_id) REFERENCES customers (customer_id);
ALTER TABLE order_items ADD CONSTRAINT fk_items_order     FOREIGN KEY (order_id)    REFERENCES orders (order_id);
ALTER TABLE order_items ADD CONSTRAINT fk_items_product   FOREIGN KEY (product_id)  REFERENCES products (product_id);
SELECT TABLE_NAME, CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS
 WHERE CONSTRAINT_SCHEMA = 'ubuntu_retail' AND CONSTRAINT_TYPE = 'FOREIGN KEY' ORDER BY 1, 2;
