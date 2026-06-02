# REQ-002: VoiceBridge v2 — 单人翻译器

> **版本：** v2.0
> **上一版本：** REQ-001 (MVP，已废弃)
> **状态：** ✅ 老大确认

---

## 背景

v1 要求创建会话、分享 ID、双方加入，操作太复杂。v2 改为单人模式：打开页面即用。

## 功能描述

### 唯一页面

| 元素 | 说明 |
|------|------|
| 语言选择 | 「我说」下拉 + 「对方说」下拉，默认 中文↔西班牙语 |
| 开始按钮 | 一个大按钮 🎤 开始/停止翻译 |
| 状态指示 | ● 正在听... / ● 翻译中... / ○ 已停止 |
| 当前翻译 | 原文 + 译文 实时显示 |
| 翻译历史 | 最近 20 条，最新在上，自动滚动 |
| 音频输出切换 | 扬声器 / 耳机 切换按钮 |

### 操作流程

1. 打开页面 → 默认中文↔西班牙语已选好
2. 点 🎤 开始 → 浏览器请求麦克风权限
3. 说话 → VAD 检测语音段 → Deepgram 识别 → DeepSeek 翻译 → ElevenLabs 合成语音 → 扬声器播放
4. 对方说话 → 麦克风收音 → 同上流程 → 翻译为中文 → 播放
5. 翻译记录实时显示在历史区
6. 点停止或关闭页面结束

### 不做

- ❌ 会话创建/加入
- ❌ 双人 WebSocket
- ❌ Voice Clone 录制界面
- ❌ 登录/注册

---

## 验收标准

| # | 标准 | 验证方式 |
|---|------|---------|
| 1 | 打开页面看到语言选择 + 开始按钮 | 浏览器 |
| 2 | 点开始后麦克风正常工作 | 浏览器权限弹窗 |
| 3 | 说中文 → 听到西班牙语语音 | 实际说话测试 |
| 4 | 翻译历史实时追加 | 页面观察 |
| 5 | 音频输出切换可用 | 点击按钮切换 |
| 6 | `/health` 返回 200 | curl |

---

## 技术规格

### 路由

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 唯一页面（index.html） |
| `/health` | GET | 健康检查 |
| `/version` | GET | 版本信息 |
| `/ws/translate` | WS | 翻译管线 |

### 删除

| 路由/文件 | 原因 |
|-----------|------|
| `/api/session/*` | 不再需要会话管理 |
| `app/session.py` | 删除 |
| `static/session.html` | 删除 |

### WebSocket 协议

```
客户端 → 服务端:
  {"type": "audio", "data": "<base64 wav>", "source_lang": "zh", "target_lang": "es"}

服务端 → 客户端:
  {"type": "result", "original": "你好", "translated": "Hola", "audio": "<base64 mp3>"}
  {"type": "status", "state": "listening|translating|idle"}
```

---

## 改动清单

| 文件 | 操作 |
|------|------|
| `app/main.py` | 删 session 路由，加 `/ws/translate` |
| `app/session.py` | 删除 |
| `app/ws.py` | 重写为单连接管线 |
| `static/index.html` | 重写为单人 UI |
| `static/session.html` | 删除 |
| `static/app.js` | 重写 |
| `static/style.css` | 更新 |
| `tests/test_app.py` | 更新 |
| `requirements.txt` | 移除 webrtcvad（已完成） |

---

## Sprint 排期

| 任务 | 工时 | 依赖 |
|------|------|------|
| T1: 重写 ws.py（单连接管线） | 30m | - |
| T2: 重写 main.py（删旧路由+新WS） | 15m | T1 |
| T3: 重写 index.html（单人UI） | 30m | - |
| T4: 重写 app.js（单人逻辑） | 30m | T1, T3 |
| T5: 更新 style.css | 15m | T3 |
| T6: 更新测试 | 20m | T1-T5 |
| T7: 构建+推送镜像 | 10m | T6 |
| **合计** | **~2.5h** | |
