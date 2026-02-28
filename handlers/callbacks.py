"""
🔘 Обработчики callback-кнопок — меню, настройки, персоналити
"""

import logging
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config.settings import settings, PLANS
from database import get_session, UserRepo, MessageRepo, PromptRepo, PresetRepo
from keyboards import (
    main_menu, plans_keyboard, plan_detail_keyboard,
    personality_keyboard, settings_keyboard, confirm_keyboard,
    language_keyboard, presets_keyboard, back_to_main, back_button,
    history_keyboard
)
from utils import (
    format_plan_limits, format_datetime, format_date,
    time_until, format_number, escape_html
)

logger = logging.getLogger(__name__)
router = Router()


class SettingsStates(StatesGroup):
    waiting_preset_name   = State()
    waiting_preset_prompt = State()


# ── Главное меню ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "back_main")
async def cb_back_main(callback: CallbackQuery, user, state: FSMContext):
    await state.clear()
    await callback.answer()
    fname = escape_html(user.first_name or "друг")
    plan = PLANS[user.plan.value]
    await callback.message.edit_text(
        f"👋 <b>{fname}</b>, чем могу помочь?\n\n"
        f"💎 {plan['name']} · {format_plan_limits(user, user.plan.value)}",
        parse_mode="HTML",
        reply_markup=main_menu(is_admin=user.is_admin),
    )


# ── Новый диалог ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "new_chat")
async def cb_new_chat(callback: CallbackQuery, user):
    async with get_session() as session:
        count = await MessageRepo.clear_history(session, user.id)
    await callback.answer("✅ Новый диалог!")
    await callback.message.edit_text(
        f"🔄 <b>Новый диалог начат!</b>\n\n"
        f"{'Удалено ' + str(count) + ' сообщений.' if count else 'История и так была пуста.'}\n"
        f"О чём поговорим? 🙂",
        parse_mode="HTML",
        reply_markup=main_menu(user.is_admin),
    )


# ── История диалога ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "show_history")
async def cb_show_history(callback: CallbackQuery, user):
    async with get_session() as session:
        history = await MessageRepo.get_history(session, user.id, 10)

    await callback.answer()
    if not history:
        await callback.message.edit_text(
            "💭 <b>История пуста</b>\n\nПросто напиши мне что-нибудь!",
            parse_mode="HTML",
            reply_markup=back_to_main(),
        )
        return

    lines = [f"📜 <b>Последние {len(history)} сообщений:</b>\n"]
    for msg in history:
        role = "👤 Ты" if msg.role == "user" else "🤖 AI"
        preview = msg.content[:70].replace("\n", " ")
        if len(msg.content) > 70:
            preview += "…"
        t = msg.created_at.strftime("%H:%M")
        lines.append(f"<b>{role}</b> [{t}]: {escape_html(preview)}")

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=history_keyboard(),
    )


# ── Подтверждение очистки ─────────────────────────────────────────────────────

@router.callback_query(F.data == "confirm_clear")
async def cb_confirm_clear(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🗑 <b>Очистить историю диалога?</b>\n\n"
        "Все сообщения будут удалены из памяти AI.\n"
        "Это действие нельзя отменить.",
        parse_mode="HTML",
        reply_markup=confirm_keyboard("clear_history", "🗑 Да, очистить", "❌ Отмена"),
    )


@router.callback_query(F.data == "confirm_yes:clear_history")
async def cb_clear_confirmed(callback: CallbackQuery, user):
    async with get_session() as session:
        count = await MessageRepo.clear_history(session, user.id)
    await callback.answer("✅ История очищена!")
    await callback.message.edit_text(
        f"🗑 <b>История очищена</b>\n\n"
        f"Удалено {count} сообщений. Начинаем заново! 🙂",
        parse_mode="HTML",
        reply_markup=main_menu(user.is_admin),
    )


