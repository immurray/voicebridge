# VoiceBridge — Translation (DeepL, multi-language)
import deepl
from app.config import settings

# DeepL language code mapping
LANG_TO_DEEPL = {
    "zh": "ZH",
    "en": "EN-US",
    "es": "ES",
    "ar": "AR",
    "pt": "PT-BR",
}

_translator = None


def _get_translator() -> deepl.Translator:
    global _translator
    if _translator is None:
        _translator = deepl.Translator(settings.deepl_api_key)
    return _translator


def translate(text: str, source_lang: str, target_lang: str) -> str:
    """Translate text using DeepL API."""
    if not text.strip():
        return ""

    src_code = LANG_TO_DEEPL.get(source_lang)
    tgt_code = LANG_TO_DEEPL.get(target_lang, "EN-US")

    try:
        translator = _get_translator()
        result = translator.translate_text(
            text,
            source_lang=src_code,
            target_lang=tgt_code,
        )
        return result.text.strip()
    except Exception as e:
        return f"[Translation error: {e}]"
