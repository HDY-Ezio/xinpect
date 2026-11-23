#!/usr/bin/env bash
# 会员到期提醒：每天 09:00 跑一次。
# 三档按剩余天数自动选（7/4 天、3/2 天、1/0 天），每轮到期每档只发一次；
# 续费后到期日变了会自动重新开始。只发给付过费的会员。
#
# 为什么不写 /dev/null：这个任务必须留下"跑了没、成没成"的痕迹，
# 否则失败一次就是客户少收一封邮件，而没人会发现。
set -euo pipefail

LOG=/var/log/xinpect/membership_reminder.log
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
/usr/bin/python3 -m modules.membership_reminder >> "$LOG" 2>&1
RC=$?
set -e

if [ "$RC" -ne 0 ]; then
    echo "[$(date '+%F %T')] 失败 rc=$RC" >> "$LOG"
    exit "$RC"
fi

echo "[$(date '+%F %T')] 结束 rc=0" >> "$LOG"
