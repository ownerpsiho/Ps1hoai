"""
📋 Репозиторий — все операции с базой данных
"""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, update, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings, PLANS
from .models import (
    User, Message, Transaction, Preset, BotSetting,
    SystemPrompt, BotStats, PlanEnum, MessageTypeEnum, TransactionTypeEnum
)


# ── Пользователи ──────────────────────────────────────────────────────────────

class UserRepo:

    @staticmethod
    async def get(session: AsyncSession, user_id: int) -> Optional[User]:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_or_create(
        session: AsyncSession,
        user_id: int,
        username: Optional[str] = None,
        first_name: str = "",
        last_name: Optional[str] = None,
        language_code: str = "ru",
        referrer_id: Optional[int] = None,
    ) -> tuple[User, bool]:
        """Возвращает (user, created)"""
        user = await UserRepo.get(session, user_id)
        if user:
            # Обновляем данные если изменились
            changed = False
            if username and user.username != username:
                user.username = username
                changed = True
            if first_name and user.first_name != first_name:
                user.first_name = first_name
                changed = True
            if last_name and user.last_name != last_name:
                user.last_name = last_name
                changed = True
            user.last_activity = datetime.utcnow()
            if changed:
                await session.flush()
            return user, False

        # Создаём нового пользователя
        is_admin = user_id in settings.admin_ids
        user = User(
            id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
            is_admin=is_admin,
            referrer_id=referrer_id,
            last_activity=datetime.utcnow(),
        )
        session.add(user)
        await session.flush()

        # Бонус рефереру
        if referrer_id:
            referrer = await UserRepo.get(session, referrer_id)
            if referrer:
                referrer.referral_count += 1
                referrer.referral_bonus += settings.referral_bonus_messages
                await session.flush()

        return user, True

    @staticmethod
    async def reset_daily_if_needed(session: AsyncSession, user: User) -> bool:
        """Сбрасывает дневные счётчики если нужно. Возвращает True если сбросил."""
        now = datetime.utcnow()
        today = now.date()
        if user.last_reset is None or user.last_reset.date() < today:
            user.today_messages = 0
            user.today_images = 0
            user.today_voice = 0
            user.last_reset = now
            await session.flush()
            return True
        return False

    @staticmethod
    async def check_plan_expired(session: AsyncSession, user: User) -> bool:
        """Проверяет и сбрасывает истёкшую подписку. Возвращает True если сбросил."""
        if user.plan != PlanEnum.free and user.plan_expires:
            if user.plan_expires < datetime.utcnow():
                user.plan = PlanEnum.free
                user.plan_expires = None
                await session.flush()
                return True
        return False

    @staticmethod
    async def can_send_message(user: User) -> tuple[bool, str]:
        """Проверяет может ли пользователь отправить сообщение"""
        if user.is_banned:
            return False, f"🚫 Ты заблокирован.\nПричина: {user.ban_reason or 'не указана'}"
        if user.is_admin:
            return True, ""
        plan = PLANS[user.plan.value]
        limit = plan["daily_limit"]
        if limit == -1:
            return True, ""
        used = user.today_messages + max(0, -user.referral_bonus)
        bonus = user.referral_bonus
        effective_limit = limit + bonus
        if user.today_messages >= effective_limit:
            return False, (
                f"⛔ <b>Лимит исчерпан</b>\n\n"
                f"Тариф: <b>{plan['name']}</b>\n"
                f"Использовано: <b>{user.today_messages}/{effective_limit}</b>"
                + (f"\n🎁 Реферальный бонус: +{bonus}" if bonus else "") +
                f"\n🔄 Сброс завтра в 00:00\n\n"
                f"⬆️ Подними тариф:"
            )
        return True, ""

    @staticmethod
    async def can_generate_image(user: User) -> tuple[bool, str]:
        """Проверяет можно ли генерировать изображение"""
        if user.is_admin:
            return True, ""
        plan = PLANS[user.plan.value]
        limit = plan["image_limit"]
        if limit == -1:
            return True, ""
        if user.today_images >= limit:
            return False, (
                f"🖼 <b>Лимит картинок исчерпан</b>\n\n"
                f"Тариф: <b>{plan['name']}</b>\n"
                f"Использовано: <b>{user.today_images}/{limit}</b>\n"
                f"🔄 Сброс завтра в 00:00"
            )
        return True, ""

    @staticmethod
    async def can_use_voice(user: User) -> tuple[bool, str]:
        """Проверяет можно ли использовать голос"""
        if user.is_admin:
            return True, ""
        plan = PLANS[user.plan.value]
        limit = plan["voice_limit"]
        if limit == -1:
            return True, ""
        if user.today_voice >= limit:
            return False, (
                f"🎙 <b>Лимит голосовых исчерпан</b>\n\n"
                f"Тариф: <b>{plan['name']}</b>\n"
                f"Использовано: <b>{user.today_voice}/{limit}</b>\n"
                f"🔄 Сброс завтра в 00:00"
            )
        return True, ""

    @staticmethod
    async def use_message(session: AsyncSession, user: User):
        user.today_messages += 1
        user.total_messages += 1
        user.last_activity = datetime.utcnow()
        await session.flush()

    @staticmethod
    async def use_image(session: AsyncSession, user: User):
        user.today_images += 1
        user.total_images += 1
        user.last_activity = datetime.utcnow()
        await session.flush()

    @staticmethod
    async def use_voice(session: AsyncSession, user: User):
        user.today_voice += 1
        user.total_voice += 1
        user.last_activity = datetime.utcnow()
        await session.flush()

    @staticmethod
    async def set_plan(
        session: AsyncSession,
        user: User,
        plan_key: str,
        days: int = 30,
        admin_id: Optional[int] = None,
        payment_method: str = "manual",
        amount_usd: float = 0.0,
    ):
        """Устанавливает тарифный план и создаёт транзакцию"""
        old_plan = user.plan.value
        user.plan = PlanEnum(plan_key)
        if plan_key != "free":
            now = datetime.utcnow()
            # Продлеваем если подписка ещё активна
            if user.plan_expires and user.plan_expires > now:
                user.plan_expires = user.plan_expires + timedelta(days=days)
            else:
                user.plan_expires = now + timedelta(days=days)
        else:
            user.plan_expires = None

        plan = PLANS.get(plan_key, PLANS["free"])
        if amount_usd == 0.0 and plan_key != "free":
            amount_usd = plan["price"]

        # Записываем транзакцию
        tx = Transaction(
            user_id=user.id,
            transaction_type=TransactionTypeEnum.subscription,
            plan=plan_key,
            amount_usd=amount_usd,
            days=days,
            payment_method=payment_method,
            status="completed",
            admin_id=admin_id,
            note=f"Upgrade {old_plan} → {plan_key}",
        )
        session.add(tx)
        user.total_spent += amount_usd
        await session.flush()

    @staticmethod
    async def ban(session: AsyncSession, user: User, reason: str = ""):
        user.is_banned = True
        user.ban_reason = reason
        await session.flush()

    @staticmethod
    async def unban(session: AsyncSession, user: User):
        user.is_banned = False
        user.ban_reason = None
        await session.flush()

    @staticmethod
    async def get_all_ids(session: AsyncSession) -> list[int]:
        result = await session.execute(select(User.id))
        return [row[0] for row in result.fetchall()]

    @staticmethod
    async def get_stats(session: AsyncSession) -> dict:
        total = await session.scalar(select(func.count(User.id)))
        active_today = await session.scalar(
            select(func.count(User.id)).where(
                User.last_activity >= datetime.utcnow() - timedelta(hours=24)
            )
        )
        active_week = await session.scalar(
            select(func.count(User.id)).where(
                User.last_activity >= datetime.utcnow() - timedelta(days=7)
            )
        )
        by_plan = {}
        for plan_key in PLANS.keys():
            count = await session.scalar(
                select(func.count(User.id)).where(User.plan == PlanEnum(plan_key))
            )
            by_plan[plan_key] = count

        total_msgs = await session.scalar(select(func.sum(User.total_messages))) or 0
        total_imgs = await session.scalar(select(func.sum(User.total_images))) or 0
        total_revenue = await session.scalar(select(func.sum(Transaction.amount_usd)).where(
            Transaction.status == "completed"
        )) or 0.0

        top_users = await session.execute(
            select(User).order_by(desc(User.total_messages)).limit(5)
        )
        top = top_users.scalars().all()

        new_today = await session.scalar(
            select(func.count(User.id)).where(
                User.created_at >= datetime.utcnow() - timedelta(hours=24)
            )
        )

        return {
            "total": total,
            "active_today": active_today,
            "active_week": active_week,
            "new_today": new_today,
            "by_plan": by_plan,
            "total_messages": total_msgs,
            "total_images": total_imgs,
            "total_revenue": total_revenue,
            "top_users": top,
        }


