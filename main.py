import os
import re
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse, unquote

import aiosqlite
import httpx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="TF2 Trading Companion API (SQLite)")

DB_PATH = "app.db"

# Your watchlist accepts sku-like strings (not necessarily what backpack.tf expects).
# Examples:
#  - 5021;6
#  - 721;5;u89
SKU_PATTERN = re.compile(r"^[0-9]+;[0-9]+(;[A-Za-z0-9\-]+)*$")

# Map backpack.tf stats quality strings to TF2 quality IDs
QUALITY_NAME_TO_ID: Dict[str, int] = {
    "Unique": 6,
    "Genuine": 1,
    "Vintage": 3,
    "Unusual": 5,
    "Strange": 11,
    "Haunted": 13,
    "Collector's": 14,
    "Collectors": 14,
    "Decorated": 15,
}


# -----------------------
# Pydantic models + validation
# -----------------------
class WatchlistCreate(BaseModel):
    sku: str = Field(..., min_length=3, max_length=64, examples=["5021;6"])
    name: str = Field(..., min_length=2, max_length=120, examples=["Mann Co. Supply Crate Key"])
    target_price_ref: float = Field(..., gt=0, le=100000, examples=[80.0])
    note: Optional[str] = Field(None, max_length=300, examples=["Buy if price drops below target"])

    @field_validator("sku")
    @classmethod
    def validate_sku(cls, v: str) -> str:
        v = v.strip()
        if not SKU_PATTERN.match(v):
            raise ValueError("sku must look like 'defindex;quality' (example: 5021;6)")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if "  " in v:
            raise ValueError("name must not contain double spaces")
        return v


class WatchlistItem(WatchlistCreate):
    id: int


