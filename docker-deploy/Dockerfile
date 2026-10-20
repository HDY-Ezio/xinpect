FROM python:3.12-slim

LABEL maintainer="xingwangzhineng.com"
LABEL description="煋鉴 Xinpect - AI代码质量检测平台"

# 阿里云 apt 镜像 + 安装依赖（合并为一步减少层数）
RUN sed -i "s|deb.debian.org|mirrors.aliyun.com|g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i "s|deb.debian.org|mirrors.aliyun.com|g" /etc/apt/sources.list 2>/dev/null || true && \
    apt-get update && apt-get install -y --no-install-recommends \
    git nginx curl ca-certificates openssl && \
    rm -rf /var/lib/apt/lists/*

# 清华 pip 镜像 + Python 依赖
COPY docker-deploy/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r /tmp/requirements.txt

# 创建目录
RUN mkdir -p /opt/xinpect-website /data/db /data/reports /data/logs /data/uploads /var/log/xinpect
WORKDIR /opt/xinpect-website

# 复制代码
COPY app.py .
COPY modules/ modules/
COPY templates/ templates/
COPY static/ static/
COPY scripts/ scripts/

# nginx 配置
COPY docker-deploy/nginx.conf /etc/nginx/sites-available/xinpect
RUN ln -sf /etc/nginx/sites-available/xinpect /etc/nginx/sites-enabled/xinpect && \
    rm -f /etc/nginx/sites-enabled/default

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8621/health || exit 1

COPY docker-deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 80 443
ENTRYPOINT ["/entrypoint.sh"]
