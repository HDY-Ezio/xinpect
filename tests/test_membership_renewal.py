"""续费到期日的守卫。

钉住一件事：客户提前续费，没到期的那几天不能凭空消失。

2026-11-14 实证的 bug：`vip_expire = paid_dt + days`。客户还剩 20 天到期时
买下个月，新到期日被改写成「今天 + 30 天」——白吞 20 天，等于少给货。
真实客户（user 15）当时只剩 1 天到期，仍然每天在跑扫描，随时会踩到。

这条以前没被抓住，是因为测试只覆盖了「首次开通」，没人测过「非首次」。
所以这里除了断言结果，还留了一条自检：旧公式必须算出不同答案，
否则说明用例根本没在验「累加」，变成摆设。
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ensure_env():
    """modules 包初始化要求 XINPECT_SECRET 至少 32 位。

    这个测试只验纯计算，不连库、不发信，所以不需要真实密钥；缺了就给一个
    长度合规的测试专用值，保证单跑这个文件也能验证。QA 套件已 source
    /etc/xinpect/website.env，那时这里不会覆盖真密钥。
    """
    if not os.environ.get('XINPECT_SECRET'):
        os.environ['XINPECT_SECRET'] = 'test-only-' + 'x' * 40


_ensure_env()

from modules.payment import calc_vip_expire  # noqa: E402

PAID = datetime(2026, 11, 10, 10, 0, 0)
FMT = '%Y-%m-%d %H:%M:%S'


def test_renewal_keeps_remaining_days():
    """还剩 21 天时续 30 天 → 到期日 = 原到期日 + 30，不是 支付时间 + 30。"""
    prev = '2026-12-01 00:00:00'
    got = calc_vip_expire(PAID, prev, 30)
    assert got == '2026-12-31 00:00:00', got


def test_renewal_from_expired_starts_at_paid_time():
    """已经过期的老客户续费 → 从支付时间起算，不能倒扣。"""
    prev = '2026-10-01 00:00:00'
    got = calc_vip_expire(PAID, prev, 30)
    assert got == '2026-12-10 10:00:00', got


def test_first_purchase_has_no_previous_expire():
    """首次开通：没有原到期日（None / 空串）都按支付时间起算。"""
    for prev in (None, '', '   '):
        got = calc_vip_expire(PAID, prev, 30)
        assert got == '2026-12-10 10:00:00', (prev, got)


def test_dirty_expire_does_not_break_purchase():
    """存量脏数据不该阻断开通，也不能把到期日算成奇怪的值。"""
    for prev in ('0000-00-00 00:00:00', '不是时间', '2026/12/01'):
        got = calc_vip_expire(PAID, prev, 30)
        assert got == '2026-12-10 10:00:00', (prev, got)


def test_guard_can_catch_the_old_bug():
    """自检：把旧公式套进去必须算出不同答案，否则这条守卫是摆设。"""
    prev = '2026-12-01 00:00:00'
    new_way = calc_vip_expire(PAID, prev, 30)
    old_way = (PAID + timedelta(days=30)).strftime(FMT)
    assert new_way != old_way, '新旧公式算出了同一个结果，说明用例没在验累加'
    assert datetime.strptime(new_way, FMT) > datetime.strptime(old_way, FMT)
    assert new_way == '2026-12-31 00:00:00', new_way


def test_handler_actually_uses_the_shared_calc():
    """支付处理函数必须调用同一个算法，不许在别处另写一套。"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, 'modules', 'payment.py'), encoding='utf-8') as fh:
        src = fh.read()
    assert 'def _handle_subscription_paid' in src
    body = src.split('def _handle_subscription_paid', 1)[1].split('\ndef ', 1)[0]
    assert 'calc_vip_expire(' in body, '支付处理没走统一算法，续费累加会再次失守'


def test_no_hardcoded_unlimited_user():
    """身份不许硬编码进代码。

    旧代码写着 `UNLIMITED_USER_ID = 15`，注释是 Boss，实际 15 是唯一付费客户。
    这行是死代码（无人引用），但只要将来有人用它，付费客户就会变成免费无限。
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    offenders = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in ('_archive', 'node_modules', '__pycache__',
                                    '.git', '_backup_20260910_131717')]
        for name in filenames:
            if not name.endswith('.py'):
                continue
            path = os.path.join(dirpath, name)
            if os.path.abspath(path) == os.path.abspath(__file__):
                continue  # 守卫自己会提到这个名字，不算违规
            try:
                with open(path, encoding='utf-8') as fh:
                    text = fh.read()
            except (UnicodeDecodeError, PermissionError):
                continue
            if 'UNLIMITED_USER_ID' in text:
                offenders.append(os.path.relpath(path, root))
    assert not offenders, '身份硬编码回来了：%s' % offenders


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