# ── История диалогов ──────────────────────────────────────────────────────────

class MessageRepo:

    @staticmethod
    async def add(
        session: AsyncSession,
        user_id: int,
        role: str,
        content: str,
        msg_type: MessageTypeEnum = MessageTypeEnum.text,
        tokens_used: int = 0,
        model_used: str = "",
        latency_ms: int = 0,
    ) -> Message:
        msg = Message(
            user_id=user_id,
            role=role,
            content=content,
            msg_type=msg_type,
            tokens_used=tokens_used,
            model_used=model_used,
            latency_ms=latency_ms,
        )
        session.add(msg)
        await session.flush()
        return msg

    @staticmethod
    async def get_history(
        session: AsyncSession,
        user_id: int,
        limit: int = 20,
    ) -> list[Message]:
        result = await session.execute(
            select(Message)
            .where(Message.user_id == user_id)
            .order_by(desc(Message.created_at))
            .limit(limit)
        )
        messages = result.scalars().all()
        return list(reversed(messages))

    @staticmethod
    async def clear_history(session: AsyncSession, user_id: int) -> int:
        from sqlalchemy import delete
        result = await session.execute(
            delete(Message).where(Message.user_id == user_id)
        )
        return result.rowcount

    @staticmethod
    async def get_history_for_gemini(
        session: AsyncSession,
        user_id: int,
        limit: int = 20,
    ) -> list[dict]:
        """Возвращает историю в формате для Gemini API"""
        messages = await MessageRepo.get_history(session, user_id, limit)
        result = []
        for msg in messages:
            if msg.role == "user":
                result.append({"role": "user", "parts": [{"text": msg.content}]})
            elif msg.role == "assistant":
                result.append({"role": "model", "parts": [{"text": msg.content}]})
        return result


