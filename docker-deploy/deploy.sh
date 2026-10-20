#!/bin/bash
# ============================================================
# 煋鉴 Xinpect - 一键部署脚本
# 用法:
#   首次部署: ./deploy.sh install
#   更新代码: ./deploy.sh update
#   查看状态: ./deploy.sh status
#   查看日志: ./deploy.sh logs
#   停止服务: ./deploy.sh stop
#   备份数据: ./deploy.sh backup
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
ENV_FILE="$SCRIPT_DIR/.env"
BACKUP_DIR="/data/backup/xinpect"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ── 检查依赖 ──
check_deps() {
    if ! command -v docker &>/dev/null; then
        log_error "Docker 未安装，请先安装 Docker"
        exit 1
    fi
    if ! docker compose version &>/dev/null; then
        log_error "Docker Compose 未安装"
        exit 1
    fi
    log_info "Docker $(docker --version | awk '{print $3}') ✓"
    log_info "Docker Compose $(docker compose version --short) ✓"
}

# ── 首次安装 ─
install() {
    log_info "=== 煋鉴 Xinpect 首次部署 ==="
    check_deps

    # 检查 .env 文件
    if [ ! -f "$ENV_FILE" ]; then
        log_warn ".env 文件不存在，从模板创建..."
        cp "$SCRIPT_DIR/.env.example" "$ENV_FILE"
        log_warn "请编辑 $ENV_FILE 填入真实配置后再运行: ./deploy.sh install"
        exit 0
    fi

    # 创建数据目录
    mkdir -p /data/db /data/reports /data/logs /data/uploads /data/backup/xinpect

    # 构建并启动
    log_info "构建 Docker 镜像..."
    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" build --no-cache

    log_info "启动服务..."
    docker compose -f "$COMPOSE_FILE" up -d

    log_info "等待服务就绪..."
    sleep 5

    # 检查健康状态
    if curl -sf http://localhost:8621/health &>/dev/null; then
        log_info "✅ 煋鉴部署成功！"
        log_info "访问地址: http://localhost:8621"
        log_info ""
        log_info "是否同时安装 VS Code 插件？运行: ./deploy.sh install-extension"
    else
        log_warn "服务已启动但健康检查未通过，请稍后检查: ./deploy.sh logs"
    fi

    # 显示状态
    status
}

# ── 更新代码 ──
update() {
    log_info "=== 更新煋鉴代码 ==="

    cd "$PROJECT_DIR"

    log_info "拉取最新代码..."
    # 如果是 git 仓库
    if [ -d "$PROJECT_DIR/.git" ]; then
        git pull --rebase
    fi

    log_info "重新构建镜像..."
    docker compose -f "$COMPOSE_FILE" build

    log_info "重启服务..."
    docker compose -f "$COMPOSE_FILE" up -d

    log_info "清理旧镜像..."
    docker image prune -f

    log_info "✅ 更新完成"
    status
}

# ── 查看状态 ──
status() {
    log_info "=== 服务状态 ==="
    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" ps
    echo ""

    # 健康检查
    if curl -sf http://localhost:8621/health &>/dev/null; then
        log_info "健康检查: ✅ 正常"
    else
        log_error "健康检查: ❌ 失败"
    fi

    # 磁盘使用
    echo ""
    log_info "=== 数据存储 ==="
    du -sh /data/db /data/reports /data/logs 2>/dev/null || true
}

# ── 查看日志 ──
logs() {
    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" logs -f --tail=100 xinpect
}

# ── 停止服务 ──
stop() {
    log_info "停止服务..."
    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" down
    log_info "✅ 服务已停止"
}

# ── 备份数据 ──
backup() {
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_PATH="$BACKUP_DIR/backup_$TIMESTAMP"

    log_info "=== 备份数据 ==="
    mkdir -p "$BACKUP_PATH"

    # 备份数据库
    if [ -f /data/db/xinpect.db ]; then
        cp /data/db/xinpect.db "$BACKUP_PATH/xinpect.db"
        log_info "数据库已备份: $BACKUP_PATH/xinpect.db"
    fi

    # 备份报告
    if [ -d /data/reports ]; then
        tar -czf "$BACKUP_PATH/reports.tar.gz" -C /data reports/
        log_info "报告已备份: $BACKUP_PATH/reports.tar.gz"
    fi

    # 备份 .env（不含敏感信息提示）
    if [ -f "$ENV_FILE" ]; then
        cp "$ENV_FILE" "$BACKUP_PATH/.env"
        log_info "配置已备份: $BACKUP_PATH/.env"
    fi

    # 清理30天前的备份
    find "$BACKUP_DIR" -maxdepth 1 -name "backup_*" -mtime +30 -exec rm -rf {} \;
    log_info "已清理30天前的旧备份"

    log_info "✅ 备份完成: $BACKUP_PATH"
    du -sh "$BACKUP_PATH"
}

# ── 主逻辑 ──
case "${1:-}" in
    install) install ;;
    update)  update ;;
    status)  status ;;
    logs)    logs ;;
    stop)    stop ;;
    backup)  backup ;;
    install-extension) install_extension ;;
    *)
        echo "煋鉴 Xinpect Docker 部署工具"
        echo ""
        echo "用法: $0 <命令>"
        echo ""
        echo "命令:"
        echo "  install  首次部署"
        echo "  update   更新代码并重启"
        echo "  status   查看服务状态"
        echo "  logs     查看实时日志"
        echo "  stop     停止服务"
        echo "  backup   备份数据"
        echo "  install-extension  安装 VS Code 插件"
        echo ""
        exit 1
        ;;
esac

# ── 安装 VS Code 插件 ──
install_extension() {
    VSIX_FILE="$SCRIPT_DIR/xinpect-1.0.0.vsix"
    
    if [ ! -f "$VSIX_FILE" ]; then
        log_error "未找到插件文件: $VSIX_FILE"
        exit 1
    fi
    
    # 检查 VS Code 是否安装
    if ! command -v code &>/dev/null; then
        log_error "未检测到 VS Code CLI (code 命令)"
        log_warn "请先安装 VS Code: https://code.visualstudio.com/"
        exit 1
    fi
    
    log_info "=== 安装煋鉴 VS Code 插件 ==="
    
    # 安装插件
    code --install-extension "$VSIX_FILE" --force
    
    log_info "✅ 插件安装成功！"
    log_info "请在 VS Code 中配置 API Key:"
    log_info "  1. 打开 VS Code"
    log_info "  2. Ctrl+Shift+P → 煋鉴: 检测当前文件"
    log_info "  3. 首次使用会提示输入 API Key（在煋鉴会员中心获取）"
    log_info ""
    log_info "或者手动配置:"
    log_info "  设置 → 搜索 xinpect → 填入 API Key 和服务器地址"
}
