# VoiceBridge — Edge TTS (Microsoft, free, no API key)
import asyncio
import logging

logger = logging.getLogger("voicebridge")

# Voice mapping per language
VOICES = {
    "zh": "zh-CN-XiaoxiaoNeural",       # 晓晓 — natural female Chinese
    "en": "en-US-JennyNeural",          # Jenny — natural female English
    "es": "es-ES-ElviraNeural",         # Elvira — natural female Spanish
    "ar": "ar-SA-ZariyahNeural",        # Zariyah — natural female Arabic (Saudi)
    "pt": "pt-BR-FranciscaNeural",      # Francisca — natural female Portuguese
}

# Cache: reuse voice objects to avoid re-creating
_voice_cache: dict = {}


async def text_to_speech(text: str, voice_id: str = "", language: str = "en") -> bytes:
    """Convert text to MP3 speech using Microsoft Edge TTS.

    Returns MP3 audio bytes, or empty bytes on failure.
    `voice_id` is ignored — voice is selected by language.
    """
    if not text.strip():
        return b""

    voice = VOICES.get(language, VOICES["en"])

    try:
        import edge_tts

        communicate = edge_tts.Communicate(text, voice)
        audio_bytes = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]
            elif chunk["type"] == "WordBoundary":
                pass  # timing events, ignore

        if not audio_bytes:
            logger.warning(f"[EdgeTTS] No audio generated for: {text[:50]}")
            return b""

        logger.info(f"[EdgeTTS] {len(audio_bytes)} bytes, {voice}, text={text[:40]}")
        return audio_bytes

    except ImportError:
        logger.error("[EdgeTTS] edge-tts package not installed")
        return b""
    except Exception as e:
        logger.error(f"[EdgeTTS] {e}")
        return b""
