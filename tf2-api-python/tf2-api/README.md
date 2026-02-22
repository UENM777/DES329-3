# TF2 Item Trading – Stablecoin Marketplace REST API
**Python · FastAPI · MySQL · JWT**

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy env and fill in your DB + secret
cp .env.example .env

# 3. Create DB and run schema
mysql -u root -p -e "CREATE DATABASE tf2_marketplace;"
mysql -u root -p tf2_marketplace < schema.sql

# 4. Start the server
uvicorn main:app --reload
# Swagger UI -> http://localhost:8000/docs
```

---

## Test with curl (CRUD walkthrough)

### Login → get token
```bash
curl -s -X POST http://localhost:8000/v1/auth/steam \
  -H "Content-Type: application/json" \
  -d '{"steam_id": "76561198000000002"}'

# Copy the token, then:
TOKEN="<paste_token_here>"
```

### CREATE – new item listing
```bash
curl -s -X POST http://localhost:8000/v1/items \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Mann Co. Key","item_type":"key","price_usdt":2.50,"quantity":5,"network":"polygon"}'
```

### READ – list all active items
```bash
curl -s http://localhost:8000/v1/items
curl -s "http://localhost:8000/v1/items?type=key&maxPrice=3.00"   # with filters
```

### READ – single item
```bash
curl -s http://localhost:8000/v1/items/1
```

### UPDATE – change price
```bash
curl -s -X PUT http://localhost:8000/v1/items/1 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"price_usdt": 2.30}'
```

### DELETE – cancel listing
```bash
curl -s -X DELETE http://localhost:8000/v1/items/1 \
  -H "Authorization: Bearer $TOKEN"
```

### Place a buy order (login as buyer first)
```bash
TOKEN2=$(curl -s -X POST http://localhost:8000/v1/auth/steam \
  -H "Content-Type: application/json" \
  -d '{"steam_id":"76561198000000003"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

curl -s -X POST http://localhost:8000/v1/orders \
  -H "Authorization: Bearer $TOKEN2" \
  -H "Content-Type: application/json" \
  -d '{"item_id": 2, "quantity": 1}'
```

### Check wallet balance
```bash
curl -s http://localhost:8000/v1/wallet/balance \
  -H "Authorization: Bearer $TOKEN"
```

### Admin report (login as admin steam_id first)
```bash
ADMIN=$(curl -s -X POST http://localhost:8000/v1/auth/steam \
  -H "Content-Type: application/json" \
  -d '{"steam_id":"76561198000000001"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

curl -s http://localhost:8000/v1/admin/reports/sales \
  -H "Authorization: Bearer $ADMIN"
```

---

## Project Structure
```
tf2-api/
├── main.py                  # App entry point, registers all routers
├── database.py              # MySQL connection (PyMySQL)
├── requirements.txt
├── schema.sql               # DB schema + seed data
├── .env.example
├── middleware/
│   └── auth.py              # JWT create / verify / admin guard
└── routers/
    ├── auth.py              # POST /v1/auth/steam
    ├── items.py             # CRUD /v1/items
    ├── orders.py            # CRUD /v1/orders
    ├── wallet.py            # /v1/wallet/balance|deposit|withdraw
    └── admin.py             # /v1/admin/reports|inventory
```

## Auto-generated docs
FastAPI generates interactive docs automatically:
- Swagger UI → http://localhost:8000/docs
- ReDoc      → http://localhost:8000/redoc
