#!/usr/bin/env bash
# 扫描结果库清理：每晚 04:10 跑一次（错开 02:00 备份、09:00 会员提醒、09:15 对账）。
#
# 为什么要有它：/opt/xinpect-data/scan_results.db 只增不删，11-14 已经 4.2 GB /
# 18.5 万条扫描。没有任何一处代码问过「这些旧记录还有没有人要」。盘满了网站会
# 直接写不进数据，而那种故障最先表现为「莫名其妙报错」，最难查。
#
# 这个脚本不只「跑一下清理」：跑完还要**回头核对**过期记录是不是真的没了。
# 只问「脚本退出码 0」等于只问「进程活不活」——收钱没给货那次就是这么躺几个月的。
set -uo pipefail

LOG=/var/log/xinpect/cache_purge.log
mkdir -p "$(dirname "$LOG")"

log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

if [ ! -r /etc/xinpect/website.env ]; then
    log "失败：读不到 /etc/xinpect/website.env"
    exit 1
fi

set -a
# shellcheck disable=SC1091
. /etc/xinpect/website.env
set +a

if [ -z "${XINPECT_DATA_DIR:-}" ]; then
    log "失败：XINPECT_DATA_DIR 没有配置，不敢猜库路径（猜错就是操作了另一个库）"
    exit 1
fi

cd /opt/xinpect-website || { log "失败：进不去 /opt/xinpect-website"; exit 1; }

log "开始（库目录 $XINPECT_DATA_DIR）"

/usr/bin/python3 scripts/purge_scan_cache.py \
    --compact --json /var/log/xinpect/cache_purge_last.json >> "$LOG" 2>&1
RC=$?

if [ "$RC" -ne 0 ]; then
    log "清理失败 rc=$RC（详见上方输出）"
    exit "$RC"
fi

# 回头核对：过期记录必须真的为 0；库体积不许比清理前更大。
/usr/bin/python3 - "$XINPECT_DATA_DIR" <<'PY' >> "$LOG" 2>&1
import json, os, sys, time
sys.path.insert(0, '/opt/xinpect-website')
from modules import result_retention as rr

data_dir = sys.argv[1]
db = os.path.join(data_dir, rr.DB_FILENAME)
after = rr.survey(db)
path = '/var/log/xinpect/cache_purge_last.json'
before_size = None
if os.path.exists(path):
    with open(path, encoding='utf-8') as f:
        before_size = json.load(f).get('size_before')

print('[核对] 剩余 %d 条扫描、%d 条过期未删、库 %.2f GB' % (
    after['total_scans'], after['expired_scans'],
    after['size_bytes'] / 1024 / 1024 / 1024))

problems = []
if after['expired_scans'] > 0:
    problems.append('过期记录还剩 %d 条（清理没做完）' % after['expired_scans'])
if before_size and after['size_bytes'] > before_size:
    problems.append('库变大了：%d → %d' % (before_size, after['size_bytes']))
if rr.dangling_code_rows(db) > 0:
    problems.append('有孤儿代码副本')

if problems:
    print('[核对] ❌ ' + '；'.join(problems))
    sys.exit(2)
print('[核对] ✅ 过期记录已清空，无孤儿行')
PY
CHECK_RC=$?

if [ "$CHECK_RC" -ne 0 ]; then
    log "核对没过 rc=$CHECK_RC"
    exit "$CHECK_RC"
fi

log "结束 rc=0"
