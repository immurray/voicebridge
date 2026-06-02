#!/bin/bash
# ====================================================
# VoiceBridge — 一键部署脚本
# 在 1Panel 终端直接粘贴执行
#
# 前置条件：确保 .env 已就绪（含 API Keys）
# ====================================================

echo "=========================================="
echo "  VoiceBridge 一键部署"
echo "=========================================="

# 1️⃣ 拉取镜像
echo "[1/4] 拉取镜像..."
docker pull ghcr.io/immurray/voicebridge:latest

# 2️⃣ 启动应用
echo "[2/4] 启动 voicebridge..."
docker rm -f voicebridge 2>/dev/null
docker run -d \
  --name voicebridge \
  --restart unless-stopped \
  -p 8000:8000 \
  --env-file $(pwd)/.env \
  ghcr.io/immurray/voicebridge:latest

# 3️⃣ 启动自动更新（Watchtower，如已存在则跳过）
echo "[3/4] 确保自动更新运行中..."
if ! docker ps --format '{{.Names}}' | grep -q '^watchtower$'; then
  docker run -d \
    --name watchtower \
    --restart unless-stopped \
    -v /var/run/docker.sock:/var/run/docker.sock \
    containrrr/watchtower \
    --interval 60 --cleanup
fi

echo ""
echo "✅ 部署完成！"
docker ps | grep -E "(voicebridge|watchtower)"
echo ""
echo "📌 访问地址：http://服务器IP:8000"
echo "📌 健康检查：http://服务器IP:8000/health"
echo "📌 自动更新：已启用（每60秒检查一次）"
echo "📌 以后只需 git push，自动部署"
