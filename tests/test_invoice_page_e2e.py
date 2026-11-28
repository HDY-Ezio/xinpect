#!/usr/bin/env python3
"""真浏览器跑一遍开票全流程：勾单 → 提交 → 后台标记已开具。

为什么要有这一层（2026-11-28）
------------------------------
老板用自己的账号（16 笔订单全部 expired、0 笔 paid）进开票页，看到
「选择订单」下面是空的，第一反应是「是不是我这个账号没权限」。这句话
问出来，说明页面根本没解释「为什么一笔都不显示」。

三种情况在页面上原本长得一模一样：
  ① 从没下过单   ② 有订单但都没付款   ③ 付过款但都开过票
所以这一层断言的是**渲染出来的提示**，不是模板里有没有那句话 ——
上一轮 /try 那次教训：后端断言全绿、模板里也有那行字，浏览器一点就是错。

同时把「钱和发票」这条链路真跑一遍：勾选 → 填写抬头税号 → 提交 →
后台看到 pending → 标记已开具 → 用户页显示「已开票」。
只断言接口返回 200 是不够的，要断言数据库里那行真的变了。

隔离
----
空库（XINPECT_DB_PATH 指临时文件）、随机端口、独立数据目录，不碰生产。
用户、订单、管理员全部在临时库里现场造。

用法
----
    /opt/xinpect-e2e/venv/bin/python tests/test_invoice_page_e2e.py
    /opt/xinpect-e2e/venv/bin/python tests/test_invoice_page_e2e.py --self-test

退出码：0 通过 / 1 失败 / 2 环境缺失（没装 playwright，明确「没执行」）
"""
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVE = os.path.join(SITE, 'tests', 'e2e_serve.py')
SYS_PY = '/usr/bin/python3'
ENV_FILE = '/etc/xinpect/website.env'

# 浏览器目录必须和已有三个真渲染守卫（颜色真值 / 冷光质感 / 元素一致性）一致。
# 另建一份只会让一边找不到 —— 我上一次把目录挪到 /opt 就把那三个守卫全判红了。
_PW_BROWSERS = '/home/ubuntu/.cache/ms-playwright'
if os.path.isdir(_PW_BROWSERS) and not os.environ.get('PLAYWRIGHT_BROWSERS_PATH'):
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = _PW_BROWSERS

U1, P1 = 'e2e-invoice-paid@test.local', 'Paid#2026xp'      # 有 1 笔可开票
U2, P2 = 'e2e-invoice-unpaid@test.local', 'Unpaid#2026xp'  # 3 笔全部过期
U3, P3 = 'e2e-invoice-empty@test.local', 'Empty#2026xp'    # 一笔订单都没有
UA, PA = 'e2e-invoice-admin@test.local', 'Admin#2026xp'    # 管理员

PAID_ORDER = 'E2EPAIDORDER0000000000000000000001'

