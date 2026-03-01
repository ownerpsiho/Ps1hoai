"""
🤖 Сервис AI — поддержка Groq (Llama) и Google Gemini
"""

import asyncio
import logging
import base64
from typing import Optional

import aiohttp

from config.settings import settings

logger = logging.getLogger(__name__)


class GeminiError(Exception):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


class GeminiRateLimitError(GeminiError):
    pass


class GeminiAuthError(GeminiError):
    pass


class GeminiService:
    """
    Универсальный AI сервис — автоматически выбирает провайдера:
    - Если задан GROQ_KEY → использует Groq (Llama 3.3 70B)
    - Если задан GEMINI_KEY → использует Google Gemini
    """

    GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
    GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self):
        self.groq_key    = getattr(settings, 'groq_key', '') or ''
        self.gemini_key  = settings.gemini_key
        self.model       = settings.gemini_model
        self.max_tokens  = settings.gemini_max_tokens
        self.temperature = settings.gemini_temperature
        self.timeout     = settings.gemini_timeout

        # Автовыбор провайдера
        if self.groq_key:
            self.provider = "groq"
            logger.info("🤖 AI провайдер: Groq (Llama)")
        else:
            self.provider = "gemini"
            logger.info("🤖 AI провайдер: Google Gemini")

    async def chat(
        self,
        history: list[dict],
        user_message: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> tuple[str, int, int]:
        if self.provider == "groq":
            return await self._groq_chat(history, user_message, system_prompt, temperature)
        else:
            return await self._gemini_chat(history, user_message, system_prompt, temperature)

    # ── Groq ──────────────────────────────────────────────────────────────────

    async def _groq_chat(
        self,
        history: list[dict],
        user_message: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> tuple[str, int, int]:
        """Запрос к Groq API (OpenAI-совместимый)"""

        # Конвертируем историю из формата Gemini в формат OpenAI
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        for msg in history:
            if msg.get("role") == "user":
                parts = msg.get("parts", [])
                content = parts[0].get("text", "") if parts else ""
                messages.append({"role": "user", "content": content})
            elif msg.get("role") == "model":
                parts = msg.get("parts", [])
                content = parts[0].get("text", "") if parts else ""
                messages.append({"role": "assistant", "content": content})

        messages.append({"role": "user", "content": user_message})

        # Выбираем модель Groq
        groq_model = getattr(settings, 'groq_model', 'llama-3.3-70b-versatile')

        payload = {
            "model": groq_model,
            "messages": messages,
            "max_tokens": min(self.max_tokens, 8000),
            "temperature": temperature or self.temperature,
        }

        headers = {
            "Authorization": f"Bearer {self.groq_key}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    self.GROQ_URL,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        answer = data["choices"][0]["message"]["content"]
                        usage = data.get("usage", {})
                        prompt_tokens   = usage.get("prompt_tokens", 0)
                        response_tokens = usage.get("completion_tokens", 0)
                        return answer, prompt_tokens, response_tokens
                    elif resp.status == 429:
                        raise GeminiRateLimitError("⏳ Слишком много запросов. Подожди немного.")
                    elif resp.status in (401, 403):
                        raise GeminiAuthError("❌ Неверный ключ Groq. Проверь GROQ_KEY.")
                    else:
                        err = await resp.text()
                        logger.error(f"Groq error {resp.status}: {err}")
                        raise GeminiError(f"❌ Ошибка Groq API ({resp.status}).")
            except asyncio.TimeoutError:
                raise GeminiError("⏳ Groq думает слишком долго. Попробуй ещё раз.")
            except aiohttp.ClientError as e:
                logger.error(f"Groq connection error: {e}")
                raise GeminiError("❌ Ошибка соединения с Groq.")

    # ── Gemini ────────────────────────────────────────────────────────────────

    async def _gemini_chat(
        self,
        history: list[dict],
        user_message: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> tuple[str, int, int]:
        contents = list(history)
        contents.append({"role": "user", "parts": [{"text": user_message}]})

        payload = self._build_gemini_payload(contents, system_prompt, temperature)
        url = f"{self.GEMINI_URL}/{self.model}:generateContent?key={self.gemini_key}"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    return await self._parse_gemini_response(resp)
            except asyncio.TimeoutError:
                raise GeminiError("⏳ Gemini думает слишком долго. Попробуй ещё раз.")
            except aiohttp.ClientError as e:
                raise GeminiError("❌ Ошибка соединения с Gemini.")

    def _build_gemini_payload(
        self,
        contents: list[dict],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> dict:
        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": self.max_tokens,
                "temperature": temperature or self.temperature,
            },
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            ],
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        return payload

    async def _parse_gemini_response(self, resp) -> tuple[str, int, int]:
        if resp.status == 200:
            data = await resp.json()
            try:
                candidate = data["candidates"][0]
                if candidate.get("finishReason") == "SAFETY":
                    return "⚠️ Ответ заблокирован системой безопасности.", 0, 0
                answer = candidate["content"]["parts"][0]["text"]
                usage  = data.get("usageMetadata", {})
                return answer, usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0)
            except (KeyError, IndexError) as e:
                logger.error(f"Gemini parse error: {e}, data: {data}")
                raise GeminiError("❌ Не удалось распарсить ответ Gemini.")
        elif resp.status == 429:
            raise GeminiRateLimitError("⏳ Слишком много запросов к Gemini. Подожди немного.")
        elif resp.status in (401, 403):
            raise GeminiAuthError("❌ Ошибка авторизации Gemini.")
        else:
            err = await resp.text()
            logger.error(f"Gemini {resp.status}: {err}")
            raise GeminiError(f"❌ Ошибка Gemini API ({resp.status}). Попробуй позже.")

    # ── Vision (только Gemini) ────────────────────────────────────────────────

    async def chat_with_image(
        self,
        user_message: str,
        image_data: bytes,
        image_mime: str = "image/jpeg",
        system_prompt: Optional[str] = None,
    ) -> tuple[str, int, int]:
        """Анализирует изображение — только через Gemini Vision"""
        if not self.gemini_key:
            return "❌ Анализ изображений требует GEMINI_KEY.", 0, 0

        image_b64 = base64.b64encode(image_data).decode("utf-8")
        contents = [{
            "role": "user",
            "parts": [
                {"inline_data": {"mime_type": image_mime, "data": image_b64}},
                {"text": user_message or "Что на этом изображении? Опиши подробно."},
            ]
        }]
        payload = self._build_gemini_payload(contents, system_prompt)
        vision_model = getattr(settings, 'gemini_vision_model', 'gemini-2.0-flash')
        url = f"{self.GEMINI_URL}/{vision_model}:generateContent?key={self.gemini_key}"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url, json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    return await self._parse_gemini_response(resp)
            except asyncio.TimeoutError:
                raise GeminiError("⏳ Анализ изображения занял слишком много времени.")

    async def analyze_document(
        self,
        user_message: str,
        document_data: bytes,
        mime_type: str,
        system_prompt: Optional[str] = None,
    ) -> tuple[str, int, int]:
        """Анализирует документ — только через Gemini"""
        if not self.gemini_key:
            return "❌ Анализ документов требует GEMINI_KEY.", 0, 0

        doc_b64 = base64.b64encode(document_data).decode("utf-8")
        contents = [{
            "role": "user",
            "parts": [
                {"inline_data": {"mime_type": mime_type, "data": doc_b64}},
                {"text": user_message or "Проанализируй этот документ и сделай краткое резюме."},
            ]
        }]
        payload = self._build_gemini_payload(contents, system_prompt)
        vision_model = getattr(settings, 'gemini_vision_model', 'gemini-2.0-flash')
        url = f"{self.GEMINI_URL}/{vision_model}:generateContent?key={self.gemini_key}"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url, json=payload,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    return await self._parse_gemini_response(resp)
            except asyncio.TimeoutError:
                raise GeminiError("⏳ Анализ документа занял слишком много времени.")

    async def transcribe_audio(self, audio_data: bytes, mime_type: str = "audio/ogg") -> str:
        """Транскрибирует аудио — только через Gemini"""
        if not self.gemini_key:
            raise GeminiError("❌ Транскрибация требует GEMINI_KEY.")

        audio_b64 = base64.b64encode(audio_data).decode("utf-8")
        contents = [{
            "role": "user",
            "parts": [
                {"inline_data": {"mime_type": mime_type, "data": audio_b64}},
                {"text": "Транскрибируй это аудио дословно. Верни только текст без комментариев."},
            ]
        }]
        payload = self._build_gemini_payload(
            contents,
            system_prompt="Ты — транскрибатор. Переводи речь в текст дословно.",
            temperature=0.0,
        )
        vision_model = getattr(settings, 'gemini_vision_model', 'gemini-2.0-flash')
        url = f"{self.GEMINI_URL}/{vision_model}:generateContent?key={self.gemini_key}"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url, json=payload,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    text, _, _ = await self._parse_gemini_response(resp)
                    return text
            except Exception as e:
                logger.error(f"Transcription error: {e}")
                raise GeminiError("❌ Не удалось распознать речь.")


# ── Singleton ─────────────────────────────────────────────────────────────────

gemini_service = GeminiService()
