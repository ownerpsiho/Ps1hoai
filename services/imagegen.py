"""
🎨 Сервис генерации изображений — Together AI (FLUX)
"""

import asyncio
import base64
import logging
from typing import Optional

import aiohttp

from config.settings import settings

logger = logging.getLogger(__name__)


class ImageGenError(Exception):
    pass


class ImageGenService:
    """Генерация изображений через Together AI (FLUX.1)"""

    TOGETHER_URL = "https://api.together.xyz/v1/images/generations"

    # Подсказки для улучшения промптов
    QUALITY_SUFFIX = ", highly detailed, professional quality, 8k resolution"
    NEGATIVE_PROMPT = "blurry, low quality, distorted, ugly, bad anatomy, watermark, text, logo"

    def __init__(self):
        self.key = settings.imagegen_key
        self.model = settings.imagegen_model
        self.steps = settings.imagegen_steps
        self.width = settings.imagegen_width
        self.height = settings.imagegen_height

    async def generate(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        steps: int = 4,
        style: str = "default",
    ) -> bytes:
        """
        Генерирует изображение по текстовому описанию.
        Возвращает байты PNG.
        """
        if not self.key:
            raise ImageGenError("❌ Ключ для генерации изображений не настроен.")

        enhanced_prompt = self._enhance_prompt(prompt, style)

        payload = {
            "model": self.model,
            "prompt": enhanced_prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "n": 1,
            "response_format": "b64_json",
        }

        headers = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    self.TOGETHER_URL,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        b64_data = data["data"][0]["b64_json"]
                        return base64.b64decode(b64_data)
                    elif resp.status == 401:
                        raise ImageGenError("❌ Неверный ключ Together AI.")
                    elif resp.status == 429:
                        raise ImageGenError("⏳ Слишком много запросов. Подожди немного.")
                    else:
                        err = await resp.text()
                        logger.error(f"ImageGen error {resp.status}: {err}")
                        raise ImageGenError(f"❌ Ошибка генерации ({resp.status}).")

            except asyncio.TimeoutError:
                raise ImageGenError("⏳ Генерация заняла слишком долго. Попробуй ещё раз.")
            except aiohttp.ClientError as e:
                logger.error(f"ImageGen connection error: {e}")
                raise ImageGenError("❌ Ошибка соединения с сервером генерации.")

    def _enhance_prompt(self, prompt: str, style: str = "default") -> str:
        """Улучшает промпт для лучшего результата"""
        style_prefixes = {
            "default":     "",
            "realistic":   "photorealistic, ",
            "anime":       "anime style, manga art, ",
            "oil_paint":   "oil painting style, classical art, ",
            "watercolor":  "watercolor painting, soft colors, ",
            "cyberpunk":   "cyberpunk style, neon lights, futuristic, ",
            "pixel":       "pixel art, 8-bit style, ",
            "sketch":      "pencil sketch, hand drawn, ",
        }
        prefix = style_prefixes.get(style, "")
        return f"{prefix}{prompt}{self.QUALITY_SUFFIX}"

    @staticmethod
    def parse_size(size_str: str) -> tuple[int, int]:
        """Парсит строку размера '1024x1024' -> (1024, 1024)"""
        try:
            parts = size_str.lower().split("x")
            w = int(parts[0].strip())
            h = int(parts[1].strip())
            # Ограничиваем разумными значениями
            w = min(max(w, 256), 2048)
            h = min(max(h, 256), 2048)
            # Кратность 64
            w = (w // 64) * 64
            h = (h // 64) * 64
            return w, h
        except Exception:
            return 1024, 1024

    # Доступные стили
    STYLES = {
        "default":    "🎨 Обычный",
        "realistic":  "📸 Реалистичный",
        "anime":      "🎌 Аниме",
        "oil_paint":  "🖼 Масло",
        "watercolor": "💧 Акварель",
        "cyberpunk":  "🌃 Киберпанк",
        "pixel":      "👾 Пиксель-арт",
        "sketch":     "✏️ Набросок",
    }

    # Доступные размеры
    SIZES = {
        "square":    ("1024x1024", "⬛ Квадрат 1024×1024"),
        "portrait":  ("832x1216", "📱 Портрет 832×1216"),
        "landscape": ("1216x832", "🖥 Альбом 1216×832"),
        "wide":      ("1344x768", "🎬 Широкий 1344×768"),
        "small":     ("512x512", "🔸 Маленький 512×512"),
    }


# ── TTS Service ───────────────────────────────────────────────────────────────

class TTSService:
    """Синтез речи через gTTS (бесплатный)"""

    async def synthesize(self, text: str, lang: str = "ru") -> bytes:
        """Синтезирует речь и возвращает MP3 байты"""
        try:
            # gTTS в отдельном потоке чтобы не блокировать event loop
            loop = asyncio.get_event_loop()
            audio_bytes = await loop.run_in_executor(
                None, self._sync_synthesize, text, lang
            )
            return audio_bytes
        except Exception as e:
            logger.error(f"TTS error: {e}")
            raise ImageGenError(f"❌ Ошибка синтеза речи: {e}")

    def _sync_synthesize(self, text: str, lang: str) -> bytes:
        try:
            from gtts import gTTS
            import io
            tts = gTTS(text=text, lang=lang, slow=False)
            buf = io.BytesIO()
            tts.write_to_fp(buf)
            buf.seek(0)
            return buf.read()
        except ImportError:
            raise ImageGenError("❌ gTTS не установлен. Добавь 'gtts' в requirements.")

    async def text_to_voice_message(self, text: str, lang: str = "ru") -> bytes:
        """Конвертирует текст в голосовое сообщение (OGG для Telegram)"""
        mp3_bytes = await self.synthesize(text, lang)

        # Конвертируем MP3 → OGG через pydub если доступен
        try:
            loop = asyncio.get_event_loop()
            ogg_bytes = await loop.run_in_executor(
                None, self._mp3_to_ogg, mp3_bytes
            )
            return ogg_bytes
        except Exception:
            # Fallback — возвращаем MP3
            return mp3_bytes

    def _mp3_to_ogg(self, mp3_bytes: bytes) -> bytes:
        try:
            from pydub import AudioSegment
            import io
            audio = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
            buf = io.BytesIO()
            audio.export(buf, format="ogg", codec="libopus", parameters=["-b:a", "24k"])
            buf.seek(0)
            return buf.read()
        except Exception:
            return mp3_bytes  # Fallback


# ── Singletons ────────────────────────────────────────────────────────────────

image_service = ImageGenService()
tts_service = TTSService()
