#!/usr/bin/env bash
# 扫描成本核算与告警：每天 21:05 核算当天，次日 06:05 核算昨天（补全整天数据）。
#
# 为什么要有这个：11-14 扫了一个开源项目，一晚上烧掉 90 元 LLM 费用，是事后
# 翻三个库、写四条 SQL 才拼出来的。从今往后这件事必须自己算、自己报。
#
# 为什么不只看进程：进程活着、接口 200、扫描成功，全都跟花了多少钱无关。
# 钱是唯一不会撒谎的指标。
#
# 口径：一次扫描的成本 = [本次提交, 下次提交) 窗口内该 key 的 LLM 实际花费。
# 生产扫描串行执行，窗口不重叠。已用 11-14 真实数据校准：算出 86.77，实际 90.28。
set -uo pipefail

LOG=/var/log/xinpect/scan_cost.log
JSON_OUT=/var/log/xinpect/scan_cost_last.json
APP=/opt/xinpect-website

mkdir -p "$(dirname "$LOG")"

if [ ! -r /etc/xinpect/website.env ]; then
    echo "[$(date '+%F %T')] 失败：读不到 /etc/xinpect/website.env" >> "$LOG"
    exit 1
fi

set -a
# shellcheck disable=SC1091
. /etc/xinpect/website.env
set +a

cd "$APP" || exit 1

# 参数：空=今天，--yesterday=昨天，或直接传 YYYY-MM-DD
TARGET_ARGS=""
case "${1:-}" in
    --yesterday) TARGET_ARGS="--date $(date -d 'yesterday' '+%F')" ;;
    "")          TARGET_ARGS="--date $(date '+%F')" ;;
    *)           TARGET_ARGS="--date $1" ;;
esac

echo "[$(date '+%F %T')] 开始 ${TARGET_ARGS}" >> "$LOG"

# 1. 出机器可读账目（给网站/守卫读，也留痕）
set +e
/usr/bin/python3 scripts/scan_cost_report.py $TARGET_ARGS --json \
    > "$JSON_OUT" 2>> "$LOG"
RC_JSON=$?
set -e

if [ "$RC_JSON" -ne 0 ] || [ ! -s "$JSON_OUT" ]; then
    echo "[$(date '+%F %T')] ❌ 账目生成失败 rc=$RC_JSON，文件为空或不存在" >> "$LOG"
    exit 1
fi

# 2. 人读版写日志（便于事后翻）
set +e
/usr/bin/python3 scripts/scan_cost_report.py $TARGET_ARGS >> "$LOG" 2>&1
set -e

# 3. 超限告警（同一天同一问题只发一次，状态文件去重）
# 退出码：0=健康  2=超限且已发信  3=超限但发信失败
set +e
/usr/bin/python3 scripts/scan_cost_report.py $TARGET_ARGS --notify >> "$LOG" 2>&1
RC_ALERT=$?
set -e

case "$RC_ALERT" in
    0) echo "[$(date '+%F %T')] 成本在阈值内" >> "$LOG" ;;
    2) echo "[$(date '+%F %T')] ⚠ 超限，已发告警邮件" >> "$LOG" ;;
    3) echo "[$(date '+%F %T')] ❌ 超限但告警邮件发送失败" >> "$LOG"; exit 1 ;;
    4) echo "[$(date '+%F %T')] ⚠ 超限，今天已告过警，不重复发" >> "$LOG" ;;
    *) echo "[$(date '+%F %T')] ? 未知返回码 $RC_ALERT" >> "$LOG" ;;
esac

echo "[$(date '+%F %T')] 结束 rc_json=$RC_JSON rc_alert=$RC_ALERT" >> "$LOG"
exit 0
