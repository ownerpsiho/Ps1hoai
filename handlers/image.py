"""
🎨 Хэндлер генерации изображений
"""

import logging
from io import BytesIO

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config.settings import settings
from database import get_session, UserRepo
from services import image_service, ImageGenError
from keyboards import (
    image_style_keyboard, image_result_keyboard,
    upgrade_keyboard, main_menu
)
from utils import escape_html

logger = logging.getLogger(__name__)
router = Router()


class ImageGenStates(StatesGroup):
    waiting_prompt = State()
    waiting_prompt_edit = State()


# ── Вспомогательные ───────────────────────────────────────────────────────────

async def process_image_generation(
    message: Message,
    user,
    prompt: str,
    style: str = "default",
    size: str = "square",
) -> None:
    """Генерирует и отправляет изображение"""
    async with get_session() as session:
        fresh_user = await UserRepo.get(session, user.id)
        if not fresh_user:
            return

        can, reason = await UserRepo.can_generate_image(fresh_user)
        if not can:
            await message.answer(reason, parse_mode="HTML", reply_markup=upgrade_keyboard())
            return

        status_msg = await message.answer(
            f"🎨 <b>Генерирую изображение...</b>\n\n"
            f"📝 Запрос: <i>{escape_html(prompt[:100])}</i>\n"
            f"🖌 Стиль: {style}\n"
            f"⏳ Обычно занимает 10-30 секунд...",
            parse_mode="HTML",
        )

        try:
            from services.imagegen import ImageGenService
            width, height = ImageGenService.parse_size(
                ImageGenService.SIZES.get(size, ("1024x1024", ""))[0]
            )

            image_bytes = await image_service.generate(
                prompt=prompt,
                width=width,
                height=height,
                style=style,
            )

            await UserRepo.use_image(session, fresh_user)
            await session.commit()

            await status_msg.delete()

            photo = BufferedInputFile(image_bytes, filename="generated.png")
            await message.answer_photo(
                photo=photo,
                caption=(
                    f"🎨 <b>Готово!</b>\n\n"
                    f"📝 {escape_html(prompt[:200])}\n"
                    f"🖌 Стиль: {style} · 📐 {width}×{height}"
                ),
                parse_mode="HTML",
                reply_markup=image_result_keyboard(prompt),
            )

        except ImageGenError as e:
            await status_msg.edit_text(
                f"{str(e)}\n\n"
                f"Попробуй изменить описание или обратись к {settings.owner_username}",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.exception(f"Image generation error: {e}")
            await status_msg.edit_text(
                "❌ Произошла ошибка при генерации. Попробуй ещё раз.",
            )


# ── Callback: начало генерации ────────────────────────────────────────────────

@router.callback_query(F.data == "gen_image_start")
async def cb_gen_image_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(ImageGenStates.waiting_prompt)
    await state.update_data(style="default", size="square")
    await callback.message.edit_text(
        "🎨 <b>Генерация изображений</b>\n\n"
        "Выбери стиль или сразу опиши что хочешь нарисовать:",
        parse_mode="HTML",
        reply_markup=image_style_keyboard(),
    )


# ── Callback: выбор стиля ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("img_style:"))
async def cb_image_style(callback: CallbackQuery, state: FSMContext):
    style = callback.data.split(":")[1]
    await state.update_data(style=style)
    current = await state.get_data()
    await callback.answer(f"Стиль: {style}")
    await callback.message.edit_text(
        f"🎨 Стиль выбран: <b>{style}</b>\n\n"
        f"✍️ <b>Опиши что нарисовать:</b>",
        parse_mode="HTML",
    )
    await state.set_state(ImageGenStates.waiting_prompt)


# ── Callback: повторная генерация ─────────────────────────────────────────────

@router.callback_query(F.data == "img_regenerate")
async def cb_regenerate(callback: CallbackQuery, state: FSMContext, user):
    data = await state.get_data()
    prompt = data.get("last_prompt", "")
    style = data.get("style", "default")
    size = data.get("size", "square")

    if not prompt:
        await callback.answer("❌ Нет предыдущего запроса", show_alert=True)
        return

    await callback.answer("🔄 Регенерирую...")
    await process_image_generation(callback.message, user, prompt, style, size)


# ── Callback: изменить промпт ─────────────────────────────────────────────────

@router.callback_query(F.data == "img_edit_prompt")
async def cb_edit_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(ImageGenStates.waiting_prompt_edit)
    await callback.message.answer(
        "✏️ Напиши новое описание для картинки:"
    )


# ── Message: получение промпта ────────────────────────────────────────────────

@router.message(ImageGenStates.waiting_prompt)
async def handle_image_prompt(message: Message, state: FSMContext, user):
    data = await state.get_data()
    style = data.get("style", "default")
    size = data.get("size", "square")
    prompt = message.text.strip()

    if not prompt:
        await message.answer("❌ Напиши описание картинки:")
        return

    await state.update_data(last_prompt=prompt)
    await state.clear()

    await process_image_generation(message, user, prompt, style, size)


@router.message(ImageGenStates.waiting_prompt_edit)
async def handle_image_prompt_edit(message: Message, state: FSMContext, user):
    data = await state.get_data()
    style = data.get("style", "default")
    size = data.get("size", "square")
    prompt = message.text.strip()

    if not prompt:
        await message.answer("❌ Опиши что нарисовать:")
        return

    await state.update_data(last_prompt=prompt)
    await state.clear()

    await process_image_generation(message, user, prompt, style, size)
