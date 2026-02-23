<?php
ini_set('display_errors', 1);
error_reporting(E_ALL);
header("Content-Type: application/json");

$host   = "localhost";
$dbname = "des329";
$user   = "root";
$pass   = "";

try {
    $pdo = new PDO("mysql:host=$host;dbname=$dbname;charset=utf8mb4", $user, $pass);
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    $pdo->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);
} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(["error" => "Database connection failed: " . $e->getMessage()]);
    exit;
}

$method   = $_SERVER['REQUEST_METHOD'];
$path     = isset($_GET['path']) ? $_GET['path'] : '';
$parts    = explode('/', trim($path, '/'));
$resource = $parts[0] ?? '';
$id       = $parts[1] ?? null;
$body     = json_decode(file_get_contents("php://input"), true) ?? [];

if ($resource === 'user') {
    handleUser($method, $id, $body, $pdo);
} elseif ($resource === 'item') {
    handleItem($method, $id, $body, $pdo);
} else {
    http_response_code(404);
    echo json_encode(["error" => "Route not found. Use ?path=user or ?path=item"]);
}

function handleUser($method, $id, $body, $pdo) {
    switch ($method) {
        case 'GET':
            if ($id) {
                $stmt = $pdo->prepare("SELECT UID, Name, Surname, UserName, email, CID, creatTime FROM `user` WHERE UID = ?");
                $stmt->execute([$id]);
                $user = $stmt->fetch();
                if (!$user) { http_response_code(404); echo json_encode(["error" => "User not found"]); }
                else { echo json_encode($user); }
            } else {
                $stmt = $pdo->query("SELECT UID, Name, Surname, UserName, email, CID, creatTime FROM `user`");
                echo json_encode($stmt->fetchAll());
            }
            break;

        case 'POST':
            $required = ['Name', 'Surname', 'UserName', 'email', 'Password', 'CID'];
            foreach ($required as $field) {
                if (empty($body[$field])) { http_response_code(400); echo json_encode(["error" => "$field is required"]); return; }
            }
            if (strlen($body['CID']) !== 13) { http_response_code(400); echo json_encode(["error" => "CID must be exactly 13 characters"]); return; }
            try {
                $stmt = $pdo->prepare("INSERT INTO `user` (Name, Surname, UserName, email, Password, CID) VALUES (?, ?, ?, ?, ?, ?)");
                $stmt->execute([$body['Name'], $body['Surname'], $body['UserName'], $body['email'], password_hash($body['Password'], PASSWORD_BCRYPT), $body['CID']]);
                http_response_code(201);
                echo json_encode(["message" => "User created", "UID" => $pdo->lastInsertId()]);
            } catch (PDOException $e) {
                http_response_code(409);
                echo json_encode(["error" => "Duplicate entry - UserName, email or CID already exists"]);
            }
            break;

        case 'PUT':
        case 'PATCH':
            if (!$id) { http_response_code(400); echo json_encode(["error" => "UID required e.g. ?path=user/1"]); return; }
            $allowed = ['Name', 'Surname', 'UserName', 'email', 'Password', 'CID'];
            $set = []; $values = [];
            foreach ($allowed as $field) {
                if (isset($body[$field])) {
                    if ($field === 'CID' && strlen($body[$field]) !== 13) { http_response_code(400); echo json_encode(["error" => "CID must be exactly 13 characters"]); return; }
                    $set[] = "$field = ?";
                    $values[] = ($field === 'Password') ? password_hash($body[$field], PASSWORD_BCRYPT) : $body[$field];
                }
            }
            if (empty($set)) { http_response_code(400); echo json_encode(["error" => "No valid fields to update"]); return; }
            $values[] = $id;
            $stmt = $pdo->prepare("UPDATE `user` SET " . implode(', ', $set) . " WHERE UID = ?");
            $stmt->execute($values);
            if ($stmt->rowCount() === 0) { http_response_code(404); echo json_encode(["error" => "User not found"]); }
            else { echo json_encode(["message" => "User updated successfully"]); }
            break;

        case 'DELETE':
            if (!$id) { http_response_code(400); echo json_encode(["error" => "UID required e.g. ?path=user/1"]); return; }
            $stmt = $pdo->prepare("DELETE FROM `user` WHERE UID = ?");
            $stmt->execute([$id]);
            if ($stmt->rowCount() === 0) { http_response_code(404); echo json_encode(["error" => "User not found"]); }
            else { echo json_encode(["message" => "User deleted successfully"]); }
            break;

        default:
            http_response_code(405); echo json_encode(["error" => "Method not allowed"]);
    }
}

