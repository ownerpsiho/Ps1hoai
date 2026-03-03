"""
📋 Обработчики команд
"""

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Router, Bot, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from config.settings import settings, PLANS
from database import get_session, UserRepo, MessageRepo
from keyboards import main_menu, back_to_main, referral_keyboard, history_keyboard
from utils import (
    format_limit_bar, format_plan_limits, format_datetime,
    format_date, time_until, format_number, escape_html
)

logger = logging.getLogger(__name__)
router = Router()


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, user, db, is_new_user: bool = False):
    fname = escape_html(user.first_name or "друг")
    plan = PLANS[user.plan.value]

    if is_new_user:
        # Выдаём пробный Pro на 3 дня
        async with get_session() as session:
            fresh_user = await UserRepo.get(session, user.id)
            if fresh_user:
                await UserRepo.set_plan(session, fresh_user, "pro", days=3)

        welcome_text = (
            f"👋 Привет, <b>{fname}</b>! Добро пожаловать в Psiho Ai!\n\n"
            f"🎁 <b>Подарок для новых пользователей:</b>\n"
            f"Тебе активирован <b>🔥 Pro на 3 дня бесплатно!</b>\n"
            f"200 сообщений · 30 картинок · 50 голосовых в день\n\n"
            f"🧠 <b>Что я умею:</b>\n"
            f"• 💬 Отвечать на любые вопросы\n"
            f"• 👨‍💻 Писать и объяснять код\n"
            f"• 🔍 Анализировать фото, PDF, документы\n"
            f"• 🎙 Распознавать голосовые сообщения\n"
            f"• 🎨 Генерировать изображения\n"
            f"• 🧠 Помнить контекст диалога\n\n"
            f"<i>Просто напиши мне что-нибудь!</i>"
        )
    else:
        welcome_text = (
            f"👋 С возвращением, <b>{fname}</b>!\n\n"
            f"💎 Тариф: <b>{plan['name']}</b>\n"
            f"{format_plan_limits(user, user.plan.value)}\n\n"
            f"О чём поговорим? 🙂"
        )

    await message.answer(
        welcome_text,
        parse_mode="HTML",
        reply_markup=main_menu(is_admin=user.is_admin),
    )

    if is_new_user and user.referrer_id:
        await message.answer(
            "🎁 Ты пришёл по реферальной ссылке!\n"
            "Твой друг получил бонусные сообщения 🎉",
            parse_mode="HTML",
        )


# ── /help ─────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message, user):
    plan = PLANS[user.plan.value]
    plan_is_premium = user.plan.value != "free"

    text = (
        "📖 <b>Команды бота:</b>\n\n"
        "/start — главное меню\n"
        "/new — начать новый диалог\n"
        "/history — история разговора\n"
        "/stats — моя статистика\n"
        "/image <i>описание</i> — генерация картинки\n"
        "/ref — реферальная программа\n"
        "/help — эта справка\n\n"
        "📎 <b>Поддерживаемые типы:</b>\n"
        "• Текст — обычный чат с AI\n"
        "• 🎙 Голосовые — автоматическое распознавание\n"
        "• 🖼 Фото — анализ изображений\n"
        "• 📄 Документы — PDF, TXT, CSV, JSON\n\n"
        f"💎 <b>Твой тариф:</b> {plan['name']}\n"
        f"📊 {plan['desc']}\n\n"
    )

    if not plan_is_premium:
        text += (
            "⬆️ <b>Хочешь больше возможностей?</b>\n"
            "Смотри тарифы в главном меню → 💎 Подписка"
        )

    await message.answer(text, parse_mode="HTML", reply_markup=main_menu(user.is_admin))


# ── /new ──────────────────────────────────────────────────────────────────────

@router.message(Command("new"))
async def cmd_new(message: Message, user):
    async with get_session() as session:
        count = await MessageRepo.clear_history(session, user.id)

    await message.answer(
        f"🔄 <b>Новый диалог начат!</b>\n\n"
        f"{'Удалено ' + str(count) + ' сообщений из памяти.' if count else 'История была пуста.'}\n"
        f"Начинаем с чистого листа 🙂",
        parse_mode="HTML",
        reply_markup=main_menu(user.is_admin),
    )


