# -*- coding: utf-8 -*-
"""守卫：大包分片扫描不许独占整台机器。

背景（2026-11-14 客户实测）：
321 个文件 / 4 万行切成 57 片连续跑，引擎 CPU 上限设的是"可吃满 2 核"，
57 片首尾相接不松手，官网 / MySQL / nginx 全程抢不到核心 ——
客户看到的是"整个服务器卡死"。

这条守卫不查"代码里有没有写 sleep"（那种检查把声明挪个位置就骗过去了），
而是真跑一次分片循环、量出实际耗时：没有让路就一定测不到间隔。

同时守住两条配置判据（按物理核数算，换机器自动适配）：
- 引擎并发上限不得超过 核数的一半；
- 引擎 CPU 配额必须留出至少半个核给官网/数据库。

不依赖 pytest fixture：QA 里 pytest 与直跑两个分支都要能过。
"""
import os
import re
import sys
import time
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
if str(SITE) not in sys.path:
    sys.path.insert(0, str(SITE))


def _ensure_env():
    """modules 包初始化要求 XINPECT_SECRET；测试自带兜底，保证能单独跑。"""
    if os.environ.get('XINPECT_SECRET'):
        return
    try:
        with open('/etc/xinpect/website.env', encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, val = line.partition('=')
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
    except (FileNotFoundError, PermissionError):
        pass


_ensure_env()
from modules import api as api_mod  # noqa: E402


def _run_fake_chunks(n_chunks):
    """用假引擎跑一次分片循环，返回 (实际耗时, 进度文案列表, 引擎调用次数)。"""
    texts = []
    calls = []

    def fake_plan(code_files, *a, **kw):
        return [{'files': {'f%d.py' % i: 'x = 1\n'}, 'lines': 1, 'offsets': {}}
                for i in range(n_chunks)]

    def fake_call(files, brains, options=None):
        calls.append(len(files))
        return {'issues': [], 'scan_time': 0.01}

    def fake_progress(scan_id, pct, text):
        texts.append(text)

    origin = (api_mod._plan_scan_chunks, api_mod.call_scanner,
              api_mod._update_scan_progress)
    api_mod._plan_scan_chunks = fake_plan
    api_mod.call_scanner = fake_call
    api_mod._update_scan_progress = fake_progress
    try:
        t0 = time.time()
        api_mod._execute_scan_in_chunks(
            'GUARD-TEST', {'f0.py': 'x = 1\n'}, 'python', None, 1, 1)
        elapsed = time.time() - t0
    finally:
        (api_mod._plan_scan_chunks, api_mod.call_scanner,
         api_mod._update_scan_progress) = origin
    return elapsed, texts, calls


def test_chunks_yield_cpu_between_slices():
    """片与片之间必须真的松手（否则整机被独占，官网卡死）。

    行为判据：3 片 = 2 次让路，实测耗时必须接近 2 × 让路时长。
    这条不看源码写了什么，只认实际花了多少时间。
    """
    yield_expected = getattr(api_mod, '_CHUNK_YIELD_SECONDS', 0)
    assert yield_expected > 0, (
        '分片循环没有让路常量 _CHUNK_YIELD_SECONDS —— 片与片首尾相接不松手，'
        '大包会再次独占整机')
    elapsed, texts, calls = _run_fake_chunks(3)
    assert len(calls) == 3, '假引擎应被调用 3 次，实际 %d 次' % len(calls)
    floor = 2 * yield_expected * 0.85
    assert elapsed >= floor, (
        '3 片之间应有 2 次让路（约 %.1fs），实测只用了 %.2fs —— '
        '说明片间没有让出 CPU，大包会再次独占整机' % (2 * yield_expected, elapsed))


def test_single_chunk_does_not_wait():
    """单片任务不该白等（小包是客户等结果的常态，不能加无谓延迟）。"""
    elapsed, texts, calls = _run_fake_chunks(1)
    assert len(calls) == 1
    assert elapsed < 0.5, '单片任务不该有让路延迟，实测 %.2fs' % elapsed


def test_progress_shows_slice_number_and_eta():
    """多片任务必须在进度里说明「第几片 / 共几片」，否则客户以为死机。"""
    _, texts, _ = _run_fake_chunks(3)
    assert texts, '分片循环没有报过一次进度'
    assert any('第 1/3 片' in t for t in texts), (
        '进度里看不到「第 1/3 片」，客户无从判断还剩多少：%s' % texts[:3])


def test_single_chunk_progress_has_no_slice_number():
    """单片（小包）不该显示「第 1/1 片」，那会让客户误以为自己被拆包了。"""
    _, texts, _ = _run_fake_chunks(1)
    assert texts
    assert not any('/1 片' in t for t in texts), (
        '单片任务不该出现片号：%s' % texts[:2])


def test_chunk_size_not_too_small():
    """每片行数不能太小：每片都要重新初始化全部规则引擎（实测约 27 秒）。

    依据 2026-11-14 冷缓存实测（同一批代码只改切法）：
      2100 行/片 → 1 片 18.7s；700 行/片 → 3 片 99.5s。
    片太细等于把"开工费"重复付，大包耗时成倍放大。1500 行是保守下限。
    """
    n = getattr(api_mod, '_CHUNK_TARGET_LINES', 0)
    assert n >= 1500, (
        '每片只有 %d 行：每片要重新拉起全部规则引擎（约 27 秒），'
        '切这么细会把大包耗时翻几倍' % n)


def _read_env_int(path, key):
    p = Path(path)
    if not p.is_file():
        raise AssertionError('配置文件不存在：%s' % path)
    try:
        raw = p.read_text(encoding='utf-8', errors='replace')
    except PermissionError:
        raise AssertionError(
            '%s 需要 root 读取（QA 请用 sudo 跑，否则这条守卫无法验证生产配置）' % path)
    m = re.search(r'^%s\s*=\s*(\d+)' % re.escape(key), raw, re.M)
    if not m:
        raise AssertionError('%s 里找不到 %s（配置项必须有明确取值）' % (path, key))
    return int(m.group(1))


_ENGINE_TARGETS = [
    ('/etc/xinpect/scanner-green.env',
     '/etc/systemd/system/xinpect-scanner-green.service.d/resource-limit.conf',
     '生产引擎(绿)'),
    ('/etc/xinpect/scanner-blue.env',
     '/etc/systemd/system/xinpect-scanner-blue.service.d/resource-limit.conf',
     '开发引擎(蓝)'),
]


def test_engine_concurrency_within_cores():
    """引擎同时跑的扫描数，不得超过物理核数的一半。

    2 核机器允许 3 路并发时，三路互抢 CPU，官网/数据库全饿死。
    这条按核数算上限，换到 8 核机器自动放宽到 4。
    两台引擎都要查：只改生产、漏改开发，开发扫描一样能拖死整机。
    """
    cores = os.cpu_count() or 1
    ceiling = max(1, cores // 2)
    bad = []
    for env_path, _, label in _ENGINE_TARGETS:
        val = _read_env_int(env_path, 'SCAN_MAX_CONCURRENT')
        if val > ceiling:
            bad.append('%s 并发 %d（上限 %d，%d 核机器）' % (label, val, ceiling, cores))
    assert not bad, '；'.join(bad) + ' —— 会互相抢 CPU 拖死官网'


def test_engine_cpu_quota_leaves_headroom():
    """引擎 CPU 配额必须留出至少半个核，官网/数据库才有机会响应客户。"""
    cores = os.cpu_count() or 1
    ceiling = cores * 100 - 50      # 至少留半个核
    bad = []
    for _, conf, label in _ENGINE_TARGETS:
        p = Path(conf)
        if not p.is_file():
            bad.append('%s 找不到资源限制配置 %s' % (label, conf))
            continue
        try:
            raw = p.read_text(encoding='utf-8', errors='replace')
        except PermissionError:
            raise AssertionError('%s 需要 root 读取（QA 请用 sudo 跑）' % conf)
        m = re.search(r'^CPUQuota=(\d+)%', raw, re.M)
        if not m:
            bad.append('%s 没设 CPUQuota（等于允许吃满全部核）' % label)
            continue
        quota = int(m.group(1))
        if quota > ceiling:
            bad.append('%s CPU 配额 %d%%（%d 核机型上限应为 %d%%）'
                       % (label, quota, cores, ceiling))
    assert not bad, '；'.join(bad) + ' —— 扫描期间官网会抢不到 CPU'


if __name__ == '__main__':
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith('test_')]
    bad = 0
    for name, fn in fns:
        try:
            fn()
            print('  ok   %s' % name)
        except AssertionError as e:
            bad += 1
            print('  FAIL %s: %s' % (name, e))
    print('%d 条用例，失败 %d 条' % (len(fns), bad))
    raise SystemExit(1 if bad else 0)