SEED_TMPL = '''
import sqlite3, sys
from werkzeug.security import generate_password_hash

conn = sqlite3.connect(sys.argv[1])
conn.row_factory = sqlite3.Row


def add_user(email, pw, admin=0):
    conn.execute(
        "INSERT INTO users (email, password_hash, is_admin, onboarding_completed,"
        " first_login_at) VALUES (?, ?, ?, 1, datetime('now','localtime'))",
        (email, generate_password_hash(pw), admin))
    return conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]


def add_order(uid, oid, plan, amount, status):
    paid_at = "2026-11-28 10:00:00" if status == "paid" else None
    conn.execute(
        "INSERT INTO orders (order_id, user_id, plan_id, plan_name, amount, status,"
        " paid_at) VALUES (?, ?, 'p_month', ?, ?, ?, ?)",
        (oid, uid, plan, amount, status, paid_at))


u1 = add_user("__U1__", "__P1__")
add_order(u1, "__PAID__", "月卡", 99.0, "paid")
add_order(u1, "E2EEXPIREDORDER000000000000000001", "月卡", 99.0, "expired")

u2 = add_user("__U2__", "__P2__")
for i in range(3):
    add_order(u2, "E2EUNPAIDORDER%026d" % i, "季卡", 269.0, "expired")

add_user("__U3__", "__P3__")
add_user("__UA__", "__PA__", 1)

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
            .replace('__U2__', U2).replace('__P2__', P2)
            .replace('__U3__', U3).replace('__P3__', P3)
            .replace('__UA__', UA).replace('__PA__', PA)
            .replace('__PAID__', PAID_ORDER))
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


def _wait_db(db_path, sql, args=(), timeout=15):
    deadline = time.time() + timeout
    last = []
    while time.time() < deadline:
        last = _rows(db_path, sql, args)
        if last:
            return last
        time.sleep(0.3)
    return last


def _login(page, base, email, pw):
    page.goto(base + '/login', wait_until='domcontentloaded')
    page.fill('input[name=email]', email)
    page.fill('input[name=password]', pw)
    page.click('button[type=submit]')
    page.wait_for_load_state('domcontentloaded')
    if '/login' in page.url:
        raise RuntimeError('登录没成功（停在 %s）' % page.url)


def _new_page(browser, on_error, on_console, accept_dialogs=False, on_response=None):
    page = browser.new_page(viewport={'width': 1280, 'height': 900})
    page.on('pageerror', on_error)
    page.on('console', on_console)
    if on_response is not None:
        page.on('response', on_response)
    page.on('dialog', lambda d: d.accept() if accept_dialogs else d.dismiss())
    return page


def _shot(page, shot_dir, name):
    if not shot_dir:
        return
    try:
        os.makedirs(shot_dir, exist_ok=True)
        page.screenshot(path=os.path.join(shot_dir, name), full_page=True)
    except Exception as exc:
        _log('      （截图失败，不影响判定：%s）' % exc)


def _open_invoice(page, base):
    # 不等 DOMContentLoaded：控制台页引了站内字体/样式，偶发被外部资源拖住，
    # 那是「页面慢」不是「页面错」。判据落在表单真的出现，这才是要看的东西。
    page.goto(base + '/dashboard/invoice', wait_until='commit', timeout=60000)
    try:
        page.wait_for_selector('#invoiceForm', timeout=60000)
    except Exception:
        body = ''
        try:
            body = page.inner_text('body')[:400].replace('\n', ' / ')
        except Exception:
            pass
        raise RuntimeError('开票页没渲染出来：url=%s 正文=%r' % (page.url, body))


def _hint_text(page):
    """空态卡片的文字。有单可开时这张卡不渲染，返回空串。

    不按 CSS 选择器猜位置（那等于拿行窗口当语义），直接取表单里有
    「不能开票 / 没下过单 / 都已开过票 / 都还没付款」的那段。
    """
    text = page.inner_text('#invoiceForm')
    for line in text.splitlines():
        line = line.strip()
        if any(k in line for k in ('都还没付款', '还没有下过单', '都已开过票')):
            return line
    return ''


def _case_unpaid_only(page, base, shot_dir, selftest=False):
    """场景 A：3 笔订单全部过期 —— 必须说出「都没付款」，不许只说「暂无可开票订单」。"""
    problems = []
    _open_invoice(page, base)
    text = page.inner_text('#invoiceForm')
    if '都还没付款' not in text:
        problems.append('没说「订单都还没付款」，用户还会以为是自己没权限：%r'
                        % text[:160])
    if '3 笔' not in text:
        problems.append('没写出具体笔数（3 笔），用户不知道自己名下有订单')
    if '不能开票' not in text:
        problems.append('没解释为什么不能开票')
    if '查看我的订单' not in text:
        problems.append('没给下一步入口「查看我的订单」')
    btn = page.query_selector('#submitBtn')
    if btn and btn.is_enabled():
        problems.append('没有可开票订单，提交按钮却是可点的')
    hint = _hint_text(page)
    _log('      空态：%s' % hint.replace('\n', ' / ')[:160])
    _shot(page, shot_dir, 'invoice_unpaid.png')
    return problems


def _case_no_orders(page, base, shot_dir):
    """场景 B：从没下过单 —— 说「还没下过单」并给「查看套餐」。"""
    problems = []
    _open_invoice(page, base)
    text = page.inner_text('#invoiceForm')
    if '还没有下过单' not in text:
        problems.append('没下过单却说成了别的原因：%r' % text[:160])
    if '查看套餐' not in text:
        problems.append('没给「查看套餐」入口')
    _shot(page, shot_dir, 'invoice_no_orders.png')
    return problems


def _case_full_flow(page, base, db_path, shot_dir):
    """场景 C：有 1 笔已付款 —— 勾单提交，后台标记完成，用户页显示已开票。"""
    problems = []
    _open_invoice(page, base)
    boxes = page.query_selector_all('.order-checkbox')
    if len(boxes) != 1:
        return ['可开票订单应为 1 笔，实际 %d 笔（列表没渲染出来或过滤错了）'
                % len(boxes)]
    if PAID_ORDER not in page.inner_text('#invoiceForm'):
        problems.append('订单号没显示在勾选列表里')
    _shot(page, shot_dir, 'invoice_with_order.png')

    page.check('.order-checkbox')
    page.fill('[name=company_name]', '长沙煋旺智能科技有限公司')
    page.fill('[name=tax_number]', '91430100MA4L0E2Q3W')
    page.fill('[name=email]', 'hdyabcd@163.com')
    page.click('#submitBtn')

    try:
        page.wait_for_function(
            "document.getElementById('submitMsg') &&"
            " document.getElementById('submitMsg').textContent.indexOf('申请已提交') >= 0",
            timeout=30000)
    except Exception as exc:
        msg = ''
        try:
            msg = page.inner_text('#submitMsg')
        except Exception:
            pass
        return ['提交没成功（页面提示：%r，%s）'
                % (msg, str(exc).splitlines()[0])]
    _shot(page, shot_dir, 'invoice_submitted.png')

    rows = _wait_db(db_path, 'SELECT * FROM invoice_requests ORDER BY id DESC')
    if not rows:
        return ['页面说提交成功，数据库里没有开票申请 —— 这就是「假成功」']
    row = rows[0]
    if row['status'] != 'pending':
        problems.append('新申请状态应为 pending，实际 %s' % row['status'])
    if row['order_id'] != PAID_ORDER:
        problems.append('申请的订单号对不上：%s' % row['order_id'])
    if abs(float(row['amount']) - 99.0) > 0.01:
        problems.append('金额不对：%s（应为 99）' % row['amount'])
    if row['tax_number'] != '91430100MA4L0E2Q3W':
        problems.append('税号没存对：%s' % row['tax_number'])

    # 提交后：该订单不能再被选第二次，且要说清「都已开过票」
    _open_invoice(page, base)
    if page.query_selector_all('.order-checkbox'):
        problems.append('同一笔订单提交后还能再勾一次，会开出重复发票')
    text = page.inner_text('#invoiceForm')
    if '都已开过票' not in text:
        problems.append('提交后空态没说「都已开过票」：%r' % text[:160])
    if '待处理' not in page.inner_text('body'):
        problems.append('「我的开票记录」里看不到待处理的申请')
    _log('      ✅ 提交成功：pending / 订单号 / 金额 / 税号 都对，且不能重复勾选')

    # 后台标记已开具：用管理员账号走一次真实 HTTP。
    # 不走 /admin/* 页面 —— 那些页面带 device_check_required（设备绑定），
    # 端到端测试不该去跨那道安全门；要验的是状态流转本身。
    status, body = _admin_complete(base, row['id'])
    if status != 200 or 'success' not in body:
        problems.append('后台标记完成返回 %s：%s' % (status, body[:200]))
        return problems
    done = _wait_db(db_path, 'SELECT status FROM invoice_requests WHERE id = ?',
                    (row['id'],))
    if not done or done[0]['status'] != 'completed':
        problems.append('后台返回 200，库里状态还是 %r —— 假成功'
                        % (done[0]['status'] if done else None))
        return problems

    _open_invoice(page, base)
    page_text = page.inner_text('body')
    if '已开票' not in page_text:
        problems.append('后台已标记完成，用户页却看不到「已开票」')
    if '待处理' in page_text:
        problems.append('用户页仍显示「待处理」，状态没同步过去')
    _shot(page, shot_dir, 'invoice_completed.png')
    _log('      ✅ 后台标记完成，用户页同步为「已开票」')
    return problems


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """不跟 302：跟了就会拿到登录页的 200，看起来像成功 —— 那是假绿。"""

    def redirect_request(self, *args, **kwargs):
        return None


def _admin_complete(base, inv_id):
    """以管理员身份走真实 HTTP 标记已开具，返回 (状态码, 正文)。

    cookie 要手工带上：生产把 session cookie 设成 Secure（HTTPS 上正确），
    Chrome 把 127.0.0.1 当安全上下文所以照存照发，而 Python 的 cookiejar
    不会 —— 直接用它复现，登录会被判定没登录，302 回登录页。
    """
    opener = urllib.request.build_opener(_NoRedirect())
    login_req = urllib.request.Request(
        base + '/login', method='POST',
        data=urllib.parse.urlencode({'email': UA, 'password': PA}).encode())
    heads = None
    try:
        with opener.open(login_req, timeout=30) as resp:
            heads = resp.headers
    except urllib.error.HTTPError as exc:
        heads = exc.headers
        if exc.code not in (301, 302, 303, 307):
            return exc.code, exc.read().decode('utf-8', 'replace')
    cookie = '; '.join(c.split(';')[0] for c in (heads.get_all('Set-Cookie') or []))
    if 'session=' not in cookie:
        return 401, '登录没拿到 session cookie：%r' % cookie[:120]

    req = urllib.request.Request(
        base + '/api/admin/invoices/%d/complete' % inv_id, data=b'',
        method='POST', headers={'X-Requested-With': 'XMLHttpRequest',
                                'Cookie': cookie})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode('utf-8', 'replace')


def run(base, db_path, shot_dir, selftest=False):
    from playwright.sync_api import sync_playwright

    js_errors = []
    console_errors = []
    http_noise = re.compile(r'Failed to load resource.*\b(4\d\d)\b')

    def on_error(exc):
        js_errors.append('%s' % exc)

    bad_responses = []

    def on_console(msg):
        if msg.type == 'error' and not http_noise.search(msg.text):
            console_errors.append(msg.text)

    def on_response(resp):
        if resp.status >= 500:
            bad_responses.append('%d %s' % (resp.status, resp.url))

    failures = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--no-sandbox'])

        # ---- 场景 A（也承载造坏自检）----
        js_errors.clear()
        console_errors.clear()
        page = _new_page(browser, on_error, on_console, on_response=on_response)
        _login(page, base, U2, P2)
        if selftest:
            state = {'anchor': 0}

            def handler(route):
                resp = route.fetch()
                body = resp.text()
                bad, n = re.subn(r'都还没付款', '暂无可开票订单', body)
                state['anchor'] = n
                route.fulfill(response=resp, body=bad)

            page.route('**/dashboard/invoice', handler)
            _open_invoice(page, base)
            if state['anchor'] == 0:
                browser.close()
                return 1, ['造坏锚点失效：页面里找不到「都还没付款」，'
                           '坏例根本没造出来，自检不算数']
            problems = _case_unpaid_only(page, base, shot_dir)
            page.close()
            browser.close()
            if problems:
                _log('      造坏后确实判红：%s' % problems[0])
                return 0, []
            return 1, ['换成旧文案仍然全绿 —— 这条守不住「为什么没订单」，自检不算通过']

        problems = _case_unpaid_only(page, base, shot_dir)
        if js_errors:
            problems.append('页面抛了 JS 异常：%s' % js_errors[0].splitlines()[0][:200])
        if console_errors:
            problems.append('控制台报错：%s' % console_errors[0][:200])
        if bad_responses:
            problems.append('有请求 500：%s' % bad_responses[0])
        if problems:
            failures.append('场景 A（只有过期订单）：' + '；'.join(problems))
        else:
            _log('      ✅ 说过期订单都没付款、写明笔数、带入口')
        page.close()

        # ---- 场景 B ----
        js_errors.clear()
        console_errors.clear()
        page = _new_page(browser, on_error, on_console, on_response=on_response)
        _login(page, base, U3, P3)
        problems = _case_no_orders(page, base, shot_dir)
        if js_errors:
            problems.append('页面抛了 JS 异常：%s' % js_errors[0].splitlines()[0][:200])
        if problems:
            failures.append('场景 B（没有订单）：' + '；'.join(problems))
        else:
            _log('      ✅ 没下过单时说清了原因并给套餐入口')
        page.close()

        # ---- 场景 C：全流程 ----
        js_errors.clear()
        console_errors.clear()
        page = _new_page(browser, on_error, on_console, on_response=on_response)
        _login(page, base, U1, P1)
        problems = _case_full_flow(page, base, db_path, shot_dir)
        if js_errors:
            problems.append('页面抛了 JS 异常：%s' % js_errors[0].splitlines()[0][:200])
        if console_errors:
            problems.append('控制台报错：%s' % console_errors[0][:200])
        if bad_responses:
            problems.append('有请求 500：%s' % bad_responses[0])
        if problems:
            failures.append('场景 C（提交开票）：' + '；'.join(problems))
        page.close()

        browser.close()

    return (1 if failures else 0), failures


def main(argv):
    selftest = '--self-test' in argv
    try:
        import playwright  # noqa: F401
    except ImportError:
        _log('❌ 没装 playwright（%s）。这一层没有跑，不等于开票页没问题。'
             % sys.executable)
        return 2

    tmp = tempfile.mkdtemp(prefix='xp-inv-e2e-')
    db = os.path.join(tmp, 'xinpect.db')
    data_dir = os.path.join(tmp, 'data')
    os.makedirs(data_dir, exist_ok=True)

    port = _free_port()
    base = 'http://127.0.0.1:%d' % port

    env = os.environ.copy()
    _load_env_file(env)
    env['PORT'] = str(port)
    env['XP_E2E_PORT'] = str(port)
    env['XINPECT_DB_PATH'] = db
    env['XINPECT_DATA_DIR'] = data_dir
    env['FLASK_DEBUG'] = 'false'
    env.pop('PYTHONPATH', None)

    _log('实例隔离：db=%s port=%d' % (db, port))
    proc = subprocess.Popen([SYS_PY, SERVE], cwd=SITE, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True)
    try:
        _wait_ready(base, proc)
        _seed(db)
        _log('      造数完成：1 笔 paid + 1 笔 expired / 3 笔 expired / 0 笔 / 管理员')

        shot_dir = (os.environ.get('XP_E2E_SHOT_DIR')
                    or os.path.join(SITE, 'tests', 'reports', 'e2e'))
        rc, failures = run(base, db, shot_dir, selftest=selftest)
    except Exception:
        # 页面 500 时必须能看到隔离实例自己的报错，否则只能猜。
        proc.terminate()
        out = ''
        try:
            out = proc.stdout.read() or ''
        except Exception:
            pass
        except_text = out[-4000:]
        if except_text.strip():
            _log('--- 隔离实例输出（截尾 4000 字）---')
            _log(except_text)
        raise
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()

    server_out = ''
    try:
        server_out = proc.stdout.read() or ''
    except Exception:
        pass

    if failures:
        # 500 的 traceback 只在隔离实例自己的日志里，不打出来就只能猜。
        noise = ('GET /static/', 'GET /dashboard', 'GET /login')
        keep = [ln for ln in server_out.splitlines()
                if ln.strip() and not ln.lstrip().startswith('127.0.0.1')
                or ('POST' in ln or ' 500 ' in ln)]
        keep = [ln for ln in keep if not any(n in ln for n in noise)]
        if keep:
            _log('')
            _log('--- 隔离实例日志（截尾 30 行）---')
            for ln in keep[-30:]:
                _log(ln)
        _log('')
        _log('❌ 开票端到端不通过（%d 项）：' % len(failures))
        for item in failures:
            _log('   · %s' % item)
        return 1
    _log('')
    _log('✅ 开票端到端通过：三种空态说清原因，提交→后台→完成 全链路走通')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
