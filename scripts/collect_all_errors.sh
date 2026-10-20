#!/bin/bash
# 收集所有煋鉴相关服务的错误

REPORT_DIR="/opt/xinpect-website/reports"
DATE=$(date +%Y%m%d)
YESTERDAY=$(date -d yesterday +%Y-%m-%d)
REPORT_FILE="$REPORT_DIR/all_services_errors_${DATE}.log"

mkdir -p "$REPORT_DIR"

echo "# 全服务器错误报告" > "$REPORT_FILE"
echo "**日期**: $YESTERDAY" >> "$REPORT_FILE"
echo "**生成时间**: $(date '+%Y-%m-%d %H:%M:%S')" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# 收集所有xinpect相关服务的错误
echo "## xinpect-website 错误" >> "$REPORT_FILE"
journalctl -u xinpect-website --since "yesterday 00:00:00" --until "yesterday 23:59:59" --priority=err --no-pager >> "$REPORT_FILE" 2>&1

echo "" >> "$REPORT_FILE"
echo "## xinpect-scanner 错误" >> "$REPORT_FILE"
journalctl -u xinpect-scanner --since "yesterday 00:00:00" --until "yesterday 23:59:59" --priority=err --no-pager >> "$REPORT_FILE" 2>&1

# 如果有其他服务，也收集
for service in $(systemctl list-units --type=service --state=running | grep -E 'xinpect|starwang|pdf' | awk '{print $1}'); do
    if [[ "$service" != "xinpect-website" && "$service" != "xinpect-scanner" ]]; then
        echo "" >> "$REPORT_FILE"
        echo "## $service 错误" >> "$REPORT_FILE"
        journalctl -u "$service" --since "yesterday 00:00:00" --until "yesterday 23:59:59" --priority=err --no-pager >> "$REPORT_FILE" 2>&1
    fi
done

echo "" >> "$REPORT_FILE"
echo "---" >> "$REPORT_FILE"
echo "报告生成完成" >> "$REPORT_FILE"

echo "全服务器错误报告已生成: $REPORT_FILE"
