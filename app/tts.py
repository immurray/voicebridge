# VoiceBridge — Edge TTS (Microsoft, free, no API key)
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


async def text_to_speech(text: str, voice_id: str = "", language: str = "en") -> bytes:
    """Convert text to MP3 speech using Microsoft Edge TTS.

    Returns MP3 audio bytes, or empty bytes on failure.
    Reports errors to app.ws.diag for /debug/status visibility.
    """
    if not text.strip():
        return b""

    voice = VOICES.get(language, VOICES["en"])

    # Try importing edge-tts
    try:
        import edge_tts
    except ImportError as e:
        err = f"edge-tts import failed: {e}"
        logger.error(f"[EdgeTTS] {err}")
        _set_diag_error(err)
        return b""

    # Generate speech
    try:
        communicate = edge_tts.Communicate(text, voice)
        audio_bytes = b""
        chunk_count = 0
        async for chunk in communicate.stream():
            chunk_count += 1
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]
            elif chunk["type"] == "WordBoundary":
                pass

        if not audio_bytes:
            err = f"No audio from stream: {chunk_count} chunks, voice={voice}, text={text[:50]}"
            logger.warning(f"[EdgeTTS] {err}")
            _set_diag_error(err)
            return b""

        logger.info(f"[EdgeTTS] {len(audio_bytes)}B, {voice}, text={text[:40]}")
        return audio_bytes

    except Exception as e:
        err = f"edge-tts exception: {type(e).__name__}: {e}"
        logger.error(f"[EdgeTTS] {err}")
        _set_diag_error(err)
        return b""


def _set_diag_error(msg: str):
    """Write error to ws.diag so it's visible in /debug/status."""
    try:
        from app.ws import diag
        diag["last_tts_error"] = msg[:200]
    except Exception:
        pass
