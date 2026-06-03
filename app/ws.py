# VoiceBridge v2.3 — Bidirectional Streaming ASR with Explicit Language Switching
import json
import struct
import base64
import logging
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings

logger = logging.getLogger("voicebridge")
router = APIRouter()

diag = {
    "audio_chunks": 0, "transcripts": 0, "translations": 0, "tts": 0,
    "last_asr_error": None, "last_translate_error": None, "last_tts_error": None,
    "last_asr_text": None, "last_translated_text": None,
}

LANG_MAP_DG = {"zh": "zh-CN", "en": "en-US", "es": "es", "ar": "ar", "pt": "pt-BR"}
DG_REVERSE = {
    "zh": "zh", "zh-CN": "zh",
    "en": "en", "en-US": "en",
    "es": "es", "ar": "ar",
    "pt": "pt", "pt-BR": "pt",
}


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
    }


def _detect_lang(text: str) -> str | None:
    """Heuristic language detection — checks for CJK characters.
    Returns 'zh' if Chinese detected, None otherwise."""
    for ch in text:
        cp = ord(ch)
        if (0x4E00 <= cp <= 0x9FFF or
            0x3400 <= cp <= 0x4DBF or
            0xF900 <= cp <= 0xFAFF or
            0x2F800 <= cp <= 0x2FA1F):
            return "zh"
    return None


