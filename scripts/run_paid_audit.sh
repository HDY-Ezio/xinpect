#!/usr/bin/env bash
# 付费履约对账：每天 09:15 跑一次（错开 09:00 的会员到期提醒）。
#
# 只做一件事：把每一笔已付订单，跟它该产生的权益（积分 / 会员时长）对一遍。
# 起因是技能按次付费通道收了 1.49 元、履约代码是坏的，躺了几个月没人发现——
# 因为监控只问「进程活不活」，没问「钱收了货给了没」。
#
# 为什么不写 /dev/null：对不上必须留痕。收了钱没给货，是唯一不能靠日志滚动
# 掩盖的事故。
set -euo pipefail

LOG=/var/log/xinpect/paid_audit.log
mkdir -p "$(dirname "$LOG")"

if [ ! -r /etc/xinpect/website.env ]; then
    echo "[$(date '+%F %T')] 失败：读不到 /etc/xinpect/website.env" >> "$LOG"
    exit 1
fi

set -a
# shellcheck disable=SC1091
. /etc/xinpect/website.env
set +a

cd /opt/xinpect-website

echo "[$(date '+%F %T')] 开始" >> "$LOG"
set +e
/usr/bin/python3 scripts/audit_paid_orders.py \
    --json /var/log/xinpect/paid_audit_last.json >> "$LOG" 2>&1
RC=$?
set -e

if [ "$RC" -ne 0 ]; then
    echo "[$(date '+%F %T')] 有订单权益没落地 rc=$RC" >> "$LOG"
    exit "$RC"
fi

echo "[$(date '+%F %T')] 结束 rc=0" >> "$LOG"