# ── /history ──────────────────────────────────────────────────────────────────

@router.message(Command("history"))
async def cmd_history(message: Message, user):
    async with get_session() as session:
        history = await MessageRepo.get_history(session, user.id, 10)

    if not history:
        await message.answer(
            "💭 <b>История пуста</b>\n\nНапиши что-нибудь!",
            parse_mode="HTML",
            reply_markup=main_menu(user.is_admin),
        )
        return

    lines = [f"📜 <b>Последние {len(history)} сообщений:</b>\n"]
    for msg in history:
        role = "👤 Ты" if msg.role == "user" else "🤖 AI"
        text_preview = msg.content[:80].replace("\n", " ")
        if len(msg.content) > 80:
            text_preview += "…"
        time_str = msg.created_at.strftime("%H:%M")
        lines.append(f"<b>{role}</b> [{time_str}]: {escape_html(text_preview)}")

    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=history_keyboard(),
    )


# ── /stats ────────────────────────────────────────────────────────────────────

@router.message(Command("stats"))
async def cmd_stats(message: Message, user):
    plan = PLANS[user.plan.value]
    expires = time_until(user.plan_expires) if user.plan.value != "free" else "бессрочно"

    text = (
        f"📊 <b>Моя статистика</b>\n\n"
        f"👤 {escape_html(user.display_name)}\n"
        f"🆔 ID: <code>{user.id}</code>\n\n"
        f"{'─' * 24}\n"
        f"💎 Тариф: <b>{plan['name']}</b>\n"
        f"⏰ Подписка: {expires}\n\n"
        f"📈 <b>Сегодня:</b>\n"
        f"{format_plan_limits(user, user.plan.value)}\n\n"
        f"🏆 <b>Всего:</b>\n"
        f"💬 Сообщений: <b>{format_number(user.total_messages)}</b>\n"
        f"🎨 Картинок: <b>{format_number(user.total_images)}</b>\n"
        f"🎙 Голосовых: <b>{format_number(user.total_voice)}</b>\n\n"
        f"👥 Рефералов: <b>{user.referral_count}</b>\n"
        f"🎁 Реф. бонус: <b>+{user.referral_bonus}</b> сообщений\n\n"
        f"📅 В боте с: {format_date(user.created_at)}"
    )

    await message.answer(text, parse_mode="HTML")


# ── /image ────────────────────────────────────────────────────────────────────

@router.message(Command("image"))
async def cmd_image(message: Message, user):
    from handlers.image import process_image_generation
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer(
            "🎨 <b>Генерация изображений</b>\n\n"
            "Использование:\n"
            "<code>/image описание картинки</code>\n\n"
            "Примеры:\n"
            "• <code>/image котёнок в космосе</code>\n"
            "• <code>/image realistic горный пейзаж на рассвете</code>\n"
            "• <code>/image anime девушка с цветами</code>",
            parse_mode="HTML",
        )
        return

    from utils import parse_image_command
    prompt, style, size = parse_image_command(args[1])
    if not prompt:
        await message.answer("❌ Напиши описание картинки после команды.")
        return
    await process_image_generation(message, user, prompt, style, size)


# ── /ref ──────────────────────────────────────────────────────────────────────

@router.message(Command("ref"))
async def cmd_referral(message: Message, user):
    bot_info = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user.id}"

    text = (
        f"👥 <b>Реферальная программа</b>\n\n"
        f"Приглашай друзей и получай бонусные сообщения!\n\n"
        f"🎁 <b>Твой бонус:</b> {settings.referral_bonus_messages} сообщений за каждого друга\n"
        f"👥 Приглашено: <b>{user.referral_count}</b> друзей\n"
        f"💰 Накоплено бонусов: <b>+{user.referral_bonus}</b> сообщений\n\n"
        f"🔗 <b>Твоя ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"<i>Просто поделись этой ссылкой — и когда друг запустит бота, ты получишь бонус!</i>"
    )

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=referral_keyboard(bot_info.username, user.id),
    )
