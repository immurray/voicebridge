# VoiceBridge — ElevenLabs TTS + Voice Clone
from app.config import settings

# Default voices per language (fallback when no cloned voice)
DEFAULT_VOICES = {
    "en": "21m00Tcm4TlvDq8ikWAM",  # Rachel (natural American English)
    "zh": "EXAVITQu4vr4xnSDxMaL",  # Bella (warm female, decent Chinese)
}


def _get_el_client():
    from elevenlabs import ElevenLabs
    return ElevenLabs(api_key=settings.elevenlabs_api_key)


def get_default_voice_id(language: str) -> str:
    return DEFAULT_VOICES.get(language, DEFAULT_VOICES["en"])


def create_cloned_voice(name: str, audio_samples_path: str) -> str | None:
    try:
        client = _get_el_client()
        with open(audio_samples_path, "rb") as f:
            voice = client.clone(name=name, files=[f])
        return voice.voice_id
    except Exception as e:
        print(f"[Voice Clone Error] {e}")
        return None


def text_to_speech(text: str, voice_id: str = "", language: str = "en") -> bytes:
    if not text.strip():
        return b""

    vid = voice_id or get_default_voice_id(language)

    try:
        client = _get_el_client()
        audio_generator = client.text_to_speech.convert_as_stream(
            voice_id=vid,
            model_id="eleven_turbo_v2_5",
            text=text,
            output_format="pcm_16000",
        )

        audio_bytes = b""
        for chunk in audio_generator:
            if chunk:
                audio_bytes += chunk

        return _pcm_to_wav(audio_bytes, sample_rate=16000)

    except Exception as e:
        print(f"[TTS Error] {e}")
        return b""


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
