#!/bin/bash
# ============================================================================
# 煋鉴数据库备份系统安装脚本 v1.0
# 用途：一键安装备份系统，配置 crontab 定时任务
# 部署位置：在服务器 154.8.211.17 上执行
# 用法：sudo bash setup_backup.sh
# ============================================================================
set -e

# ======================== 配置 ========================
INSTALL_DIR="/opt/xinpect-website"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_USER="root"

# ======================== 颜色 ========================
GREEN_C='\033[0;32m'; YELLOW='\033[1;33m'; BLUE_C='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${BLUE_C}[$(date '+%H:%M:%S')]${NC} $*"; }
ok()   { echo -e "${GREEN_C}[  ✅]${NC} $*"; }
warn() { echo -e "${YELLOW}[  ⚠️]${NC} $*"; }

# ======================== 前置检查 ========================
if [[ $EUID -ne 0 ]]; then
    echo "请使用 sudo 运行此脚本"
    exit 1
fi

log "=========================================="
log "煋鉴数据库备份系统安装"
log "=========================================="

# ======================== Step 1: 创建目录 ========================
log "Step 1/6: 创建目录结构..."
mkdir -p "${INSTALL_DIR}/backups/database"
mkdir -p "${INSTALL_DIR}/scripts"
mkdir -p "${INSTALL_DIR}/logs"
ok "目录已就绪"

# ======================== Step 2: 复制脚本 ========================
log "Step 2/6: 复制备份脚本..."
cp "$SCRIPT_DIR/backup_database.sh" "${INSTALL_DIR}/scripts/backup_database.sh"
cp "$SCRIPT_DIR/restore_database.sh" "${INSTALL_DIR}/scripts/restore_database.sh"
cp "$SCRIPT_DIR/check_backup.sh" "${INSTALL_DIR}/scripts/check_backup.sh"

chmod +x "${INSTALL_DIR}/scripts/backup_database.sh"
chmod +x "${INSTALL_DIR}/scripts/restore_database.sh"
chmod +x "${INSTALL_DIR}/scripts/check_backup.sh"
ok "脚本已安装并设置可执行权限"

# ======================== Step 3: 配置环境变量 ========================
log "Step 3/6: 配置环境变量..."
ENV_FILE="${INSTALL_DIR}/scripts/.backup_env"
if [[ ! -f "$ENV_FILE" ]]; then
    cat > "$ENV_FILE" << 'EOF'
# 煋鉴数据库备份配置
# 飞书告警 Webhook URL（选填，不填则不发告警）
FEISHU_WEBHOOK_URL=

# 异地备份配置
REMOTE_BACKUP_ENABLED=false
REMOTE_HOST=root@170.106.137.97
REMOTE_BACKUP_DIR=/backup/xinpect
EOF
    warn "请编辑 $ENV_FILE 填入飞书 Webhook URL（可选）"
else
    ok ".backup_env 已存在，跳过"
fi

# ======================== Step 4: 配置 Crontab ========================
log "Step 4/6: 配置定时任务..."
CRON_FILE="/etc/cron.d/xinpect-database-backup"
cat > "$CRON_FILE" << 'EOF'
# 煋鉴数据库备份 - 每天凌晨2点执行
0 2 * * * root /bin/bash -c 'source /opt/xinpect-website/scripts/.backup_env 2>/dev/null; export FEISHU_WEBHOOK_URL; /opt/xinpect-website/scripts/backup_database.sh >> /opt/xinpect-website/logs/database_backup.log 2>&1'

# 煋鉴数据库备份检查 - 每天凌晨3点执行（备份完成后1小时检查）
0 3 * * * root /bin/bash -c 'source /opt/xinpect-website/scripts/.backup_env 2>/dev/null; export FEISHU_WEBHOOK_URL; /opt/xinpect-website/scripts/check_backup.sh >> /opt/xinpect-website/logs/backup_check.log 2>&1'

# 清理备份检查日志 - 保留30天
0 4 * * * root find /opt/xinpect-website/logs -name "backup_check.log" -mtime +30 -exec truncate -s 0 {} \; 2>/dev/null
EOF

chmod 644 "$CRON_FILE"
ok "Crontab 已配置"

# ======================== Step 5: 测试运行 ========================
log "Step 5/6: 测试备份脚本..."
if [[ -f "${INSTALL_DIR}/xinpect.db" ]]; then
    source "$ENV_FILE" 2>/dev/null || true
    export FEISHU_WEBHOOK_URL
    "${INSTALL_DIR}/scripts/backup_database.sh"
    if [[ $? -eq 0 ]]; then
        ok "测试备份成功"
    else
        warn "测试备份失败，请检查日志"
    fi
else
    warn "数据库文件不存在: ${INSTALL_DIR}/xinpect.db"
    warn "请确认数据库路径正确后手动运行: ${INSTALL_DIR}/scripts/backup_database.sh"
fi

# ======================== Step 6: 显示安装结果 ========================
log "Step 6/6: 安装完成"

echo ""
echo "=========================================="
echo -e "${GREEN_C}  ✅ 煋鉴数据库备份系统安装完成${NC}"
echo "=========================================="
echo ""
echo "📁 文件位置:"
echo "  备份脚本: ${INSTALL_DIR}/scripts/backup_database.sh"
echo "  恢复脚本: ${INSTALL_DIR}/scripts/restore_database.sh"
echo "  检查脚本: ${INSTALL_DIR}/scripts/check_backup.sh"
echo "  备份目录: ${INSTALL_DIR}/backups/database/"
echo "  配置文辑: vi $ENV_FILE"
echo ""
echo "📅 定时任务:"
echo "  备份时间: 每天凌晨 2:00"
echo "  检查时间: 每天凌晨 3:00"
echo "  保留策略: 7天"
echo "  查看任务: cat /etc/cron.d/xinpect-database-backup"
echo ""
echo "🔧 常用命令:"
echo "  手动备份: sudo ${INSTALL_DIR}/scripts/backup_database.sh"
echo "  手动恢复: sudo ${INSTALL_DIR}/scripts/restore_database.sh --list"
echo "            sudo ${INSTALL_DIR}/scripts/restore_database.sh --latest"
echo "  检查状态: sudo ${INSTALL_DIR}/scripts/check_backup.sh"
echo "  查看日志: tail -f ${INSTALL_DIR}/logs/database_backup.log"
echo ""
echo "📋 查看定时任务:"
echo "  cat /etc/cron.d/xinpect-database-backup"
echo ""
echo "⚙️  配置告警（可选）:"
echo "  vi $ENV_FILE"
echo "  # 填入飞书 Webhook URL"
echo ""
echo "=========================================="

exit 0
