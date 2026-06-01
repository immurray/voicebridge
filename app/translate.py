# VoiceBridge — Translation (GPT-4o-mini)
from openai import OpenAI
from app.config import settings

client = OpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
)


def translate(text: str, source_lang: str, target_lang: str) -> str:
    """翻译文本 — 中文↔英文双向"""
    if not text.strip():
        return ""

    lang_pair = f"{source_lang}→{target_lang}"

    prompt_map = {
        "zh→en": "Translate the following Chinese to natural, conversational English. "
                  "Keep it brief and natural. Only return the translation, nothing else.\n\n"
                  f'Chinese: "{text}"\nEnglish:',
        "en→zh": "将以下英文翻译成自然地道的中文口语。"
                  "保持简洁自然。只返回翻译结果，不要加任何其他内容。\n\n"
                  f'English: "{text}"\n中文：',
    }

    system_prompt = prompt_map.get(lang_pair, prompt_map["zh→en"])

    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": system_prompt}],
            temperature=0.3,
            max_tokens=200,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[Translation error: {e}]"
