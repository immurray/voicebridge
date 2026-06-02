# VoiceBridge — Google TTS (gTTS, free, no API key)
import asyncio
import logging
from functools import partial

logger = logging.getLogger("voicebridge")

# Language mapping for gTTS
LANG_MAP = {
    "zh": "zh-CN",
    "en": "en",
    "es": "es",
    "ar": "ar",
    "pt": "pt",
}


async def text_to_speech(text: str, voice_id: str = "", language: str = "en") -> bytes:
    """Convert text to MP3 speech using Google TTS (gTTS).

    Returns MP3 audio bytes, or empty bytes on failure.
    """
    if not text.strip():
        return b""

    tld = "com"
    lang = LANG_MAP.get(language, "en")

    try:
        from gtts import gTTS
    except ImportError as e:
        err = f"gTTS import failed: {e}"
        logger.error(f"[gTTS] {err}")
        _set_diag_error(err)
        return b""

    try:
        # gTTS is synchronous — run in thread pool
        loop = asyncio.get_running_loop()
        tts = await loop.run_in_executor(
            None,
            partial(_generate, text, lang, tld),
        )
        if tts:
            logger.info(f"[gTTS] {len(tts)}B, lang={lang}, text={text[:40]}")
            return tts
        else:
            err = f"gTTS returned None: lang={lang}, text={text[:50]}"
            logger.warning(f"[gTTS] {err}")
            _set_diag_error(err)
            return b""

    except Exception as e:
        err = f"gTTS exception: {type(e).__name__}: {e}"
        logger.error(f"[gTTS] {err}")
        _set_diag_error(err)
        return b""


def _generate(text: str, lang: str, tld: str) -> bytes | None:
    """Synchronous gTTS call to run in executor."""
    from gtts import gTTS
    from io import BytesIO

    tts = gTTS(text=text, lang=lang, tld=tld, slow=False)
    buf = BytesIO()
    tts.write_to_fp(buf)
    buf.seek(0)
    return buf.read()


def _set_diag_error(msg: str):
    """Write error to ws.diag so it's visible in /debug/status."""
    try:
        from app.ws import diag
        diag["last_tts_error"] = msg[:200]
    except Exception:
        pass
