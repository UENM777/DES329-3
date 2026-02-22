import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from database import get_db
from middleware.auth import get_current_user

router = APIRouter(prefix="/v1/wallet", tags=["Wallet"])

VALID_TOKENS   = {"USDT", "USDC"}
VALID_NETWORKS = {"polygon", "bsc"}
EVM_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


class DepositConfirm(BaseModel):
    order_id: int
    tx_hash:  str
    amount:   float = Field(..., gt=0)
    token:    str
    network:  str


class WithdrawRequest(BaseModel):
    amount:     float = Field(..., gt=0)
    token:      str
    network:    str
    to_address: str


# ── READ balance ──────────────────────────────────────────────────────────
@router.get("/balance", summary="Get your token balances")
def get_balance(user: dict = Depends(get_current_user)):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "SELECT token, network, amount FROM balances WHERE user_id = %s",
                (user["user_id"],),
            )
            return {"user_id": user["user_id"], "balances": cur.fetchall()}
    finally:
        db.close()


# ── Confirm deposit (blockchain webhook) ──────────────────────────────────
@router.post("/deposit/confirm", summary="Confirm a blockchain deposit (webhook)")
def confirm_deposit(body: DepositConfirm, user: dict = Depends(get_current_user)):
    if body.token not in VALID_TOKENS:
        raise HTTPException(status_code=400, detail=f"token must be one of {VALID_TOKENS}")
    if body.network not in VALID_NETWORKS:
        raise HTTPException(status_code=400, detail=f"network must be one of {VALID_NETWORKS}")

    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("SELECT * FROM orders WHERE id = %s", (body.order_id,))
            order = cur.fetchone()

        if not order or order["status"] != "pending":
            raise HTTPException(status_code=404, detail="Order not found or already processed")

        with db.cursor() as cur:
            # Mark order paid
            cur.execute("UPDATE orders SET status = 'paid', tx_hash = %s WHERE id = %s",
                        (body.tx_hash, order["id"]))
            # Mark item sold
            cur.execute("UPDATE items SET status = 'sold' WHERE id = %s", (order["item_id"],))
            # Credit buyer balance
            cur.execute(
                "INSERT INTO balances (user_id, token, network, amount) VALUES (%s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE amount = amount + %s",
                (order["buyer_id"], body.token, body.network, body.amount, body.amount),
            )
            # Record transaction
            cur.execute(
                "INSERT INTO transactions (user_id, order_id, type, amount, token, network, tx_hash, confirmed_at) "
                "VALUES (%s, %s, 'deposit', %s, %s, %s, %s, NOW())",
                (order["buyer_id"], order["id"], body.amount, body.token, body.network, body.tx_hash),
            )
            # Inventory event
            cur.execute(
                "INSERT INTO inventory_events (user_id, item_id, event_type) VALUES (%s, %s, 'received')",
                (order["buyer_id"], order["item_id"]),
            )
        return {"message": "Deposit confirmed and order marked as paid"}
    finally:
        db.close()


# ── Withdraw ──────────────────────────────────────────────────────────────
@router.post("/withdraw", summary="Request a withdrawal to your wallet")
def withdraw(body: WithdrawRequest, user: dict = Depends(get_current_user)):
    if body.token not in VALID_TOKENS:
        raise HTTPException(status_code=400, detail=f"token must be one of {VALID_TOKENS}")
    if body.network not in VALID_NETWORKS:
        raise HTTPException(status_code=400, detail=f"network must be one of {VALID_NETWORKS}")
    if not EVM_ADDRESS_RE.match(body.to_address):
        raise HTTPException(status_code=400, detail="Invalid EVM wallet address format")

    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "SELECT amount FROM balances WHERE user_id = %s AND token = %s AND network = %s",
                (user["user_id"], body.token, body.network),
            )
            bal = cur.fetchone()

        if not bal or float(bal["amount"]) < body.amount:
            raise HTTPException(status_code=400, detail="Insufficient balance")

        with db.cursor() as cur:
            cur.execute(
                "UPDATE balances SET amount = amount - %s "
                "WHERE user_id = %s AND token = %s AND network = %s",
                (body.amount, user["user_id"], body.token, body.network),
            )
            cur.execute(
                "INSERT INTO transactions (user_id, type, amount, token, network, confirmed_at) "
                "VALUES (%s, 'withdrawal', %s, %s, %s, NOW())",
                (user["user_id"], body.amount, body.token, body.network),
            )
        return {
            "message":    "Withdrawal request submitted",
            "amount":     body.amount,
            "token":      body.token,
            "network":    body.network,
            "to_address": body.to_address,
        }
    finally:
        db.close()
