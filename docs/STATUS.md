# VoiceBridge — Project Status

> **Last Updated:** 2026-06-01  
> **Commit:** TBD  
> **Status:** 🟢 MVP 开发完成，待部署

## Architecture

```
Browser (Web Audio API) ↔ WebSocket ↔ FastAPI
  → Deepgram ASR → GPT-4o-mini Translate → ElevenLabs TTS
```

## Quick Start

```bash
cp .env.example .env  # Fill in API keys
docker-compose -f docker/docker-compose.yml up --build
```

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/version` | GET | Version info |
| `/api/session/create` | POST | Create session |
| `/api/session/join/{sid}` | POST | Join session |
| `/api/session/{sid}` | GET | Session info |
| `/ws/{session_id}/{peer_id}` | WS | Audio pipeline |

## Key Files

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI entry + routes |
| `app/ws.py` | WebSocket + ASR→Translate→TTS pipeline |
| `app/asr.py` | Deepgram voice recognition |
| `app/translate.py` | GPT-4o-mini translation |
| `app/tts.py` | ElevenLabs TTS + voice clone |
| `app/session.py` | Session CRUD |
| `static/app.js` | Frontend Web Audio API + VAD |
| `static/session.html` | Call page |

## Known Limitations

- Deepgram uses REST (not live streaming) per audio chunk — adds ~200ms latency
- Voice Clone requires manual sample upload (not yet in UI)
- No auth/rate limiting
- In-memory session storage (lost on restart)

## Environment Variables

- `DEEPGRAM_API_KEY` — Deepgram API key
- `OPENAI_API_KEY` — OpenAI/OpenAI-compatible key
- `ELEVENLABS_API_KEY` — ElevenLabs API key
- `BUILD_COMMIT` — Git SHA for version display
