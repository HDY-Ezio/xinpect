#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真浏览器点一遍「删除过期订单」：点 → 行消失 → 刷新还在消失 → 能恢复。

为什么要有这一层（2026-11-29）
------------------------------
删订单这件事，后端返回 200 不等于事情成了：可能 UPDATE 没落库、可能页面
没重新渲染、可能按钮点了根本没发请求。上一轮 /try 的教训是「后端全绿、
浏览器一点就错」；开票那轮的教训是「接口返回 200 但库里没变 = 假成功」。

所以这里断言三样东西一起成立：
  ① 页面上那行真的不见了；
  ② 刷新之后仍然不见（落库了，不是前端删 DOM）；
  ③ 数据库里 hidden_at 真有值。

隔离
----
空库（XINPECT_DB_PATH 指临时文件）、随机端口、独立数据目录，不碰生产。

用法
----
    /opt/xinpect-e2e/venv/bin/python tests/test_orders_page_e2e.py
    /opt/xinpect-e2e/venv/bin/python tests/test_orders_page_e2e.py --self-test

退出码：0 通过 / 1 失败 / 2 环境缺失
"""
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request

SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVE = os.path.join(SITE, 'tests', 'e2e_serve.py')
SYS_PY = '/usr/bin/python3'
ENV_FILE = '/etc/xinpect/website.env'

# 浏览器目录必须和已有几个真渲染守卫一致，另建一份只会让一边找不到。
_PW_BROWSERS = '/home/ubuntu/.cache/ms-playwright'
if os.path.isdir(_PW_BROWSERS) and not os.environ.get('PLAYWRIGHT_BROWSERS_PATH'):
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = _PW_BROWSERS

U1, P1 = 'e2e-orders@test.local', 'Orders#2026xp'

EXP_A = 'E2EORDEREXPIREDAAAAAAAAAAAAAAAA01'
EXP_B = 'E2EORDEREXPIREDBBBBBBBBBBBBBBBB02'
PAID = 'E2EORDERPAIDCCCCCCCCCCCCCCCCCCCCC03'

SEED_TMPL = '''
import sqlite3, sys
from werkzeug.security import generate_password_hash

conn = sqlite3.connect(sys.argv[1])
conn.row_factory = sqlite3.Row

conn.execute(
    "INSERT INTO users (email, password_hash, onboarding_completed, first_login_at)"
    " VALUES (?, ?, 1, datetime('now','localtime'))",
    ("__U1__", generate_password_hash("__P1__")))
uid = conn.execute("SELECT id FROM users WHERE email = ?", ("__U1__",)).fetchone()[0]


def add_order(oid, plan, amount, status):
    conn.execute(
        "INSERT INTO orders (order_id, user_id, plan_id, plan_name, amount, status,"
        " created_at) VALUES (?, ?, 'monthly', ?, ?, ?, datetime('now','localtime'))",
        (oid, uid, plan, amount, status))


add_order("__EXPA__", "月卡", 99.0, "expired")
add_order("__EXPB__", "季卡", 269.0, "expired")
add_order("__PAID__", "年卡", 899.0, "paid")

conn.commit()
print("SEEDED")
'''


def _log(msg):
    print(msg, flush=True)


def _free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _load_env_file(env):
    if not os.path.exists(ENV_FILE):
        return
    try:
        with open(ENV_FILE, 'r', encoding='utf-8', errors='replace') as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, val = line.split('=', 1)
                key = key.strip()
                if key and key not in env:
                    env[key] = val.strip().strip('"').strip("'")
    except OSError:
        pass


def _wait_ready(base, proc, timeout=90):
    last = ''
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            out = ''
            try:
                out = (proc.stdout.read() or '')[-2000:]
            except Exception:
                pass
            raise RuntimeError('隔离实例提前退出 rc=%s\n%s' % (proc.returncode, out))
        try:
            with urllib.request.urlopen(base + '/login', timeout=3) as resp:
                if resp.status == 200:
                    return True
        except Exception as exc:
            last = '%s' % exc
        time.sleep(0.4)
    raise RuntimeError('%ds 内实例没起来（最后一次错误：%s）' % (timeout, last))


def _seed(db_path):
    code = (SEED_TMPL
            .replace('__U1__', U1).replace('__P1__', P1)
            .replace('__EXPA__', EXP_A).replace('__EXPB__', EXP_B)
            .replace('__PAID__', PAID))
    res = subprocess.run([SYS_PY, '-c', code, db_path],
                         capture_output=True, text=True)
    if 'SEEDED' not in (res.stdout or ''):
        raise RuntimeError('造数据失败：%s\n%s' % (res.stdout, res.stderr))


def _rows(db_path, sql, args=()):
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def _hidden(db_path, oid):
    rows = _rows(db_path, 'SELECT hidden_at FROM orders WHERE order_id = ?', (oid,))
    return rows[0]['hidden_at'] if rows else 'MISSING'


def _login(page, base, email, pw):
    page.goto(base + '/login', wait_until='domcontentloaded')
    page.fill('input[name=email]', email)
    page.fill('input[name=password]', pw)
    page.click('button[type=submit]')
    page.wait_for_load_state('domcontentloaded')
    if '/login' in page.url:
        raise RuntimeError('登录没成功（停在 %s）' % page.url)


def _open_orders(page, base):
    page.goto(base + '/dashboard/orders', wait_until='commit', timeout=60000)
    page.wait_for_selector('table.data-table, .empty-state', timeout=60000)


def _shot(page, shot_dir, name):
    if not shot_dir:
        return
    try:
        os.makedirs(shot_dir, exist_ok=True)
        page.screenshot(path=os.path.join(shot_dir, name), full_page=True)
    except Exception as exc:
        _log('      （截图失败，不影响判定：%s）' % exc)


def _row_html(page, oid):
    """取订单所在的整个 <tr>，没找到返回空串。"""
    return page.evaluate(
        """(oid) => {
             const rows = Array.from(document.querySelectorAll('table.data-table tbody tr'));
             const hit = rows.find(r => r.innerText.indexOf(oid) >= 0);
             return hit ? hit.innerHTML : '';
           }""", oid)


def _rendered_has(page, oid):
    """页面渲染完成后，表格（或空态）里有没有这串单号。

    返回 None 表示「还没渲染完 / 正在导航」，不能当成「没有」。
    """
    try:
        return page.evaluate(
            """(oid) => {
                 const t = document.querySelector('table.data-table');
                 const e = document.querySelector('.empty-state');
                 if (!t && !e) return null;      /* 还没渲染 */
                 const txt = t ? t.innerText : '';
                 return txt.indexOf(oid) >= 0;
               }""", oid)
    except Exception:
        return None          # 导航中，执行上下文被销毁


def _wait_gone(page, oid, timeout=20):
    """等「表格渲染完成 且 里面没有这串单号」。

    不能写成「body 里搜不到就算没了」：点完删除会 400ms 后 location.reload()，
    刷新那一瞬间 body 是空字符串，任何单号都「搜不到」，于是假成功也会判绿。
    也不能用 wait_for_function：导航会销毁执行上下文，它当场抛异常不会续等。
    所以自己轮询，导航期间的异常跳过，等新页面渲染好再判。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _rendered_has(page, oid) is False:
            return True
        page.wait_for_timeout(300)
    return False


