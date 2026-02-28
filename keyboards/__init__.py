"""
⌨️ Все клавиатуры бота
"""

from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
)

from config.settings import settings, PLANS
from services.imagegen import ImageGenService


# ── Главное меню ──────────────────────────────────────────────────────────────

def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="🤖 Новый диалог",    callback_data="new_chat"),
            InlineKeyboardButton(text="🎨 Картинка",        callback_data="gen_image_start"),
        ],
        [
            InlineKeyboardButton(text="🧠 Персонаж AI",     callback_data="personality_menu"),
            InlineKeyboardButton(text="📜 История",         callback_data="show_history"),
        ],
        [
            InlineKeyboardButton(text="💎 Подписка",        callback_data="plans_menu"),
            InlineKeyboardButton(text="📊 Статистика",      callback_data="my_stats"),
        ],
        [
            InlineKeyboardButton(text="⚙️ Настройки",       callback_data="settings_menu"),
            InlineKeyboardButton(text="ℹ️ О боте",          callback_data="about"),
        ],
        [
            InlineKeyboardButton(text="🛍 Магазин",         url=settings.main_bot_link),
            InlineKeyboardButton(text="📢 Канал",           url=settings.channel_link),
        ],
    ]
    if is_admin:
        rows.insert(0, [
            InlineKeyboardButton(text="🔑 Админ-панель", callback_data="admin_panel")
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_main")]
    ])


def back_button(callback_data: str = "back_main", text: str = "◀️ Назад") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, callback_data=callback_data)]
    ])


# ── Тарифы ────────────────────────────────────────────────────────────────────

def plans_keyboard(current_plan: str) -> InlineKeyboardMarkup:
    rows = []
    for key, plan in PLANS.items():
        is_current = key == current_plan
        label = f"{plan['emoji']} {plan['name']}"
        if is_current:
            label = f"✅ {label} (активен)"
        rows.append([
            InlineKeyboardButton(text=label, callback_data=f"plan_info:{key}")
        ])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plan_detail_keyboard(plan_key: str, current_plan: str) -> InlineKeyboardMarkup:
    rows = []
    if plan_key != current_plan and plan_key != "free":
        plan = PLANS[plan_key]
        rows.append([
            InlineKeyboardButton(
                text=f"💳 Купить {plan['name']} — {plan['price']}$/мес",
                url=f"https://t.me/{settings.owner_username[1:]}"
            )
        ])
    rows.append([InlineKeyboardButton(text="◀️ К тарифам", callback_data="plans_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Персоналити / системные промпты ──────────────────────────────────────────

def personality_keyboard(personalities: list, current: str, is_premium: bool) -> InlineKeyboardMarkup:
    rows = []
    for p in personalities:
        label = f"{p.emoji} {p.name}"
        if p.key == current:
            label = f"✅ {label}"
        if p.is_premium and not is_premium:
            label = f"🔒 {p.name}"
            rows.append([InlineKeyboardButton(text=label, callback_data="personality_locked")])
        else:
            rows.append([InlineKeyboardButton(text=label, callback_data=f"set_personality:{p.key}")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Генерация изображений ─────────────────────────────────────────────────────

def image_style_keyboard() -> InlineKeyboardMarkup:
    rows = []
    styles = list(ImageGenService.STYLES.items())
    # Группируем по 2 в ряд
    for i in range(0, len(styles), 2):
        row = []
        for key, label in styles[i:i+2]:
            row.append(InlineKeyboardButton(text=label, callback_data=f"img_style:{key}"))
        rows.append(row)
    rows.append([InlineKeyboardButton(text="◀️ Отмена", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def image_size_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for key, (size_str, label) in ImageGenService.SIZES.items():
        rows.append([InlineKeyboardButton(text=label, callback_data=f"img_size:{key}")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="gen_image_start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def image_result_keyboard(prompt: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Ещё раз",  callback_data="img_regenerate"),
            InlineKeyboardButton(text="✏️ Изменить", callback_data="img_edit_prompt"),
        ],
        [InlineKeyboardButton(text="🎨 Стиль",       callback_data="gen_image_start")],
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_main")],
    ])


# ── Настройки пользователя ─────────────────────────────────────────────────────

def settings_keyboard(voice_enabled: bool, notifications: bool) -> InlineKeyboardMarkup:
    voice_icon = "🔊" if voice_enabled else "🔇"
    notif_icon = "🔔" if notifications else "🔕"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{voice_icon} Голос в ответах: {'Вкл' if voice_enabled else 'Выкл'}",
            callback_data="toggle_voice"
        )],
        [InlineKeyboardButton(
            text=f"{notif_icon} Уведомления: {'Вкл' if notifications else 'Выкл'}",
            callback_data="toggle_notifications"
        )],
        [InlineKeyboardButton(text="🗣 Голос TTS",   callback_data="tts_voice_menu")],
        [InlineKeyboardButton(text="🌍 Язык",        callback_data="language_menu")],
        [InlineKeyboardButton(text="📋 Мои пресеты", callback_data="presets_menu")],
        [InlineKeyboardButton(text="🗑 Очистить историю", callback_data="confirm_clear")],
        [InlineKeyboardButton(text="◀️ Назад",        callback_data="back_main")],
    ])


def confirm_keyboard(action: str, yes_text: str = "✅ Да", no_text: str = "❌ Нет") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=yes_text, callback_data=f"confirm_yes:{action}"),
            InlineKeyboardButton(text=no_text,  callback_data="back_main"),
        ]
    ])


