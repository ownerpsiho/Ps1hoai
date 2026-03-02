"""
🎨 Хэндлер генерации изображений
"""

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from keyboards import main_menu, back_to_main

logger = logging.getLogger(__name__)
router = Router()


class ImageGenStates(StatesGroup):
    waiting_prompt = State()
    waiting_prompt_edit = State()


UNAVAILABLE_TEXT = (
    "🎨 <b>Генерация изображений</b>\n\n"
    "⚙️ Функция временно недоступна — ведутся технические работы.\n\n"
    "Следи за обновлениями в канале "
    "<a href='https://t.me/psihoaioff'>@psihoaioff</a> 🔔"
)


@router.callback_query(F.data == "gen_image_start")
async def cb_gen_image_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        UNAVAILABLE_TEXT,
        parse_mode="HTML",
        reply_markup=back_to_main(),
    )


@router.callback_query(F.data.startswith("img_style:"))
async def cb_image_style(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        UNAVAILABLE_TEXT,
        parse_mode="HTML",
        reply_markup=back_to_main(),
    )


@router.callback_query(F.data == "img_regenerate")
async def cb_regenerate(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.answer(
        UNAVAILABLE_TEXT,
        parse_mode="HTML",
        reply_markup=back_to_main(),
    )


@router.callback_query(F.data == "img_edit_prompt")
async def cb_edit_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.answer(
        UNAVAILABLE_TEXT,
        parse_mode="HTML",
        reply_markup=back_to_main(),
    )


@router.message(ImageGenStates.waiting_prompt)
async def handle_image_prompt(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        UNAVAILABLE_TEXT,
        parse_mode="HTML",
        reply_markup=back_to_main(),
    )


@router.message(ImageGenStates.waiting_prompt_edit)
async def handle_image_prompt_edit(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        UNAVAILABLE_TEXT,
        parse_mode="HTML",
        reply_markup=back_to_main(),
    )
