# -*- coding: utf-8 -*-
"""定时任务「真的在出活」的守卫。

为什么要有这条（2026-11-14 巡检实录）：

- 人眼看 `monitoring/cron.log` 停在 10-05、只有三行 `Killed`，差点判成「监控停摆 40 天」。
  真相是那个脚本只写自己的 `monitor.log`，stdout 本来就空 —— 我拿错了判据文件。
- 反过来，备份脚本的注释写着「数据库归 03:00 那条 cron」，而 root 的 crontab 里没有，
  因为它在 **ubuntu** 的 crontab 里 —— 我只查了一个用户就下结论。

两次都是同一个病：**在某个文件、某个用户身上找到答案就收工。**
所以判据交给机器，逐条核对三件事，缺一条就叫：
1. 这条任务还在 crontab 里（整条被删是发生过的：备份脚本消失 15 天）
2. 它的产出文件还在（路径被改、目录被删，一样等于没跑）
3. 产出文件是最近更新的（跑着但不出活，跟没跑一样）

窗口按各自周期给足余量：宁可晚一小时发现，也不要天天误报，把人吵到不看。
"""
import os
import subprocess
import sys
import time

H = 3600

# (任务名, 哪个用户的表, crontab 里必须出现的片段, 产出文件, 允许静默秒数, 产出最小字节)
JOBS = [
    ('源码每日快照', 'root',
     '/opt/xinpect-backups/daily_backup.sh',
     '/opt/xinpect-backups/backup.log', 26 * H, 50),

    ('数据库每日备份', 'ubuntu',
     'scripts/backup_database.sh',
     '/opt/xinpect-website/backups/backup.log', 26 * H, 50),

    ('本机体检(5分)', 'root',
     'xinpect_monitor.py',
     '/opt/xinpect-website/monitoring/monitor.log', 1 * H, 50),

    ('关键链路监控(15分)', 'ubuntu',
     'critical_path_monitor.py',
     '/opt/xinpect-website/critical_path_monitor.log', 1 * H, 50),

    ('全站自检(6小时)', 'root',
     'run_qa_suite.sh',
     '/opt/xinpect-website/tests/reports/cron.log', 7 * H, 50),

    ('扫描缓存清理(每日)', 'root',
     'run_cache_purge.sh',
     '/var/log/xinpect/cache_purge.log', 26 * H, 50),

    ('付费履约对账(每日)', 'root',
     'run_paid_audit.sh',
     '/var/log/xinpect/paid_audit.log', 26 * H, 50),

    ('技能付费对账(每日)', 'root',
     'run_skillpay_audit.sh',
     '/var/log/xinpect/skillpay_audit.log', 26 * H, 50),

    ('会员到期提醒(每日)', 'root',
     'run_membership_reminder.sh',
     '/var/log/xinpect/membership_reminder.log', 26 * H, 50),

    ('状态页生成(每小时)', 'root',
     'generate_status.py',
     '/var/log/xinpect_status.log', 2 * H, 50),
]


def _read_crontab(user):
    """读某个用户的定时任务表（去掉注释行）。读不到返回空串。"""
    cmd = ['crontab', '-l'] if user == 'root' else ['crontab', '-l', '-u', user]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ''
    if p.returncode != 0:
        return ''
    return '\n'.join(l for l in p.stdout.splitlines() if not l.lstrip().startswith('#'))


