from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from database import get_db
from middleware.auth import get_current_user

router = APIRouter(prefix="/v1/items", tags=["Items"])

VALID_TYPES    = {"key", "metal", "ticket", "other"}
VALID_NETWORKS = {"polygon", "bsc"}
VALID_STATUSES = {"active", "sold", "cancelled"}


class ItemCreate(BaseModel):
    name:       str            = Field(..., min_length=1)
    item_type:  str
    price_usdt: float          = Field(..., gt=0)
    quantity:   int            = Field(..., ge=1)
    network:    str


class ItemUpdate(BaseModel):
    name:       Optional[str]   = None
    price_usdt: Optional[float] = Field(None, gt=0)
    quantity:   Optional[int]   = Field(None, ge=1)
    status:     Optional[str]   = None


# ── READ all ──────────────────────────────────────────────────────────────
@router.get("", summary="List item listings (supports filters)")
def list_items(
    type:     Optional[str]   = None,
    minPrice: Optional[float] = None,
    maxPrice: Optional[float] = None,
    network:  Optional[str]   = None,
    status:   str             = "active",
):
    db = get_db()
    try:
        sql    = "SELECT i.*, u.username AS seller_name FROM items i JOIN users u ON u.id = i.seller_id WHERE 1=1"
        values = []

        if type:
            sql += " AND i.item_type = %s";     values.append(type)
        if minPrice is not None:
            sql += " AND i.price_usdt >= %s";   values.append(minPrice)
        if maxPrice is not None:
            sql += " AND i.price_usdt <= %s";   values.append(maxPrice)
        if network:
            sql += " AND i.network = %s";       values.append(network)

        sql += " AND i.status = %s ORDER BY i.created_at DESC"
        values.append(status)

        with db.cursor() as cur:
            cur.execute(sql, values)
            return cur.fetchall()
    finally:
        db.close()


# ── READ one ──────────────────────────────────────────────────────────────
@router.get("/{item_id}", summary="Get a single listing by ID")
def get_item(item_id: int):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "SELECT i.*, u.username AS seller_name FROM items i "
                "JOIN users u ON u.id = i.seller_id WHERE i.id = %s",
                (item_id,),
            )
            item = cur.fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Item listing not found")
        return item
    finally:
        db.close()


# ── CREATE ────────────────────────────────────────────────────────────────
@router.post("", status_code=201, summary="Create a new item listing")
def create_item(body: ItemCreate, user: dict = Depends(get_current_user)):
    if body.item_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"item_type must be one of {VALID_TYPES}")
    if body.network not in VALID_NETWORKS:
        raise HTTPException(status_code=400, detail=f"network must be one of {VALID_NETWORKS}")

    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO items (seller_id, name, item_type, price_usdt, quantity, network) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (user["user_id"], body.name.strip(), body.item_type,
                 body.price_usdt, body.quantity, body.network),
            )
            item_id = cur.lastrowid

            # Log inventory event
            cur.execute(
                "INSERT INTO inventory_events (user_id, item_id, event_type) VALUES (%s, %s, 'listed')",
                (user["user_id"], item_id),
            )
            cur.execute("SELECT * FROM items WHERE id = %s", (item_id,))
            return cur.fetchone()
    finally:
        db.close()


# ── UPDATE ────────────────────────────────────────────────────────────────
@router.put("/{item_id}", summary="Update an existing listing")
def update_item(item_id: int, body: ItemUpdate, user: dict = Depends(get_current_user)):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("SELECT * FROM items WHERE id = %s", (item_id,))
            item = cur.fetchone()

        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        if item["seller_id"] != user["user_id"] and not user.get("is_admin"):
            raise HTTPException(status_code=403, detail="You do not own this listing")
        if body.status and body.status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"status must be one of {VALID_STATUSES}")

        updates = body.model_dump(exclude_none=True)
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        set_clause = ", ".join(f"{k} = %s" for k in updates)
        with db.cursor() as cur:
            cur.execute(
                f"UPDATE items SET {set_clause} WHERE id = %s",
                (*updates.values(), item_id),
            )
            cur.execute("SELECT * FROM items WHERE id = %s", (item_id,))
            return cur.fetchone()
    finally:
        db.close()


# ── DELETE ────────────────────────────────────────────────────────────────
@router.delete("/{item_id}", status_code=204, summary="Cancel / delete a listing")
def delete_item(item_id: int, user: dict = Depends(get_current_user)):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("SELECT * FROM items WHERE id = %s", (item_id,))
            item = cur.fetchone()

        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        if item["seller_id"] != user["user_id"] and not user.get("is_admin"):
            raise HTTPException(status_code=403, detail="You do not own this listing")
        if item["status"] == "sold":
            raise HTTPException(status_code=409, detail="Cannot delete a sold listing")

        with db.cursor() as cur:
            cur.execute("UPDATE items SET status = 'cancelled' WHERE id = %s", (item_id,))
            cur.execute(
                "INSERT INTO inventory_events (user_id, item_id, event_type) VALUES (%s, %s, 'cancelled')",
                (user["user_id"], item_id),
            )
    finally:
        db.close()
