# VoiceBridge — Translation (Gemini Flash via OpenAI-compatible API)
from openai import OpenAI
from app.config import settings

LANG_NAMES = {
    "zh": "Chinese",
    "en": "English",
    "es": "Spanish",
    "ar": "Arabic",
    "pt": "Portuguese",
}

client = OpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
)


def translate(text: str, source_lang: str, target_lang: str) -> str:
    """Translate via Gemini Flash (OpenAI-compatible endpoint)."""
    if not text.strip():
        return ""

    src_name = LANG_NAMES.get(source_lang, source_lang)
    tgt_name = LANG_NAMES.get(target_lang, target_lang)

    prompt = (
        f"Translate the following {src_name} to {tgt_name}. "
        f"Keep it brief and conversational. Only return the translation, nothing else.\n\n"
        f'{src_name}: "{text}"\n{tgt_name}:'
    )

    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[Translation error: {e}]"
