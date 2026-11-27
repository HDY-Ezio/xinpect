#!/usr/bin/env python3
"""真浏览器跑一次 /try：断言的是渲染出来的 DOM，不是源码里有没有那行字。

为什么必须有这一层（2026-11-27）
--------------------------------
11-26 修「短碎片也要给结论」时，后端 15 条断言全绿、node --check rc=0、
showNotScannable 也确实在 try.html 里，浏览器一点却是「网络错误，请稍后再试」。
根因是那个函数引用了 doTryScan 的局部变量 errBox，ReferenceError 被 fetch 的
catch 吞掉。作用域错误任何静态检查都看不见，只有页面真跑一遍才现形。

这一层的职责就一句话：起一个隔离实例，用无头 Chromium 点一次 #scan-btn，
断言 DOM 长成该有的样子，并把所有 JS 异常当失败。

隔离
----
不碰生产库（XINPECT_DB_PATH 指向临时空库）、不碰生产端口、不写生产结果库
（XINPECT_DATA_DIR 同样指到临时目录）、不起后台队列线程。

用法
----
    /opt/xinpect-e2e/venv/bin/python tests/test_try_page_e2e.py
    /opt/xinpect-e2e/venv/bin/python tests/test_try_page_e2e.py --self-test

退出码：0 通过 / 1 失败 / 2 环境缺失（没装浏览器：明确「没执行」，不是绿）
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVE = os.path.join(SITE, 'tests', 'e2e_serve.py')
SYS_PY = '/usr/bin/python3'
ENV_FILE = '/etc/xinpect/website.env'

# 浏览器目录必须和已有三个真渲染守卫（颜色真值 / 冷光质感 / 元素一致性）一致：
# 它们硬编码 glob /home/ubuntu/.cache/ms-playwright/chromium-*/chrome-linux64/chrome。
# 这里改用同一个位置而不是另建一处 —— 两份浏览器只会导致「一边能跑一边找不到」，
# 我第一次把目录挪到 /opt 就把那三个守卫全判红了。root 跑时必须显式给路径，
# 否则 playwright 会去 /root/.cache 找。
_PW_BROWSERS = '/home/ubuntu/.cache/ms-playwright'
if os.path.isdir(_PW_BROWSERS) and not os.environ.get('PLAYWRIGHT_BROWSERS_PATH'):
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = _PW_BROWSERS

# 一段什么都不像的输入。用户 11-21 连试 8 次就卡在这种东西上（"1"、"a = 1"）。
NOT_CODE = '1'

# 一段真会被判高危的 Python：只用来看「正常链路还能不能出报告」。
VULN_CODE = (
    'import sqlite3\n'
    'from flask import request\n'
    '\n'
    'def login():\n'
    "    user = request.args.get('user')\n"
    "    conn = sqlite3.connect('db.sqlite')\n"
    '    conn.execute("SELECT * FROM users WHERE name=\'" + user + "\'")\n'
    '    return "ok"\n'
)


def _log(msg):
    print(msg, flush=True)


def _free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _load_env_file(env):
    """补齐 XINPECT_SECRET / SCANNER_* 等必需环境变量（只补缺的，不覆盖）。"""
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
            with urllib.request.urlopen(base + '/try', timeout=3) as resp:
                if resp.status == 200:
                    return True
        except Exception as exc:  # 还在启动
            last = '%s' % exc
        time.sleep(0.4)
    raise RuntimeError('%ds 内实例没起来（最后一次错误：%s）' % (timeout, last))


def _api_not_code_error(base):
    """直接问后端要一次文案，用于验证前端是用 data.error 而不是自己编话。"""
    payload = json.dumps({'code': NOT_CODE, 'language': 'auto'}).encode('utf-8')
    req = urllib.request.Request(
        base + '/api/try-scan', data=payload,
        headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read().decode('utf-8'))


def _new_page(browser, base, on_error, on_console):
    page = browser.new_page(viewport={'width': 1280, 'height': 900})
    page.on('pageerror', on_error)
    page.on('console', on_console)
    page.on('dialog', lambda d: d.dismiss())
    page.goto(base + '/try', wait_until='domcontentloaded')
    return page


def _case_not_scannable(page, base, expected_error, timeout=60000):
    """场景 A：贴一个「1」，必须给结论卡，且不能同时出现空报告。"""
    problems = []
    page.fill('#code-input', NOT_CODE)
    page.click('#scan-btn')
    try:
        page.wait_for_selector('#result-error', state='visible', timeout=timeout)
    except Exception as exc:
        return ['结论卡没出现（%s）' % str(exc).splitlines()[0]]

    text = page.inner_text('#result-error')
    if '这次没有检查' not in text:
        problems.append('卡片标题不是「这次没有检查」：%r' % text[:120])
    if '没有执行扫描' not in text:
        problems.append('没写明「没有执行扫描」，用户会读成检查通过')
    # 文案必须来自后端：后端那句里带「没有任何一门编程语言的语法特征」
    if expected_error and '没有任何一门编程语言' not in text:
        problems.append('卡片正文不是后端返回的 data.error（前端自己编了话）')
    if '网络错误' in text or '请稍后再试' in text:
        problems.append('把「没有代码」说成了系统故障：%r' % text[:120])
    if page.is_visible('#result-content'):
        problems.append('结果区同时亮着，等于用空报告冒充「检查通过」')
    return problems


def _case_vuln_code(page, base):
    """场景 B：真代码必须照常出报告 —— 修 A 不能把正常链路改坏。"""
    problems = []
    page.fill('#code-input', VULN_CODE)
    page.click('#scan-btn')
    try:
        page.wait_for_selector('#result-content', state='visible', timeout=120000)
    except Exception as exc:
        return ['正常代码没出报告（%s）' % str(exc).splitlines()[0]]
    text = page.inner_text('#result-content')
    if len(text.strip()) < 20:
        problems.append('结果区是空的：%r' % text[:120])
    if '网络错误' in text:
        problems.append('结果区显示网络错误')
    _log('      结果区前 240 字：%s' % text.strip().replace('\n', ' / ')[:240])
    return problems


def run(base, shot_dir, selftest=False):
    from playwright.sync_api import sync_playwright

    js_errors = []
    console_errors = []

    # 浏览器会把「我们自己回的 4xx」也记成 console error：
    # 不可扫描是 400、超量是 413/429，这些都是**有内容的答案**，不是故障。
    # 只放过这一种，凡是 console.error 主动报的、或别的资源挂了，照旧判红。
    http_answer_noise = re.compile(r'Failed to load resource.*\b(400|413|429)\b')

    def on_error(exc):
        js_errors.append('%s' % exc)

    def on_console(msg):
        if msg.type == 'error' and not http_answer_noise.search(msg.text):
            console_errors.append(msg.text)

    expected = _api_not_code_error(base)
    if not expected.get('not_scannable'):
        return 1, ['后端对「1」没有返回 not_scannable：%r' % expected]

    failures = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--no-sandbox'])

        # ---- 场景 A ----
        js_errors.clear()
        console_errors.clear()
        if selftest:
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            page.on('pageerror', on_error)
            page.on('console', on_console)
            page.on('dialog', lambda d: d.dismiss())
            state = {'anchor': 0}

            def handler(route):
                resp = route.fetch()
                body = resp.text()
                bad, n = re.subn(
                    r"[ \t]*const box = document\.getElementById\('result-error'\);",
                    '', body)
                state['anchor'] = n
                route.fulfill(response=resp, body=bad)

            page.route('**/try', handler)
            page.goto(base + '/try', wait_until='domcontentloaded')
            if state['anchor'] == 0:
                browser.close()
                return 1, ['造坏锚点失效：try.html 里找不到 `const box = ...`，'
                           '坏例根本没造出来，自检不算数']
        else:
            page = _new_page(browser, base, on_error, on_console)

        problems = _case_not_scannable(
            page, base, expected.get('error'), timeout=15000 if selftest else 60000)
        if js_errors:
            problems.append('页面抛了 JS 异常：%s' % js_errors[0].splitlines()[0][:200])
        if console_errors:
            problems.append('控制台报错：%s' % console_errors[0][:200])
        if shot_dir:
            try:
                os.makedirs(shot_dir, exist_ok=True)
                name = 'try_not_scannable_bad.png' if selftest else 'try_not_scannable.png'
                page.screenshot(path=os.path.join(shot_dir, name), full_page=True)
            except Exception as exc:
                _log('      （截图失败，不影响判定：%s）' % exc)

        if selftest:
            page.close()
            browser.close()
            if problems:
                _log('      造坏后确实判红：%s' % problems[0])
                return 0, []
            return 1, ['造坏后仍然全绿 —— 这条测试守不住作用域错误，自检不算通过']

        if problems:
            failures.append('场景 A（贴「1」）：' + '；'.join(problems))
        else:
            _log('      ✅ 结论卡标题、后端文案、未出报告 都对')
        page.close()

        # ---- 场景 B ----
        js_errors.clear()
        console_errors.clear()
        page = _new_page(browser, base, on_error, on_console)
        problems = _case_vuln_code(page, base)
        if js_errors:
            problems.append('页面抛了 JS 异常：%s' % js_errors[0].splitlines()[0][:200])
        if shot_dir:
            try:
                page.screenshot(path=os.path.join(shot_dir, 'try_report.png'),
                                full_page=True)
            except Exception:
                pass
        if problems:
            failures.append('场景 B（真代码）：' + '；'.join(problems))
        else:
            _log('      ✅ 正常代码照常出报告')
        page.close()
        browser.close()

    return (1 if failures else 0), failures


def main(argv):
    selftest = '--self-test' in argv
    try:
        import playwright  # noqa: F401
    except ImportError:
        _log('❌ 没装 playwright（%s）。这一层没有跑，不等于前端没问题。' % sys.executable)
        return 2

    tmp = tempfile.mkdtemp(prefix='xp-e2e-')
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
        shot_dir = os.environ.get('XP_E2E_SHOT_DIR') or os.path.join(SITE, 'tests', 'reports', 'e2e')
        rc, failures = run(base, shot_dir, selftest=selftest)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        shutil.rmtree(tmp, ignore_errors=True)

    if rc == 0:
        _log('✅ 前端实点通过（%s）' % ('造坏自检' if selftest else '两个场景'))
        return 0
    _log('❌ 前端实点失败：')
    for f in failures:
        _log('   - ' + f)
    return rc


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
