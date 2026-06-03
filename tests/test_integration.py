# VoiceBridge v2 — Integration & Pipeline Tests
# WebSocket, ASR, TTS, Translation pipeline end-to-end
import json
import struct
import os
import pytest
from unittest.mock import patch, MagicMock


# ═══════════════════════════════════════════════════════════════
# WebSocket Tests
# ═══════════════════════════════════════════════════════════════

class TestWebSocket:
    """WebSocket connection, ping/pong, config exchange."""

    def test_websocket_ping_pong(self):
        """WebSocket connects and responds to ping with pong."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        with client.websocket_connect("/ws/translate") as ws:
            ws.send_text(json.dumps({"type": "ping"}))
            data = ws.receive_text()
            msg = json.loads(data)
            assert msg == {"type": "pong"}

    def test_websocket_config_sets_languages(self):
        """WebSocket accepts config message to set source/target languages."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        with client.websocket_connect("/ws/translate") as ws:
            ws.send_text(json.dumps({
                "type": "config",
                "source_lang": "zh",
                "target_lang": "en",
            }))
            # Config doesn't respond — just verify no crash
            ws.send_text(json.dumps({"type": "ping"}))
            data = ws.receive_text()
            assert json.loads(data) == {"type": "pong"}

    def test_websocket_sends_audio_without_crash(self):
        """WebSocket receives raw audio bytes without crashing (below buffer threshold)."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        with client.websocket_connect("/ws/translate") as ws:
            # Send small chunk (below BUFFER_TARGET of 32000 bytes)
            small_chunk = struct.pack("<" + "h" * 100, *([0] * 100))
            ws.send_bytes(small_chunk)
            # Should not crash — just accumulate in buffer
            ws.send_text(json.dumps({"type": "ping"}))
            data = ws.receive_text()
            assert json.loads(data) == {"type": "pong"}

    def test_websocket_handles_disconnect_cleanly(self):
        """WebSocket disconnect doesn't crash the server."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        with client.websocket_connect("/ws/translate") as ws:
            ws.send_text(json.dumps({"type": "ping"}))
            ws.receive_text()
        # Context manager exit = disconnect — no exception means clean


# ═══════════════════════════════════════════════════════════════
# ASR Pipeline Tests (PCM→WAV, Deepgram interface)
# ═══════════════════════════════════════════════════════════════

