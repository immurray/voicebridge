# VoiceBridge — Google TTS (gTTS, free, no API key)
import asyncio
import logging
from functools import partial

logger = logging.getLogger("voicebridge")

LANG_MAP = {"zh": "zh-CN", "en": "en", "es": "es", "ar": "ar", "pt": "pt"}


async def text_to_speech(text: str, voice_id: str = "", language: str = "en") -> bytes:
    """Convert text to MP3 speech using Google TTS."""
    if not text.strip():
        return b""

    lang = LANG_MAP.get(language, "en")

    try:
        from gtts import gTTS
    except ImportError as e:
        _set_error(f"gTTS import failed: {e}")
        return b""

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, partial(_generate, text, lang))
        if result:
            logger.info(f"[gTTS] {len(result)}B, lang={lang}, text={text[:40]}")
            return result
        _set_error(f"gTTS returned empty: lang={lang}, text={text[:50]}")
        return b""
    except Exception as e:
        _set_error(f"gTTS exception: {type(e).__name__}: {e}")
        return b""


def _generate(text: str, lang: str) -> bytes | None:
    from gtts import gTTS
    from io import BytesIO
    try:
        tts = gTTS(text=text, lang=lang, tld="com", slow=False)
        buf = BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except Exception:
        return None


def _set_error(msg: str):
    try:
        from app.ws import diag
        diag["last_tts_error"] = msg[:200]
    except Exception:
        pass