function handleItem($method, $id, $body, $pdo) {
    switch ($method) {
        case 'GET':
            if ($id) {
                $stmt = $pdo->prepare("SELECT i.*, u.Name, u.Surname FROM item i LEFT JOIN `user` u ON u.UID = i.UID WHERE i.IID = ?");
                $stmt->execute([$id]);
                $item = $stmt->fetch();
                if (!$item) { http_response_code(404); echo json_encode(["error" => "Item not found"]); }
                else { echo json_encode($item); }
            } else {
                $stmt = $pdo->query("SELECT i.*, u.Name, u.Surname FROM item i LEFT JOIN `user` u ON u.UID = i.UID");
                echo json_encode($stmt->fetchAll());
            }
            break;

        case 'POST':
            $required = ['UID', 'ItemName', 'price'];
            foreach ($required as $field) {
                if (!isset($body[$field]) || $body[$field] === '') { http_response_code(400); echo json_encode(["error" => "$field is required"]); return; }
            }
            if (!is_numeric($body['price']) || $body['price'] <= 0) { http_response_code(400); echo json_encode(["error" => "price must be a positive number"]); return; }
            $stmt = $pdo->prepare("SELECT UID FROM `user` WHERE UID = ?");
            $stmt->execute([$body['UID']]);
            if (!$stmt->fetch()) { http_response_code(404); echo json_encode(["error" => "User (UID) not found"]); return; }
            $stmt = $pdo->prepare("INSERT INTO item (UID, ItemName, price) VALUES (?, ?, ?)");
            $stmt->execute([$body['UID'], $body['ItemName'], $body['price']]);
            http_response_code(201);
            echo json_encode(["message" => "Item created", "IID" => $pdo->lastInsertId()]);
            break;

        case 'PUT':
        case 'PATCH':
            if (!$id) { http_response_code(400); echo json_encode(["error" => "IID required e.g. ?path=item/1"]); return; }
            $allowed = ['UID', 'ItemName', 'price'];
            $set = []; $values = [];
            foreach ($allowed as $field) {
                if (isset($body[$field])) {
                    if ($field === 'price' && (!is_numeric($body[$field]) || $body[$field] <= 0)) { http_response_code(400); echo json_encode(["error" => "price must be a positive number"]); return; }
                    $set[] = "$field = ?";
                    $values[] = $body[$field];
                }
            }
            if (empty($set)) { http_response_code(400); echo json_encode(["error" => "No valid fields to update"]); return; }
            $values[] = $id;
            $stmt = $pdo->prepare("UPDATE item SET " . implode(', ', $set) . " WHERE IID = ?");
            $stmt->execute($values);
            if ($stmt->rowCount() === 0) { http_response_code(404); echo json_encode(["error" => "Item not found"]); }
            else { echo json_encode(["message" => "Item updated successfully"]); }
            break;

        case 'DELETE':
            if (!$id) { http_response_code(400); echo json_encode(["error" => "IID required e.g. ?path=item/1"]); return; }
            $stmt = $pdo->prepare("DELETE FROM item WHERE IID = ?");
            $stmt->execute([$id]);
            if ($stmt->rowCount() === 0) { http_response_code(404); echo json_encode(["error" => "Item not found"]); }
            else { echo json_encode(["message" => "Item deleted successfully"]); }
            break;

        default:
            http_response_code(405); echo json_encode(["error" => "Method not allowed"]);
    }
}