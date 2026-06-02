# VoiceBridge v2 Tests
import pytest


def test_imports():
    """Test that all modules can be imported."""
    from app.config import Settings
    from app.ws import router


def test_config_defaults():
    """Test config default values."""
    from app.config import Settings
    s = Settings()
    assert s.sample_rate == 16000
    assert s.port == 8000


def test_translate_empty():
    """Test translation handles empty input."""
    try:
        from app.translate import translate
    except ImportError:
        pytest.skip("openai SDK not installed")
    result = translate("", "zh", "en")
    assert result == ""


def test_translate_zh_en():
    """Test Chinese to English translation."""
    try:
        from app.translate import translate
    except ImportError:
        pytest.skip("openai SDK not installed")
    result = translate("你好", "zh", "en")
    assert isinstance(result, str)
    assert len(result) > 0


def test_health():
    """Test health endpoint."""
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["version"] == "0.2.0"


def test_version():
    """Test version endpoint."""
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.get("/version")
    assert resp.status_code == 200
    assert "version" in resp.json()


def test_pcm_to_wav():
    """Test PCM to WAV conversion."""
    import struct

    def pcm_to_wav(pcm_bytes, sample_rate=16000):
        num_samples = len(pcm_bytes) // 2
        wav_header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF", 36 + len(pcm_bytes), b"WAVE", b"fmt ",
            16, 1, 1, sample_rate, sample_rate * 2, 2, 16,
            b"data", len(pcm_bytes),
        )
        return wav_header + pcm_bytes

    pcm = struct.pack("<" + "h" * 160, *([0] * 160))
    wav = pcm_to_wav(pcm)
    assert wav[:4] == b"RIFF"
    assert len(wav) == 44 + len(pcm)


def test_no_session_routes():
    """Test v2 has no session routes."""
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.post("/api/session/create", json={"language": "zh"})
    assert resp.status_code in (404, 405)  # Session routes removed


def test_static_served():
    """Test static files are served."""
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "VoiceBridge" in resp.text
