# Phase 0：发现与验证 — VoiceBridge 实时双向语音翻译

> **日期：** 2026-06-01  
> **角色：** PM + Arch 联合审查  
> **状态：** ✅ GO → 进 Step 1

---

## 1. 需求概述

**一句话：** 实时双工语音翻译系统 — 用户说中文，对方听到英文；对方说英文，用户听到中文。保留双方原始音色。

| 维度 | 描述 |
|------|------|
| 场景 | 商务会议、跨国通话、直播互动 |
| 用户 | 需要中英双向沟通的非双语者 |
| 设备 | PC/Mac 浏览器（V1）；移动端（V2） |
| 核心KPI | 端到端延迟 < 1.5s；翻译准确率 > 90%；音色可辨识 |

---

## 2. 技术可行性评估

### 2.1 音频管线

```
用户说话 → 浏览器采集(Web Audio API)
    → WebSocket → 后端
    → [VAD语音活动检测] → 切分语音段
    → [ASR语音识别] → 文本
    → [翻译] → 译文
    → [TTS语音合成] → 音频
    → WebSocket → 浏览器播放(Web Audio API)
    → 对方听到翻译后的语音
```

### 2.2 各环节技术选型

| 环节 | 方案 | 延迟 | 成本 | 评分 |
|------|------|------|------|:--:|
| **ASR** | Deepgram 流式 | ~200ms | $0.0059/min | ⭐⭐⭐⭐⭐ |
| | OpenAI Whisper | ~500ms | $0.006/min | ⭐⭐⭐ |
| | 开源 Whisper(local) | ~800ms | 免费(GPU) | ⭐⭐ |
| **翻译** | GPT-4o-mini | ~300ms | $0.15/M tokens | ⭐⭐⭐⭐⭐ |
| | DeepL API | ~500ms | $25/月 | ⭐⭐⭐ |
| | Claude 4 Haiku | ~200ms | $0.25/M tokens | ⭐⭐⭐⭐ |
| **TTS** | ElevenLabs Turbo | ~200ms(流式) | $0.30/1K字符 | ⭐⭐⭐⭐⭐ |
| | OpenAI TTS | ~400ms | $0.015/1K字符 | ⭐⭐⭐⭐ |
| | Azure Speech | ~300ms | $15/月+用量 | ⭐⭐⭐ |
| **音色保留** | ElevenLabs Voice Clone | 需预录30s+ | 含在TTS中 | ⭐⭐⭐⭐⭐ |
| | OpenVoice(开源) | 即时 | 免费(GPU) | ⭐⭐⭐ |

### 2.3 MVP 推荐方案

```
ASR: Deepgram (流式, 最低延迟)
翻译: GPT-4o-mini (OpenAI 协议, 质量好)
TTS: ElevenLabs Turbo + Voice Clone (音色保留)
通信: FastAPI + WebSocket 全双工
前端: HTML5 Web Audio API + WebSocket
```

### 2.4 延迟分析

| 环节 | 单程延迟 | 备注 |
|------|---------|------|
| 音频采集+传输 | ~100ms | 浏览器缓冲+网络 |
| VAD 切分 | ~50ms | 静音检测 |
| ASR（Deepgram） | ~200ms | 流式实时返回 |
| 翻译（GPT-4o-mini） | ~300ms | 短句，流式 |
| TTS（ElevenLabs流式） | ~200ms | 边生成边播放 |
| 音频传输+播放 | ~50ms | |
| **总计** | **~900ms** | 可满足1.5s KPI |

---

## 3. 架构选型

```
[浏览器A]                    [服务器]                    [浏览器B]
Web Audio API  ──WebSocket──► FastAPI  ──WebSocket──► Web Audio API
  ▲ 采集                      │  VAD                     播放 ▼
  │                           │  ASR (Deepgram)              │
  ▼ 播放                      │  翻译 (GPT-4o-mini)          ▲ 采集
Web Audio API ◄──WebSocket──  │  TTS (ElevenLabs) ◄──WebSocket── Web Audio API
```

**关键设计决策：**
- 两个 WebSocket 通道各自独立（A→B 和 B→A 不干扰）
- VAD 在前端做轻量检测，后端做精确切分
- WebSocket 支持二进制帧传音频（减少 base64 开销）
- 全双工：A 和 B 可同时说话，各自管线独立

---

## 4. 音色保留方案

### ElevenLabs Voice Clone

**流程：**
1. 用户首次使用时录制 30-60 秒语音样本
2. 调用 ElevenLabs `POST /v1/voices/add` 创建 voice profile
3. 后续 TTS 调用指定 `voice_id`
4. 生成的语音保留用户原始音色特征

**成本：** ElevenLabs 个人版 $5/月（30K字符），Creator 版 $22/月（100K字符）

**限制：** 需要提前录制样本；Voice Clone 需要 ElevenLabs 账户

### 降级方案

如果音色保留不可用 → 使用 ElevenLabs 预置的多语言自然声音（11个英文声音可选）

---

## 5. 成本估算

### 月均成本（按每天1小时通话估算）

| 服务 | 单价 | 月量 | 月成本 |
|------|------|------|--------|
| Deepgram ASR | $0.0059/min | 60min×30天=1800min | $10.62 |
| GPT-4o-mini 翻译 | $0.15/M input tokens | ~300K tokens | $0.05 |
| ElevenLabs TTS | $0.30/1K字符 | ~90K字符(45K输入+45K输出) | $27 |
| 服务器 | VPS $5-10/月 | | $10 |
| **合计** | | | **~$48/月** |

### ElevenLabs Creator 计划更划算

| 计划 | 月费 | 包含字符 | 超量单价 |
|------|------|----------|---------|
| Starter | $5 | 30K | $0.30/1K |
| **Creator** | **$22** | **100K** | $0.30/1K |
| Pro | $99 | 500K | $0.24/1K |

---

## 6. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|:--:|:--:|------|
| 延迟超标(>1.5s) | 中 | 高 | 流式处理；前端预缓冲；WebSocket优化 |
| 音色克隆不准 | 中 | 中 | 降级使用预置声音 |
| Deepgram 不支持中文 | 低 | 中 | 切换 Whisper 降级 |
| 浏览器兼容性 | 中 | 中 | Chrome/Firefox 优先；Safari 测试 |
| 网络抖动 | 高 | 中 | Jitter buffer；丢帧降级 |
| 成本超预期 | 低 | 低 | 用量监控+限流 |

---

## 7. Gate 决策

| # | 检查项 | 证据 | 状态 |
|---|--------|------|:--:|
| 1 | 需求解决什么问题？ | 中英实时双向沟通 | ✅ |
| 2 | 有现成方案可复用？ | 无；全新项目 | ✅ |
| 3 | 技术阻塞风险？ | 音色克隆需预录样本；总体可行 | ✅ |
| 4 | 改动范围？ | 新项目；3-4个核心模块 | ✅ |
| 5 | 兼容性？ | 新项目；无迁移问题 | ✅ |

**Go / No-Go / Need More：** 🟢 **GO** → 进 Step 1 需求文档

---

## 8. 该项目名：VoiceBridge

> 桥接两种语言，保留你的声音。
