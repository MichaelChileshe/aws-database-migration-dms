-- Ubuntu Retail's order database, as it runs on-premises (MySQL 8.0).
CREATE DATABASE IF NOT EXISTS ubuntu_retail;
USE ubuntu_retail;

CREATE TABLE customers (
  customer_id     INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  email           VARCHAR(120) NOT NULL,
  full_name       VARCHAR(100) NOT NULL,
  province        ENUM('GP','WC','KZN','EC','FS','LP','MP','NW','NC') NOT NULL,
  loyalty_member  TINYINT(1) NOT NULL DEFAULT 0,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_customers_email (email)
) ENGINE=InnoDB;

CREATE TABLE products (
  product_id  INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  sku         VARCHAR(20) NOT NULL,
  name        VARCHAR(120) NOT NULL,
  price_zar   DECIMAL(10,2) NOT NULL,
  UNIQUE KEY uq_products_sku (sku)
) ENGINE=InnoDB;

CREATE TABLE orders (
  order_id     INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  customer_id  INT UNSIGNED NOT NULL,
  status       ENUM('NEW','PAID','SHIPPED','CANCELLED') NOT NULL DEFAULT 'NEW',
  total_zar    DECIMAL(12,2) NOT NULL DEFAULT 0,
  created_at   DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at   DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  KEY idx_orders_customer (customer_id),
  KEY idx_orders_status_created (status, created_at),
  CONSTRAINT fk_orders_customer FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
) ENGINE=InnoDB;

CREATE TABLE order_items (
  order_item_id  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  order_id       INT UNSIGNED NOT NULL,
  product_id     INT UNSIGNED NOT NULL,
  qty            SMALLINT UNSIGNED NOT NULL,
  price_zar      DECIMAL(10,2) NOT NULL,
  KEY idx_items_order (order_id),
  KEY idx_items_product (product_id),
  CONSTRAINT fk_items_order FOREIGN KEY (order_id) REFERENCES orders (order_id),
  CONSTRAINT fk_items_product FOREIGN KEY (product_id) REFERENCES products (product_id)
) ENGINE=InnoDB;
