"""
🤖 Сервис Gemini AI — чат, анализ изображений, потоковые ответы
"""

import asyncio
import logging
import time
from typing import Optional, AsyncGenerator

import aiohttp

from config.settings import settings

logger = logging.getLogger(__name__)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiError(Exception):
    """Базовый класс ошибок Gemini"""
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


class GeminiRateLimitError(GeminiError):
    pass


class GeminiAuthError(GeminiError):
    pass


class GeminiService:
    """Сервис для работы с Google Gemini API"""

    def __init__(self):
        self.key = settings.gemini_key
        self.model = settings.gemini_model
        self.vision_model = settings.gemini_vision_model
        self.max_tokens = settings.gemini_max_tokens
        self.temperature = settings.gemini_temperature
        self.timeout = settings.gemini_timeout

    def _build_url(self, model: str, method: str = "generateContent") -> str:
        return f"{GEMINI_BASE}/{model}:{method}?key={self.key}"

    def _build_payload(
        self,
        contents: list[dict],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> dict:
        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens or self.max_tokens,
                "temperature": temperature or self.temperature,
                "topP": 0.95,
                "topK": 40,
            },
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            ],
        }
        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }
        return payload

    async def chat(
        self,
        history: list[dict],
        user_message: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> tuple[str, int, int]:
        """
        Отправляет сообщение и получает ответ.
        Возвращает (ответ, токены_запроса, токены_ответа)
        """
        contents = list(history)
        contents.append({"role": "user", "parts": [{"text": user_message}]})

        payload = self._build_payload(contents, system_prompt, temperature)

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    self._build_url(self.model),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    return await self._parse_response(resp)
            except asyncio.TimeoutError:
                raise GeminiError("⏳ Gemini думает слишком долго. Попробуй ещё раз.")
            except aiohttp.ClientError as e:
                logger.error(f"Gemini connection error: {e}")
                raise GeminiError("❌ Ошибка соединения с Gemini. Попробуй позже.")

    async def chat_with_image(
        self,
        user_message: str,
        image_data: bytes,
        image_mime: str = "image/jpeg",
        system_prompt: Optional[str] = None,
    ) -> tuple[str, int, int]:
        """Анализирует изображение вместе с текстовым вопросом"""
        import base64
        image_b64 = base64.b64encode(image_data).decode("utf-8")

        contents = [{
            "role": "user",
            "parts": [
                {
                    "inline_data": {
                        "mime_type": image_mime,
                        "data": image_b64,
                    }
                },
                {"text": user_message or "Что на этом изображении? Опиши подробно."},
            ]
        }]

        payload = self._build_payload(contents, system_prompt)

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    self._build_url(self.vision_model),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    return await self._parse_response(resp)
            except asyncio.TimeoutError:
                raise GeminiError("⏳ Анализ изображения занял слишком много времени.")
            except aiohttp.ClientError as e:
                logger.error(f"Gemini vision error: {e}")
                raise GeminiError("❌ Ошибка при анализе изображения.")

    async def analyze_document(
        self,
        user_message: str,
        document_data: bytes,
        mime_type: str,
        system_prompt: Optional[str] = None,
    ) -> tuple[str, int, int]:
        """Анализирует документ (PDF, текст)"""
        import base64
        doc_b64 = base64.b64encode(document_data).decode("utf-8")

        contents = [{
            "role": "user",
            "parts": [
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": doc_b64,
                    }
                },
                {"text": user_message or "Проанализируй этот документ и сделай краткое резюме."},
            ]
        }]

        payload = self._build_payload(contents, system_prompt)

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    self._build_url(self.vision_model),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120),  # документы могут быть большими
                ) as resp:
                    return await self._parse_response(resp)
            except asyncio.TimeoutError:
                raise GeminiError("⏳ Анализ документа занял слишком много времени.")

    async def _parse_response(self, resp) -> tuple[str, int, int]:
        """Парсит ответ Gemini API"""
        if resp.status == 200:
            data = await resp.json()
            try:
                candidate = data["candidates"][0]

                # Проверяем finish reason
                finish_reason = candidate.get("finishReason", "STOP")
                if finish_reason == "SAFETY":
                    return "⚠️ Ответ заблокирован системой безопасности. Попробуй перефразировать запрос.", 0, 0

                answer = candidate["content"]["parts"][0]["text"]
                usage = data.get("usageMetadata", {})
                prompt_tokens = usage.get("promptTokenCount", 0)
                response_tokens = usage.get("candidatesTokenCount", 0)
                return answer, prompt_tokens, response_tokens

            except (KeyError, IndexError) as e:
                logger.error(f"Gemini parse error: {e}, data: {data}")
                # Проверяем на ошибку safety
                if "promptFeedback" in data:
                    feedback = data["promptFeedback"]
                    if feedback.get("blockReason"):
                        return f"⚠️ Запрос заблокирован: {feedback['blockReason']}", 0, 0
                raise GeminiError("❌ Не удалось распарсить ответ Gemini.")

        elif resp.status == 400:
            err = await resp.text()
            logger.error(f"Gemini 400: {err}")
            raise GeminiError("❌ Некорректный запрос к Gemini.", 400)
        elif resp.status in (401, 403):
            raise GeminiAuthError("❌ Ошибка авторизации Gemini. Проверь API ключ.", resp.status)
        elif resp.status == 429:
            raise GeminiRateLimitError("⏳ Слишком много запросов к Gemini. Подожди немного.", 429)
        elif resp.status == 503:
            raise GeminiError("🔧 Gemini временно недоступен. Попробуй через минуту.", 503)
        else:
            err = await resp.text()
            logger.error(f"Gemini {resp.status}: {err}")
            raise GeminiError(f"❌ Ошибка Gemini API ({resp.status}). Попробуй позже.", resp.status)

    async def transcribe_audio(self, audio_data: bytes, mime_type: str = "audio/ogg") -> str:
        """Транскрибирует аудио через Gemini"""
        import base64
        audio_b64 = base64.b64encode(audio_data).decode("utf-8")

        contents = [{
            "role": "user",
            "parts": [
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": audio_b64,
                    }
                },
                {"text": "Транскрибируй это аудио дословно. Верни только текст без комментариев."},
            ]
        }]

        payload = self._build_payload(
            contents,
            system_prompt="Ты — транскрибатор. Переводи речь в текст дословно.",
            max_tokens=2048,
        )

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    self._build_url(self.vision_model),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    text, _, _ = await self._parse_response(resp)
                    return text
            except Exception as e:
                logger.error(f"Transcription error: {e}")
                raise GeminiError("❌ Не удалось распознать речь.")

    async def generate_tts_via_gemini(self, text: str) -> Optional[bytes]:
        """
        Синтез речи — заглушка, используем gTTS
        В реальном боте здесь Google Cloud TTS или ElevenLabs
        """
        return None


# ── Singleton ─────────────────────────────────────────────────────────────────

gemini_service = GeminiService()
