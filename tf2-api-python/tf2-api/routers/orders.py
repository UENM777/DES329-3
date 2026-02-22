from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from database import get_db
from middleware.auth import get_current_user
import os, secrets

router = APIRouter(prefix="/v1/orders", tags=["Orders"])


class OrderCreate(BaseModel):
    item_id:  int
    quantity: int = Field(1, ge=1)


# ── READ all (current user's orders) ─────────────────────────────────────
@router.get("", summary="List your orders")
def list_orders(user: dict = Depends(get_current_user)):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "SELECT o.*, i.name AS item_name, i.item_type FROM orders o "
                "JOIN items i ON i.id = o.item_id "
                "WHERE o.buyer_id = %s ORDER BY o.created_at DESC",
                (user["user_id"],),
            )
            return cur.fetchall()
    finally:
        db.close()


# ── READ one ──────────────────────────────────────────────────────────────
@router.get("/{order_id}", summary="Get a single order")
def get_order(order_id: int, user: dict = Depends(get_current_user)):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "SELECT o.*, i.name AS item_name FROM orders o "
                "JOIN items i ON i.id = o.item_id WHERE o.id = %s",
                (order_id,),
            )
            order = cur.fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        if order["buyer_id"] != user["user_id"] and not user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Forbidden")
        return order
    finally:
        db.close()


# ── CREATE ────────────────────────────────────────────────────────────────
@router.post("", status_code=201, summary="Place a buy order")
def create_order(body: OrderCreate, user: dict = Depends(get_current_user)):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("SELECT * FROM items WHERE id = %s", (body.item_id,))
            item = cur.fetchone()

        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        if item["status"] != "active":
            raise HTTPException(status_code=409, detail="Item is no longer available")
        if item["seller_id"] == user["user_id"]:
            raise HTTPException(status_code=409, detail="You cannot buy your own listing")
        if body.quantity > item["quantity"]:
            raise HTTPException(status_code=400, detail="Not enough quantity available")

        total           = round(float(item["price_usdt"]) * body.quantity, 2)
        payment_address = "0x" + secrets.token_hex(20)   # mock; replace with HD wallet derivation

        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO orders (buyer_id, item_id, quantity, amount_usdt, network, payment_address) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (user["user_id"], item["id"], body.quantity, total, item["network"], payment_address),
            )
            order_id = cur.lastrowid
            cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
            return cur.fetchone()
    finally:
        db.close()


# ── UPDATE (cancel) ───────────────────────────────────────────────────────
@router.put("/{order_id}/cancel", summary="Cancel a pending order")
def cancel_order(order_id: int, user: dict = Depends(get_current_user)):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
            order = cur.fetchone()

        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        if order["buyer_id"] != user["user_id"]:
            raise HTTPException(status_code=403, detail="Forbidden")
        if order["status"] != "pending":
            raise HTTPException(status_code=409, detail="Only pending orders can be cancelled")

        with db.cursor() as cur:
            cur.execute("UPDATE orders SET status = 'cancelled' WHERE id = %s", (order_id,))
        return {"message": "Order cancelled successfully"}
    finally:
        db.close()
