<?php
/**
 * NexusTrade - Simple REST API
 * 
 * Endpoints:
 *   GET    /api.php/items          - List all items
 *   GET    /api.php/items/{id}     - Get one item
 *   POST   /api.php/orders         - Place a trade order
 *   GET    /api.php/orders         - List all orders
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST');
header('Access-Control-Allow-Headers: Content-Type');

// ── DB CONFIG ────────────────────────────────────────────────
$DB_HOST = 'localhost';
$DB_NAME = 'nexustrade';
$DB_USER = 'root';
$DB_PASS = 'secret';

function getDB($host, $name, $user, $pass) {
    try {
        return new PDO("mysql:host=$host;dbname=$name;charset=utf8mb4", $user, $pass, [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        ]);
    } catch (PDOException $e) {
        jsonError(500, 'Database connection failed: ' . $e->getMessage());
    }
}

// ── HELPERS ──────────────────────────────────────────────────
function jsonOK($data, $code = 200) {
    http_response_code($code);
    echo json_encode($data, JSON_PRETTY_PRINT);
    exit;
}

function jsonError($code, $message) {
    http_response_code($code);
    echo json_encode(['error' => $message]);
    exit;
}

function getBody() {
    return json_decode(file_get_contents('php://input'), true) ?? [];
}

// ── ROUTING ──────────────────────────────────────────────────
$method = $_SERVER['REQUEST_METHOD'];
$path   = trim(parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH), '/');
$parts  = explode('/', $path); // e.g. ['api.php', 'items', '3']

$resource = $parts[1] ?? '';   // 'items' or 'orders'
$id       = $parts[2] ?? null; // optional ID

$pdo = getDB($DB_HOST, $DB_NAME, $DB_USER, $DB_PASS);

// ── ITEMS ────────────────────────────────────────────────────
if ($resource === 'items') {

    if ($method === 'GET' && $id) {
        // GET /items/{id}
        $stmt = $pdo->prepare("SELECT * FROM items WHERE id = ?");
        $stmt->execute([$id]);
        $item = $stmt->fetch();
        if (!$item) jsonError(404, 'Item not found');
        jsonOK($item);
    }

    if ($method === 'GET') {
        // GET /items
        $stmt = $pdo->query("SELECT * FROM items ORDER BY id ASC");
        jsonOK($stmt->fetchAll());
    }

// ── ORDERS ───────────────────────────────────────────────────
} elseif ($resource === 'orders') {

    if ($method === 'GET') {
        // GET /orders
        $stmt = $pdo->query("
            SELECT o.*, i.name AS item_name, i.emoji
            FROM orders o
            JOIN items i ON i.id = o.item_id
            ORDER BY o.created_at DESC
        ");
        jsonOK($stmt->fetchAll());
    }

    if ($method === 'POST') {
        // POST /orders
        $body = getBody();

        // Validate
        foreach (['item_id', 'order_type', 'crypto', 'price', 'wallet'] as $f) {
            if (empty($body[$f])) jsonError(400, "Missing field: $f");
        }
        if (!in_array($body['order_type'], ['buy', 'sell']))      jsonError(400, 'order_type must be buy or sell');
        if (!in_array($body['crypto'],     ['ETH', 'BTC', 'SOL'])) jsonError(400, 'crypto must be ETH, BTC or SOL');
        if ((float)$body['price'] <= 0)                           jsonError(400, 'price must be > 0');

        // Check item exists
        $iStmt = $pdo->prepare("SELECT id FROM items WHERE id = ?");
        $iStmt->execute([$body['item_id']]);
        if (!$iStmt->fetch()) jsonError(404, 'Item not found');

        // Insert order
        $stmt = $pdo->prepare("
            INSERT INTO orders (item_id, order_type, price_crypto, crypto_symbol, wallet_address)
            VALUES (?, ?, ?, ?, ?)
        ");
        $stmt->execute([
            (int)$body['item_id'],
            $body['order_type'],
            (float)$body['price'],
            $body['crypto'],
            $body['wallet'],
        ]);

        jsonOK(['success' => true, 'order_id' => $pdo->lastInsertId()], 201);
    }

} else {
    jsonError(404, 'Unknown endpoint. Use /items or /orders');
}