def language_keyboard(current: str) -> InlineKeyboardMarkup:
    languages = [
        ("ru", "🇷🇺 Русский"),
        ("en", "🇬🇧 English"),
        ("uk", "🇺🇦 Українська"),
        ("de", "🇩🇪 Deutsch"),
        ("fr", "🇫🇷 Français"),
        ("es", "🇪🇸 Español"),
    ]
    rows = []
    for code, name in languages:
        label = f"✅ {name}" if code == current else name
        rows.append([InlineKeyboardButton(text=label, callback_data=f"set_lang:{code}")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="settings_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Пресеты ───────────────────────────────────────────────────────────────────

def presets_keyboard(presets, active_id: int = None) -> InlineKeyboardMarkup:
    rows = []
    for preset in presets:
        label = f"{'✅ ' if preset.id == active_id else ''}📋 {preset.name}"
        rows.append([
            InlineKeyboardButton(text=label,       callback_data=f"preset_use:{preset.id}"),
            InlineKeyboardButton(text="🗑",         callback_data=f"preset_del:{preset.id}"),
        ])
    rows.append([InlineKeyboardButton(text="➕ Новый пресет", callback_data="preset_create")])
    rows.append([InlineKeyboardButton(text="◀️ Назад",       callback_data="settings_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Лимиты / апгрейд ──────────────────────────────────────────────────────────

def upgrade_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Посмотреть тарифы", callback_data="plans_menu")],
        [InlineKeyboardButton(text="◀️ Назад",             callback_data="back_main")],
    ])


def limit_warning_keyboard(remaining: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"⬆️ Поднять лимит (осталось {remaining})",
            callback_data="plans_menu"
        )],
    ])


# ── Админ-панель ──────────────────────────────────────────────────────────────

def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Статистика",      callback_data="adm_stats"),
            InlineKeyboardButton(text="👥 Пользователи",    callback_data="adm_users"),
        ],
        [
            InlineKeyboardButton(text="💎 Выдать подписку", callback_data="adm_give_sub"),
            InlineKeyboardButton(text="🔍 Найти юзера",     callback_data="adm_find_user"),
        ],
        [
            InlineKeyboardButton(text="🚫 Забанить",        callback_data="adm_ban"),
            InlineKeyboardButton(text="✅ Разбанить",       callback_data="adm_unban"),
        ],
        [
            InlineKeyboardButton(text="📢 Рассылка",        callback_data="adm_broadcast"),
            InlineKeyboardButton(text="🎯 Рассылка по тарифу", callback_data="adm_broadcast_plan"),
        ],
        [
            InlineKeyboardButton(text="🗑 Очистить все чаты", callback_data="adm_clear_all"),
            InlineKeyboardButton(text="📝 Системный промпт", callback_data="adm_edit_prompt"),
        ],
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_main")],
    ])


def admin_broadcast_plan_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for key, plan in PLANS.items():
        rows.append([InlineKeyboardButton(
            text=f"{plan['emoji']} {plan['name']}",
            callback_data=f"adm_bcast_plan:{key}"
        )])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def give_sub_plan_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for key, plan in PLANS.items():
        if key == "free":
            continue
        rows.append([InlineKeyboardButton(
            text=f"{plan['emoji']} {plan['name']} — {plan['price']}$/мес",
            callback_data=f"adm_sub_plan:{key}"
        )])
    rows.append([InlineKeyboardButton(text="🆓 Сбросить до Free", callback_data="adm_sub_plan:free")])
    rows.append([InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def give_sub_days_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="7 дней",   callback_data="adm_sub_days:7"),
            InlineKeyboardButton(text="14 дней",  callback_data="adm_sub_days:14"),
            InlineKeyboardButton(text="30 дней",  callback_data="adm_sub_days:30"),
        ],
        [
            InlineKeyboardButton(text="60 дней",  callback_data="adm_sub_days:60"),
            InlineKeyboardButton(text="90 дней",  callback_data="adm_sub_days:90"),
            InlineKeyboardButton(text="365 дней", callback_data="adm_sub_days:365"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_give_sub")],
    ])


# ── История ────────────────────────────────────────────────────────────────────

def history_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Очистить историю", callback_data="confirm_clear")],
        [InlineKeyboardButton(text="◀️ Назад",           callback_data="back_main")],
    ])


# ── Реферальная система ───────────────────────────────────────────────────────

def referral_keyboard(bot_username: str, user_id: int) -> InlineKeyboardMarkup:
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться ссылкой", url=f"https://t.me/share/url?url={ref_link}&text=🤖+Попробуй+этого+AI+бота!")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")],
    ])
