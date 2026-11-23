"""外部探活自己也得有人盯。

2026-11-14 这天上了「GitHub 每 5 分钟探一次官网」之后，剩一个问题：
GitHub 会因为仓库 60 天没提交而自动停用定时任务，也会在它自己出故障时静默。
停用之后一切看起来都正常——没有红、没有错，就是不跑了。这正是我们反复栽的坑：
装了东西不等于东西在干活。

所以本机每轮自检顺手查两件事：
1. 外部探活最近一次运行是不是够新（超过 2 小时没跑 = 它自己瞎了）
2. 有没有「官网失联」的未结单（有 = 真出事了，本机也应该知道）

查不到（网络不通 / GitHub 限流）一律判红并写明「没查成」——
报绿等于给假信号，比红更危险。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

REPO = os.environ.get('WATCHDOG_REPO', 'HDY-Ezio/xinpect-bench')
WORKFLOW_PATH = '.github/workflows/uptime.yml'
ISSUE_TITLE = '煋鉴官网失联'

# 阈值唯一出处：外部探活每 5 分钟一次，2 小时没动静就是停了（留足 GitHub 排队延迟）
MAX_GAP_HOURS = 2
API = 'https://api.github.com'
UA = 'xinpect-selfcheck/1.0'


def _get(url, attempt_times=3):
    last = None
    for i in range(attempt_times):
        req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/vnd.github+json'})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode('utf-8', 'replace')[:200]
        except Exception as e:                        # noqa: BLE001
            last = '%s: %s' % (type(e).__name__, e)
            if i + 1 < attempt_times:
                time.sleep(3)
    return None, last


def parse_ts(s):
    return datetime.strptime(s, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)


def check_enabled():
    """探活文件必须还在默认分支上。被删/被改路径，定时任务就静默消失。"""
    code, data = _get('%s/repos/%s/contents/%s' % (API, REPO, WORKFLOW_PATH))
    if code is None:
        return ['没能确认外部探活文件还在（查询失败：%s）——这不代表它正常' % data]
    if code == 404:
        return ['外部探活文件不见了：%s（定时任务会静默停掉）' % WORKFLOW_PATH]
    if code != 200:
        return ['查外部探活文件返回 HTTP %s' % code]
    return []


def check_running():
    code, data = _get('%s/repos/%s/actions/runs?per_page=20' % (API, REPO))
    if code is None:
        return ['没能查到外部探活最近有没有跑（查询失败：%s）——这不代表它正常' % data], None
    if code != 200:
        return ['查外部探活运行记录返回 HTTP %s' % code], None

    runs = [r for r in data.get('workflow_runs', []) if r.get('path') == WORKFLOW_PATH]
    if not runs:
        return ['外部探活一次都没跑过（刚加上？或已被禁用）'], None

    latest = runs[0]
    when = parse_ts(latest['created_at'])
    gap = datetime.now(timezone.utc) - when
    hours = gap.total_seconds() / 3600.0
    detail = {
        'latest_at': latest['created_at'],
        'event': latest['event'],
        'conclusion': latest['conclusion'],
        'gap_hours': round(hours, 2),
    }
    if hours > MAX_GAP_HOURS:
        return ['外部探活已经 %.1f 小时没跑了（上限 %d 小时），它自己可能被停用了'
                % (hours, MAX_GAP_HOURS)], detail
    return [], detail


def check_open_alert():
    code, data = _get('%s/repos/%s/issues?state=open&per_page=50' % (API, REPO))
    if code is None:
        return ['没能查到有没有未结的失联单（查询失败：%s）——这不代表没事' % data]
    if code != 200:
        return ['查未结单返回 HTTP %s' % code]
    openers = [i for i in data if isinstance(i, dict) and (i.get('title') or '').startswith(ISSUE_TITLE)]
    if openers:
        nums = ', #'.join(str(i['number']) for i in openers)
        return ['外部探活报了「官网失联」且还没结单：#%s' % nums]
    return []


def collect():
    problems = []
    problems += check_enabled()
    p, detail = check_running()
    problems += p
    problems += check_open_alert()
    return problems, detail


def main():
    problems, detail = collect()
    if detail:
        print('最近一次外部探活：%s（%s / %s），距今 %.2f 小时'
              % (detail['latest_at'], detail['event'], detail['conclusion'], detail['gap_hours']))
    if problems:
        print('❌ 外部探活有问题：')
        for p in problems:
            print('   -', p)
        return 1
    print('✅ 外部探活正常：文件在、最近 2 小时跑过、没有未结的失联单')
    return 0


if __name__ == '__main__':
    sys.exit(main())
