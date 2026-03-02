"""
🎨 Сервис генерации изображений — Hugging Face (FLUX)
"""

import asyncio
import base64
import logging
import io

import aiohttp

from config.settings import settings

logger = logging.getLogger(__name__)


class ImageGenError(Exception):
    pass


class ImageGenService:

    HF_URL = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"

    QUALITY_SUFFIX = ", highly detailed, professional quality, 8k resolution"

    def __init__(self):
        self.key = getattr(settings, 'hf_token', '') or ''

    async def generate(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        steps: int = 4,
        style: str = "default",
    ) -> bytes:
        if not self.key:
            raise ImageGenError("❌ Ключ для генерации изображений не настроен.")

        enhanced_prompt = self._enhance_prompt(prompt, style)

        payload = {
            "inputs": enhanced_prompt,
            "parameters": {
                "width": width,
                "height": height,
                "num_inference_steps": steps,
            }
        }

        headers = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    self.HF_URL,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    elif resp.status == 401:
                        raise ImageGenError("❌ Неверный Hugging Face токен.")
                    elif resp.status == 429:
                        raise ImageGenError("⏳ Слишком много запросов. Подожди немного.")
                    elif resp.status == 503:
                        raise ImageGenError("⏳ Модель загружается. Попробуй через 20 секунд.")
                    else:
                        err = await resp.text()
                        logger.error(f"HF error {resp.status}: {err}")
                        raise ImageGenError(f"❌ Ошибка генерации ({resp.status}).")

            except asyncio.TimeoutError:
                raise ImageGenError("⏳ Генерация заняла слишком долго. Попробуй ещё раз.")
            except aiohttp.ClientError as e:
                logger.error(f"ImageGen connection error: {e}")
                raise ImageGenError("❌ Ошибка соединения с сервером генерации.")

    def _enhance_prompt(self, prompt: str, style: str = "default") -> str:
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
        try:
            parts = size_str.lower().split("x")
            w = int(parts[0].strip())
            h = int(parts[1].strip())
            w = min(max(w, 256), 1024)
            h = min(max(h, 256), 1024)
            w = (w // 64) * 64
            h = (h // 64) * 64
            return w, h
        except Exception:
            return 1024, 1024

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

    SIZES = {
        "square":    ("1024x1024", "⬛ Квадрат 1024×1024"),
        "portrait":  ("832x1216", "📱 Портрет 832×1216"),
        "landscape": ("1216x832", "🖥 Альбом 1216×832"),
        "wide":      ("1344x768", "🎬 Широкий 1344×768"),
        "small":     ("512x512", "🔸 Маленький 512×512"),
    }


class TTSService:

    async def synthesize(self, text: str, lang: str = "ru") -> bytes:
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._sync_synthesize, text, lang)
        except Exception as e:
            logger.error(f"TTS error: {e}")
            raise ImageGenError(f"❌ Ошибка синтеза речи: {e}")

    def _sync_synthesize(self, text: str, lang: str) -> bytes:
        from gtts import gTTS
        import io
        tts = gTTS(text=text, lang=lang, slow=False)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()

    async def text_to_voice_message(self, text: str, lang: str = "ru") -> bytes:
        mp3_bytes = await self.synthesize(text, lang)
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._mp3_to_ogg, mp3_bytes)
        except Exception:
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
            return mp3_bytes


image_service = ImageGenService()
tts_service = TTSService()
