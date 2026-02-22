from fastapi import FastAPI
from routers import auth, items, orders, wallet, admin

app = FastAPI(
    title="TF2 Item Trading – Stablecoin Marketplace API",
    description="Buy and sell TF2 items using USDT/USDC on Polygon and BSC.",
    version="1.0.0",
)

app.include_router(auth.router)
app.include_router(items.router)
app.include_router(orders.router)
app.include_router(wallet.router)
app.include_router(admin.router)


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "message": "TF2 Marketplace API is running"}
