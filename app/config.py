# VoiceBridge Config
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    # Deepgram ASR
    deepgram_api_key: str = field(default_factory=lambda: os.getenv("DEEPGRAM_API_KEY", ""))

    # DeepL Translation
    deepl_api_key: str = field(default_factory=lambda: os.getenv("DEEPL_API_KEY", ""))

    # ElevenLabs TTS
    elevenlabs_api_key: str = field(default_factory=lambda: os.getenv("ELEVENLABS_API_KEY", ""))

    # Server
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))

    # Session
    session_ttl_hours: int = field(default_factory=lambda: int(os.getenv("SESSION_TTL_HOURS", "24")))

    # Audio
    sample_rate: int = 16000
    vad_silence_threshold_ms: int = 500  # VAD 静音阈值
    chunk_duration_ms: int = 200          # 音频块大小


settings = Settings()
