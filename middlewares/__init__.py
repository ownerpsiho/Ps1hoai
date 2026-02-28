"""
🛡️ Middleware — rate limiting, загрузка пользователя, anti-spam
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from config.settings import settings
from database import get_session, UserRepo

logger = logging.getLogger(__name__)


# ── Middleware: загрузка пользователя ─────────────────────────────────────────

class UserMiddleware(BaseMiddleware):
    """
    Загружает/создаёт пользователя из БД и кладёт его в data['user'].
    Также сбрасывает дневные счётчики и проверяет истечение подписки.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Получаем пользователя Telegram из события
        tg_user = None
        if isinstance(event, Message):
            tg_user = event.from_user
        elif isinstance(event, CallbackQuery):
            tg_user = event.from_user

        if tg_user is None:
            return await handler(event, data)

        async with get_session() as session:
            # Разбираем реферальный код из /start если есть
            referrer_id = None
            if isinstance(event, Message) and event.text:
                text = event.text.strip()
                if text.startswith("/start ref_"):
                    try:
                        referrer_id = int(text.split("ref_")[1])
                        if referrer_id == tg_user.id:
                            referrer_id = None  # нельзя пригласить самого себя
                    except (ValueError, IndexError):
                        pass

            user, created = await UserRepo.get_or_create(
                session,
                user_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name or "",
                last_name=tg_user.last_name,
                language_code=tg_user.language_code or "ru",
                referrer_id=referrer_id,
            )

            # Сбрасываем дневные счётчики если новый день
            await UserRepo.reset_daily_if_needed(session, user)
            # Проверяем истечение подписки
            await UserRepo.check_plan_expired(session, user)

            data["user"] = user
            data["db"] = session
            data["is_new_user"] = created

            return await handler(event, data)


# ── Middleware: anti-spam / rate limiting ─────────────────────────────────────

class RateLimitMiddleware(BaseMiddleware):
    """
    Ограничивает частоту сообщений.
    settings.rate_limit_messages сообщений за settings.rate_limit_period секунд.
    """

    def __init__(self):
        self._user_timestamps: dict[int, list[float]] = defaultdict(list)
        self._throttled: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        user_id = event.from_user.id if event.from_user else None
        if user_id is None or user_id in settings.admin_ids:
            return await handler(event, data)

        now = asyncio.get_event_loop().time()
        period = settings.rate_limit_period
        limit = settings.rate_limit_messages

        # Очищаем старые метки
        self._user_timestamps[user_id] = [
            t for t in self._user_timestamps[user_id]
            if now - t < period
        ]

        if len(self._user_timestamps[user_id]) >= limit:
            # Throttle — отвечаем не чаще раза в 5 секунд
            last_warn = self._throttled.get(user_id, 0)
            if now - last_warn > 5:
                self._throttled[user_id] = now
                await event.answer(
                    f"⚡ <b>Слишком быстро!</b>\n"
                    f"Максимум {limit} сообщений за {period} секунд.",
                    parse_mode="HTML",
                )
            return  # Не передаём дальше

        self._user_timestamps[user_id].append(now)
        return await handler(event, data)


# ── Middleware: logging ───────────────────────────────────────────────────────

class LoggingMiddleware(BaseMiddleware):
    """Логирует все входящие сообщения"""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.from_user:
            user = event.from_user
            text = event.text or event.caption or f"[{event.content_type}]"
            text_preview = text[:50] + ("..." if len(text) > 50 else "")
            logger.info(
                f"MSG uid={user.id} "
                f"@{user.username or 'none'} "
                f"| {text_preview}"
            )
        elif isinstance(event, CallbackQuery) and event.from_user:
            logger.info(
                f"CBQ uid={event.from_user.id} "
                f"| data={event.data}"
            )
        return await handler(event, data)


# ── Middleware: ban check ─────────────────────────────────────────────────────

class BanCheckMiddleware(BaseMiddleware):
    """Быстрая проверка бана (после UserMiddleware)"""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("user")
        if user and user.is_banned:
            if isinstance(event, Message):
                await event.answer(
                    f"🚫 <b>Ты заблокирован</b>\n"
                    f"Причина: {user.ban_reason or 'не указана'}\n\n"
                    f"По вопросам разблокировки: {settings.owner_username}",
                    parse_mode="HTML",
                )
            elif isinstance(event, CallbackQuery):
                await event.answer("🚫 Ты заблокирован.", show_alert=True)
            return
        return await handler(event, data)
