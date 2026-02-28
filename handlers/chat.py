"""
💬 Главный обработчик сообщений — AI чат
"""

import asyncio
import logging
import time
from typing import Optional

from aiogram import Bot, Router, F
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from config.settings import settings, PLANS
from database import get_session, UserRepo, MessageRepo, PromptRepo
from database.models import MessageTypeEnum
from services import gemini_service, GeminiError, GeminiRateLimitError
from keyboards import main_menu, upgrade_keyboard, limit_warning_keyboard
from utils import markdown_to_html, split_long_message, format_limit_bar

logger = logging.getLogger(__name__)
router = Router()


async def _keep_typing(bot: Bot, chat_id: int, interval: float = 3.0):
    """Отправляет 'печатает...' каждые N секунд"""
    while True:
        await asyncio.sleep(interval)
        try:
            await bot.send_chat_action(chat_id, "typing")
        except Exception:
            break


async def process_ai_message(
    message: Message,
    user,
    text: str,
    session,
) -> None:
    """Обрабатывает текстовое сообщение через Gemini"""

    # Проверяем лимит
    can, reason = await UserRepo.can_send_message(user)
    if not can:
        await message.answer(
            reason,
            parse_mode="HTML",
            reply_markup=upgrade_keyboard(),
        )
        return

    # Предупреждение о низком остатке
    plan = PLANS[user.plan.value]
    if plan["daily_limit"] != -1 and user.id not in settings.admin_ids:
        remaining = plan["daily_limit"] - user.today_messages
        if 0 < remaining <= 3:
            await message.answer(
                f"⚠️ Осталось запросов: <b>{remaining}</b>\n🔄 Сброс в 00:00",
                parse_mode="HTML",
                reply_markup=limit_warning_keyboard(remaining),
            )

    # Увеличиваем счётчик
    await UserRepo.use_message(session, user)
    await session.commit()

    # Начинаем показывать "печатает..."
    await message.bot.send_chat_action(message.chat.id, "typing")
    typing_task = asyncio.create_task(
        _keep_typing(message.bot, message.chat.id, settings.typing_interval)
    )

    start_ts = time.monotonic()

    try:
        # Получаем историю из БД
        history_limit = PLANS[user.plan.value]["history"]
        history = await MessageRepo.get_history_for_gemini(session, user.id, history_limit)

        # Получаем системный промпт
        prompt_obj = await PromptRepo.get_for_user(session, user)
        system_prompt = prompt_obj.prompt if prompt_obj else None

        # Запрос к Gemini
        answer, prompt_tokens, response_tokens = await gemini_service.chat(
            history=history,
            user_message=text,
            system_prompt=system_prompt,
        )

        latency_ms = int((time.monotonic() - start_ts) * 1000)

        # Сохраняем в историю
        await MessageRepo.add(session, user.id, "user", text,
                              MessageTypeEnum.text, prompt_tokens, settings.gemini_model)
        await MessageRepo.add(session, user.id, "assistant", answer,
                              MessageTypeEnum.text, response_tokens, settings.gemini_model,
                              latency_ms)
        await session.commit()

        # Форматируем и отправляем
        formatted = markdown_to_html(answer)
        chunks = split_long_message(formatted, 4096)

        for i, chunk in enumerate(chunks):
            try:
                await message.answer(
                    chunk,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            except Exception:
                # Если HTML невалиден — шлём без форматирования
                await message.answer(
                    split_long_message(answer)[i],
                    disable_web_page_preview=True,
                )
            if i < len(chunks) - 1:
                await asyncio.sleep(0.3)

    except GeminiRateLimitError:
        await message.answer(
            "⏳ <b>Слишком много запросов к Gemini.</b>\n"
            "Подожди немного и попробуй ещё раз.",
            parse_mode="HTML",
        )
    except GeminiError as e:
        await message.answer(str(e), parse_mode="HTML")
    except Exception as e:
        logger.exception(f"Unexpected error in process_ai_message: {e}")
        await message.answer(
            "❌ Произошла непредвиденная ошибка. Попробуй ещё раз.",
        )
    finally:
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass


# ── Хэндлер обычных текстовых сообщений ──────────────────────────────────────

@router.message(F.text & ~F.text.startswith("/"))
async def handle_text_message(message: Message, user, db, state: FSMContext):
    """Главный хэндлер — обрабатывает все обычные сообщения как запросы к AI"""
    # Проверяем нет ли активного FSM состояния
    current_state = await state.get_state()
    if current_state is not None:
        return  # Передаём управление конкретному хэндлеру

    text = message.text.strip()
    if not text:
        return

    async with get_session() as session:
        # Обновляем данные пользователя из актуальной сессии
        from database.repository import UserRepo as UR
        fresh_user = await UR.get(session, user.id)
        if fresh_user:
            await process_ai_message(message, fresh_user, text, session)


# ── Хэндлер голосовых сообщений ───────────────────────────────────────────────

@router.message(F.voice)
async def handle_voice_message(message: Message, user, db):
    """Транскрибирует голосовое сообщение и отправляет в AI"""
    from services import GeminiError

    async with get_session() as session:
        fresh_user = await UserRepo.get(session, user.id)
        if not fresh_user:
            return

        # Проверяем лимит голосовых
        can, reason = await UserRepo.can_use_voice(fresh_user)
        if not can:
            await message.answer(reason, parse_mode="HTML", reply_markup=upgrade_keyboard())
            return

        await message.bot.send_chat_action(message.chat.id, "typing")
        status_msg = await message.answer("🎙 Распознаю речь...")

        try:
            # Скачиваем аудио
            voice = message.voice
            file = await message.bot.get_file(voice.file_id)
            file_data = await message.bot.download_file(file.file_path)
            audio_bytes = file_data.read()

            # Транскрибируем через Gemini
            transcribed = await gemini_service.transcribe_audio(audio_bytes, "audio/ogg")

            await UserRepo.use_voice(session, fresh_user)
            await session.commit()

            await status_msg.edit_text(
                f"🎙 <b>Распознано:</b> {transcribed}",
                parse_mode="HTML",
            )

            # Отправляем в AI как обычный текст
            await process_ai_message(message, fresh_user, transcribed, session)

        except GeminiError as e:
            await status_msg.edit_text(str(e), parse_mode="HTML")
        except Exception as e:
            logger.exception(f"Voice processing error: {e}")
            await status_msg.edit_text("❌ Не удалось обработать голосовое сообщение.")


# ── Хэндлер фото / изображений ───────────────────────────────────────────────

@router.message(F.photo)
async def handle_photo_message(message: Message, user, db):
    """Анализирует фото через Gemini Vision"""
    async with get_session() as session:
        fresh_user = await UserRepo.get(session, user.id)
        if not fresh_user:
            return

        can, reason = await UserRepo.can_send_message(fresh_user)
        if not can:
            await message.answer(reason, parse_mode="HTML", reply_markup=upgrade_keyboard())
            return

        await message.bot.send_chat_action(message.chat.id, "typing")
        status_msg = await message.answer("🔍 Анализирую изображение...")

        try:
            # Берём самое большое фото
            photo = message.photo[-1]
            file = await message.bot.get_file(photo.file_id)
            file_data = await message.bot.download_file(file.file_path)
            image_bytes = file_data.read()

            caption = message.caption or "Что изображено на этом фото? Опиши подробно."

            # Получаем системный промпт
            prompt_obj = await PromptRepo.get_for_user(session, fresh_user)
            system_prompt = prompt_obj.prompt if prompt_obj else None

            answer, pt, rt = await gemini_service.chat_with_image(
                user_message=caption,
                image_data=image_bytes,
                image_mime="image/jpeg",
                system_prompt=system_prompt,
            )

            await UserRepo.use_message(session, fresh_user)
            await MessageRepo.add(session, fresh_user.id, "user",
                                  f"[Фото] {caption}", MessageTypeEnum.image, pt)
            await MessageRepo.add(session, fresh_user.id, "assistant",
                                  answer, MessageTypeEnum.image, rt)
            await session.commit()

            await status_msg.delete()

            formatted = markdown_to_html(answer)
            chunks = split_long_message(formatted, 4096)
            for chunk in chunks:
                try:
                    await message.answer(chunk, parse_mode="HTML", disable_web_page_preview=True)
                except Exception:
                    await message.answer(answer[:4096])

        except GeminiError as e:
            await status_msg.edit_text(str(e), parse_mode="HTML")
        except Exception as e:
            logger.exception(f"Photo processing error: {e}")
            await status_msg.edit_text("❌ Не удалось проанализировать изображение.")


# ── Хэндлер документов ────────────────────────────────────────────────────────

@router.message(F.document)
async def handle_document(message: Message, user, db):
    """Анализирует PDF/текстовые документы"""
    doc = message.document
    SUPPORTED_MIMES = {
        "application/pdf": "application/pdf",
        "text/plain": "text/plain",
        "text/html": "text/html",
        "text/csv": "text/csv",
        "text/xml": "text/xml",
        "application/json": "application/json",
    }

    if doc.mime_type not in SUPPORTED_MIMES:
        await message.answer(
            f"❌ Формат не поддерживается.\n\n"
            f"Поддерживаемые: PDF, TXT, HTML, CSV, JSON\n"
            f"Твой файл: {doc.mime_type or 'неизвестный формат'}"
        )
        return

    async with get_session() as session:
        fresh_user = await UserRepo.get(session, user.id)
        if not fresh_user:
            return

        can, reason = await UserRepo.can_send_message(fresh_user)
        if not can:
            await message.answer(reason, parse_mode="HTML", reply_markup=upgrade_keyboard())
            return

        # Ограничение размера файла — 10 МБ
        if doc.file_size and doc.file_size > 10 * 1024 * 1024:
            await message.answer("❌ Файл слишком большой. Максимум 10 МБ.")
            return

        await message.bot.send_chat_action(message.chat.id, "typing")
        status_msg = await message.answer(f"📄 Читаю документ <b>{doc.file_name}</b>...", parse_mode="HTML")

        try:
            file = await message.bot.get_file(doc.file_id)
            file_data = await message.bot.download_file(file.file_path)
            doc_bytes = file_data.read()

            caption = message.caption or "Проанализируй этот документ. Сделай подробное резюме."

            prompt_obj = await PromptRepo.get_for_user(session, fresh_user)
            system_prompt = prompt_obj.prompt if prompt_obj else None

            answer, pt, rt = await gemini_service.analyze_document(
                user_message=caption,
                document_data=doc_bytes,
                mime_type=doc.mime_type,
                system_prompt=system_prompt,
            )

            await UserRepo.use_message(session, fresh_user)
            await MessageRepo.add(session, fresh_user.id, "user",
                                  f"[Документ: {doc.file_name}] {caption}",
                                  MessageTypeEnum.file, pt)
            await MessageRepo.add(session, fresh_user.id, "assistant",
                                  answer, MessageTypeEnum.file, rt)
            await session.commit()

            await status_msg.delete()
            formatted = markdown_to_html(answer)
            chunks = split_long_message(formatted, 4096)
            for chunk in chunks:
                try:
                    await message.answer(chunk, parse_mode="HTML", disable_web_page_preview=True)
                except Exception:
                    await message.answer(answer[:4096])

        except GeminiError as e:
            await status_msg.edit_text(str(e), parse_mode="HTML")
        except Exception as e:
            logger.exception(f"Document processing error: {e}")
            await status_msg.edit_text("❌ Не удалось обработать документ.")
