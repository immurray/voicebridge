# VoiceBridge — Deepgram ASR Integration
from app.config import settings

# Language mapping
LANG_MAP = {
    "zh": "zh-CN",
    "en": "en-US",
}


def _get_dg_client():
    from deepgram import DeepgramClient
    return DeepgramClient(settings.deepgram_api_key)


def _get_live_options(language: str):
    from deepgram import LiveOptions
    return LiveOptions(
        model="nova-2",
        language=LANG_MAP.get(language, "zh-CN"),
        smart_format=True,
        interim_results=True,
        endpointing=500,
        encoding="linear16",
        sample_rate=settings.sample_rate,
        channels=1,
    )