def _wait_present(page, oid, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _rendered_has(page, oid) is True:
            return True
        page.wait_for_timeout(300)
    return False


def case_delete_one(page, base, db_path, shot_dir, selftest=False):
    problems = []

    _open_orders(page, base)
    body = page.inner_text('body')
    for oid in (EXP_A, EXP_B, PAID):
        if oid not in body:
            problems.append('初始状态就看不到订单 %s' % oid)
    if problems:
        return problems

    # 已支付那行绝不能有删除按钮
    if 'orders-del' in _row_html(page, PAID):
        problems.append('已支付订单那一行出现了删除按钮')

    # 顶部按钮要说清有几笔可清
    if '清理全部已过期（2 笔）' not in body:
        problems.append('顶部没有「清理全部已过期（2 笔）」，实际文案里没找到：%r'
                        % body[:200])

    _shot(page, shot_dir, 'orders_before.png')

    if selftest:
        # 造坏：让接口返回「成功」但根本不改库 —— 页面 reload 后那行还在。
        # 如果测试只看接口返回，这里就会假绿。
        def handler(route):
            if '/api/orders/' in route.request.url and route.request.method == 'POST':
                route.fulfill(status=200, content_type='application/json',
                              body='{"success": true, "hidden": 1, '
                                   '"message": "已删除 1 笔订单"}')
            else:
                route.continue_()

        page.route('**/api/orders/*/hide', handler)

    # 点第一笔过期订单的「删除」
    btn = page.query_selector('button.orders-del[data-order="%s"]' % EXP_A)
    if not btn:
        return problems + ['找不到过期订单 %s 的删除按钮' % EXP_A]
    btn.click()

    if not _wait_gone(page, EXP_A, timeout=12):
        problems.append('点了删除，页面刷新后那笔过期订单还在（接口可能只是假成功）')
        return problems

    if not _wait_present(page, EXP_B, timeout=10):
        problems.append('删了一笔，另一笔过期订单也跟着消失了')
    if not _wait_present(page, PAID, timeout=10):
        problems.append('删过期订单把已支付订单也删没了')

    _shot(page, shot_dir, 'orders_after_one.png')
    return problems


def case_clean_all(page, base, db_path, shot_dir):
    problems = []
    _open_orders(page, base)

    btn = page.query_selector('#clean-expired')
    if not btn:
        return ['没有剩下 1 笔可清理的过期订单按钮（上一步可能没删成功）']
    label = btn.inner_text()
    if '1 笔' not in label:
        problems.append('清理按钮上的笔数不对：%r' % label)
    btn.click()

    if not _wait_gone(page, EXP_B, timeout=12):
        problems.append('批量清理后，最后一笔过期订单还在页面上')
        return problems

    body = page.inner_text('body')
    if not _wait_present(page, PAID, timeout=10):
        problems.append('批量清理把已支付订单也删了')
    if '已删除 2 笔' not in body:
        problems.append('没有显示「已删除 2 笔」，实际：%r' % body[:300])
    if page.query_selector('#clean-expired'):
        problems.append('过期订单清完了，清理按钮还挂在那儿（死按钮）')

    _shot(page, shot_dir, 'orders_all_cleaned.png')
    return problems


def case_restore(page, base, db_path, shot_dir):
    problems = []
    _open_orders(page, base)

    btn = page.query_selector('#restore-hidden')
    if not btn:
        return ['找不到「恢复显示」入口 —— 删完就再也找不回来了']
    btn.click()

    if not _wait_present(page, EXP_A, timeout=12):
        problems.append('点了恢复显示，过期订单没回来')
        return problems

    body = page.inner_text('body')
    for oid in (EXP_A, EXP_B, PAID):
        if oid not in body:
            problems.append('恢复后仍看不到 %s' % oid)

    _shot(page, shot_dir, 'orders_restored.png')
    return problems


def run(base, db_path, shot_dir, selftest=False):
    from playwright.sync_api import sync_playwright

    js_errors = []
    console_errors = []
    bad_responses = []

    def on_error(exc):
        js_errors.append('%s' % exc)

    def on_console(msg):
        if msg.type == 'error':
            console_errors.append(msg.text)

    def on_response(resp):
        if resp.status >= 500:
            bad_responses.append('%d %s' % (resp.status, resp.url))

    failures = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        page.on('pageerror', on_error)
        page.on('console', on_console)
        page.on('response', on_response)
        page.on('dialog', lambda d: d.accept())

        _login(page, base, U1, P1)

        problems = case_delete_one(page, base, db_path, shot_dir, selftest=selftest)
        if js_errors:
            problems.append('页面抛了 JS 异常：%s' % js_errors[0].splitlines()[0][:200])
        if console_errors:
            problems.append('控制台报错：%s' % console_errors[0][:200])
        if bad_responses:
            problems.append('有请求 5xx：%s' % bad_responses[0])
        if problems:
            failures.append('单笔删除：' + '；'.join(problems))
        else:
            _log('      ✅ 单笔删除：行消失、另一笔和已支付都还在')

        # 页面刷新后要仍然消失 —— 这一条才证明「落库了」而不是删了 DOM。
        if not selftest:
            _open_orders(page, base)
            if EXP_A in page.inner_text('body'):
                failures.append('刷新后第 1 笔过期订单又出现了 —— 没落库，只删了前端')
            if _hidden(db_path, EXP_A) in (None, 'MISSING'):
                failures.append('页面上删掉了，数据库 hidden_at 却是 %r'
                                % _hidden(db_path, EXP_A))
            if _hidden(db_path, PAID) is not None:
                failures.append('已支付订单的 hidden_at 被写了值')
            else:
                _log('      ✅ 刷新仍在消失，库里 hidden_at 有值，已支付订单未被碰')

            problems = case_clean_all(page, base, db_path, shot_dir)
            if problems:
                failures.append('批量清理：' + '；'.join(problems))
            else:
                _log('      ✅ 批量清理：只剩已支付订单，按钮消失，提示「已删除 2 笔」')

            problems = case_restore(page, base, db_path, shot_dir)
            if problems:
                failures.append('恢复显示：' + '；'.join(problems))
            else:
                _log('      ✅ 恢复显示：三笔订单全部回来')
            if _hidden(db_path, EXP_A) is not None or _hidden(db_path, EXP_B) is not None:
                failures.append('恢复后数据库 hidden_at 没清空')

        browser.close()

    return (1 if failures else 0), failures


def main(argv):
    selftest = '--self-test' in argv
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        _log('SKIP: 没装 playwright，这条守卫没有执行（不是通过）')
        return 2

    tmp = tempfile.mkdtemp(prefix='xp-orders-e2e-')
    db_path = os.path.join(tmp, 'e2e.db')
    data_dir = os.path.join(tmp, 'data')
    os.makedirs(data_dir, exist_ok=True)
    port = _free_port()
    base = 'http://127.0.0.1:%d' % port

    env = dict(os.environ)
    _load_env_file(env)
    env.update({
        'XINPECT_DB_PATH': db_path,
        'XINPECT_DATA_DIR': data_dir,
        'XP_E2E_PORT': str(port),
        'PYTHONDONTWRITEBYTECODE': '1',
    })

    _log('隔离实例：%s（库 %s）' % (base, db_path))
    proc = subprocess.Popen([SYS_PY, SERVE], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True)

    shot_dir = (os.environ.get('XP_E2E_SHOT_DIR')
                or os.path.join(SITE, 'tests', 'reports', 'e2e'))
    try:
        _wait_ready(base, proc)
        _seed(db_path)
        _log('      造数完成：2 笔过期 + 1 笔已支付')
        rc, failures = run(base, db_path, shot_dir, selftest=selftest)
    except Exception as exc:
        _log('❌ 没跑起来：%s' % exc)
        proc.terminate()
        return 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()

    if failures:
        if selftest:
            # 造坏自检的语义：坏例让测试变红 = 自检成功 = 退出码 0。
            # 只有「弄坏了它还全绿」才算这条守卫不合格 —— 那说明它守不住东西。
            # （run_qa_suite.sh 会把 --self-test 的退出码也算进 e2e= 那一段，
            #   所以这里反转不能反。第一版写反了，整套体检会直接判红。）
            _log('')
            _log('✅ 造坏自检通过：坏掉之后确实判红')
            for f in failures:
                _log('   （预期的红）%s' % f)
            return 0
        _log('')
        _log('❌ 订单删除端到端不通过（%d 项）：' % len(failures))
        for f in failures:
            _log('   - %s' % f)
        return 1

    if selftest:
        _log('')
        _log('❌ 造坏自检失败：把接口改成假成功，测试居然还是绿的 —— 守不住')
        return 1

    _log('')
    _log('✅ 订单删除端到端通过')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
