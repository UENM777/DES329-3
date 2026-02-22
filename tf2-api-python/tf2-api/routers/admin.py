from fastapi import APIRouter, Depends
from database import get_db
from middleware.auth import require_admin

router = APIRouter(prefix="/v1/admin", tags=["Admin"])


# ── Sales report ──────────────────────────────────────────────────────────
@router.get("/reports/sales", summary="Sales summary report (admin only)")
def sales_report(user: dict = Depends(require_admin)):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*)                                                        AS total_orders,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END)          AS completed_orders,
                    SUM(CASE WHEN status = 'pending'   THEN 1 ELSE 0 END)          AS pending_orders,
                    SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END)          AS cancelled_orders,
                    SUM(CASE WHEN status = 'completed' THEN amount_usdt ELSE 0 END) AS total_revenue_usdt
                FROM orders
            """)
            summary = cur.fetchone()

            cur.execute("""
                SELECT i.name, i.item_type,
                       COUNT(o.id)          AS times_sold,
                       SUM(o.amount_usdt)   AS revenue_usdt
                FROM orders o
                JOIN items i ON i.id = o.item_id
                WHERE o.status = 'completed'
                GROUP BY i.id
                ORDER BY times_sold DESC
                LIMIT 10
            """)
            top_items = cur.fetchall()

            cur.execute("""
                SELECT DATE(created_at)  AS date,
                       COUNT(*)          AS orders,
                       SUM(amount_usdt)  AS revenue_usdt
                FROM orders
                WHERE status = 'completed'
                GROUP BY DATE(created_at)
                ORDER BY date DESC
                LIMIT 30
            """)
            daily_sales = cur.fetchall()

        return {"summary": summary, "top_items": top_items, "daily_sales": daily_sales}
    finally:
        db.close()


# ── Inventory log ─────────────────────────────────────────────────────────
@router.get("/inventory", summary="Inventory event log (admin only)")
def inventory_log(user: dict = Depends(require_admin)):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("""
                SELECT ie.*, u.username, i.name AS item_name
                FROM inventory_events ie
                JOIN users u ON u.id = ie.user_id
                JOIN items i ON i.id = ie.item_id
                ORDER BY ie.created_at DESC
                LIMIT 100
            """)
            return cur.fetchall()
    finally:
        db.close()
