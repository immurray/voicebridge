# VoiceBridge WebSocket Handler — Full Audio Pipeline
import json
import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings

logger = logging.getLogger("voicebridge")
router = APIRouter()

# Active connections: {session_id: {peer_id: WebSocket}}
connections: dict[str, dict[str, WebSocket]] = {}
# Voice IDs per peer
voice_ids: dict[str, dict[str, str]] = {}


@router.websocket("/ws/{session_id}/{peer_id}")
async def websocket_endpoint(ws: WebSocket, session_id: str, peer_id: str):
    """WebSocket 端点：接收原始音频 → ASR → 翻译 → TTS → 转发给对端"""
    await ws.accept()
    logger.info(f"[WS] {peer_id} connected to session {session_id}")

    if session_id not in connections:
        connections[session_id] = {}
    connections[session_id][peer_id] = ws

    lang = _get_peer_language(session_id, peer_id) or "zh"
    target_lang = "en" if lang == "zh" else "zh"
    voice_id = _get_peer_voice(session_id, peer_id)

    try:
        while True:
            data = await ws.receive()

            if "bytes" in data:
                audio_bytes = data["bytes"]
                if len(audio_bytes) < 100:
                    continue

                # Lazy imports (avoid module-level import of heavy SDKs)
                from app.translate import translate
                from app.tts import text_to_speech

                # Step 1: ASR via Deepgram REST
                transcript = await _transcribe_chunk(audio_bytes, lang)
                if not transcript or not transcript.strip():
                    continue

                logger.info(f"[ASR] {peer_id}: {transcript[:80]}")

                # Step 2: Translate
                translated = translate(transcript, lang, target_lang)
                if not translated or translated.startswith("[Translation error"):
                    logger.warning(f"[Translate] failed: {transcript[:50]}")
                    continue

                logger.info(f"[Translate] {lang}→{target_lang}: {translated[:80]}")

                # Step 3: TTS
                tts_audio = text_to_speech(
                    translated,
                    voice_id=voice_id or "",
                    language=target_lang,
                )

                if not tts_audio or len(tts_audio) < 100:
                    continue

                # Step 4: Send to peer
                peer_ws = get_peer(session_id, peer_id)
                if peer_ws and peer_ws.client_state.name == "CONNECTED":
                    try:
                        await peer_ws.send_bytes(tts_audio)
                        logger.info(f"[TTS→Peer] {len(tts_audio)} bytes")
                    except Exception as e:
                        logger.error(f"[Send Error] {e}")

            elif "text" in data:
                msg = json.loads(data["text"])
                msg_type = msg.get("type")

                if msg_type == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))

                elif msg_type == "vad_event":
                    peer_ws = get_peer(session_id, peer_id)
                    if peer_ws and peer_ws.client_state.name == "CONNECTED":
                        await peer_ws.send_text(json.dumps({
                            "type": "vad_event",
                            "peer_id": peer_id,
                            "speaking": msg.get("speaking", False),
                        }))

                elif msg_type == "voice_id":
                    if session_id not in voice_ids:
                        voice_ids[session_id] = {}
                    voice_ids[session_id][peer_id] = msg.get("voice_id", "")

    except WebSocketDisconnect:
        logger.info(f"[WS] {peer_id} disconnected")
    except Exception as e:
        logger.error(f"[WS Error] {peer_id}: {e}")
    finally:
        if session_id in connections and peer_id in connections[session_id]:
            del connections[session_id][peer_id]
            if not connections[session_id]:
                del connections[session_id]


async def _transcribe_chunk(audio_bytes: bytes, language: str) -> str:
    """Transcribe a PCM audio chunk using Deepgram REST API."""
    import httpx

    lang_map = {"zh": "zh-CN", "en": "en-US"}
    dg_lang = lang_map.get(language, "zh-CN")

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
                logger.warning(f"[Deepgram] HTTP {resp.status_code}: {resp.text[:200]}")
                return ""

            result = resp.json()
            channel = result.get("results", {}).get("channels", [{}])[0]
            alternatives = channel.get("alternatives", [{}])
            transcript = alternatives[0].get("transcript", "")
            return transcript.strip()

    except Exception as e:
        logger.error(f"[Deepgram Error] {e}")
        return ""


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
    import struct

    num_samples = len(pcm_bytes) // 2
    wav_header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm_bytes), b"WAVE", b"fmt ",
        16, 1, 1, sample_rate, sample_rate * 2, 2, 16,
        b"data", len(pcm_bytes),
    )
    return wav_header + pcm_bytes


def get_peer(session_id: str, current_peer: str) -> WebSocket | None:
    if session_id in connections:
        for pid, w in connections[session_id].items():
            if pid != current_peer:
                return w
    return None


def _get_peer_language(session_id: str, peer_id: str) -> str | None:
    try:
        from app.session import sessions
        if session_id in sessions:
            peer = sessions[session_id].get("peers", {}).get(peer_id)
            if peer:
                return peer.get("language")
    except Exception:
        pass
    return None


def _get_peer_voice(session_id: str, peer_id: str) -> str | None:
    return voice_ids.get(session_id, {}).get(peer_id)
