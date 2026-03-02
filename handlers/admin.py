"""
👑 Обработчики админ-панели
"""

import asyncio
import logging
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config.settings import settings, PLANS
from database import get_session, UserRepo, MessageRepo
from keyboards import (
    admin_keyboard, give_sub_plan_keyboard, give_sub_days_keyboard,
    admin_broadcast_plan_keyboard, back_button
)
from utils import format_user_card, format_number, format_datetime, escape_html

logger = logging.getLogger(__name__)
router = Router()


# ── Состояния ─────────────────────────────────────────────────────────────────

class AdminStates(StatesGroup):
    broadcast_text      = State()
    broadcast_plan      = State()
    give_sub_uid        = State()
    give_sub_plan       = State()
    give_sub_days       = State()
    find_user           = State()
    ban_user_id         = State()
    ban_user_reason     = State()
    unban_user_id       = State()
    edit_prompt_key     = State()
    edit_prompt_text    = State()
    users_page          = State()


# ── /admin ─────────────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message, user):
    if user.id not in settings.admin_ids:
        await message.answer("⛔ Нет доступа")
        return

    async with get_session() as session:
        stats = await UserRepo.get_stats(session)

    text = (
        f"⚙️ <b>Панель администратора</b>\n\n"
        f"👥 Всего пользователей: <b>{format_number(stats['total'])}</b>\n"
        f"🟢 Активны сегодня: <b>{stats['active_today']}</b>\n"
        f"📅 Новых сегодня: <b>{stats['new_today']}</b>\n\n"
        f"💬 Сообщений всего: <b>{format_number(stats['total_messages'])}</b>\n"
        f"🎨 Картинок всего: <b>{format_number(stats['total_images'])}</b>\n\n"
        f"💰 Выручка: <b>${stats['total_revenue']:.2f}</b>\n\n"
        f"🧠 Модель: <code>{settings.gemini_model}</code>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=admin_keyboard())


# ── Callback: панель ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: CallbackQuery, user):
    if user.id not in settings.admin_ids:
        await callback.answer("⛔", show_alert=True)
        return
    await callback.answer()
    async with get_session() as session:
        stats = await UserRepo.get_stats(session)

    text = (
        f"⚙️ <b>Панель администратора</b>\n\n"
        f"👥 Пользователей: <b>{format_number(stats['total'])}</b>\n"
        f"🟢 Активны сегодня: <b>{stats['active_today']}</b>\n"
        f"💬 Сообщений: <b>{format_number(stats['total_messages'])}</b>\n"
        f"💰 Выручка: <b>${stats['total_revenue']:.2f}</b>"
    )
    await callback.message.edit_text(
        text, parse_mode="HTML", reply_markup=admin_keyboard()
    )


@router.callback_query(F.data == "back_admin")
async def cb_back_admin(callback: CallbackQuery, user):
    if user.id not in settings.admin_ids:
        await callback.answer("⛔"); return
    await callback.answer()
    await callback.message.edit_text(
        "⚙️ <b>Панель администратора</b>",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )


# ── Детальная статистика ──────────────────────────────────────────────────────

@router.callback_query(F.data == "adm_stats")
async def adm_stats(callback: CallbackQuery, user):
    if user.id not in settings.admin_ids:
        await callback.answer("⛔"); return

    async with get_session() as session:
        stats = await UserRepo.get_stats(session)

    plans_text = ""
    for key, plan in PLANS.items():
        count = stats["by_plan"].get(key, 0)
        plans_text += f"  {plan['emoji']} {plan['name']}: <b>{count}</b>\n"

    top_text = ""
    for i, u in enumerate(stats["top_users"], 1):
        name = escape_html(u.display_name)
        top_text += f"  {i}. {name} — {format_number(u.total_messages)} сообщ.\n"

    await callback.answer()
    await callback.message.edit_text(
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Пользователей: <b>{format_number(stats['total'])}</b>\n"
        f"🟢 Активны сегодня: <b>{stats['active_today']}</b>\n"
        f"📅 Активны за неделю: <b>{stats['active_week']}</b>\n"
        f"✨ Новых сегодня: <b>{stats['new_today']}</b>\n\n"
        f"💬 Сообщений всего: <b>{format_number(stats['total_messages'])}</b>\n"
        f"🎨 Картинок всего: <b>{format_number(stats['total_images'])}</b>\n"
        f"💰 Выручка: <b>${stats['total_revenue']:.2f}</b>\n\n"
        f"💎 <b>По тарифам:</b>\n{plans_text}\n"
        f"🏆 <b>Топ пользователей:</b>\n{top_text}",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )


# ── Список пользователей ──────────────────────────────────────────────────────

@router.callback_query(F.data == "adm_users")
async def adm_users(callback: CallbackQuery, user):
    if user.id not in settings.admin_ids:
        await callback.answer("⛔"); return
    await callback.answer()
    await _show_users_page(callback, page=0)


@router.callback_query(F.data.startswith("adm_users_page:"))
async def adm_users_page(callback: CallbackQuery, user):
    if user.id not in settings.admin_ids:
        await callback.answer("⛔"); return
    await callback.answer()
    page = int(callback.data.split(":")[1])
    await _show_users_page(callback, page=page)


async def _show_users_page(callback: CallbackQuery, page: int = 0):
    """Показывает список пользователей постранично"""
    from sqlalchemy import select, desc
    from database.models import User as UserModel
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    page_size = 10

    async with get_session() as session:
        # Получаем пользователей
        result = await session.execute(
            select(UserModel)
            .order_by(desc(UserModel.created_at))
            .offset(page * page_size)
            .limit(page_size)
        )
        users = result.scalars().all()

        # Считаем общее количество
        from sqlalchemy import func
        total = await session.scalar(select(func.count(UserModel.id)))

    if not users:
        await callback.message.edit_text(
            "👥 Пользователей нет.",
            reply_markup=admin_keyboard()
        )
        return

    lines = [f"👥 <b>Пользователи</b> (стр. {page + 1}, всего {total}):\n"]
    for u in users:
        plan = PLANS[u.plan.value]
        name = escape_html(u.display_name)
        username = f"@{u.username}" if u.username else "—"
        ban = " 🚫" if u.is_banned else ""
        lines.append(
            f"• <code>{u.id}</code> {name} ({username}){ban}\n"
            f"  {plan['emoji']} {plan['name']} · {u.total_messages} сообщ."
        )

    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"adm_users_page:{page-1}"))
    if (page + 1) * page_size < total:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"adm_users_page:{page+1}"))

    rows = []
    if nav_buttons:
        rows.append(nav_buttons)
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_admin")])

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