# ── Тарифы ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "plans_menu")
async def cb_plans_menu(callback: CallbackQuery, user):
    await callback.answer()
    plan = PLANS[user.plan.value]
    expires = time_until(user.plan_expires) if user.plan.value != "free" else "бессрочно"

    text = (
        f"💎 <b>Тарифные планы</b>\n\n"
        f"Текущий тариф: <b>{plan['name']}</b>\n"
        f"Подписка: {expires}\n\n"
        f"Выбери тариф для подробной информации:"
    )
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=plans_keyboard(user.plan.value),
    )


@router.callback_query(F.data.startswith("plan_info:"))
async def cb_plan_info(callback: CallbackQuery, user):
    plan_key = callback.data.split(":")[1]
    plan = PLANS.get(plan_key)
    if not plan:
        await callback.answer("❌ Тариф не найден")
        return

    await callback.answer()

    limit_str = "∞ безлимит" if plan["daily_limit"] == -1 else f"{plan['daily_limit']}/день"
    img_str = "∞" if plan["image_limit"] == -1 else str(plan["image_limit"])
    voice_str = "∞" if plan["voice_limit"] == -1 else str(plan["voice_limit"])
    price_str = "Бесплатно" if plan["price"] == 0 else f"{plan['price']}$/мес ({plan['price_rub']}₽)"

    features_text = "\n".join(f"  {f}" for f in plan["features"])

    text = (
        f"{plan['emoji']} <b>{plan['name']}</b>\n\n"
        f"💬 Сообщений: <b>{limit_str}</b>\n"
        f"🎨 Картинок: <b>{img_str}/день</b>\n"
        f"🎙 Голосовых: <b>{voice_str}/день</b>\n"
        f"🧠 Память: <b>{plan['history']} сообщений</b>\n\n"
        f"<b>Включено:</b>\n{features_text}\n\n"
        f"💰 Цена: <b>{price_str}</b>"
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=plan_detail_keyboard(plan_key, user.plan.value),
    )


# ── Персоналити / Характер AI ─────────────────────────────────────────────────

@router.callback_query(F.data == "personality_menu")
async def cb_personality_menu(callback: CallbackQuery, user):
    async with get_session() as session:
        personalities = await PromptRepo.get_all(session)

    is_premium = user.plan.value != "free"
    await callback.answer()
    await callback.message.edit_text(
        "🧠 <b>Выбери характер AI</b>\n\n"
        "Это определяет как AI будет общаться с тобой.\n"
        "🔒 — только для платных тарифов.",
        parse_mode="HTML",
        reply_markup=personality_keyboard(personalities, user.ai_personality, is_premium),
    )


@router.callback_query(F.data == "personality_locked")
async def cb_personality_locked(callback: CallbackQuery):
    await callback.answer(
        "🔒 Этот персонаж доступен только на платных тарифах!",
        show_alert=True,
    )


@router.callback_query(F.data.startswith("set_personality:"))
async def cb_set_personality(callback: CallbackQuery, user):
    personality_key = callback.data.split(":")[1]

    async with get_session() as session:
        prompt = await PromptRepo.get_by_key(session, personality_key)
        if not prompt:
            await callback.answer("❌ Персонаж не найден")
            return

        # Проверяем доступ
        if prompt.is_premium and user.plan.value == "free":
            await callback.answer("🔒 Только для платных тарифов!", show_alert=True)
            return

        # Устанавливаем
        fresh_user = await UserRepo.get(session, user.id)
        fresh_user.ai_personality = personality_key
        await session.commit()

    await callback.answer(f"✅ Персонаж изменён: {prompt.emoji} {prompt.name}")
    await callback.message.edit_text(
        f"✅ <b>Персонаж изменён!</b>\n\n"
        f"{prompt.emoji} <b>{prompt.name}</b>\n\n"
        f"Теперь AI будет общаться в этом стиле.\n"
        f"<i>Рекомендуем начать /new для чистого диалога.</i>",
        parse_mode="HTML",
        reply_markup=main_menu(user.is_admin),
    )


