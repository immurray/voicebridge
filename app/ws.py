# VoiceBridge v2.1 — Deepgram WebSocket Streaming ASR
import json
import struct
import base64
import logging
import asyncio
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

LANG_MAP_DG = {"zh": "zh-CN", "en": "en-US", "es": "es", "ar": "ar", "pt": "pt-BR"}


@router.get("/debug/status")
async def debug_status():
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
    """WebSocket endpoint — streaming ASR pipeline (Deepgram WS → Translate → gTTS)."""
    await ws.accept()
    logger.info("[WS] Client connected")

    source_lang = "zh"
    target_lang = "es"
    dg_task = None  # Deepgram streaming task, started on first audio
    dg_ws = None

    async def start_dg_stream():
        """Open Deepgram WebSocket and start processing transcripts."""
        nonlocal dg_ws

        dg_lang = LANG_MAP_DG.get(source_lang, "zh-CN")
        dg_url = (
            f"wss://api.deepgram.com/v1/listen"
            f"?model=nova-2"
            f"&language={dg_lang}"
            f"&smart_format=true"
            f"&interim_results=true"
            f"&encoding=linear16"
            f"&sample_rate=16000"
            f"&channels=1"
            f"&endpointing=300"
        )

        import websockets as ws_lib

        try:
            async with ws_lib.connect(
                dg_url,
                additional_headers={"Authorization": f"Token {settings.deepgram_api_key}"},
                ping_interval=5,
                close_timeout=5,
            ) as dg:
                dg_ws = dg
                logger.info(f"[Deepgram] Streaming connected, lang={dg_lang}")

                from app.translate import translate
                from app.tts import text_to_speech

                async for raw in dg:
                    try:
                        result = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    channel = result.get("channel", {})
                    alternatives = channel.get("alternatives", [])
                    if not alternatives:
                        continue

                    alt = alternatives[0]
                    transcript = alt.get("transcript", "").strip()
                    if not transcript:
                        continue

                    is_final = result.get("is_final", False)
                    speech_final = result.get("speech_final", False)

                    if is_final or speech_final:
                        diag["transcripts"] += 1
                        diag["last_asr_text"] = transcript[:200]
                        logger.info(f"[ASR Final] {transcript[:80]}")

                        await ws.send_text(json.dumps({
                            "type": "recognized",
                            "text": transcript,
                        }, ensure_ascii=False))

                        # Translate
                        try:
                            translated = translate(transcript, source_lang, target_lang)
                        except Exception as e:
                            diag["last_translate_error"] = str(e)[:200]
                            continue

                        if not translated or translated.startswith("[Translation error"):
                            diag["last_translate_error"] = translated or "Empty result"
                            continue

                        diag["translations"] += 1
                        diag["last_translated_text"] = translated[:200]

                        # TTS
                        tts_audio = b""
                        try:
                            tts_audio = await text_to_speech(translated, language=target_lang) or b""
                        except Exception as e:
                            diag["last_tts_error"] = str(e)[:200]

                        if tts_audio and len(tts_audio) >= 100:
                            diag["tts"] += 1

                        result_msg = {
                            "type": "result",
                            "original": transcript,
                            "translated": translated,
                            "source_lang": source_lang,
                            "target_lang": target_lang,
                        }
                        if tts_audio and len(tts_audio) >= 100:
                            result_msg["audio"] = base64.b64encode(tts_audio).decode()

                        await ws.send_text(json.dumps(result_msg, ensure_ascii=False))
                    else:
                        # Interim result
                        await ws.send_text(json.dumps({
                            "type": "interim",
                            "text": transcript,
                        }, ensure_ascii=False))

        except ws_lib.exceptions.ConnectionClosed:
            logger.info("[Deepgram] Connection closed")
        except Exception as e:
            logger.error(f"[Deepgram Error] {e}")
            diag["last_asr_error"] = str(e)[:200]
            await ws.send_text(json.dumps({
                "type": "error",
                "message": f"ASR connection failed: {e}"
            }))
        finally:
            dg_ws = None

    try:
        while True:
            data = await ws.receive()

            if "bytes" in data:
                audio = data["bytes"]
                if len(audio) < 64:
                    continue

                diag["audio_chunks"] += 1

                # Lazy-start Deepgram on first audio
                if dg_task is None or dg_task.done():
                    dg_task = asyncio.create_task(start_dg_stream())
                    # Brief yield to let Deepgram connect
                    await asyncio.sleep(0)

                if dg_ws:
                    try:
                        await dg_ws.send(audio)
                    except Exception:
                        pass  # Deepgram connection died, will restart on next audio

            elif "text" in data:
                msg = json.loads(data["text"])
                t = msg.get("type")

                if t == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
                elif t == "config":
                    source_lang = msg.get("source_lang", source_lang)
                    target_lang = msg.get("target_lang", target_lang)
                    logger.info(f"[Config] {source_lang}→{target_lang}")
                    # Cancel old Deepgram task — new one will start on next audio
                    if dg_task and not dg_task.done():
                        dg_task.cancel()
                    dg_task = None
                    dg_ws = None

    except WebSocketDisconnect:
        logger.info("[WS] Client disconnected")
    except Exception as e:
        logger.error(f"[WS Error] {e}")
    finally:
        if dg_task and not dg_task.done():
            dg_task.cancel()


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
    """Convert raw PCM to WAV (kept for testing/reference)."""
    num_samples = len(pcm_bytes) // 2
    wav_header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm_bytes), b"WAVE", b"fmt ",
        16, 1, 1, sample_rate, sample_rate * 2, 2, 16,
        b"data", len(pcm_bytes),
    )
    return wav_header + pcm_bytes
