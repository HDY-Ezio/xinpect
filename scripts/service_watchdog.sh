#!/bin/bash
# 煋鉴服务存活监控 - 每5分钟检查，挂了就拉起来
SERVICES=("8765:xinpect-pay:systemd:xinpect-pay" "8612:menfang-license:manual:/opt/xinpect-pay/server.py:/opt/xinpect-pay/venv/bin/python" "8766:pdf-batch-pro:pm2:pdf-batch-pro" "8620:xinpect-scanner-green:systemd:xinpect-scanner-green" "8622:xinpect-scanner-blue:systemd:xinpect-scanner-blue")
LOG="/opt/xinpect-website/logs/watchdog.log"
ALERT_FILE="/tmp/watchdog_alert_sent"

for svc in "${SERVICES[@]}"; do
    IFS=: read -r port name type arg1 arg2 <<< "$svc"
    if ! ss -tlnp | grep -q ":${port} "; then
        echo "$(date) [ALERT] $name (port $port) is DOWN!" >> "$LOG"
        case "$type" in
            systemd)
                sudo systemctl restart "$arg1" && echo "$(date) [RECOVERED] $name restarted via systemd" >> "$LOG"
                ;;
            manual)
                cd $(dirname "$arg1") && nohup $arg2 $arg1 > /dev/null 2>&1 &
                echo "$(date) [RECOVERED] $name restarted manually" >> "$LOG"
                ;;
            pm2)
                pm2 restart "$arg1" && echo "$(date) [RECOVERED] $name restarted via pm2" >> "$LOG"
                ;;
        esac
        # 发告警（写入标记文件，由cron读取）
        echo "$(date) $name port=$port DOWN+RECOVERED" >> "$ALERT_FILE"
    fi
done
