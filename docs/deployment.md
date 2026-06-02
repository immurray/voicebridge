# VoiceBridge 部署文档

> **镜像地址：** `ghcr.io/immurray/voicebridge:latest`
> **端口：** `8000`
> **更新方式：** Watchtower 自动拉取（每 60 秒检查）

---

## 前置条件

### 1. 准备 `.env` 文件

```bash
# 在服务器上创建 .env
cat > .env << 'EOF'
# Deepgram ASR
DEEPGRAM_API_KEY=你的key

# DeepSeek 翻译（OpenAI 兼容协议）
OPENAI_API_KEY=sk-你的key
OPENAI_MODEL=deepseek-chat
OPENAI_BASE_URL=https://api.deepseek.com/v1

# ElevenLabs TTS + 音色克隆
ELEVENLABS_API_KEY=你的key

# 服务器
HOST=0.0.0.0
PORT=8000
BUILD_COMMIT=dev

# 会话有效期（小时）
SESSION_TTL_HOURS=24
EOF
```

### 2. 确保 Docker 已安装

```bash
docker --version  # 需要 20.10+
```

---

## 部署命令

### 一键部署（复制粘贴到 1Panel 终端）

```bash
# 拉取镜像
docker pull ghcr.io/immurray/voicebridge:latest

# 停止旧容器（如果存在）
docker rm -f voicebridge 2>/dev/null

# 启动
docker run -d \
  --name voicebridge \
  --restart unless-stopped \
  -p 8000:8000 \
  --env-file $(pwd)/.env \
  ghcr.io/immurray/voicebridge:latest

# 启动自动更新（如已存在则跳过）
if ! docker ps --format '{{.Names}}' | grep -q '^watchtower$'; then
  docker run -d \
    --name watchtower \
    --restart unless-stopped \
    -v /var/run/docker.sock:/var/run/docker.sock \
    containrrr/watchtower \
    --interval 60 --cleanup
fi
```

---

## 验证

```bash
# 容器状态
docker ps | grep voicebridge

# 健康检查
curl http://localhost:8000/health
# 预期: {"status":"ok"}

# 版本信息
curl http://localhost:8000/version
# 预期: {"version":"...","commit":"..."}
```

---

## 更新流程

代码推到 GitHub → GitHub Actions 自动构建镜像 → Watchtower 自动拉取部署

```bash
# 手动触发更新（如果需要立即生效）
docker pull ghcr.io/immurray/voicebridge:latest
docker rm -f voicebridge
docker run -d \
  --name voicebridge \
  --restart unless-stopped \
  -p 8000:8000 \
  --env-file $(pwd)/.env \
  ghcr.io/immurray/voicebridge:latest
```

---

## 常用命令

```bash
# 查看日志
docker logs -f voicebridge

# 查看最近 50 行
docker logs --tail 50 voicebridge

# 重启
docker restart voicebridge

# 停止
docker stop voicebridge

# 进容器调试
docker exec -it voicebridge /bin/bash
```

---

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/version` | GET | 版本信息 |
| `/api/session/create` | POST | 创建通话会话 |
| `/api/session/join/{sid}` | POST | 加入会话 |
| `/api/session/{sid}` | GET | 查看会话 |
| `/ws/{session_id}/{peer_id}` | WS | 音频管线 |

---

## 架构

```
浏览器 (Web Audio API) ↔ WebSocket ↔ FastAPI:8000
  → Deepgram ASR → DeepSeek 翻译 → ElevenLabs TTS
```