def _fmt_age(sec):
    if sec < 0:
        sec = 0
    if sec < H:
        return '%d 分钟' % (sec // 60)
    return '%.1f 小时' % (sec / H)


def check_jobs(jobs=None, crontabs=None, now=None):
    """逐条核对，返回问题清单；空列表 = 全部在出活。

    crontabs 可注入，供造坏自检用（不碰真实 crontab）。
    """
    now = time.time() if now is None else now
    jobs = JOBS if jobs is None else jobs

    users = sorted({j[1] for j in jobs})
    if crontabs is None:
        crontabs = {user: _read_crontab(user) for user in users}

    # 读不到就等于没查。宁可红，也不要给一个「全绿」的假信号。
    empty = [u for u in users if not crontabs.get(u)]
    if empty:
        return ['读不到 %s 的定时任务表（要 root 权限；读不到就等于没查）' % u for u in empty]

    problems = []
    for name, user, needle, out_path, window, min_bytes in jobs:
        table = crontabs.get(user, '')
        if needle not in table:
            problems.append('%s：%s 的定时任务表里找不到这条（整条被删了？）' % (name, user))
            continue

        if not os.path.isfile(out_path):
            problems.append('%s：产出文件不见了 %s' % (name, out_path))
            continue

        st = os.stat(out_path)
        age = now - st.st_mtime
        if age > window:
            problems.append('%s：已经 %s 没有新产出（上限 %s）— %s'
                            % (name, _fmt_age(age), _fmt_age(window), out_path))
            continue

        if st.st_size < min_bytes:
            problems.append('%s：产出文件只有 %d 字节，像被清空或写失败 — %s'
                            % (name, st.st_size, out_path))
    return problems


# --------------------------------------------------------------------------
# 守卫本体
# --------------------------------------------------------------------------
def test_all_jobs_alive():
    problems = check_jobs()
    assert not problems, '定时任务有问题：\n  - ' + '\n  - '.join(problems)


def test_window_is_neither_too_tight_nor_useless():
    """窗口太短会天天误报（没人看了等于没有），太长会漏掉一整天。"""
    for name, user, needle, out_path, window, _mb in JOBS:
        assert 1800 <= window <= 48 * H, '%s 的允许静默窗口不合理: %ds' % (name, window)


def test_every_job_names_its_owner_and_needle():
    for name, user, needle, out_path, _w, _mb in JOBS:
        assert user in ('root', 'ubuntu'), '%s 没写清楚是哪个用户的定时任务' % name
        assert needle and len(needle) > 8, '%s 的 crontab 匹配片段太短，容易误命中' % name
        assert out_path.startswith('/'), '%s 的产出路径必须是绝对路径' % name


def test_missing_from_crontab_is_caught():
    """造坏：把一条任务从表里拿掉 —— 必须红。"""
    victim = JOBS[1]
    trimmed = {u: _read_crontab(u) or 'placeholder' for u in {j[1] for j in JOBS}}
    trimmed[victim[1]] = trimmed[victim[1]].replace(victim[2], '# 造坏：这条被删了')
    problems = check_jobs(crontabs=trimmed)
    assert any(victim[0] in p and '找不到这条' in p for p in problems), problems


def test_stale_output_is_caught():
    """造坏：窗口压到 1 秒 —— 再新鲜的文件也算过期，必须红。"""
    tight = [(n, u, d, o, 1, mb) for n, u, d, o, _w, mb in JOBS]
    problems = check_jobs(tight)
    assert any('没有新产出' in p for p in problems), problems


def test_missing_output_is_caught():
    """造坏：产出路径写成不存在的 —— 必须红。"""
    broken = [(n, u, d, o + '.不存在', w, mb) for n, u, d, o, w, mb in JOBS]
    problems = check_jobs(broken)
    assert any('产出文件不见了' in p for p in problems), problems


def test_unreadable_crontab_is_not_reported_as_green():
    """造坏：一条表都读不到时，必须报「没查」而不是全绿。"""
    problems = check_jobs(crontabs={})
    assert problems and any('读不到' in p for p in problems), problems


def main():
    problems = check_jobs()
    total = len(JOBS)
    if problems:
        print('❌ 定时任务守卫: %d 条任务，%d 个问题' % (total, len(problems)))
        for p in problems:
            print('   - ' + p)
        return 1
    print('✅ 定时任务守卫: %d 条任务全部在出活' % total)
    for name, _u, _d, out_path, window, _mb in JOBS:
        age = time.time() - os.stat(out_path).st_mtime
        print('   %-20s 最近产出 %8s（上限 %s）' % (name, _fmt_age(age), _fmt_age(window)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
