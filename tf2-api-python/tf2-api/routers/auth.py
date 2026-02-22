from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from database import get_db
from middleware.auth import create_token

router = APIRouter(prefix="/v1/auth", tags=["Auth"])


class SteamLoginRequest(BaseModel):
    steam_id: str


@router.post("/steam", summary="Login with Steam ID and receive a JWT token")
def steam_login(body: SteamLoginRequest):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE steam_id = %s", (body.steam_id,))
            user = cur.fetchone()

            # Auto-register if new
            if not user:
                username = f"User_{body.steam_id[-6:]}"
                cur.execute(
                    "INSERT INTO users (steam_id, username) VALUES (%s, %s)",
                    (body.steam_id, username),
                )
                cur.execute("SELECT * FROM users WHERE steam_id = %s", (body.steam_id,))
                user = cur.fetchone()

        token = create_token(user)
        return {
            "token":      token,
            "token_type": "Bearer",
            "expires_in": 86400,
            "user": {
                "id":       user["id"],
                "username": user["username"],
                "steam_id": user["steam_id"],
            },
        }
    finally:
        db.close()