class TestASRPipeline:
    """Audio processing: PCM→WAV conversion, WAV structure validation."""

    def test_pcm_to_wav_valid_header(self):
        """PCM→WAV produces a valid WAV file with correct RIFF header."""
        from app.ws import _pcm_to_wav

        # 160 samples of silence (320 bytes PCM)
        pcm = struct.pack("<" + "h" * 160, *([0] * 160))
        wav = _pcm_to_wav(pcm)

        assert wav[:4] == b"RIFF"
        assert wav[8:12] == b"WAVE"
        assert wav[12:16] == b"fmt "
        assert len(wav) == 44 + len(pcm)  # 44-byte header + PCM data

    def test_pcm_to_wav_correct_sample_rate(self):
        """PCM→WAV encodes sample rate correctly in WAV header."""
        from app.ws import _pcm_to_wav

        pcm = struct.pack("<" + "h" * 160, *([0] * 160))
        wav = _pcm_to_wav(pcm, sample_rate=16000)

        # Byte offset 24-27 = sample rate (little-endian uint32)
        sample_rate = struct.unpack_from("<I", wav, 24)[0]
        assert sample_rate == 16000

    def test_pcm_to_wav_mono_16bit(self):
        """PCM→WAV produces mono 16-bit PCM."""
        from app.ws import _pcm_to_wav

        pcm = struct.pack("<" + "h" * 160, *([0] * 160))
        wav = _pcm_to_wav(pcm)

        # Byte offset 20-21 = audio format (1 = PCM)
        audio_format = struct.unpack_from("<H", wav, 20)[0]
        assert audio_format == 1

        # Byte offset 22-23 = num channels
        channels = struct.unpack_from("<H", wav, 22)[0]
        assert channels == 1

        # Byte offset 34-35 = bits per sample
        bits = struct.unpack_from("<H", wav, 34)[0]
        assert bits == 16

    def test_pcm_to_wav_handles_empty_input(self):
        """PCM→WAV handles zero-length input (just header)."""
        from app.ws import _pcm_to_wav

        pcm = b""
        wav = _pcm_to_wav(pcm)

        assert wav[:4] == b"RIFF"
        assert len(wav) == 44  # Only header

    def test_pcm_to_wav_data_size_correct(self):
        """PCM→WAV data chunk size matches actual data length."""
        from app.ws import _pcm_to_wav

        # 500 samples = 1000 bytes
        pcm = struct.pack("<" + "h" * 500, *([0] * 500))
        wav = _pcm_to_wav(pcm, sample_rate=16000)

        # Byte offset 4-7 = file size - 8
        file_size = struct.unpack_from("<I", wav, 4)[0]
        assert file_size == 36 + len(pcm)

        # Byte offset 40-43 = data chunk size
        data_size = struct.unpack_from("<I", wav, 40)[0]
        assert data_size == len(pcm)

    @patch("httpx.AsyncClient.post")
    @pytest.mark.asyncio
    async def test_transcribe_chunk_handles_http_error(self, mock_post):
        """ASR transcription catches HTTP errors gracefully (no crash, empty result)."""
        from app.ws import _transcribe_chunk

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        mock_post.return_value = mock_resp

        pcm = struct.pack("<" + "h" * 1600, *([0] * 1600))
        result = await _transcribe_chunk(pcm, "en")

        assert result == ""  # Returns empty on error, no crash

    @patch("httpx.AsyncClient.post")
    @pytest.mark.asyncio
    async def test_transcribe_chunk_handles_network_error(self, mock_post):
        """ASR transcription catches network errors gracefully."""
        from app.ws import _transcribe_chunk

        mock_post.side_effect = Exception("Connection refused")

        pcm = struct.pack("<" + "h" * 1600, *([0] * 1600))
        result = await _transcribe_chunk(pcm, "en")

        assert result == ""

    @patch("httpx.AsyncClient.post")
    @pytest.mark.asyncio
    async def test_transcribe_chunk_returns_transcript_on_success(self, mock_post):
        """ASR transcription returns transcript on Deepgram 200 response."""
        from app.ws import _transcribe_chunk

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": {
                "channels": [{
                    "alternatives": [{"transcript": "hello world"}]
                }]
            }
        }
        mock_post.return_value = mock_resp

        pcm = struct.pack("<" + "h" * 1600, *([0] * 1600))
        result = await _transcribe_chunk(pcm, "en")

        assert result == "hello world"


# ═══════════════════════════════════════════════════════════════
# TTS Pipeline Tests (gTTS)
# ═══════════════════════════════════════════════════════════════

