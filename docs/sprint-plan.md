# Sprint 计划 — VoiceBridge MVP

> **日期：** 2026-06-01  
> **角色：** EM  
> **状态：** ✅ 已排期，进开发  
> **依赖：** REQ-001（已确认）

---

## 1. 任务拆解

| ID | 任务 | 估时 | 依赖 | 角色 |
|----|------|:--:|------|:--:|
| T1 | 项目骨架：Docker + FastAPI + 目录结构 | 0.5d | — | Dev |
| T2 | WebSocket 通信层（前端↔后端双工） | 1d | T1 | Dev |
| T3 | 前端页面：会话创建/加入、对话界面 | 1d | T2 | Dev |
| T4 | VAD 语音活动检测（前端+后端） | 0.5d | T2 | Dev |
| T5 | Deepgram ASR 集成（流式识别） | 1d | T4 | Dev |
| T6 | GPT-4o 翻译集成（中↔英） | 0.5d | T5 | Dev |
| T7 | ElevenLabs TTS + Voice Clone 集成 | 1d | T6 | Dev |
| T8 | 会话管理（创建/加入/链接分享） | 0.5d | T3 | Dev |
| T9 | 端到端联调测试 | 0.5d | T7+T8 | QA |
| T10 | 部署上线 | 0.5d | T9 | Ops |

**总估时：6.5 天**

## 2. 依赖关系

```
T1（骨架）
  └→ T2（WebSocket）
       ├→ T3（前端页面）
       │    └→ T8（会话管理）
       └→ T4（VAD）
            └→ T5（ASR）
                 └→ T6（翻译）
                      └→ T7（TTS+音色）
                           └→ T9（联调测试）
                                └→ T10（部署）
```

### 并行机会

- T3（前端页面）和 T4（VAD）可并行（都依赖 T2）
- T8（会话管理）和 T4-T5-T6 可并行（T8 依赖 T3 不依赖音频管线）

## 3. 里程碑

| 里程碑 | 任务 | 预计完成 | 产出 |
|--------|------|----------|------|
| M1: 骨架+通信 | T1, T2 | Day 1.5 | WebSocket echo 通 |
| M2: 音频管线 | T4, T5, T6 | Day 4 | ASR→翻译→TTS 跑通 |
| M3: 前端+会话 | T3, T8 | Day 3 | 页面可创建/加入会话 |
| M4: 音色克隆 | T7 | Day 5 | 完整翻译+音色保留 |
| M5: 上线 | T9, T10 | Day 6.5 | 生产环境可用 |

## 4. 技术栈确认

| 层 | 选择 | 版本 |
|----|------|------|
| 后端框架 | FastAPI | latest |
| WebSocket | FastAPI WebSocket | — |
| ASR | Deepgram SDK | latest |
| 翻译 | OpenAI SDK (GPT-4o-mini) | latest |
| TTS | ElevenLabs SDK | latest |
| 容器化 | Docker + Docker Compose | — |
| 部署 | 单容器，复用 apptopup 服务器 | — |

## 5. 项目结构

```
voicebridge/
├── app/
│   ├── main.py           # FastAPI 入口
│   ├── ws.py             # WebSocket handler
│   ├── asr.py            # Deepgram 集成
│   ├── translate.py      # GPT-4o 翻译
│   ├── tts.py            # ElevenLabs TTS+Clone
│   ├── vad.py            # 语音活动检测
│   ├── session.py        # 会话管理
│   └── config.py         # 配置
├── static/
│   ├── index.html        # 主页
│   ├── session.html      # 对话页面
│   ├── style.css         # 样式
│   └── app.js            # 前端逻辑
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── docs/
│   ├── phase0-discovery.md
│   └── reqs/
│       └── req-001-voicebridge-mvp.md
├── requirements.txt
└── .env.example
```

## 6. 风险

| 风险 | 缓解 |
|------|------|
| ElevenLabs Voice Clone API 调不通 | 降级使用预置声音（不阻塞主流程） |
| Deepgram 中文识别差 | 切换 Whisper API 备选 |
| WebSocket 双工音频回声 | 前端 AudioContext 精确控制播放/录制时序 |

## 7. Step 2 Quality Gate

| # | 检查项 | 状态 |
|---|--------|:--:|
| 1 | 任务拆到可独立验证粒度 | ✅ |
| 2 | 每任务有验收标准 | ✅ |
| 3 | 依赖关系清晰 | ✅ |
| 4 | 风险已识别 | ✅ |
| 5 | 老大已点头 | ✅（"好"） |