# ── Настройки ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings_menu")
async def cb_settings_menu(callback: CallbackQuery, user):
    await callback.answer()
    await callback.message.edit_text(
        f"⚙️ <b>Настройки</b>\n\n"
        f"🗣 Голос в ответах: {'включён' if user.voice_enabled else 'выключен'}\n"
        f"🔔 Уведомления: {'включены' if user.notifications else 'выключены'}\n"
        f"🌍 Язык: {user.language}",
        parse_mode="HTML",
        reply_markup=settings_keyboard(user.voice_enabled, user.notifications),
    )


@router.callback_query(F.data == "toggle_voice")
async def cb_toggle_voice(callback: CallbackQuery, user):
    async with get_session() as session:
        fresh_user = await UserRepo.get(session, user.id)
        fresh_user.voice_enabled = not fresh_user.voice_enabled
        new_state = fresh_user.voice_enabled
        await session.commit()

    status = "включён 🔊" if new_state else "выключен 🔇"
    await callback.answer(f"Голос {status}")
    await callback.message.edit_reply_markup(
        reply_markup=settings_keyboard(new_state, user.notifications)
    )


@router.callback_query(F.data == "toggle_notifications")
async def cb_toggle_notifications(callback: CallbackQuery, user):
    async with get_session() as session:
        fresh_user = await UserRepo.get(session, user.id)
        fresh_user.notifications = not fresh_user.notifications
        new_state = fresh_user.notifications
        await session.commit()

    status = "включены 🔔" if new_state else "выключены 🔕"
    await callback.answer(f"Уведомления {status}")
    await callback.message.edit_reply_markup(
        reply_markup=settings_keyboard(user.voice_enabled, new_state)
    )


@router.callback_query(F.data == "language_menu")
async def cb_language_menu(callback: CallbackQuery, user):
    await callback.answer()
    await callback.message.edit_text(
        "🌍 <b>Выбери язык</b>\n\n"
        "Язык влияет на интерфейс бота.",
        parse_mode="HTML",
        reply_markup=language_keyboard(user.language),
    )


@router.callback_query(F.data.startswith("set_lang:"))
async def cb_set_language(callback: CallbackQuery, user):
    lang = callback.data.split(":")[1]
    async with get_session() as session:
        fresh_user = await UserRepo.get(session, user.id)
        fresh_user.language = lang
        await session.commit()

    await callback.answer(f"✅ Язык изменён")
    await callback.message.edit_text(
        "⚙️ <b>Настройки обновлены!</b>",
        parse_mode="HTML",
        reply_markup=settings_keyboard(user.voice_enabled, user.notifications),
    )


# ── Пресеты ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "presets_menu")
async def cb_presets_menu(callback: CallbackQuery, user):
    async with get_session() as session:
        presets = await PresetRepo.get_user_presets(session, user.id)
        active = await PresetRepo.get_active(session, user.id)

    await callback.answer()

    if not presets:
        await callback.message.edit_text(
            "📋 <b>Пресеты системных промптов</b>\n\n"
            "Пресеты позволяют сохранить свои инструкции для AI.\n\n"
            "У тебя пока нет пресетов. Создай первый!",
            parse_mode="HTML",
            reply_markup=presets_keyboard([], None),
        )
    else:
        active_id = active.id if active else None
        await callback.message.edit_text(
            f"📋 <b>Мои пресеты ({len(presets)})</b>\n\n"
            "✅ — активный пресет (используется как доп. инструкция)",
            parse_mode="HTML",
            reply_markup=presets_keyboard(presets, active_id),
        )


@router.callback_query(F.data == "preset_create")
async def cb_preset_create(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsStates.waiting_preset_name)
    await callback.message.edit_text(
        "📋 <b>Новый пресет</b>\n\nВведи название пресета:",
        parse_mode="HTML",
    )


@router.message(SettingsStates.waiting_preset_name)
async def handle_preset_name(message, state: FSMContext):
    name = message.text.strip()
    if len(name) > 64:
        await message.answer("❌ Слишком длинное название (макс. 64 символа):")
        return
    await state.update_data(preset_name=name)
    await state.set_state(SettingsStates.waiting_preset_prompt)
    await message.answer(
        f"✅ Название: <b>{escape_html(name)}</b>\n\n"
        "Теперь напиши текст системного промпта:\n\n"
        "<i>Например: 'Отвечай только кратко, не более 2 предложений'</i>",
        parse_mode="HTML",
    )


