#!/bin/bash
# ============================================================================
# 煋鉴数据库备份检查脚本 v1.0
# 用途：验证备份是否正常运行，异常时发送告警
# 部署位置：/opt/xinpect-website/scripts/check_backup.sh
# 调用方式：由 crontab 或 monitor.py 调用
# ============================================================================
set -uo pipefail

# ======================== 配置 ========================
BACKUP_DIR="/opt/xinpect-website/backups/database"
LOG_DIR="/opt/xinpect-website/logs"
CHECK_LOG="${LOG_DIR}/backup_check.log"
MAX_AGE_HOURS=25  # 备份最大允许年龄（小时），超过25小时未备份则告警
MIN_SIZE_KB=1     # 最小备份文件大小（KB）
ALERT_COOLDOWN_FILE="/tmp/xinpect_backup_alert_cooldown"
ALERT_COOLDOWN_MINUTES=60

# 飞书告警 Webhook
FEISHU_WEBHOOK_URL="${FEISHU_WEBHOOK_URL:-}"

# ======================== 颜色 ========================
RED='\033[0;31m'; GREEN_C='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN_C}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $*" | tee -a "$CHECK_LOG"; }
warn() { echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️${NC} $*" | tee -a "$CHECK_LOG"; }
fail() { echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ❌${NC} $*" | tee -a "$CHECK_LOG"; }

mkdir -p "$LOG_DIR"

# ======================== 检查逻辑 ========================
ERRORS=()
WARNINGS=()
STATUS="OK"

# 1. 检查备份目录是否存在
if [[ ! -d "$BACKUP_DIR" ]]; then
    ERRORS+=("备份目录不存在: $BACKUP_DIR")
    STATUS="CRITICAL"
else
    log "备份目录存在: ✅"
fi

# 2. 检查最新备份的时间
if [[ -d "$BACKUP_DIR" ]]; then
    LATEST_BACKUP=$(ls -1t "${BACKUP_DIR}"/xinpect_backup_*.db.gz 2>/dev/null | head -1)
    
    if [[ -z "$LATEST_BACKUP" ]]; then
        ERRORS+=("未找到任何备份文件")
        STATUS="CRITICAL"
    else
        # 计算备份年龄（小时）
        BACKUP_MTIME=$(stat -c %Y "$LATEST_BACKUP" 2>/dev/null || echo "0")
        CURRENT_TIME=$(date +%s)
        AGE_HOURS=$(( (CURRENT_TIME - BACKUP_MTIME) / 3600 ))
        
        if [[ $AGE_HOURS -gt $MAX_AGE_HOURS ]]; then
            ERRORS+=("最新备份已超过 ${AGE_HOURS} 小时未更新（阈值: ${MAX_AGE_HOURS}h）")
            STATUS="CRITICAL"
        else
            log "最新备份时间: ${AGE_HOURS} 小时前 ✅"
        fi
        
        # 3. 检查备份文件大小
        BACKUP_SIZE_KB=$(du -k "$LATEST_BACKUP" | cut -f1)
        if [[ $BACKUP_SIZE_KB -lt $MIN_SIZE_KB ]]; then
            ERRORS+=("最新备份文件异常偏小: ${BACKUP_SIZE_KB}KB < ${MIN_SIZE_KB}KB")
            STATUS="CRITICAL"
        else
            log "备份文件大小: $(du -h "$LATEST_BACKUP" | cut -f1) ✅"
        fi
        
        # 4. 验证最新备份完整性
        if command -v sqlite3 &>/dev/null && [[ -f "$LATEST_BACKUP" ]]; then
            TEMP_CHECK="/tmp/xinpect_check_$$.db"
            gunzip -c "$LATEST_BACKUP" > "$TEMP_CHECK" 2>/dev/null
            if [[ $? -eq 0 ]]; then
                INTEGRITY=$(sqlite3 "$TEMP_CHECK" "PRAGMA integrity_check;" 2>&1)
                rm -f "$TEMP_CHECK"
                if [[ "$INTEGRITY" != "ok" ]]; then
                    ERRORS+=("最新备份完整性检查失败: $INTEGRITY")
                    STATUS="CRITICAL"
                else
                    log "备份完整性: ✅ OK"
                fi
            else
                WARNINGS+=("无法解压最新备份进行验证")
                rm -f "$TEMP_CHECK"
            fi
        fi
        
        # 5. 检查 MD5 校验文件
        MD5_FILE="${LATEST_BACKUP%.db.gz}.md5"
        if [[ -f "$MD5_FILE" ]]; then
            if md5sum -c "$MD5_FILE" &>/dev/null; then
                log "MD5 校验: ✅"
            else
                WARNINGS+=("最新备份 MD5 校验失败")
            fi
        else
            WARNINGS+=("缺少 MD5 校验文件: $MD5_FILE")
        fi
    fi
    
    # 6. 统计备份信息
    TOTAL_BACKUPS=$(ls -1 "${BACKUP_DIR}"/xinpect_backup_*.db.gz 2>/dev/null | wc -l)
    TOTAL_SIZE=$(du -sh "${BACKUP_DIR}" 2>/dev/null | cut -f1)
    log "备份总数: $TOTAL_BACKUPS"
    log "总占用空间: $TOTAL_SIZE"
    
    # 7. 检查备份数量是否合理（至少保留7天的量）
    if [[ $TOTAL_BACKUPS -lt 7 ]]; then
        WARNINGS+=("备份数量不足: ${TOTAL_BACKUPS} 个（预期至少 7 个）")
    fi
fi

# ======================== 输出结果 ========================
echo ""
log "=========================================="
log "备份检查报告"
log "=========================================="

if [[ ${#ERRORS[@]} -gt 0 ]]; then
    fail "发现 ${#ERRORS[@]} 个错误:"
    for err in "${ERRORS[@]}"; do
        fail "  - $err"
    done
fi

if [[ ${#WARNINGS[@]} -gt 0 ]]; then
    warn "发现 ${#WARNINGS[@]} 个警告:"
    for w in "${WARNINGS[@]}"; do
        warn "  - $w"
    done
fi

if [[ "$STATUS" == "OK" ]]; then
    log "备份状态: ✅ 正常"
else
    fail "备份状态: ❌ 异常"
fi

log "=========================================="

# ======================== 发送告警 ========================
send_feishu_alert() {
    local message="$1"
    
    if [[ -z "$FEISHU_WEBHOOK_URL" ]]; then
        warn "未配置飞书 Webhook，跳过告警"
        return
    fi
    
    # 检查告警冷却
    if [[ -f "$ALERT_COOLDOWN_FILE" ]]; then
        LAST_ALERT=$(cat "$ALERT_COOLDOWN_FILE")
        CURRENT=$(date +%s)
        ELAPSED=$(( (CURRENT - LAST_ALERT) / 60 ))
        if [[ $ELAPSED -lt $ALERT_COOLDOWN_MINUTES ]]; then
            log "告警冷却中（${ELAPSED}/${ALERT_COOLDOWN_MINUTES}分钟），跳过"
            return
        fi
    fi
    
    # 构建飞书卡片消息
    CARD_JSON=$(cat <<EOF
{
    "msg_type": "interactive",
    "card": {
        "config": {
            "wide_screen_mode": true
        },
        "header": {
            "template": "red",
            "title": {
                "content": "🚨 煋鉴数据库备份异常告警",
                "tag": "plain_text"
            }
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "content": "**告警时间**: $(date '+%Y-%m-%d %H:%M:%S')\n**服务器**: 154.8.211.17 (北京)\n**状态**: ${STATUS}\n\n**错误详情**:\n${message}",
                    "tag": "lark_md"
                }
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {
                            "content": "查看备份日志",
                            "tag": "plain_text"
                        },
                        "url": "file://${CHECK_LOG}",
                        "type": "default"
                    }
                ]
            }
        ]
    }
}
EOF
)
    
    # 发送告警
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$CARD_JSON" \
        "$FEISHU_WEBHOOK_URL")
    
    if [[ "$HTTP_CODE" == "200" ]]; then
        log "飞书告警已发送 ✅"
        date +%s > "$ALERT_COOLDOWN_FILE"
    else
        warn "飞书告警发送失败: HTTP $HTTP_CODE"
    fi
}

# 如果有错误，发送告警
if [[ ${#ERRORS[@]} -gt 0 ]]; then
    ERROR_MSG=""
    for err in "${ERRORS[@]}"; do
        ERROR_MSG="${ERROR_MSG}\n• ${err}"
    done
    send_feishu_alert "$ERROR_MSG"
    exit 1
fi

exit 0