# -----------------------
# DB init
# -----------------------
@app.on_event("startup")
async def startup():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                target_price_ref REAL NOT NULL,
                note TEXT
            )
            """
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_sku ON watchlist(sku)")
        await db.commit()


def row_to_item(row) -> WatchlistItem:
    return WatchlistItem(
        id=row[0],
        sku=row[1],
        name=row[2],
        target_price_ref=row[3],
        note=row[4],
    )


# -----------------------
# CRUD endpoints (SQLite)
# -----------------------
@app.post("/watchlist", response_model=WatchlistItem, status_code=201)
async def create_item(payload: WatchlistCreate):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            cur = await db.execute(
                """
                INSERT INTO watchlist (sku, name, target_price_ref, note)
                VALUES (?, ?, ?, ?)
                """,
                (payload.sku, payload.name, payload.target_price_ref, payload.note),
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            raise HTTPException(status_code=409, detail="sku already exists in watchlist")

        item_id = cur.lastrowid
        row = await (
            await db.execute(
                "SELECT id, sku, name, target_price_ref, note FROM watchlist WHERE id = ?",
                (item_id,),
            )
        ).fetchone()

    return row_to_item(row)


@app.get("/watchlist", response_model=List[WatchlistItem])
async def list_items():
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (
            await db.execute(
                "SELECT id, sku, name, target_price_ref, note FROM watchlist ORDER BY id ASC"
            )
        ).fetchall()
    return [row_to_item(r) for r in rows]


@app.get("/watchlist/{item_id}", response_model=WatchlistItem)
async def get_item(item_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (
            await db.execute(
                "SELECT id, sku, name, target_price_ref, note FROM watchlist WHERE id = ?",
                (item_id,),
            )
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    return row_to_item(row)


@app.put("/watchlist/{item_id}", response_model=WatchlistItem)
async def update_item(item_id: int, payload: WatchlistCreate):
    async with aiosqlite.connect(DB_PATH) as db:
        existing = await (await db.execute("SELECT id FROM watchlist WHERE id = ?", (item_id,))).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Watchlist item not found")

        try:
            await db.execute(
                """
                UPDATE watchlist
                SET sku = ?, name = ?, target_price_ref = ?, note = ?
                WHERE id = ?
                """,
                (payload.sku, payload.name, payload.target_price_ref, payload.note, item_id),
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            raise HTTPException(status_code=409, detail="sku already exists in watchlist")

        row = await (
            await db.execute(
                "SELECT id, sku, name, target_price_ref, note FROM watchlist WHERE id = ?",
                (item_id,),
            )
        ).fetchone()

    return row_to_item(row)


@app.delete("/watchlist/{item_id}", status_code=204)
async def delete_item(item_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("DELETE FROM watchlist WHERE id = ?", (item_id,))
        await db.commit()

    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    return None


# -----------------------
# Debug: confirm server sees auth (safe preview only)
# -----------------------
@app.get("/debug/bptf-auth")
def debug_bptf_auth():
    token = (os.getenv("BPTF_TOKEN") or "").strip()
    key = (os.getenv("BPTF_KEY") or "").strip()
    return {
        "has_token": bool(token),
        "token_len": len(token),
        "token_head": (token[:6] if token else None),
        "token_tail": (token[-4:] if token else None),
        "has_key": bool(key),
        "key_len": len(key),
        "key_head": (key[:6] if key else None),
        "key_tail": (key[-4:] if key else None),
    }


# -----------------------
# backpack.tf stats URL parsing -> query params
# -----------------------
def parse_bptf_stats_url(stats_url: str) -> Dict[str, Any]:
    """
    Example:
      https://backpack.tf/stats/Unusual/Conquistador/Tradable/Craftable/89
    Extracts:
      item_name = Conquistador
      quality = 5 (Unusual)
      tradable = 1
      craftable = 1
      particle = 89
    """
    u = stats_url.strip()
    p = urlparse(u)
    if not p.netloc.endswith("backpack.tf"):
        raise HTTPException(status_code=422, detail="stats_url must be a backpack.tf link")

    parts = [seg for seg in p.path.split("/") if seg]
    if len(parts) < 5 or parts[0] != "stats":
        raise HTTPException(status_code=422, detail="stats_url path format not recognized")

    quality_name = unquote(parts[1])
    item_name = unquote(parts[2])

    tradable_seg = unquote(parts[3])
    craftable_seg = unquote(parts[4])

    tradable = 1 if tradable_seg.lower() == "tradable" else 0
    craftable = 1 if craftable_seg.lower() == "craftable" else 0

    quality = QUALITY_NAME_TO_ID.get(quality_name)
    particle: Optional[int] = None

    if len(parts) >= 6:
        tail = unquote(parts[5])
        if tail.isdigit():
            particle = int(tail)

    return {
        "item_name": item_name,
        "quality": quality,
        "tradable": tradable,
        "craftable": craftable,
        "particle": particle,
        "parsed": {
            "quality_name": quality_name,
            "tradable_seg": tradable_seg,
            "craftable_seg": craftable_seg,
        },
    }


# -----------------------
# backpack.tf v2 classifieds listings
# -----------------------
def _choose_auth(params: Dict[str, Any]) -> (Dict[str, Any], str):
    """
    For v2 classifieds listings, common usage is:
      - token=... (user access token) as query param
      - or key=... (api key) as query param
    """
    token = (os.getenv("BPTF_TOKEN") or "").strip()
    key = (os.getenv("BPTF_KEY") or "").strip()

    if token:
        params["token"] = token
        return params, "token_query"
    if key:
        params["key"] = key
        return params, "key_query"
    return params, "none"


def _extract_listings(data: Any) -> List[Dict[str, Any]]:
    """
    v2 response shape varies.
    Handle both list and dict containers, and your observed 'results' key.
    """
    def as_list(x: Any) -> List[Dict[str, Any]]:
        if isinstance(x, list):
            return x
        if isinstance(x, dict):
            return list(x.values())
        return []

    if not isinstance(data, dict):
        return []

    # A) top-level listings
    if "listings" in data:
        return as_list(data.get("listings"))

    # B) top-level results (your response has this)
    results = data.get("results")
    if isinstance(results, list):
        return results
    if isinstance(results, dict):
        # common: results contains listings
        if "listings" in results:
            return as_list(results.get("listings"))
        # sometimes results itself is dict keyed by listing id
        return as_list(results)

    # C) data wrapper
    wrapper = data.get("data")
    if isinstance(wrapper, dict):
        if "listings" in wrapper:
            return as_list(wrapper.get("listings"))
        if "results" in wrapper:
            r2 = wrapper.get("results")
            if isinstance(r2, list):
                return r2
            if isinstance(r2, dict):
                if "listings" in r2:
                    return as_list(r2.get("listings"))
                return as_list(r2)

    if isinstance(wrapper, list):
        return wrapper

    return []


@app.get("/market/listings")
async def market_listings(
    item_name: str = Query(..., description="Item name (as on backpack.tf), e.g. Mann Co. Supply Crate Key"),
    appid: int = Query(440),
    quality: Optional[int] = Query(None),
    tradable: Optional[int] = Query(None),
    craftable: Optional[int] = Query(None),
    particle: Optional[int] = Query(None, description="Unusual effect id, e.g. 89"),
    limit: int = Query(50, ge=1, le=100),
    debug_raw: bool = Query(False),
) -> Dict[str, Any]:
    item_name = item_name.strip()
    if not item_name:
        raise HTTPException(status_code=422, detail="item_name must not be empty")

    url = "https://backpack.tf/api/v2/classifieds/listings"

    params: Dict[str, Any] = {
        "appid": appid,
        "sku": item_name,
        "limit": limit,
    }

    if quality is not None:
        params["quality"] = quality
    if tradable is not None:
        params["tradable"] = tradable
    if craftable is not None:
        params["craftable"] = craftable
    if particle is not None:
        params["particle"] = particle

    params, auth_used = _choose_auth(params)

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url, params=params, headers={"User-Agent": "TF2-Companion-API/1.0"})
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Failed to reach backpack.tf: {str(e)}")

    if r.status_code == 429:
        retry_after = r.headers.get("Retry-After")
        raise HTTPException(status_code=429, detail=f"Rate limited by backpack.tf. Retry-After={retry_after}")

    if r.status_code != 200:
        body_preview = (r.text or "")[:200]
        raise HTTPException(status_code=502, detail=f"backpack.tf error: {r.status_code} {body_preview}")

    data = r.json()
    listings = _extract_listings(data)

    sells: List[Dict[str, Any]] = []
    buys: List[Dict[str, Any]] = []

    for lst in listings:
        intent = lst.get("intent")
        # intent can be "buy"/"sell" OR int (commonly 0/1)
        if isinstance(intent, int):
            intent = "buy" if intent == 0 else "sell"

        cur = lst.get("currencies") or {}
        price = {"keys": cur.get("keys"), "metal": cur.get("metal")}
        if intent == "sell":
            sells.append(price)
        elif intent == "buy":
            buys.append(price)

    def sort_key(p):
        k = p["keys"] if p["keys"] is not None else 10**9
        m = p["metal"] if p["metal"] is not None else 10**9
        return (k, m)

    lowest_sell = min(sells, key=sort_key) if sells else None
    highest_buy = max(buys, key=sort_key) if buys else None

    raw_preview = None
    if debug_raw and isinstance(data, dict):
        results_obj = data.get("results")
        raw_preview = {
            "top_keys": list(data.keys())[:30],
            "results_type": type(results_obj).__name__ if results_obj is not None else None,
            "results_keys": list(results_obj.keys())[:30] if isinstance(results_obj, dict) else None,
            "listing_count_extracted": len(listings),
        }

    return {
        "query": {
            "item_name": item_name,
            "appid": appid,
            "quality": quality,
            "tradable": tradable,
            "craftable": craftable,
            "particle": particle,
            "limit": limit,
        },
        "listing_counts": {"sell": len(sells), "buy": len(buys)},
        "lowest_sell": lowest_sell,
        "highest_buy": highest_buy,
        "auth_used": auth_used,
        "raw_preview": raw_preview,
        "note": "Using backpack.tf v2 classifieds listings.",
    }


@app.get("/market/listings/from-stats")
async def market_listings_from_stats(
    stats_url: str = Query(..., description="Backpack.tf stats URL (e.g. /stats/Unusual/Conquistador/Tradable/Craftable/89)"),
    appid: int = Query(440),
    limit: int = Query(50, ge=1, le=100),
    debug_raw: bool = Query(False),
) -> Dict[str, Any]:
    parsed = parse_bptf_stats_url(stats_url)

    return await market_listings(
        item_name=parsed["item_name"],
        appid=appid,
        quality=parsed["quality"],
        tradable=parsed["tradable"],
        craftable=parsed["craftable"],
        particle=parsed["particle"],
        limit=limit,
        debug_raw=debug_raw,
    )