@router.message(SettingsStates.waiting_preset_prompt)
async def handle_preset_prompt(message, state: FSMContext, user):
    prompt_text = message.text.strip()
    if len(prompt_text) > 2000:
        await message.answer("❌ Слишком длинный промпт (макс. 2000 символов):")
        return

    data = await state.get_data()
    name = data.get("preset_name", "Пресет")
    await state.clear()

    async with get_session() as session:
        preset = await PresetRepo.create(session, user.id, name, prompt_text)
        presets = await PresetRepo.get_user_presets(session, user.id)
        active = await PresetRepo.get_active(session, user.id)

    await message.answer(
        f"✅ <b>Пресет создан и активирован!</b>\n\n"
        f"📋 Название: <b>{escape_html(name)}</b>\n"
        f"📝 Промпт применяется к каждому диалогу.",
        parse_mode="HTML",
        reply_markup=presets_keyboard(presets, active.id if active else None),
    )


@router.callback_query(F.data.startswith("preset_use:"))
async def cb_preset_use(callback: CallbackQuery, user):
    preset_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        success = await PresetRepo.set_active(session, preset_id, user.id)
        presets = await PresetRepo.get_user_presets(session, user.id)

    if success:
        await callback.answer("✅ Пресет активирован!")
        await callback.message.edit_reply_markup(
            reply_markup=presets_keyboard(presets, preset_id)
        )
    else:
        await callback.answer("❌ Ошибка")


@router.callback_query(F.data.startswith("preset_del:"))
async def cb_preset_del(callback: CallbackQuery, user):
    preset_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        success = await PresetRepo.delete(session, preset_id, user.id)
        presets = await PresetRepo.get_user_presets(session, user.id)
        active = await PresetRepo.get_active(session, user.id)

    if success:
        await callback.answer("🗑 Пресет удалён")
        await callback.message.edit_reply_markup(
            reply_markup=presets_keyboard(presets, active.id if active else None)
        )
    else:
        await callback.answer("❌ Не удалось удалить")


# ── Статистика пользователя ───────────────────────────────────────────────────

@router.callback_query(F.data == "my_stats")
async def cb_my_stats(callback: CallbackQuery, user):
    plan = PLANS[user.plan.value]
    expires = time_until(user.plan_expires) if user.plan.value != "free" else "бессрочно"

    await callback.answer()
    await callback.message.edit_text(
        f"📊 <b>Моя статистика</b>\n\n"
        f"💎 Тариф: <b>{plan['name']}</b>\n"
        f"⏰ Подписка: {expires}\n\n"
        f"📈 <b>Сегодня:</b>\n"
        f"{format_plan_limits(user, user.plan.value)}\n\n"
        f"🏆 <b>За всё время:</b>\n"
        f"💬 Сообщений: <b>{format_number(user.total_messages)}</b>\n"
        f"🎨 Картинок: <b>{format_number(user.total_images)}</b>\n"
        f"🎙 Голосовых: <b>{format_number(user.total_voice)}</b>\n\n"
        f"👥 Рефералов: <b>{user.referral_count}</b>\n"
        f"📅 В боте с: {format_date(user.created_at)}",
        parse_mode="HTML",
        reply_markup=back_to_main(),
    )


# ── О боте ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "about")
async def cb_about(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🤖 <b>Gemini AI Bot</b>\n\n"
        "Персональный AI-ассистент на базе Google Gemini.\n\n"
        "🧠 <b>Возможности:</b>\n"
        "• Умный чат с контекстом\n"
        "• Анализ фото и документов\n"
        "• Распознавание голоса\n"
        "• Генерация изображений (FLUX)\n"
        "• 8 персонажей AI\n"
        "• Пресеты системных промптов\n\n"
        f"👤 Разработчик: {settings.owner_username}\n"
        f"📢 Канал: {settings.channel_link}",
        parse_mode="HTML",
        reply_markup=back_to_main(),
    )
