"""
🎨 Сервис генерации изображений — Pollinations AI (бесплатно, без ключей)
"""

import asyncio
import logging
import urllib.parse

import aiohttp

from config.settings import settings

logger = logging.getLogger(__name__)


class ImageGenError(Exception):
    pass


class ImageGenService:
    """Генерация изображений через Pollinations AI — бесплатно и без ключей"""

    BASE_URL = "https://image.pollinations.ai/prompt/{prompt}"

    QUALITY_SUFFIX = ", highly detailed, professional quality, 8k resolution"

    def __init__(self):
        pass  # Ключи не нужны

    async def generate(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        steps: int = 4,
        style: str = "default",
    ) -> bytes:
        enhanced_prompt = self._enhance_prompt(prompt, style)
        encoded = urllib.parse.quote(enhanced_prompt)

        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width={width}&height={height}&nologo=true&enhance=true"
        )

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    else:
                        logger.error(f"Pollinations error {resp.status}")
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