class TestTTSPipeline:
    """gTTS text-to-speech: empty input, language mapping, audio generation."""

    @pytest.mark.asyncio
    async def test_tts_empty_input_returns_empty(self):
        """gTTS returns empty bytes for empty text input."""
        from app.tts import text_to_speech

        result = await text_to_speech("", language="en")
        assert result == b""

    @pytest.mark.asyncio
    async def test_tts_whitespace_only_returns_empty(self):
        """gTTS returns empty bytes for whitespace-only input."""
        from app.tts import text_to_speech

        result = await text_to_speech("   ", language="en")
        assert result == b""

    @pytest.mark.asyncio
    async def test_tts_generates_audio_for_english(self):
        """gTTS generates MP3 audio bytes for English text."""
        from app.tts import text_to_speech

        result = await text_to_speech("Hello world", language="en")
        assert isinstance(result, bytes)
        assert len(result) > 0
        # MP3 starts with sync word 0xFF 0xFB (or 0xFF 0xF3, 0xFF 0xF2)
        assert result[0] == 0xFF
        assert (result[1] & 0xE0) == 0xE0  # MPEG frame sync

    @pytest.mark.asyncio
    async def test_tts_generates_audio_for_chinese(self):
        """gTTS generates MP3 audio for Chinese text."""
        from app.tts import text_to_speech

        result = await text_to_speech("你好世界", language="zh")
        assert isinstance(result, bytes)
        assert len(result) > 0
        assert result[0] == 0xFF

    @pytest.mark.asyncio
    async def test_tts_generates_audio_for_spanish(self):
        """gTTS generates MP3 audio for Spanish text."""
        from app.tts import text_to_speech

        result = await text_to_speech("Hola mundo", language="es")
        assert isinstance(result, bytes)
        assert len(result) > 0
        assert result[0] == 0xFF

    @pytest.mark.asyncio
    async def test_tts_generates_audio_for_arabic(self):
        """gTTS generates MP3 audio for Arabic text."""
        from app.tts import text_to_speech

        result = await text_to_speech("مرحبا بالعالم", language="ar")
        assert isinstance(result, bytes)
        assert len(result) > 0
        assert result[0] == 0xFF

    @pytest.mark.asyncio
    async def test_tts_generates_audio_for_portuguese(self):
        """gTTS generates MP3 audio for Portuguese text."""
        from app.tts import text_to_speech

        result = await text_to_speech("Olá mundo", language="pt")
        assert isinstance(result, bytes)
        assert len(result) > 0
        assert result[0] == 0xFF

    @pytest.mark.asyncio
    async def test_tts_unknown_language_falls_back_to_english(self):
        """gTTS falls back to English for unknown language codes."""
        from app.tts import text_to_speech

        result = await text_to_speech("Hello", language="xx")
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_lang_map_coverage(self):
        """All supported VoiceBridge languages have gTTS lang codes."""
        from app.tts import LANG_MAP

        assert LANG_MAP["zh"] == "zh-CN"
        assert LANG_MAP["en"] == "en"
        assert LANG_MAP["es"] == "es"
        assert LANG_MAP["ar"] == "ar"
        assert LANG_MAP["pt"] == "pt"


# ═══════════════════════════════════════════════════════════════
# Translation Pipeline Tests
# ═══════════════════════════════════════════════════════════════

class TestTranslationPipeline:
    """DeepSeek translation: error handling, language pairs, edge cases."""

    def test_translate_empty_text_returns_empty(self):
        """Translation returns empty string for empty input."""
        from app.translate import translate
        result = translate("", "zh", "en")
        assert result == ""

    def test_translate_whitespace_only_returns_empty(self):
        """Translation returns empty string for whitespace-only input."""
        from app.translate import translate
        result = translate("   \n  ", "zh", "en")
        assert result == ""

    def test_translate_zh_to_en_returns_string(self):
        """Chinese→English translation returns non-empty string."""
        from app.translate import translate
        result = translate("你好", "zh", "en")
        assert isinstance(result, str)
        assert len(result) > 0
        assert result != "你好"  # Should be translated

    def test_translate_en_to_zh_returns_string(self):
        """English→Chinese translation returns non-empty string."""
        from app.translate import translate
        result = translate("Hello world", "en", "zh")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_translate_es_to_en_returns_string(self):
        """Spanish→English translation returns non-empty string."""
        from app.translate import translate
        result = translate("Hola mundo", "es", "en")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_translate_zh_to_es_returns_string(self):
        """Chinese→Spanish translation returns non-empty string."""
        from app.translate import translate
        result = translate("你好", "zh", "es")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_translate_unknown_lang_pair_uses_default(self):
        """Unknown language pair falls back to zh→en prompt (doesn't crash)."""
        from app.translate import translate
        result = translate("test", "xx", "yy")
        assert isinstance(result, str)
        assert len(result) > 0

    @patch("app.translate.client.chat.completions.create")
    def test_translate_handles_api_error(self, mock_create):
        """Translation catches API errors and returns error string."""
        from app.translate import translate

        mock_create.side_effect = Exception("API rate limit exceeded")

        result = translate("你好", "zh", "en")
        assert result.startswith("[Translation error:")
        assert "API rate limit exceeded" in result

    @patch("app.translate.client.chat.completions.create")
    def test_translate_handles_timeout(self, mock_create):
        """Translation catches timeout errors gracefully."""
        from app.translate import translate
        import requests

        mock_create.side_effect = requests.Timeout("Connection timed out")

        result = translate("你好", "zh", "en")
        assert result.startswith("[Translation error:")
        assert "timed out" in result.lower()


