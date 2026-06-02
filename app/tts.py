# VoiceBridge — gTTS + Piper 双保险 TTS
#
# 策略：gTTS 主力 → 失败自动降级到 Piper（本地离线）
# Piper 模型首次使用时自动下载到 /data/piper-models/（持久化卷）
# 下载一次后永久缓存，容器重建不丢失
#
import os
import asyncio
import logging
import subprocess
from functools import partial
from pathlib import Path

logger = logging.getLogger("voicebridge")

# Voice model URLs — Piper low/medium quality (fast, small)
PIPER_MODELS = {
    "zh": {
        "name": "zh_CN-huayan-medium",
        "url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx.json",
    },
    "es": {
        "name": "es_ES-carlfm-x_low",
        "url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/carlfm/x_low/es_ES-carlfm-x_low.onnx",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/carlfm/x_low/es_ES-carlfm-x_low.onnx.json",
    },
    "ar": {
        "name": "ar_JO-kareem-low",
        "url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/low/ar_JO-kareem-low.onnx",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/low/ar_JO-kareem-low.onnx.json",
    },
    "en": {
        "name": "en_US-lessac-medium",
        "url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
    },
    "pt": {
        "name": "pt_BR-faber-medium",
        "url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx.json",
    },
}

MODEL_DIR = Path("/data/piper-models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)


async def text_to_speech(text: str, voice_id: str = "", language: str = "en") -> bytes:
    """双保险 TTS：gTTS → Piper 降级。

    Returns MP3 audio bytes, or empty bytes on total failure.
    """
    if not text.strip():
        return b""

    # Primary: gTTS
    result = await _gtts(text, language)
    if result:
        return result

    # Fallback: Piper (local, offline, zero external dependency)
    logger.warning(f"[TTS] gTTS failed, falling back to Piper for: {text[:50]}")
    result = await _piper(text, language)
    if result:
        return result

    _set_diag_error(f"Both gTTS and Piper failed for: {text[:50]}")
    return b""


# ─── gTTS ───────────────────────────────────────────

async def _gtts(text: str, language: str) -> bytes | None:
    """gTTS — free Google TTS, requires internet."""
    try:
        from gtts import gTTS
    except ImportError:
        return None

    lang = _gtts_lang(language)
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, partial(_gtts_sync, text, lang))
        if result:
            logger.info(f"[gTTS] {len(result)}B, lang={lang}")
            return result
        return None
    except Exception as e:
        logger.warning(f"[gTTS] {e}")
        return None


def _gtts_sync(text: str, lang: str) -> bytes | None:
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


def _gtts_lang(language: str) -> str:
    return {"zh": "zh-CN", "en": "en", "es": "es", "ar": "ar", "pt": "pt"}.get(language, "en")


# ─── Piper (local offline fallback) ─────────────────

async def _piper(text: str, language: str) -> bytes | None:
    """Piper TTS — local offline, needs model file + piper binary."""
    model = PIPER_MODELS.get(language)
    if not model:
        return None

    model_path = await _ensure_model(model)
    if not model_path:
        return None

    try:
        # Piper: text → raw PCM 16kHz 16-bit mono
        proc = await asyncio.create_subprocess_exec(
            "/usr/local/bin/piper",
            "-m", str(model_path),
            "--output-raw",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(text.encode())
        if proc.returncode != 0 or not stdout:
            logger.warning(f"[Piper] Failed: {stderr.decode()[:200]}")
            return None

        # Convert raw PCM → MP3 via ffmpeg (expects 16kHz 16-bit mono)
        pcm_bytes = stdout
        mp3_bytes = await _pcm_to_mp3(pcm_bytes)
        if mp3_bytes:
            logger.info(f"[Piper] {len(mp3_bytes)}B MP3, model={model['name']}")
            return mp3_bytes
        return None

    except FileNotFoundError:
        _set_diag_error("piper binary not found at /usr/local/bin/piper")
        return None
    except Exception as e:
        logger.error(f"[Piper] {e}")
        return None


async def _pcm_to_mp3(pcm_bytes: bytes) -> bytes | None:
    """Convert raw PCM 16kHz 16-bit mono to MP3 via ffmpeg."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-f", "s16le",       # raw signed 16-bit little-endian
            "-ar", "16000",      # sample rate
            "-ac", "1",          # mono
            "-i", "pipe:0",      # stdin
            "-f", "mp3",
            "-b:a", "64k",
            "pipe:1",            # stdout
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(pcm_bytes)
        if proc.returncode != 0:
            logger.warning(f"[ffmpeg] Failed: {stderr.decode()[:200]}")
            return None
        return stdout
    except Exception as e:
        logger.error(f"[ffmpeg] {e}")
        return None


async def _ensure_model(model: dict) -> str | None:
    """Ensure model file is downloaded. Returns path or None."""
    onnx_path = MODEL_DIR / f"{model['name']}.onnx"
    json_path = MODEL_DIR / f"{model['name']}.onnx.json"

    if onnx_path.exists() and json_path.exists():
        return str(onnx_path)

    # Download both files
    logger.info(f"[Piper] Downloading model: {model['name']} (~50MB)")
    for path, url in [(onnx_path, model["url"]), (json_path, model["json_url"])]:
        if path.exists():
            continue
        try:
            proc = await asyncio.create_subprocess_exec(
                "curl", "-sL", "--retry", "3", "-o", str(path), url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            if proc.returncode != 0:
                logger.warning(f"[Piper] Failed to download {url}")
                return None
        except Exception as e:
            logger.warning(f"[Piper] Download error: {e}")
            return None

    if onnx_path.exists() and json_path.exists():
        logger.info(f"[Piper] Model ready: {model['name']}")
        return str(onnx_path)
    return None


# ─── Diagnostic ─────────────────────────────────────

def _set_diag_error(msg: str):
    try:
        from app.ws import diag
        diag["last_tts_error"] = msg[:200]
    except Exception:
        pass
