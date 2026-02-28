"""
╔══════════════════════════════════════════════════════════════════════╗
║                    ⚙️  КОНФИГУРАЦИЯ БОТА                             ║
║                                                                      ║
║  Переменные окружения:                                               ║
║    BOT_TOKEN       — токен от @BotFather                            ║
║    GEMINI_KEY      — ключ Google AI Studio                          ║
║    DATABASE_URL    — postgresql://user:pass@host/db                 ║
║    ADMIN_IDS       — ID админов через запятую: 123,456              ║
║    IMAGEGEN_KEY    — ключ для генерации изображений (Together AI)   ║
║    OWNER_USERNAME  — username владельца бота                        ║
║    CHANNEL_LINK    — ссылка на канал                                ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Settings:
    # ── Telegram ──────────────────────────────────────────────
    bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    admin_ids: list[int] = field(default_factory=lambda: [
        int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
    ])
    owner_username: str = field(default_factory=lambda: os.getenv("OWNER_USERNAME", "@admin"))
    channel_link: str = field(default_factory=lambda: os.getenv("CHANNEL_LINK", "https://t.me/example"))
    main_bot_link: str = field(default_factory=lambda: os.getenv("MAIN_BOT_LINK", "https://t.me/example_bot"))

    # ── База данных ───────────────────────────────────────────
    database_url: str = field(default_factory=lambda: os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/gemini_bot"
    ))

    # ── Gemini AI ─────────────────────────────────────────────
    gemini_key: str = field(default_factory=lambda: os.getenv("GEMINI_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))
    gemini_vision_model: str = "gemini-2.0-flash"
    gemini_max_tokens: int = 8192
    gemini_temperature: float = 0.7
    gemini_timeout: int = 60

    # ── Генерация изображений (Together AI / Stability) ───────
    imagegen_key: str = field(default_factory=lambda: os.getenv("IMAGEGEN_KEY", ""))
    imagegen_model: str = "black-forest-labs/FLUX.1-schnell-Free"
    imagegen_steps: int = 4
    imagegen_width: int = 1024
    imagegen_height: int = 1024

    # ── Голосовые сообщения ───────────────────────────────────
    tts_voice: str = "ru-RU-Standard-A"     # Google TTS голос
    stt_language: str = "ru-RU"

    # ── Диалог ────────────────────────────────────────────────
    max_history: int = 100
    typing_interval: float = 3.0

    # ── Rate limiting ─────────────────────────────────────────
    rate_limit_messages: int = 5            # сообщений
    rate_limit_period: int = 10             # за N секунд

    # ── Реферальная система ───────────────────────────────────
    referral_bonus_messages: int = 5        # бонусных сообщений за реферала
    referral_bonus_days: int = 0            # бонусных дней

    def validate(self) -> list[str]:
        """Проверяет наличие обязательных переменных"""
        errors = []
        if not self.bot_token:
            errors.append("❌ BOT_TOKEN не задан")
        if not self.gemini_key:
            errors.append("❌ GEMINI_KEY не задан")
        if not self.database_url:
            errors.append("❌ DATABASE_URL не задан")
        return errors


# ── Тарифные планы ────────────────────────────────────────────────────────────

PLANS: dict[str, dict] = {
    "free": {
        "name":          "🆓 Бесплатный",
        "emoji":         "🆓",
        "daily_limit":   10,
        "image_limit":   2,           # генерация картинок в день
        "voice_limit":   5,           # голосовых в день
        "price":         0,
        "price_rub":     0,
        "history":       10,
        "desc":          "10 сообщений · 2 картинки · 5 голосовых в день",
        "color":         "gray",
        "features": [
            "✅ Gemini Flash",
            "✅ 10 сообщений/день",
            "✅ 2 картинки/день",
            "✅ 5 голосовых/день",
            "❌ Без приоритета",
            "❌ Без памяти Pro",
        ],
    },
    "basic": {
        "name":          "⚡ Базовый",
        "emoji":         "⚡",
        "daily_limit":   50,
        "image_limit":   10,
        "voice_limit":   20,
        "price":         3,
        "price_rub":     299,
        "history":       30,
        "desc":          "50 сообщений · 10 картинок · 20 голосовых в день · 3$/мес",
        "color":         "blue",
        "features": [
            "✅ Gemini Flash",
            "✅ 50 сообщений/день",
            "✅ 10 картинок/день",
            "✅ 20 голосовых/день",
            "✅ Приоритет обработки",
            "❌ Без памяти Pro",
        ],
    },
    "pro": {
        "name":          "🔥 Pro",
        "emoji":         "🔥",
        "daily_limit":   200,
        "image_limit":   30,
        "voice_limit":   50,
        "price":         8,
        "price_rub":     799,
        "history":       60,
        "desc":          "200 сообщений · 30 картинок · 50 голосовых · 8$/мес",
        "color":         "orange",
        "features": [
            "✅ Gemini Pro",
            "✅ 200 сообщений/день",
            "✅ 30 картинок/день",
            "✅ 50 голосовых/день",
            "✅ Высокий приоритет",
            "✅ Расширенная память (60 сообщений)",
        ],
    },
    "unlimited": {
        "name":          "👑 Безлимит",
        "emoji":         "👑",
        "daily_limit":   -1,
        "image_limit":   -1,
        "voice_limit":   -1,
        "price":         15,
        "price_rub":     1490,
        "history":       100,
        "desc":          "∞ всё безлимитное · 15$/мес",
        "color":         "gold",
        "features": [
            "✅ Gemini Pro",
            "✅ ∞ сообщений/день",
            "✅ ∞ картинок/день",
            "✅ ∞ голосовых/день",
            "✅ Максимальный приоритет",
            "✅ Максимальная память (100 сообщений)",
        ],
    },
}

# Singleton
settings = Settings()
