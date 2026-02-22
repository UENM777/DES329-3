CREATE DATABASE IF NOT EXISTS nexustrade;
USE nexustrade;

CREATE TABLE IF NOT EXISTS items (
    id       INT AUTO_INCREMENT PRIMARY KEY,
    name     VARCHAR(100) NOT NULL,
    emoji    VARCHAR(8)   DEFAULT '🎮',
    type     VARCHAR(30)  NOT NULL,
    rarity   VARCHAR(20)  NOT NULL,
    price    DECIMAL(10,4) NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    item_id        INT NOT NULL,
    order_type     ENUM('buy','sell') NOT NULL,
    price_crypto   DECIMAL(18,8) NOT NULL,
    crypto_symbol  VARCHAR(10)  NOT NULL,
    wallet_address VARCHAR(100) NOT NULL,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES items(id)
);

-- Seed items
INSERT INTO items (name, emoji, type, rarity, price) VALUES
  ('Void Blade',        '⚔️',  'weapon', 'legendary', 0.42),
  ('Aegis Shield',      '🛡️',  'armor',  'epic',       0.18),
  ('Dragon Mount',      '🐉',  'mount',  'legendary',  1.05),
  ('Elixir of Rage',    '⚗️',  'potion', 'rare',       0.05),
  ('Stormcaller Staff', '🔮',  'weapon', 'rare',       0.09),
  ('Speed Potion',      '💨',  'potion', 'common',     0.01);
