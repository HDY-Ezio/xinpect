#!/bin/bash
# ============================================================
# 煋鉴 Xinpect - 容器启动入口
# 自动处理 SSL 证书，同时启动 nginx 和 gunicorn
# ============================================================
set -e

echo "=========================================="
echo " 煋鉴 Xinpect 启动中..."
echo "=========================================="

# 1. 确保数据目录存在
mkdir -p /data/db /data/reports /data/logs /data/uploads /var/log/xinpect

# 2. SSL 证书处理
CERT_DIR="/etc/letsencrypt/live/xinpect.xingwangzhineng.com"
CERT_FILE="$CERT_DIR/fullchain.pem"
KEY_FILE="$CERT_DIR/privkey.pem"

if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
    echo "[启动] 未检测到 SSL 证书，生成自签名证书..."
    mkdir -p "$CERT_DIR"
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -keyout "$KEY_FILE" \
        -out "$CERT_FILE" \
        -subj "/CN=xinpect.xingwangzhineng.com/O=Xinpect/C=CN" 2>/dev/null
    echo "[启动] 自签名证书已生成（浏览器会提示不安全，生产环境请替换为正式证书）"
fi

# 3. 检查 nginx 配置
echo "[启动] 检查 nginx 配置..."
nginx -t 2>&1

# 4. 启动 nginx
echo "[启动] 启动 nginx..."
nginx

# 5. 启动 Flask 应用（生产环境使用 gunicorn）
WORKERS=${GUNICORN_WORKERS:-2}
THREADS=${GUNICORN_THREADS:-2}

echo "[启动] 启动 gunicorn (workers=${WORKERS}, threads=${THREADS}, port=${PORT:-8621})..."
echo "=========================================="
echo " 煋鉴 Xinpect 已就绪"
echo " HTTP:  端口 80"
echo " HTTPS: 端口 443"
echo " Flask: 端口 ${PORT:-8621}"
echo "=========================================="

exec gunicorn app:app \
    --bind "127.0.0.1:${PORT:-8621}" \
    --workers "${WORKERS}" \
    --threads "${THREADS}" \
    --timeout 300 \
    --keep-alive 5 \
    --access-logfile /data/logs/access.log \
    --error-logfile /data/logs/error.log \
    --log-level info