# ── Системный промпт ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm_edit_prompt")
async def adm_edit_prompt_start(callback: CallbackQuery, user, state: FSMContext):
    if user.id not in settings.admin_ids:
        await callback.answer("⛔"); return
    await callback.answer()

    from database import PromptRepo
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    async with get_session() as session:
        prompts = await PromptRepo.get_all(session)

    rows = []
    for p in prompts:
        rows.append([InlineKeyboardButton(
            text=f"{p.emoji} {p.name}",
            callback_data=f"adm_prompt_select:{p.key}"
        )])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_admin")])

    await callback.message.edit_text(
        "📝 <b>Системные промпты</b>\n\nВыбери промпт для редактирования:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("adm_prompt_select:"))
async def adm_prompt_select(callback: CallbackQuery, user, state: FSMContext):
    if user.id not in settings.admin_ids:
        await callback.answer("⛔"); return

    key = callback.data.split(":")[1]

    from database import PromptRepo
    async with get_session() as session:
        prompt = await PromptRepo.get_by_key(session, key)

    if not prompt:
        await callback.answer("❌ Промпт не найден"); return

    await state.set_state(AdminStates.edit_prompt_text)
    await state.update_data(edit_prompt_key=key)
    await callback.answer()
    await callback.message.edit_text(
        f"📝 <b>Редактирование промпта: {prompt.emoji} {prompt.name}</b>\n\n"
        f"<b>Текущий промпт:</b>\n"
        f"<pre>{escape_html(prompt.prompt[:500])}{'...' if len(prompt.prompt) > 500 else ''}</pre>\n\n"
        f"Напиши новый текст промпта:",
        parse_mode="HTML",
        reply_markup=back_button("adm_edit_prompt"),
    )


@router.message(AdminStates.edit_prompt_text)
async def adm_save_prompt(message: Message, user, state: FSMContext):
    if user.id not in settings.admin_ids: return

    data = await state.get_data()
    key = data.get("edit_prompt_key")
    await state.clear()

    new_prompt = message.text.strip()
    if len(new_prompt) < 10:
        await message.answer("❌ Слишком короткий промпт (мин. 10 символов):")
        return

    from database import PromptRepo
    from sqlalchemy import update
    from database.models import SystemPrompt

    async with get_session() as session:
        await session.execute(
            update(SystemPrompt)
            .where(SystemPrompt.key == key)
            .values(prompt=new_prompt)
        )

    await message.answer(
        f"✅ <b>Промпт обновлён!</b>\n\n"
        f"Ключ: <code>{key}</code>\n"
        f"Длина: {len(new_prompt)} символов",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )


# ── Выдача подписки ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm_give_sub")
async def adm_give_sub_start(callback: CallbackQuery, user, state: FSMContext):
    if user.id not in settings.admin_ids:
        await callback.answer("⛔"); return
    await state.set_state(AdminStates.give_sub_uid)
    await callback.answer()
    await callback.message.edit_text(
        "💎 <b>Выдать подписку</b>\n\nВведи Telegram ID пользователя:",
        parse_mode="HTML",
        reply_markup=back_button("back_admin"),
    )


@router.message(AdminStates.give_sub_uid)
async def adm_give_sub_uid(message: Message, user, state: FSMContext):
    if user.id not in settings.admin_ids: return
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введи числовой ID:")
        return

    await state.update_data(give_uid=target_id)
    await state.set_state(AdminStates.give_sub_plan)
    await message.answer(
        f"💎 Тариф для ID <code>{target_id}</code>:",
        parse_mode="HTML",
        reply_markup=give_sub_plan_keyboard(),
    )


@router.callback_query(F.data.startswith("adm_sub_plan:"))
async def adm_give_sub_plan(callback: CallbackQuery, user, state: FSMContext):
    if user.id not in settings.admin_ids:
        await callback.answer("⛔"); return
    plan_key = callback.data.split(":")[1]
    await state.update_data(give_plan=plan_key)

    if plan_key == "free":
        data = await state.get_data()
        target_id = data.get("give_uid")
        await state.clear()
        async with get_session() as session:
            target = await UserRepo.get(session, target_id)
            if target:
                await UserRepo.set_plan(session, target, "free", admin_id=user.id)
        await callback.answer("✅ Сброшено до Free")
        await callback.message.edit_text(
            f"✅ Пользователь <code>{target_id}</code> сброшен на Free.",
            parse_mode="HTML",
            reply_markup=admin_keyboard(),
        )
        return

    await callback.answer()
    await state.set_state(AdminStates.give_sub_days)
    await callback.message.edit_text(
        f"⏳ <b>Срок подписки для плана {PLANS[plan_key]['name']}:</b>",
        parse_mode="HTML",
        reply_markup=give_sub_days_keyboard(),
    )


@router.callback_query(F.data.startswith("adm_sub_days:"))
async def adm_give_sub_days(callback: CallbackQuery, user, state: FSMContext):
    if user.id not in settings.admin_ids:
        await callback.answer("⛔"); return

    days = int(callback.data.split(":")[1])
    data = await state.get_data()
    target_id = data.get("give_uid")
    plan_key = data.get("give_plan")
    await state.clear()

    if not target_id or not plan_key:
        await callback.answer("❌ Ошибка данных"); return

    async with get_session() as session:
        target = await UserRepo.get(session, target_id)
        if not target:
            target, _ = await UserRepo.get_or_create(session, target_id)
        await UserRepo.set_plan(session, target, plan_key, days, admin_id=user.id)

    plan = PLANS[plan_key]
    await callback.answer("✅ Подписка выдана!")

    try:
        await callback.bot.send_message(
            target_id,
            f"🎉 <b>Подписка активирована!</b>\n\n"
            f"💎 Тариф: <b>{plan['name']}</b>\n"
            f"⏰ Срок: <b>{days} дней</b>\n"
            f"📊 {plan['desc']}\n\n"
            f"Приятного использования! 🚀",
            parse_mode="HTML",
        )
        notified = "✅ Пользователь уведомлён"
    except Exception:
        notified = "⚠️ Не удалось уведомить пользователя"

    await callback.message.edit_text(
        f"✅ <b>Подписка выдана!</b>\n\n"
        f"🆔 ID: <code>{target_id}</code>\n"
        f"💎 Тариф: {plan['name']}\n"
        f"⏰ Дней: {days}\n"
        f"{notified}",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )


# ── Поиск пользователя ────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm_find_user")
async def adm_find_user_start(callback: CallbackQuery, user, state: FSMContext):
    if user.id not in settings.admin_ids:
        await callback.answer("⛔"); return
    await state.set_state(AdminStates.find_user)
    await callback.answer()
    await callback.message.edit_text(
        "🔍 <b>Найти пользователя</b>\n\nВведи Telegram ID:",
        parse_mode="HTML",
        reply_markup=back_button("back_admin"),
    )


@router.message(AdminStates.find_user)
async def adm_find_user(message: Message, user, state: FSMContext):
    if user.id not in settings.admin_ids: return
    await state.clear()
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введи числовой ID:")
        return

    async with get_session() as session:
        target = await UserRepo.get(session, target_id)

    if not target:
        await message.answer(
            f"❌ Пользователь ID <code>{target_id}</code> не найден.",
            parse_mode="HTML",
            reply_markup=admin_keyboard(),
        )
        return

    plan = PLANS[target.plan.value]
    card = format_user_card(target, plan)
    await message.answer(card, parse_mode="HTML", reply_markup=admin_keyboard())


# ── Бан/разбан ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm_ban")
async def adm_ban_start(callback: CallbackQuery, user, state: FSMContext):
    if user.id not in settings.admin_ids:
        await callback.answer("⛔"); return
    await state.set_state(AdminStates.ban_user_id)
    await callback.answer()
    await callback.message.edit_text(
        "🚫 <b>Забанить пользователя</b>\n\nВведи Telegram ID:",
        parse_mode="HTML",
        reply_markup=back_button("back_admin"),
    )


@router.message(AdminStates.ban_user_id)
async def adm_ban_uid(message: Message, user, state: FSMContext):
    if user.id not in settings.admin_ids: return
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Числовой ID:"); return

    if target_id in settings.admin_ids:
        await message.answer("❌ Нельзя банить других администраторов!")
        await state.clear()
        return

    await state.update_data(ban_uid=target_id)
    await state.set_state(AdminStates.ban_user_reason)
    await message.answer(
        f"🚫 Бан ID <code>{target_id}</code>\n\nПричина (или - чтобы без причины):",
        parse_mode="HTML",
    )


@router.message(AdminStates.ban_user_reason)
async def adm_ban_reason(message: Message, user, state: FSMContext):
    if user.id not in settings.admin_ids: return
    reason = message.text.strip()
    if reason == "-":
        reason = ""
    data = await state.get_data()
    target_id = data.get("ban_uid")
    await state.clear()

    async with get_session() as session:
        target = await UserRepo.get(session, target_id)
        if not target:
            target, _ = await UserRepo.get_or_create(session, target_id)
        await UserRepo.ban(session, target, reason)

    try:
        await message.bot.send_message(
            target_id,
            f"🚫 <b>Ты заблокирован</b>\n"
            f"Причина: {reason or 'не указана'}\n\n"
            f"По вопросам: {settings.owner_username}",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await message.answer(
        f"✅ Пользователь <code>{target_id}</code> заблокирован.\n"
        f"Причина: {reason or '—'}",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )


@router.callback_query(F.data == "adm_unban")
async def adm_unban_start(callback: CallbackQuery, user, state: FSMContext):
    if user.id not in settings.admin_ids:
        await callback.answer("⛔"); return
    await state.set_state(AdminStates.unban_user_id)
    await callback.answer()
    await callback.message.edit_text(
        "✅ <b>Разбанить пользователя</b>\n\nВведи Telegram ID:",
        parse_mode="HTML",
        reply_markup=back_button("back_admin"),
    )


@router.message(AdminStates.unban_user_id)
async def adm_unban_uid(message: Message, user, state: FSMContext):
    if user.id not in settings.admin_ids: return
    await state.clear()
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Числовой ID:"); return

    async with get_session() as session:
        target = await UserRepo.get(session, target_id)
        if target:
            await UserRepo.unban(session, target)

    try:
        await message.bot.send_message(
            target_id,
            "✅ Ты разблокирован! Можешь продолжить пользоваться ботом.",
        )
    except Exception:
        pass

    await message.answer(
        f"✅ Пользователь <code>{target_id}</code> разблокирован.",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )


# ── Рассылка ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_start(callback: CallbackQuery, user, state: FSMContext):
    if user.id not in settings.admin_ids:
        await callback.answer("⛔"); return
    await state.update_data(broadcast_plan=None)
    await state.set_state(AdminStates.broadcast_text)
    await callback.answer()
    await callback.message.edit_text(
        "📢 <b>Рассылка всем пользователям</b>\n\n"
        "Введи текст сообщения (поддерживается HTML):",
        parse_mode="HTML",
        reply_markup=back_button("back_admin"),
    )


@router.callback_query(F.data == "adm_broadcast_plan")
async def adm_broadcast_plan_start(callback: CallbackQuery, user, state: FSMContext):
    if user.id not in settings.admin_ids:
        await callback.answer("⛔"); return
    await callback.answer()
    await callback.message.edit_text(
        "📢 <b>Рассылка по тарифу</b>\n\nВыбери тариф:",
        parse_mode="HTML",
        reply_markup=admin_broadcast_plan_keyboard(),
    )


@router.callback_query(F.data.startswith("adm_bcast_plan:"))
async def adm_broadcast_plan_selected(callback: CallbackQuery, user, state: FSMContext):
    if user.id not in settings.admin_ids:
        await callback.answer("⛔"); return
    plan_key = callback.data.split(":")[1]
    await state.update_data(broadcast_plan=plan_key)
    await state.set_state(AdminStates.broadcast_text)
    plan = PLANS[plan_key]
    await callback.answer()
    await callback.message.edit_text(
        f"📢 <b>Рассылка для тарифа {plan['name']}</b>\n\n"
        "Введи текст сообщения:",
        parse_mode="HTML",
        reply_markup=back_button("back_admin"),
    )


@router.message(AdminStates.broadcast_text)
async def adm_broadcast_send(message: Message, user, state: FSMContext):
    if user.id not in settings.admin_ids: return

    data = await state.get_data()
    plan_filter = data.get("broadcast_plan")
    await state.clear()

    broadcast_text = message.text.strip()

    async with get_session() as session:
        if plan_filter:
            from sqlalchemy import select
            from database.models import User as UserModel, PlanEnum
            result = await session.execute(
                select(UserModel.id).where(UserModel.plan == PlanEnum(plan_filter))
            )
            user_ids = [row[0] for row in result.fetchall()]
        else:
            user_ids = await UserRepo.get_all_ids(session)

    if not user_ids:
        await message.answer("📭 Нет пользователей для рассылки")
        return

    plan_info = f" (тариф: {PLANS[plan_filter]['name']})" if plan_filter else ""
    status = await message.answer(
        f"📢 Рассылка{plan_info}...\n"
        f"Получателей: <b>{len(user_ids)}</b>",
        parse_mode="HTML",
    )

    sent = failed = 0
    for uid in user_ids:
        try:
            await message.bot.send_message(uid, broadcast_text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
        if (sent + failed) % 20 == 0:
            await asyncio.sleep(1)

    await status.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"✉️ Доставлено: <b>{sent}</b>\n"
        f"❌ Не доставлено: <b>{failed}</b>",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )


# ── Очистить все диалоги ──────────────────────────────────────────────────────

@router.callback_query(F.data == "adm_clear_all")
async def adm_clear_all(callback: CallbackQuery, user):
    if user.id not in settings.admin_ids:
        await callback.answer("⛔"); return
    await callback.answer()

    from keyboards import confirm_keyboard
    await callback.message.edit_text(
        "⚠️ <b>Очистить все диалоги?</b>\n\n"
        "Это удалит историю всех пользователей из БД.",
        parse_mode="HTML",
        reply_markup=confirm_keyboard("admin_clear_all", "🗑 Очистить всё", "◀️ Назад"),
    )


@router.callback_query(F.data == "confirm_yes:admin_clear_all")
async def adm_clear_all_confirmed(callback: CallbackQuery, user):
    if user.id not in settings.admin_ids:
        await callback.answer("⛔"); return

    async with get_session() as session:
        from sqlalchemy import delete
        from database.models import Message as MessageModel
        result = await session.execute(delete(MessageModel))
        count = result.rowcount

    await callback.answer(f"✅ Удалено {count} сообщений")
    await callback.message.edit_text(
        f"🗑 Удалено <b>{count}</b> сообщений из всех диалогов.",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )
