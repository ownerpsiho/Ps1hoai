"""
╔══════════════════════════════════════════════════════════════════════╗
║              🤖 GEMINI AI BOT — Production Ready                    ║
╠══════════════════════════════════════════════════════════════════════╣
║  Стек:                                                               ║
║    • aiogram 3.x — Telegram Bot framework                           ║
║    • SQLAlchemy 2.0 async + asyncpg — PostgreSQL                    ║
║    • Google Gemini API — AI чат, vision, STT                        ║
║    • Together AI / FLUX — генерация изображений                     ║
║    • gTTS — синтез речи                                             ║
╠══════════════════════════════════════════════════════════════════════╣
║  Переменные окружения:                                               ║
║    BOT_TOKEN       — токен @BotFather                               ║
║    GEMINI_KEY      — Google AI Studio API key                       ║
║    DATABASE_URL    — postgresql+asyncpg://user:pass@host/db         ║
║    ADMIN_IDS       — ID админов через запятую                       ║
║    IMAGEGEN_KEY    — Together AI API key (для генерации картинок)   ║
║    OWNER_USERNAME  — @username владельца                            ║
║    CHANNEL_LINK    — ссылка на Telegram канал                       ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config.settings import settings
from database import init_db, check_db, close_db
from handlers import setup_routers
from middlewares import (
    UserMiddleware,
    RateLimitMiddleware,
    LoggingMiddleware,
    BanCheckMiddleware,
)

# ── Логирование ───────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("aiogram").setLevel(logging.WARNING)


# ── Startup / Shutdown ────────────────────────────────────────────────────────

async def on_startup(bot: Bot) -> None:
    logger.info("🚀 Запуск бота...")

    errors = settings.validate()
    if errors:
        for err in errors:
            logger.error(err)
        sys.exit(1)

    logger.info("🗄️ Проверяем подключение к PostgreSQL...")
    if not await check_db():
        logger.error("❌ Не удалось подключиться к базе данных!")
        sys.exit(1)

    logger.info("📦 Инициализируем базу данных (создаём таблицы)...")
    await init_db()
    logger.info("✅ Таблицы созданы!")

    me = await bot.get_me()
    logger.info(f"✅ Бот @{me.username} ({me.id}) запущен!")
    logger.info(f"🧠 Модель Gemini: {settings.gemini_model}")
    logger.info(f"👑 Админов: {len(settings.admin_ids)}")

    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(
                admin_id,
                f"✅ <b>Бот запущен!</b>\n\n"
                f"🤖 @{me.username}\n"
                f"🧠 Модель: <code>{settings.gemini_model}</code>\n"
                f"🗄️ БД: подключена",
                parse_mode="HTML",
            )
        except Exception:
            pass


async def on_shutdown(bot: Bot) -> None:
    logger.info("⏹ Остановка бота...")
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, "⏹ <b>Бот остановлен</b>", parse_mode="HTML")
        except Exception:
            pass
    await close_db()
    logger.info("👋 Бот остановлен")


# ── Главная функция ───────────────────────────────────────────────────────────

async def main() -> None:
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage())

    # Lifecycle hooks — передаём bot напрямую
    async def _startup():
        await on_startup(bot)

    async def _shutdown():
        await on_shutdown(bot)

    dp.startup.register(_startup)
    dp.shutdown.register(_shutdown)

    # ── Middleware ──────────────────────────────────────────────────────────
    dp.message.middleware(LoggingMiddleware())
    dp.callback_query.middleware(LoggingMiddleware())

    dp.message.middleware(UserMiddleware())
    dp.callback_query.middleware(UserMiddleware())

    dp.message.middleware(BanCheckMiddleware())
    dp.callback_query.middleware(BanCheckMiddleware())

    dp.message.middleware(RateLimitMiddleware())

    # ── Роутеры ─────────────────────────────────────────────────────────────
    main_router = setup_routers()
    dp.include_router(main_router)

    # ── Запуск polling ───────────────────────────────────────────────────────
    logger.info("🔄 Запускаем polling...")
    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "inline_query"],
            drop_pending_updates=True,
        )
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Остановлено пользователем (Ctrl+C)")