# ── Пресеты ───────────────────────────────────────────────────────────────────

class PresetRepo:

    @staticmethod
    async def get_user_presets(session: AsyncSession, user_id: int) -> list[Preset]:
        result = await session.execute(
            select(Preset).where(Preset.user_id == user_id).order_by(Preset.created_at)
        )
        return result.scalars().all()

    @staticmethod
    async def create(session: AsyncSession, user_id: int, name: str, prompt: str) -> Preset:
        # Деактивируем все остальные
        await session.execute(
            update(Preset).where(Preset.user_id == user_id).values(is_active=False)
        )
        preset = Preset(user_id=user_id, name=name, prompt=prompt, is_active=True)
        session.add(preset)
        await session.flush()
        return preset

    @staticmethod
    async def delete(session: AsyncSession, preset_id: int, user_id: int) -> bool:
        from sqlalchemy import delete
        result = await session.execute(
            delete(Preset).where(
                and_(Preset.id == preset_id, Preset.user_id == user_id)
            )
        )
        return result.rowcount > 0

    @staticmethod
    async def get_active(session: AsyncSession, user_id: int) -> Optional[Preset]:
        result = await session.execute(
            select(Preset).where(
                and_(Preset.user_id == user_id, Preset.is_active == True)
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def set_active(session: AsyncSession, preset_id: int, user_id: int) -> bool:
        await session.execute(
            update(Preset).where(Preset.user_id == user_id).values(is_active=False)
        )
        result = await session.execute(
            update(Preset).where(
                and_(Preset.id == preset_id, Preset.user_id == user_id)
            ).values(is_active=True)
        )
        return result.rowcount > 0


# ── Системные промпты ─────────────────────────────────────────────────────────

class PromptRepo:

    @staticmethod
    async def get_all(session: AsyncSession) -> list[SystemPrompt]:
        result = await session.execute(select(SystemPrompt).order_by(SystemPrompt.id))
        return result.scalars().all()

    @staticmethod
    async def get_by_key(session: AsyncSession, key: str) -> Optional[SystemPrompt]:
        result = await session.execute(
            select(SystemPrompt).where(SystemPrompt.key == key)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_for_user(session: AsyncSession, user: User) -> Optional[SystemPrompt]:
        """Возвращает системный промпт для пользователя с учётом его персоналити"""
        prompt = await PromptRepo.get_by_key(session, user.ai_personality)
        if prompt is None:
            prompt = await PromptRepo.get_by_key(session, "default")
        return prompt


# ── Настройки бота ─────────────────────────────────────────────────────────────

class SettingRepo:

    @staticmethod
    async def get(session: AsyncSession, key: str, default: str = "") -> str:
        result = await session.execute(
            select(BotSetting).where(BotSetting.key == key)
        )
        setting = result.scalar_one_or_none()
        return setting.value if setting else default

    @staticmethod
    async def set(session: AsyncSession, key: str, value: str):
        result = await session.execute(
            select(BotSetting).where(BotSetting.key == key)
        )
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = value
        else:
            session.add(BotSetting(key=key, value=value))
        await session.flush()
