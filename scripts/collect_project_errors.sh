#!/bin/bash
# 按项目分别收集错误

REPORT_BASE="/opt/xinpect-website/reports"
DATE=$(date +%Y%m%d)

# 煋鉴项目
XINPECT_SERVICES="xinpect-website xinpect-scanner-green xinpect-scanner-blue xinpect-pay"
# 煋旺项目  
XINGWANG_SERVICES="starwang-backend starwang-backend-clean starwang-billing starwang-promotion starwang-voice starwang-voice-v3"

# 收集煋鉴错误
collect_errors() {
    local project=$1
    local services=$2
    local report_dir="$REPORT_BASE/$project"
    local report_file="$report_dir/errors_${DATE}.log"
    
    mkdir -p "$report_dir"
    
    echo "# $project 错误报告" > "$report_file"
    echo "**日期**: $(date -d yesterday +%Y-%m-%d)" >> "$report_file"
    echo "**生成时间**: $(date '+%Y-%m-%d %H:%M:%S')" >> "$report_file"
    echo "**服务**: $services" >> "$report_file"
    echo "" >> "$report_file"
    
    for service in $services; do
        errors=$(journalctl -u "$service" --since "yesterday" --priority=err --no-pager 2>/dev/null)
        if [ -n "$errors" ]; then
            echo "## $service" >> "$report_file"
            echo '```' >> "$report_file"
            echo "$errors" >> "$report_file"
            echo '```' >> "$report_file"
            echo "" >> "$report_file"
        fi
    done
    
    # 统计错误数
    error_count=$(grep -c "^--" "$report_file" 2>/dev/null || echo "0")
    echo "---" >> "$report_file"
    echo "总错误条目: $error_count" >> "$report_file"
}

# 分别收集两个项目
collect_errors "xinpect" "$XINPECT_SERVICES"
collect_errors "xingwang" "$XINGWANG_SERVICES"

echo "分项目错误报告已生成:"
echo "  煋鉴: $REPORT_BASE/xinpect/errors_${DATE}.log"
echo "  煋旺: $REPORT_BASE/xingwang/errors_${DATE}.log"
