#!/bin/bash
# ============================================================================
# 煋鉴数据库自动备份脚本 v1.0
# 数据库类型：SQLite（/opt/xinpect-website/xinpect.db）
# 备份策略：每天凌晨2点全量备份，保留7天，gzip压缩
# 部署位置：/opt/xinpect-website/scripts/backup_database.sh
# ============================================================================
set -uo pipefail

# ======================== 配置 ========================
DB_PATH="/opt/xinpect-website/xinpect.db"
BACKUP_DIR="/opt/xinpect-website/backups/database"
LOG_DIR="/opt/xinpect-website/logs"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/xinpect_backup_${DATE}.db.gz"
CHECKSUM_FILE="${BACKUP_DIR}/xinpect_backup_${DATE}.md5"
RETENTION_DAYS=7
MIN_SIZE_KB=1  # 最小备份文件大小（KB），低于此值告警

# ======================== 颜色 ========================
RED='\033[0;31m'; GREEN_C='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN_C}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $*"; }
warn() { echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️${NC} $*"; }
fail() { echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ❌${NC} $*"; }

# ======================== 前置检查 ========================
# 检查数据库文件是否存在
if [[ ! -f "$DB_PATH" ]]; then
    fail "数据库文件不存在: $DB_PATH"
    exit 1
fi

# 检查磁盘空间（至少需要500MB可用）
AVAILABLE_MB=$(df -m "$(dirname "$BACKUP_DIR")" | tail -1 | awk '{print $4}')
if [[ "$AVAILABLE_MB" -lt 500 ]]; then
    fail "磁盘空间不足: 剩余 ${AVAILABLE_MB}MB，需要至少 500MB"
    exit 1
fi

# ======================== 创建目录 ========================
mkdir -p "${BACKUP_DIR}" "${LOG_DIR}"

# ======================== 开始备份 ========================
log "=========================================="
log "煋鉴数据库备份开始"
log "=========================================="

# 记录源文件大小
DB_SIZE=$(du -h "$DB_PATH" | cut -f1)
log "数据库文件: $DB_PATH"
log "数据库大小: $DB_SIZE"

# 使用 sqlite3 的 .backup 命令进行热备份（不锁库，不影响在线服务）
TEMP_BACKUP="/tmp/xinpect_backup_${DATE}.db"

if command -v sqlite3 &>/dev/null; then
    log "使用 sqlite3 .backup 进行一致性热备份..."
    sqlite3 "$DB_PATH" ".backup '${TEMP_BACKUP}'"
    if [[ $? -ne 0 ]]; then
        fail "sqlite3 .backup 失败，降级为文件拷贝"
        cp "$DB_PATH" "$TEMP_BACKUP"
    fi
else
    log "sqlite3 未安装，使用文件拷贝（VACUUM-safe copy）..."
    # 使用 cp 拷贝，对于 SQLite 在写操作间隙拷贝是安全的
    cp "$DB_PATH" "$TEMP_BACKUP"
fi

# 验证临时备份完整性
if [[ ! -f "$TEMP_BACKUP" ]]; then
    fail "临时备份文件创建失败"
    exit 1
fi

# 用 sqlite3 验证备份文件完整性
if command -v sqlite3 &>/dev/null; then
    INTEGRITY=$(sqlite3 "$TEMP_BACKUP" "PRAGMA integrity_check;" 2>&1)
    if [[ "$INTEGRITY" != "ok" ]]; then
        fail "备份文件完整性检查失败: $INTEGRITY"
        rm -f "$TEMP_BACKUP"
        exit 1
    fi
    log "备份完整性检查: ✅ OK"
fi

# 压缩备份
log "压缩备份文件..."
gzip -c "$TEMP_BACKUP" > "$BACKUP_FILE"
rm -f "$TEMP_BACKUP"

# 生成MD5校验和
md5sum "$BACKUP_FILE" > "$CHECKSUM_FILE"

# ======================== 验证备份 ========================
if [[ ! -f "$BACKUP_FILE" ]]; then
    fail "备份文件创建失败: $BACKUP_FILE"
    exit 1
fi

BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
BACKUP_SIZE_KB=$(du -k "$BACKUP_FILE" | cut -f1)

log "备份成功: $BACKUP_FILE"
log "备份大小: $BACKUP_SIZE (压缩后)"
log "MD5校验: $(cat "$CHECKSUM_FILE" | cut -d' ' -f1)"

# 检查备份大小是否合理
if [[ "$BACKUP_SIZE_KB" -lt "$MIN_SIZE_KB" ]]; then
    warn "备份文件异常偏小: ${BACKUP_SIZE_KB}KB < ${MIN_SIZE_KB}KB"
fi

# ======================== 清理旧备份 ========================
log "清理${RETENTION_DAYS}天前的备份..."
DELETED_COUNT=$(find "${BACKUP_DIR}" -name "xinpect_backup_*.db.gz" -mtime +${RETENTION_DAYS} | wc -l)
find "${BACKUP_DIR}" -name "xinpect_backup_*.db.gz" -mtime +${RETENTION_DAYS} -delete
find "${BACKUP_DIR}" -name "xinpect_backup_*.md5" -mtime +${RETENTION_DAYS} -delete
log "已清理 ${DELETED_COUNT} 个旧备份"

# ======================== 备份统计 ========================
TOTAL_BACKUPS=$(ls -1 "${BACKUP_DIR}"/xinpect_backup_*.db.gz 2>/dev/null | wc -l)
TOTAL_SIZE=$(du -sh "${BACKUP_DIR}" 2>/dev/null | cut -f1)

log "=========================================="
log "当前备份统计:"
log "  备份总数: ${TOTAL_BACKUPS}"
log "  总占用空间: ${TOTAL_SIZE}"
log "  最新备份: $(ls -1t "${BACKUP_DIR}"/xinpect_backup_*.db.gz 2>/dev/null | head -1)"
log "=========================================="
log "备份完成 ✅"

# ======================== 异地同步（可选） ========================
# 如果硅谷服务器可达，同步备份到异地
REMOTE_BACKUP_DIR="/backup/xinpect"
REMOTE_HOST="root@170.106.137.97"
SSH_KEY="/root/.ssh/id_rsa"
SSH_TIMEOUT=10

if [[ -f "$SSH_KEY" ]]; then
    if ssh -i "$SSH_KEY" -o ConnectTimeout=$SSH_TIMEOUT -o BatchMode=yes "$REMOTE_HOST" "echo ok" &>/dev/null; then
        log "异地同步到硅谷服务器..."
        ssh -i "$SSH_KEY" "$REMOTE_HOST" "mkdir -p ${REMOTE_BACKUP_DIR}"
        rsync -avz -e "ssh -i $SSH_KEY" "$BACKUP_FILE" "$CHECKSUM_FILE" "${REMOTE_HOST}:${REMOTE_BACKUP_DIR}/" 2>&1
        if [[ $? -eq 0 ]]; then
            log "异地同步完成 ✅"
        else
            warn "异地同步失败（本地备份不受影响）"
        fi
    else
        warn "硅谷服务器不可达，跳过异地同步"
    fi
fi

exit 0
