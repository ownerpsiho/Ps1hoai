# handlers/__init__.py
from aiogram import Router

from .commands import router as commands_router
from .chat import router as chat_router
from .callbacks import router as callbacks_router
from .image import router as image_router
from .admin import router as admin_router


def setup_routers() -> Router:
    """Создаёт главный роутер и подключает все под-роутеры"""
    main_router = Router()

    # Порядок важен! Более специфичные раньше
    main_router.include_router(commands_router)   # /команды
    main_router.include_router(image_router)      # генерация изображений (FSM)
    main_router.include_router(admin_router)      # админ (FSM)
    main_router.include_router(callbacks_router)  # callback кнопки
    main_router.include_router(chat_router)       # чат (должен быть последним!)

    return main_router


__all__ = ["setup_routers"]
