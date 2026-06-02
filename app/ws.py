# VoiceBridge v2 WebSocket — Solo Translation Pipeline
import json
import struct
import base64
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings

logger = logging.getLogger("voicebridge")
router = APIRouter()

# Diagnostic counters
diag = {
    "audio_chunks": 0, "transcripts": 0, "translations": 0, "tts": 0,
    "last_asr_error": None, "last_translate_error": None, "last_tts_error": None,
    "last_asr_text": None, "last_translated_text": None,
}


@router.get("/debug/status")
async def debug_status():
    """Return diagnostic counters for ASR pipeline."""
    return {
        "audio_chunks_received": diag["audio_chunks"],
        "transcripts_detected": diag["transcripts"],
        "translations_done": diag["translations"],
        "tts_generated": diag["tts"],
        "last_asr_text": diag["last_asr_text"],
        "last_translated_text": diag["last_translated_text"],
        "last_asr_error": diag["last_asr_error"],
        "last_translate_error": diag["last_translate_error"],
        "last_tts_error": diag["last_tts_error"],
        "deepgram_key": settings.deepgram_api_key[:8] + "..." if settings.deepgram_api_key else "MISSING",
        "openai_key": settings.openai_api_key[:8] + "..." if settings.openai_api_key else "MISSING",
        "elevenlabs_key": settings.elevenlabs_api_key[:8] + "..." if settings.elevenlabs_api_key else "MISSING",
    }


@router.websocket("/ws/translate")
async def translate_endpoint(ws: WebSocket):
    """WebSocket 端点：单人实时翻译管线"""
    await ws.accept()
    logger.info("[WS] Solo client connected")

    source_lang = "zh"
    target_lang = "es"

    try:
        while True:
            data = await ws.receive()

            if "bytes" in data:
                audio_bytes = data["bytes"]
                diag["audio_chunks"] += 1
                if len(audio_bytes) < 100:
                    continue

                from app.translate import translate
                from app.tts import text_to_speech

                # Step 1: ASR
                transcript = await _transcribe_chunk(audio_bytes, source_lang)
                if not transcript or not transcript.strip():
                    continue

                diag["transcripts"] += 1
                diag["last_asr_text"] = transcript[:200]
                logger.info(f"[ASR] {transcript[:80]}")

                # Notify client: speech recognized
                await ws.send_text(json.dumps({
                    "type": "status",
                    "state": "recognized",
                    "text": transcript,
                }, ensure_ascii=False))

                # Step 2: Translate
                try:
                    translated = translate(transcript, source_lang, target_lang)
                except Exception as e:
                    diag["last_translate_error"] = str(e)[:200]
                    translated = ""
                    logger.error(f"[Translate Exception] {e}")

                if not translated:
                    diag["last_translate_error"] = diag["last_translate_error"] or "Empty result from translate()"
                    logger.warning(f"[Translate] Empty result for: {transcript[:50]}")
                    continue

                if translated.startswith("[Translation error"):
                    diag["last_translate_error"] = translated[:200]
                    logger.warning(f"[Translate] API error: {translated[:100]}")
                    continue

                diag["translations"] += 1
                diag["last_translated_text"] = translated[:200]
                logger.info(f"[Translate] {source_lang}→{target_lang}: {translated[:80]}")

                # Step 3: TTS
                try:
                    tts_audio = text_to_speech(
                        translated,
                        voice_id="",
                        language=target_lang,
                    )
                except Exception as e:
                    diag["last_tts_error"] = str(e)[:200]
                    logger.error(f"[TTS Exception] {e}")
                    continue

                if not tts_audio or len(tts_audio) < 100:
                    diag["last_tts_error"] = f"Empty/minimal audio: {len(tts_audio) if tts_audio else 0} bytes"
                    logger.warning("[TTS] No audio generated")
                    continue

                diag["tts"] += 1
                logger.info(f"[TTS] {len(tts_audio)} bytes generated")

                # Step 4: Send result
                await ws.send_text(json.dumps({
                    "type": "result",
                    "original": transcript,
                    "translated": translated,
                    "audio": base64.b64encode(tts_audio).decode(),
                    "source_lang": source_lang,
                    "target_lang": target_lang,
                }, ensure_ascii=False))

            elif "text" in data:
                msg = json.loads(data["text"])
                msg_type = msg.get("type")

                if msg_type == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))

                elif msg_type == "config":
                    source_lang = msg.get("source_lang", source_lang)
                    target_lang = msg.get("target_lang", target_lang)
                    logger.info(f"[Config] {source_lang}→{target_lang}")

    except WebSocketDisconnect:
        logger.info("[WS] Solo client disconnected")
    except Exception as e:
        logger.error(f"[WS Error] {e}")


async def _transcribe_chunk(audio_bytes: bytes, language: str) -> str:
    """Transcribe PCM audio using Deepgram REST."""
    import httpx

    lang_map = {"zh": "zh-CN", "en": "en-US", "es": "es", "ar": "ar", "pt": "pt-BR"}
    dg_lang = lang_map.get(language, language)

    wav_bytes = _pcm_to_wav(audio_bytes, settings.sample_rate)

    headers = {
        "Authorization": f"Token {settings.deepgram_api_key}",
        "Content-Type": "audio/wav",
    }

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                f"https://api.deepgram.com/v1/listen?"
                f"model=nova-2&language={dg_lang}&smart_format=true",
                headers=headers,
                content=wav_bytes,
            )

            if resp.status_code != 200:
                err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                diag["last_asr_error"] = err
                logger.warning(f"[Deepgram] {err}")
                return ""

            result = resp.json()
            channel = result.get("results", {}).get("channels", [{}])[0]
            alternatives = channel.get("alternatives", [{}])
            transcript = alternatives[0].get("transcript", "")
            return transcript.strip()

    except Exception as e:
        diag["last_asr_error"] = str(e)[:200]
        logger.error(f"[Deepgram Error] {e}")
        return ""


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
    num_samples = len(pcm_bytes) // 2
    wav_header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm_bytes), b"WAVE", b"fmt ",
        16, 1, 1, sample_rate, sample_rate * 2, 2, 16,
        b"data", len(pcm_bytes),
    )
    return wav_header + pcm_bytes
