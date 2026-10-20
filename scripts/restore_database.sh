#!/bin/bash
# ============================================================================
# 煋鉴数据库恢复脚本 v1.0
# 用途：从备份文件恢复 SQLite 数据库
# 部署位置：/opt/xinpect-website/scripts/restore_database.sh
# 用法：sudo bash restore_database.sh <备份文件路径> [--yes]
# ============================================================================
set -uo pipefail

# ======================== 配置 ========================
DB_PATH="/opt/xinpect-website/xinpect.db"
DB_BACKUP_PATH="/opt/xinpect-website/backups/database"
LOG_DIR="/opt/xinpect-website/logs"
WEBSITE_SERVICE="xinpect-website"

# ======================== 颜色 ========================
RED='\033[0;31m'; GREEN_C='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN_C}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $*"; }
warn() { echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️${NC} $*"; }
fail() { echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ❌${NC} $*"; }
info() { echo -e "${CYAN}[$(date '+%Y-%m-%d %H:%M:%S')] ℹ️${NC} $*"; }

# ======================== 帮助信息 ========================
show_help() {
    echo "煋鉴数据库恢复工具 v1.0"
    echo ""
    echo "用法: sudo bash $0 <备份文件路径> [--yes]"
    echo "      sudo bash $0 --list              # 列出可用备份"
    echo "      sudo bash $0 --latest            # 恢复最新备份"
    echo ""
    echo "示例:"
    echo "  $0 /opt/xinpect-website/backups/database/xinpect_backup_20261016_020000.db.gz"
    echo "  $0 --latest --yes                    # 自动确认恢复最新备份"
    echo ""
    echo "参数:"
    echo "  --list      列出所有可用备份"
    echo "  --latest    使用最新的备份文件"
    echo "  --yes       跳过确认提示，直接恢复"
    echo ""
}

# ======================== 参数处理 ========================
if [[ $# -lt 1 ]]; then
    show_help
    exit 1
fi

AUTO_CONFIRM=false
BACKUP_FILE=""

# 解析参数
while [[ $# -gt 0 ]]; do
    case "$1" in
        --list)
            echo "=== 可用备份列表 ==="
            if [[ -d "$DB_BACKUP_PATH" ]]; then
                ls -lht "${DB_BACKUP_PATH}"/xinpect_backup_*.db.gz 2>/dev/null || echo "无备份文件"
            else
                echo "备份目录不存在: $DB_BACKUP_PATH"
            fi
            exit 0
            ;;
        --latest)
            BACKUP_FILE=$(ls -1t "${DB_BACKUP_PATH}"/xinpect_backup_*.db.gz 2>/dev/null | head -1)
            if [[ -z "$BACKUP_FILE" ]]; then
                fail "未找到任何备份文件"
                exit 1
            fi
            info "最新备份: $BACKUP_FILE"
            shift
            ;;
        --yes)
            AUTO_CONFIRM=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            BACKUP_FILE="$1"
            shift
            ;;
    esac
done

# ======================== 前置检查 ========================
if [[ -z "$BACKUP_FILE" ]]; then
    fail "请指定备份文件路径"
    show_help
    exit 1
fi

if [[ ! -f "$BACKUP_FILE" ]]; then
    fail "备份文件不存在: $BACKUP_FILE"
    exit 1
fi

# 检查是否为 root 用户
if [[ $EUID -ne 0 ]]; then
    fail "请使用 sudo 运行此脚本"
    exit 1
fi

mkdir -p "$LOG_DIR"

# ======================== 显示恢复信息 ========================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${RED}  ⚠️  警告：即将恢复数据库！${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  备份文件: $BACKUP_FILE"
echo "  备份大小: $(du -h "$BACKUP_FILE" | cut -f1)"
echo "  备份时间: $(stat -c %y "$BACKUP_FILE" 2>/dev/null | cut -d. -f1)"
echo "  目标路径: $DB_PATH"
echo "  当前大小: $(du -h "$DB_PATH" 2>/dev/null | cut -f1 || echo '不存在')"
echo ""

# MD5 校验
MD5_FILE="${BACKUP_FILE%.db.gz}.md5"
if [[ -f "$MD5_FILE" ]]; then
    log "验证备份文件完整性..."
    if md5sum -c "$MD5_FILE" &>/dev/null; then
        log "MD5 校验通过 ✅"
    else
        fail "MD5 校验失败！备份文件可能已损坏"
        exit 1
    fi
fi

# 确认操作
if [[ "$AUTO_CONFIRM" != "true" ]]; then
    echo -e "${RED}此操作将覆盖当前数据库，且不可撤销！${NC}"
    read -p "确认恢复? (输入 yes 继续): " CONFIRM
    if [[ "$CONFIRM" != "yes" ]]; then
        echo "已取消恢复操作"
        exit 0
    fi
fi

# ======================== 开始恢复 ========================
log "=========================================="
log "开始恢复数据库"
log "=========================================="

# Step 1: 停止网站服务
log "Step 1/5: 停止网站服务..."
if systemctl is-active --quiet "$WEBSITE_SERVICE" 2>/dev/null; then
    systemctl stop "$WEBSITE_SERVICE"
    log "已停止 $WEBSITE_SERVICE"
else
    warn "服务未运行或不存在，继续..."
fi

# Step 2: 备份当前数据库（恢复前再备一次）
if [[ -f "$DB_PATH" ]]; then
    PRE_RESTORE_BACKUP="/tmp/xinpect_pre_restore_$(date +%Y%m%d_%H%M%S).db.gz"
    log "Step 2/5: 备份当前数据库到 $PRE_RESTORE_BACKUP..."
    gzip -c "$DB_PATH" > "$PRE_RESTORE_BACKUP"
    log "恢复前备份已保存（如需回滚: gunzip -c $PRE_RESTORE_BACKUP > $DB_PATH）"
else
    log "Step 2/5: 当前数据库不存在，跳过备份"
fi

# Step 3: 解压备份文件
TEMP_RESTORE="/tmp/xinpect_restore_${DATE}.db"
log "Step 3/5: 解压备份文件..."
gunzip -c "$BACKUP_FILE" > "$TEMP_RESTORE"
if [[ $? -ne 0 ]]; then
    fail "解压失败"
    rm -f "$TEMP_RESTORE"
    # 重启服务
    systemctl start "$WEBSITE_SERVICE" 2>/dev/null || true
    exit 1
fi

# Step 4: 验证解压后的数据库完整性
log "Step 4/5: 验证备份数据库完整性..."
if command -v sqlite3 &>/dev/null; then
    INTEGRITY=$(sqlite3 "$TEMP_RESTORE" "PRAGMA integrity_check;" 2>&1)
    if [[ "$INTEGRITY" != "ok" ]]; then
        fail "备份数据库完整性检查失败: $INTEGRITY"
        rm -f "$TEMP_RESTORE"
        systemctl start "$WEBSITE_SERVICE" 2>/dev/null || true
        exit 1
    fi
    log "完整性检查: ✅ OK"
    
    # 显示备份中的记录数
    TABLE_COUNT=$(sqlite3 "$TEMP_RESTORE" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>/dev/null || echo "?")
    log "备份中表数量: $TABLE_COUNT"
else
    warn "sqlite3 未安装，跳过完整性检查"
fi

# Step 5: 替换数据库文件并重启
log "Step 5/5: 替换数据库文件..."
cp "$TEMP_RESTORE" "$DB_PATH"
chown www-data:www-data "$DB_PATH" 2>/dev/null || true
chmod 644 "$DB_PATH" 2>/dev/null || true
rm -f "$TEMP_RESTORE"

log "重启网站服务..."
if systemctl list-unit-files | grep -q "$WEBSITE_SERVICE"; then
    systemctl start "$WEBSITE_SERVICE"
    sleep 3
    if systemctl is-active --quiet "$WEBSITE_SERVICE"; then
        log "服务已重启 ✅"
    else
        fail "服务重启失败！请检查日志: journalctl -u $WEBSITE_SERVICE -n 50"
    fi
else
    warn "服务 $WEBSITE_SERVICE 未注册，请手动启动"
fi

# ======================== 完成 ========================
echo ""
log "=========================================="
log "数据库恢复完成 ✅"
log "=========================================="
log "恢复自: $BACKUP_FILE"
log "恢复到: $DB_PATH"
log ""
log "如需回滚本次恢复:"
log "  gunzip -c $PRE_RESTORE_BACKUP > $DB_PATH"
log "  systemctl restart $WEBSITE_SERVICE"
log "=========================================="

exit 0