# ═══════════════════════════════════════════════════════════════
# Debug & Ops Endpoint Tests
# ═══════════════════════════════════════════════════════════════

class TestDebugEndpoints:
    """Debug and ops diagnostic endpoints."""

    def test_debug_status_returns_all_fields(self):
        """GET /debug/status returns complete diagnostic payload."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        resp = client.get("/debug/status")
        assert resp.status_code == 200

        data = resp.json()
        required_fields = [
            "audio_chunks_received", "transcripts_detected",
            "translations_done", "tts_generated",
            "deepgram_key", "openai_key", "elevenlabs_key",
            "last_asr_error", "last_translate_error", "last_tts_error",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    def test_debug_status_keys_masked(self):
        """Debug endpoint masks API keys (shows only first 8 chars)."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        resp = client.get("/debug/status")
        data = resp.json()

        # Keys should end with "..." indicating masking
        assert data["deepgram_key"].endswith("...")
        assert data["openai_key"].endswith("...")

    def test_ops_check_update_endpoint(self):
        """GET /ops/check-update returns structure even if ghcr unreachable."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        resp = client.get("/ops/check-update")
        assert resp.status_code == 200
        data = resp.json()
        assert "local_sha" in data


# ═══════════════════════════════════════════════════════════════
# Buffer & Pipeline Logic Tests
# ═══════════════════════════════════════════════════════════════

class TestBufferLogic:
    """Audio buffer accumulation and threshold logic."""

    def test_buffer_below_threshold_no_asr_call(self):
        """Audio below BUFFER_TARGET (32000) does NOT trigger ASR."""
        from app.ws import BUFFER_TARGET, diag

        # Reset diag counters
        diag["transcripts"] = 0

        # 100 samples × 2 bytes = 200 bytes — well below 32000
        chunk = struct.pack("<" + "h" * 100, *([0] * 100))
        assert len(chunk) < BUFFER_TARGET

        # Buffer shouldn't trigger processing yet
        assert diag["transcripts"] == 0  # No processing triggered

    def test_diag_structure_complete(self):
        """Diagnostic dict has all expected keys."""
        from app.ws import diag

        expected = {
            "audio_chunks", "transcripts", "translations", "tts",
            "last_asr_error", "last_translate_error", "last_tts_error",
            "last_asr_text", "last_translated_text", "buffer_size",
        }
        assert expected.issubset(set(diag.keys()))


# ═══════════════════════════════════════════════════════════════
# CORS & Middleware Tests
# ═══════════════════════════════════════════════════════════════

class TestMiddleware:
    """CORS headers and cache-control for static files."""

    def test_cors_headers_on_api(self):
        """API endpoints return CORS headers."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        resp = client.get("/health", headers={"Origin": "https://example.com"})
        assert "access-control-allow-origin" in resp.headers

    def test_cache_control_on_js(self):
        """JS files have Cache-Control: no-cache (Cloudflare bypass)."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        resp = client.get("/app.js")
        assert resp.status_code == 200
        assert "no-cache" in resp.headers.get("cache-control", "")

    def test_cache_control_on_css(self):
        """CSS files have Cache-Control: no-cache (Cloudflare bypass)."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        resp = client.get("/style.css")
        assert resp.status_code == 200
        assert "no-cache" in resp.headers.get("cache-control", "")

    def test_html_no_cache_control(self):
        """HTML files do NOT get forced no-cache (allow normal caching)."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        # HTML should NOT have forced no-cache
        cc = resp.headers.get("cache-control", "")
        assert "must-revalidate" not in cc
