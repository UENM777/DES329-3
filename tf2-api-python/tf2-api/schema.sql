-- Run: mysql -u root -p tf2_marketplace < schema.sql

CREATE DATABASE IF NOT EXISTS tf2_marketplace;
USE tf2_marketplace;

CREATE TABLE users (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    steam_id   VARCHAR(20) UNIQUE NOT NULL,
    username   VARCHAR(64) NOT NULL,
    is_admin   TINYINT(1) DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE items (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    seller_id  INT NOT NULL,
    name       VARCHAR(128) NOT NULL,
    item_type  ENUM('key','metal','ticket','other') NOT NULL,
    price_usdt DECIMAL(10,2) NOT NULL,
    quantity   INT NOT NULL DEFAULT 1,
    status     ENUM('active','sold','cancelled') DEFAULT 'active',
    network    ENUM('polygon','bsc') NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (seller_id) REFERENCES users(id)
);

CREATE TABLE orders (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    buyer_id        INT NOT NULL,
    item_id         INT NOT NULL,
    quantity        INT NOT NULL DEFAULT 1,
    amount_usdt     DECIMAL(10,2) NOT NULL,
    network         ENUM('polygon','bsc') NOT NULL,
    payment_address VARCHAR(42),
    tx_hash         VARCHAR(66),
    status          ENUM('pending','paid','completed','cancelled') DEFAULT 'pending',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (buyer_id) REFERENCES users(id),
    FOREIGN KEY (item_id)  REFERENCES items(id)
);

CREATE TABLE balances (
    id      INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    token   ENUM('USDT','USDC') NOT NULL,
    network ENUM('polygon','bsc') NOT NULL,
    amount  DECIMAL(18,6) DEFAULT 0.000000,
    UNIQUE KEY unique_balance (user_id, token, network),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE transactions (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    user_id      INT NOT NULL,
    order_id     INT,
    type         ENUM('deposit','withdrawal') NOT NULL,
    amount       DECIMAL(18,6) NOT NULL,
    token        ENUM('USDT','USDC') NOT NULL,
    network      ENUM('polygon','bsc') NOT NULL,
    tx_hash      VARCHAR(66),
    confirmed_at DATETIME,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id)  REFERENCES users(id),
    FOREIGN KEY (order_id) REFERENCES orders(id)
);

CREATE TABLE inventory_events (
    id                   INT AUTO_INCREMENT PRIMARY KEY,
    user_id              INT NOT NULL,
    item_id              INT NOT NULL,
    event_type           ENUM('listed','transferred','received','cancelled') NOT NULL,
    steam_trade_offer_id VARCHAR(32),
    created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (item_id) REFERENCES items(id)
);

-- Seed data
INSERT INTO users (steam_id, username, is_admin) VALUES
    ('76561198000000001', 'AdminUser',  1),
    ('76561198000000002', 'TestSeller', 0),
    ('76561198000000003', 'TestBuyer',  0);

INSERT INTO items (seller_id, name, item_type, price_usdt, quantity, network) VALUES
    (2, 'Mann Co. Supply Crate Key', 'key',    2.50, 10,  'polygon'),
    (2, 'Refined Metal',             'metal',  0.05, 100, 'bsc'),
    (2, 'Tour of Duty Ticket',       'ticket', 0.90, 5,   'polygon');

INSERT INTO balances (user_id, token, network, amount) VALUES
    (2, 'USDT', 'polygon', 50.00),
    (3, 'USDT', 'polygon', 20.00);
