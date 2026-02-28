"""
🛠 Утилиты — форматирование, хелперы
"""

import html
import re
from datetime import datetime, timedelta
from typing import Optional

from config.settings import PLANS


# ── HTML / форматирование ─────────────────────────────────────────────────────

def escape_html(text: str) -> str:
    """Экранирует HTML-символы"""
    return html.escape(text, quote=False)


def safe_html(text: str) -> str:
    """
    Пытается сохранить базовые HTML теги Telegram (<b>, <i>, <code>, <pre>)
    и экранирует остальное.
    """
    # Разрешённые теги
    allowed = r'</?(?:b|i|u|s|code|pre|a|tg-spoiler)(?:\s[^>]*)?>|<br\s*/?>'
    parts = re.split(f'({allowed})', text, flags=re.IGNORECASE)
    result = []
    for part in parts:
        if re.match(allowed, part, re.IGNORECASE):
            result.append(part)
        else:
            result.append(escape_html(part))
    return "".join(result)


def markdown_to_html(text: str) -> str:
    """
    Конвертирует Markdown в HTML для Telegram.
    Базовая конвертация — **bold**, *italic*, `code`, ```code block```
    """
    # Code blocks (multi-line) — обрабатываем первыми
    text = re.sub(
        r'```(?:\w+\n)?(.*?)```',
        lambda m: f'<pre><code>{escape_html(m.group(1).strip())}</code></pre>',
        text, flags=re.DOTALL
    )
    # Inline code
    text = re.sub(
        r'`([^`\n]+)`',
        lambda m: f'<code>{escape_html(m.group(1))}</code>',
        text
    )
    # Bold **text** и __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)
    # Italic *text* и _text_
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    text = re.sub(r'_([^_\n]+)_', r'<i>\1</i>', text)
    # Strikethrough ~~text~~
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)
    return text


def split_long_message(text: str, max_length: int = 4096) -> list[str]:
    """Разбивает длинное сообщение на части"""
    if len(text) <= max_length:
        return [text]

    chunks = []
    current = ""
    # Разбиваем по параграфам
    paragraphs = text.split("\n\n")
    for para in paragraphs:
        if len(current) + len(para) + 2 <= max_length:
            current += ("" if not current else "\n\n") + para
        else:
            if current:
                chunks.append(current)
            if len(para) <= max_length:
                current = para
            else:
                # Разбиваем по строкам
                for line in para.split("\n"):
                    if len(current) + len(line) + 1 <= max_length:
                        current += ("" if not current else "\n") + line
                    else:
                        if current:
                            chunks.append(current)
                        current = line
    if current:
        chunks.append(current)
    return chunks if chunks else [text[:max_length]]


# ── Прогресс-бары и форматирование ───────────────────────────────────────────

def progress_bar(used: int, total: int, length: int = 10) -> str:
    """Строит прогресс-бар: ▓▓▓░░░░░░░"""
    if total <= 0:
        return "▓" * length
    filled = min(int((used / total) * length), length)
    return "▓" * filled + "░" * (length - filled)


def format_limit_bar(used: int, total: int, label: str = "") -> str:
    """Форматирует строку лимита с прогресс-баром"""
    if total == -1:
        return f"{label} ∞"
    bar = progress_bar(used, total)
    pct = min(int((used / total) * 100), 100) if total > 0 else 0
    return f"{bar} {used}/{total} ({pct}%){' ' + label if label else ''}"


def format_plan_limits(user, plan_key: str) -> str:
    """Форматирует строку лимитов пользователя"""
    plan = PLANS[plan_key]
    msg_bar = format_limit_bar(user.today_messages, plan["daily_limit"], "сообщений")
    img_bar = format_limit_bar(user.today_images, plan["image_limit"], "картинок")
    voc_bar = format_limit_bar(user.today_voice, plan["voice_limit"], "голосовых")
    return (
        f"💬 {msg_bar}\n"
        f"🎨 {img_bar}\n"
        f"🎙 {voc_bar}"
    )


# ── Форматирование дат ────────────────────────────────────────────────────────

