# VoiceBridge — Project Status

> **Last Updated:** 2026-06-02
> **Version:** v2.0 (Solo)
> **Status:** 🟢 v2 开发完成，待部署

## Architecture

```
Browser (Web Audio API) ↔ WebSocket ↔ FastAPI
  → Deepgram ASR → DeepSeek Translate → ElevenLabs TTS → Browser Playback
```

## Quick Start

```bash
cp .env.example .env  # Fill in API keys
docker-compose -f docker/docker-compose.yml up --build
```

## v2 vs v1

| | v1 | v2 |
|---|---|---|
| 模式 | 双人会话 | 单人翻译器 |
| 操作步骤 | 创建会话→分享ID→双方加入 | 打开页面→点开始 |
| 页面数 | 2 | 1 |
| 会话管理 | ✅ | ❌ 删除 |

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | 翻译页面 |
| `/health` | GET | Health check |
| `/version` | GET | Version info |
| `/ws/translate` | WS | Solo audio pipeline |

## Key Files

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI entry |
| `app/ws.py` | WebSocket solo pipeline |
| `app/translate.py` | DeepSeek translation |
| `app/tts.py` | ElevenLabs TTS |
| `app/config.py` | Settings |
| `static/index.html` | Solo UI |
| `static/app.js` | Audio capture + WS client |
| `static/style.css` | Styles |

## Environment Variables

- `DEEPGRAM_API_KEY` — Deepgram API key
- `OPENAI_API_KEY` — DeepSeek/OpenAI-compatible key
- `ELEVENLABS_API_KEY` — ElevenLabs API key
- `BUILD_COMMIT` — Git SHA for version display