@router.websocket("/ws/translate")
async def translate_endpoint(ws: WebSocket):
    """WebSocket — bidirectional streaming ASR pipeline with explicit language switching."""
    await ws.accept()
    logger.info("[WS] Client connected")

    source_lang = "zh"
    target_lang = "es"
    bidirectional = False
    dg_task = None
    dg_ws = None
    current_dg_lang = "zh-CN"  # Track current Deepgram language for switching

    def _resolve_direction(text: str) -> tuple[str, str] | None:
        """Resolve translation direction from transcript text."""
        detected = _detect_lang(text)
        if detected == "zh":
            if source_lang == "zh":
                return (source_lang, target_lang)
            else:
                return (target_lang, source_lang)
        # Non-CJK text
        if source_lang != "zh":
            return (source_lang, target_lang)
        if target_lang != "zh":
            return (target_lang, source_lang)
        return None

    def _build_dg_url(dg_lang: str | None = None) -> str:
        """Build Deepgram WebSocket URL. 
        In bidirectional mode, uses explicit language (not 'multi') with nova-3.
        Language switching happens by restarting connection with new dg_lang."""
        nonlocal current_dg_lang
        
        if dg_lang is not None:
            current_dg_lang = dg_lang
        
        lang_code = current_dg_lang if bidirectional else LANG_MAP_DG.get(source_lang, "zh-CN")
        
        return (
            f"wss://api.deepgram.com/v1/listen"
            f"?model=nova-3"
            f"&language={lang_code}"
            f"&smart_format=true"
            f"&interim_results=true"
            f"&endpointing=5000"  # 5s silence before ending utterance — survives TTS playback gaps
            f"&utterance_end_ms=5000"  # same, explicit parameter
            f"&encoding=linear16"
            f"&sample_rate=16000"
            f"&channels=1"
        )

    async def dg_loop():
        """Keep Deepgram connection alive. Auto-switches language in bidirectional mode."""
        nonlocal dg_ws, current_dg_lang
        import websockets as ws_lib
        from app.translate import translate
        from app.tts import text_to_speech

        reconnect_count = 0
        max_reconnects = 10

        while reconnect_count < max_reconnects:
            dg_url = _build_dg_url()
            try:
                async with ws_lib.connect(
                    dg_url,
                    additional_headers={"Authorization": f"Token {settings.deepgram_api_key}"},
                    ping_interval=5,
                    close_timeout=5,
                ) as dg:
                    dg_ws = dg
                    mode = f"bidirectional(dg={current_dg_lang})" if bidirectional else f"lang={source_lang}"
                    logger.info(f"[Deepgram] Connected ({mode})")
                    reconnect_count = 0  # reset on successful connection

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

                        # Language switching in bidirectional mode
                        if bidirectional and (is_final or speech_final):
                            detected = _detect_lang(transcript)
                            if detected == "zh" and current_dg_lang != "zh-CN":
                                logger.info(f"[LangSwitch] → zh-CN (detected Chinese: {transcript[:40]})")
                                break  # Break inner loop → reconnect with zh-CN
                            elif detected is None and current_dg_lang == "zh-CN":
                                # Switch to non-zh language
                                non_zh = LANG_MAP_DG.get(
                                    source_lang if source_lang != "zh" else target_lang, "en-US"
                                )
                                if non_zh != current_dg_lang:
                                    logger.info(f"[LangSwitch] → {non_zh} (detected non-Chinese: {transcript[:40]})")
                                    current_dg_lang = non_zh
                                    break  # Break inner loop → reconnect
                            # Also switch if current_lang doesn't match source/target for extended period
                            # but only on final results to avoid flapping

                        # Resolve translation direction
                        if bidirectional:
                            direction = _resolve_direction(transcript)
                            if direction is None:
                                if is_final or speech_final:
                                    await ws.send_text(json.dumps({
                                        "type": "interim",
                                        "text": transcript,
                                        "lang": _detect_lang(transcript) or "?",
                                    }, ensure_ascii=False))
                                continue
                            src, tgt = direction
                        else:
                            src, tgt = source_lang, target_lang

                        if is_final or speech_final:
                            diag["transcripts"] += 1
                            diag["last_asr_text"] = transcript[:200]
                            logger.info(f"[ASR Final] {src}→{tgt}: {transcript[:80]}")

                            await ws.send_text(json.dumps({
                                "type": "recognized",
                                "text": transcript,
                                "source_lang": src,
                                "target_lang": tgt,
                            }, ensure_ascii=False))

                            # Translate
                            try:
                                translated = translate(transcript, src, tgt)
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
                                tts_audio = await text_to_speech(translated, language=tgt) or b""
                            except Exception as e:
                                diag["last_tts_error"] = str(e)[:200]

                            if tts_audio and len(tts_audio) >= 100:
                                diag["tts"] += 1

                            result_msg = {
                                "type": "result",
                                "original": transcript,
                                "translated": translated,
                                "source_lang": src,
                                "target_lang": tgt,
                            }
                            if tts_audio and len(tts_audio) >= 100:
                                result_msg["audio"] = base64.b64encode(tts_audio).decode()

                            await ws.send_text(json.dumps(result_msg, ensure_ascii=False))
                        else:
                            msg = {"type": "interim", "text": transcript}
                            if bidirectional:
                                msg["source_lang"] = src
                                msg["target_lang"] = tgt
                            await ws.send_text(json.dumps(msg, ensure_ascii=False))

            except ws_lib.exceptions.ConnectionClosed:
                logger.info("[Deepgram] Connection closed, reconnecting...")
                reconnect_count += 1
            except Exception as e:
                logger.error(f"[Deepgram] Error: {e}, reconnecting in 1s...")
                diag["last_asr_error"] = str(e)[:200]
                reconnect_count += 1
                await asyncio.sleep(1)
            finally:
                dg_ws = None

    try:
        dg_started = False

        while True:
            data = await ws.receive()

            if "bytes" in data:
                audio = data["bytes"]
                if len(audio) < 64:
                    continue

                diag["audio_chunks"] += 1

                if not dg_started:
                    # Initialize language for bidirectional mode
                    if bidirectional:
                        current_dg_lang = LANG_MAP_DG.get(source_lang, "zh-CN")
                        logger.info(f"[Init] Bidirectional start with dg_lang={current_dg_lang}")
                    dg_task = asyncio.create_task(dg_loop())
                    dg_started = True

                if dg_ws:
                    try:
                        await dg_ws.send(audio)
                    except Exception as e:
                        logger.warning(f"[AudioSend] dg_ws.send failed: {e}")
                        dg_ws = None  # trigger dg_loop reconnect

            elif "text" in data:
                msg = json.loads(data["text"])
                t = msg.get("type")

                if t == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
                elif t == "config":
                    source_lang = msg.get("source_lang", source_lang)
                    target_lang = msg.get("target_lang", target_lang)
                    bidirectional = msg.get("bidirectional", bidirectional)
                    logger.info(f"[Config] {source_lang}→{target_lang} bidirectional={bidirectional}")
                    
                    # Restart with new settings
                    if dg_task and not dg_task.done():
                        dg_task.cancel()
                    if bidirectional:
                        current_dg_lang = LANG_MAP_DG.get(source_lang, "zh-CN")
                    dg_task = asyncio.create_task(dg_loop())
                    dg_started = True

    except WebSocketDisconnect:
        logger.info("[WS] Client disconnected")
    except RuntimeError as e:
        if "disconnect" in str(e).lower():
            logger.info("[WS] Client disconnected (runtime)")
        else:
            logger.error(f"[WS RuntimeError] {e}")
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