def format_datetime(dt: Optional[datetime], default: str = "—") -> str:
    if not dt:
        return default
    return dt.strftime("%d.%m.%Y %H:%M")


def format_date(dt: Optional[datetime], default: str = "—") -> str:
    if not dt:
        return default
    return dt.strftime("%d.%m.%Y")


def time_until(dt: Optional[datetime]) -> str:
    """'осталось X дней/часов'"""
    if not dt:
        return "бессрочно"
    now = datetime.utcnow()
    if dt < now:
        return "истекла"
    delta = dt - now
    if delta.days > 0:
        return f"{delta.days} дн."
    hours = delta.seconds // 3600
    if hours > 0:
        return f"{hours} ч."
    minutes = delta.seconds // 60
    return f"{minutes} мин."


def format_timedelta(seconds: int) -> str:
    """Форматирует секунды в читаемую строку"""
    if seconds < 60:
        return f"{seconds}с"
    if seconds < 3600:
        return f"{seconds // 60}м {seconds % 60}с"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours}ч {minutes}м"


# ── Форматирование пользователя ───────────────────────────────────────────────

def format_user_link(user) -> str:
    """Форматирует ссылку на пользователя для HTML"""
    name = escape_html(user.display_name)
    return f'<a href="tg://user?id={user.id}">{name}</a>'


def format_user_card(user, plan: dict) -> str:
    """Карточка пользователя для статистики"""
    name = escape_html(user.display_name)
    username = f"@{user.username}" if user.username else "—"
    expires = time_until(user.plan_expires) if user.plan.value != "free" else "бессрочно"

    lines = [
        f"👤 <b>{name}</b> ({username})",
        f"🆔 ID: <code>{user.id}</code>",
        f"💎 Тариф: <b>{plan['name']}</b>",
        f"⏰ Подписка: {expires}",
        f"💬 Сообщений всего: <b>{user.total_messages}</b>",
        f"🎨 Картинок: <b>{user.total_images}</b>",
        f"📅 Регистрация: {format_date(user.created_at)}",
        f"🕐 Последняя активность: {format_datetime(user.last_activity)}",
    ]
    if user.referral_count > 0:
        lines.append(f"👥 Рефералов: <b>{user.referral_count}</b>")
    if user.is_banned:
        lines.append(f"🚫 <b>ЗАБЛОКИРОВАН</b>: {user.ban_reason or '—'}")
    return "\n".join(lines)


# ── Числовое форматирование ───────────────────────────────────────────────────

def format_number(n: int) -> str:
    """1234567 → '1 234 567'"""
    return f"{n:,}".replace(",", " ")


def format_money(amount: float, currency: str = "USD") -> str:
    symbols = {"USD": "$", "RUB": "₽", "EUR": "€", "USDT": "USDT"}
    symbol = symbols.get(currency, currency)
    if currency in ("USD", "EUR"):
        return f"{symbol}{amount:.2f}"
    return f"{amount:.0f} {symbol}"


# ── Транслитерация ────────────────────────────────────────────────────────────

def transliterate(text: str) -> str:
    """Простая транслитерация рус → лат"""
    tr = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
        'ё': 'yo', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k',
        'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
        'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
        'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
        'э': 'e', 'ю': 'yu', 'я': 'ya',
    }
    result = []
    for char in text.lower():
        result.append(tr.get(char, char))
    return "".join(result)


# ── Парсинг команды генерации ─────────────────────────────────────────────────

def parse_image_command(text: str) -> tuple[str, str, str]:
    """
    Парсит команду /image [стиль] [размер] <промпт>
    Возвращает (промпт, стиль, размер)
    """
    from services.imagegen import ImageGenService
    parts = text.strip().split()
    style = "default"
    size = "square"
    prompt_parts = []

    for part in parts:
        if part.lower() in ImageGenService.STYLES:
            style = part.lower()
        elif part.lower() in ImageGenService.SIZES:
            size = part.lower()
        else:
            prompt_parts.append(part)

    return " ".join(prompt_parts), style, size
