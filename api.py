"""
🌐 FastAPI сервер — личный кабинет Psiho AI
"""

import hashlib
import hmac
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from config.settings import settings, PLANS
from database.models import User

app = FastAPI(title="Psiho AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://psiho-ai.netlify.app", "http://localhost"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def fix_db_url(url: str) -> str:
    url = url.replace("postgres://", "postgresql+asyncpg://")
    url = url.replace("postgresql://", "postgresql+asyncpg://")
    return url


engine = create_async_engine(fix_db_url(settings.database_url))
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def verify_telegram_auth(data: dict) -> bool:
    check_hash = data.pop("hash", None)
    if not check_hash:
        return False
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hashlib.sha256(settings.bot_token.encode()).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return computed == check_hash


@app.get("/")
async def root():
    return {"status": "ok", "bot": "@PSIHO_AI_bot"}


@app.get("/api/user")
async def get_user(
    id: int = Query(...),
    first_name: str = Query(...),
    auth_date: int = Query(...),
    hash: str = Query(...),
    last_name: Optional[str] = Query(None),
    username: Optional[str] = Query(None),
    photo_url: Optional[str] = Query(None),
):
    auth_data = {
        "id": str(id),
        "first_name": first_name,
        "auth_date": str(auth_date),
        "hash": hash,
    }
    if last_name: auth_data["last_name"] = last_name
    if username: auth_data["username"] = username
    if photo_url: auth_data["photo_url"] = photo_url

    if not verify_telegram_auth(auth_data):
        raise HTTPException(status_code=403, detail="Invalid auth")

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == id))
        user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    plan = PLANS[user.plan.value]

    # Безопасно получаем дневные счётчики
    messages_today = getattr(user, 'daily_messages', 0) or getattr(user, 'messages_today', 0) or 0
    images_today = getattr(user, 'daily_images', 0) or getattr(user, 'images_today', 0) or 0

    return {
        "id": user.id,
        "name": user.display_name,
        "username": user.username,
        "photo_url": photo_url,
        "plan": {
            "key": user.plan.value,
            "name": plan["name"],
            "emoji": plan["emoji"],
            "expires": user.plan_expires.isoformat() if user.plan_expires else None,
        },
        "stats": {
            "total_messages": user.total_messages,
            "total_images": user.total_images,
            "total_voice": user.total_voice,
            "messages_today": messages_today,
            "images_today": images_today,
            "referral_count": user.referral_count,
        },
        "limits": {
            "daily_messages": plan["daily_limit"],
            "daily_images": plan["image_limit"],
            "daily_voice": plan["voice_limit"],
        },
        "created_at": user.created_at.isoformat(),
        "is_banned": user.is_banned,
    }
