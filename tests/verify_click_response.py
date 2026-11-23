#!/usr/bin/env python3
"""点击响应真值守卫（2026-11-08，QA 6i）。

背景：全局点击监控原来靠「页面上有没有 .loading / .spinner / .modal.show 这类
写死的容器」判断点击有没有响应，还给 6 类按钮开了不检查的例外。试扫换成
XpScanFX 容器之后，一次 4 秒的正常扫描被上报成 click_no_response，
错误日志里全是假警 —— 我们差点以为网站坏了。

治本后的判据：点击那一刻拍一份现场（网址 / 可见文字 / 节点数 / 被点元素状态 /
点击同拍的活动序号），3 秒后逐项比对，任何一项变了就是有响应。
本守卫不读「页面现在长什么样」去猜，而是用真浏览器跑场景，看它到底报不报：

  真没动静 / 纯 CSS 动效 / 只有后台轮询  -> 必须报
  试扫中 / 网址变 / 开关变 / 元素被移除 / 点击同拍发请求 -> 不许报

--self-test 用一份内置参考实现造 11 类坏副本，必须全判红；干净样本必须判绿。
自检不读生产状态、不读任何固定临时文件。
"""
import argparse
import glob
import os
import re
import sys
import tempfile
from pathlib import Path

DEFAULT_ROOT = "/opt/xinpect-website"
MONITOR_MARK = "// 全局错误监控 - 自动捕获并上报前端错误"

# 旧判据的语义特征：一旦复活就是回到「列容器 class + 列按钮例外」的老路。
OLD_CLASS_RE = re.compile(
    r"querySelector\([^)]*\.(?:loading|spinner|scan-progress|modal\.show)", re.I)
OLD_EXCEPTION_RE = re.compile(r"menu-group-header|g-tpl|compare-btn-sm|data-loading", re.I)
EVIDENCE_RES = [
    re.compile(r"window\.location\.href\s*!==\s*before\.url"),
    re.compile(r"visibleTextHash\(\)\s*!==\s*before\.text"),
    re.compile(r"getElementsByTagName\('\*'\)\.length\s*!==\s*before\.nodes"),
    re.compile(r"elementState\(before\.el\)\s*!==\s*before\.state"),
    re.compile(r"before\.el\.isConnected"),
    re.compile(r"activitySeq\s*>\s*before\.seq"),
]

# 参考实现：与生产 main.js 第 3 段同构，只用于自检，避免自检依赖生产当前状态。
REF_MONITOR = r"""(function() {
    'use strict';
    var REPORT_URL = '/api/report-error';
    var reportedErrors = {};
    function reportError(type, message, stack) {
        var fp = type + '|' + message.substring(0, 100);
        if (reportedErrors[fp]) return;
        reportedErrors[fp] = 1;
        navigator.sendBeacon(REPORT_URL, JSON.stringify({type: type, message: message}));
    }
    window.addEventListener('error', function(e) { reportError('js_error', e.message || 'x', ''); });
    window.addEventListener('unhandledrejection', function(e) { reportError('promise_error', 'x', ''); });

    // 3. 捕获按钮/链接点击后「真的没有响应」
    var clickTimeout = null;
    var activitySeq = 0;
    var clickPending = false;

    function noteActivity() { if (clickPending) activitySeq += 1; }

    document.addEventListener('submit', noteActivity, true);
    window.addEventListener('hashchange', noteActivity);
    (function() {
        var push = history.pushState, replace = history.replaceState;
        history.pushState = function() { noteActivity(); return push.apply(history, arguments); };
        history.replaceState = function() { noteActivity(); return replace.apply(history, arguments); };
    }());
    if (window.XMLHttpRequest && XMLHttpRequest.prototype.send) {
        var origSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.send = function() { noteActivity(); return origSend.apply(this, arguments); };
    }

    function visibleTextHash() {
        var s = (document.body && document.body.innerText) || '';
        var h = 5381;
        for (var i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
        return h + ':' + s.length;
    }

    function elementState(el) {
        return [
            el.getAttribute('disabled'), el.getAttribute('class'),
            el.getAttribute('style'), el.getAttribute('aria-expanded'),
            el.getAttribute('aria-pressed'), el.getAttribute('checked'),
            (el.textContent || '').trim().substring(0, 80)
        ].join('|');
    }

    // 捕获阶段才拍得到「点击之前」的现场；冒泡阶段拍到的是按钮改完后的样子。
    document.addEventListener('click', function(event) {
        var interactive = event.target.closest('button, a, [onclick], [role="button"], input[type="submit"]');
        if (!interactive) return;
        var before = {
            url: window.location.href,
            text: visibleTextHash(),
            nodes: document.getElementsByTagName('*').length,
            state: elementState(interactive),
            seq: activitySeq,
            el: interactive
        };
        clickPending = true;
        setTimeout(function() { clickPending = false; }, 0);
        if (clickTimeout) clearTimeout(clickTimeout);
        clickTimeout = setTimeout(function() {
            if (document.hidden) return;
            var responded =
                window.location.href !== before.url ||
                visibleTextHash() !== before.text ||
                document.getElementsByTagName('*').length !== before.nodes ||
                elementState(before.el) !== before.state ||
                !before.el.isConnected ||
                activitySeq > before.seq;
            if (responded) return;
            reportError(
                'click_no_response',
                '点击元素无响应: ' + before.el.tagName + (before.el.id ? '#' + before.el.id : '') + ' "' + (before.el.textContent || '').trim().substring(0, 30) + '"',
                ''
            );
        }, 3000);
    }, true);

    // 4. 捕获 fetch 请求失败
    var origFetch = window.fetch;
    window.fetch = function(url, options) {
        noteActivity();
        return origFetch.apply(this, arguments).then(function(response) {
            if (response.status >= 500) reportError('api_error', 'API请求失败', '');
            return response;
        }).catch(function(error) { throw error; });
    };
})();"""

STUB = r"""<script>
window.__reports = [];
Object.defineProperty(navigator, 'sendBeacon', {configurable: true,
  value: function(u, b) { window.__reports.push(JSON.parse(b)); return true; }});
Object.defineProperty(document, 'hidden', {configurable: true,
  get: function() { return false; }});
window.fetch = function() { return Promise.resolve({status: 200, statusText: 'OK'}); };
// 把场景里的定时器按固定比例加速：生产监控等 3 秒，测试等 150 毫秒即可，
// 判据本身（点击前后现场比对）一字不改。否则 10 场景 × 10 造坏用例要跑近 6 分钟。
var __st = window.setTimeout, __si = window.setInterval;
window.setTimeout = function(fn, ms) { return __st(fn, Math.max(0, Math.ceil((ms||0)/20))); };
window.setInterval = function(fn, ms) { return __si(fn, Math.max(1, Math.ceil((ms||0)/20))); };
</script>"""

PAGE_HEAD = """<!doctype html><html><head><meta charset="utf-8">
<style>@keyframes spin { from { opacity:.4 } to { opacity:1 } }
#deco { animation: spin 1s infinite alternate; }</style>
</head><body><div id="deco">装饰</div><div id="mount">原始内容</div>
<button id="btn" type="button">开始免费检测</button>
"""

# (名称, 场景脚本, 是否应当上报 click_no_response, 额外断言 JS)
SCENARIOS = [
    ("真没动静", "document.getElementById('btn').addEventListener('click', function(){});", True, None),
    ("只有 CSS 动效", "document.getElementById('btn').addEventListener('click', function(){});", True, None),
    # 轮询从「点击之后」开始：这样它的定时器到期时间必然晚于「关闭同拍窗口」的定时器，
    # 场景结果才确定。原来让轮询在页面加载时就跑，点击时可能正好有一次到期，
    # 与关闭窗口的定时器抢先后 —— 同一份代码会时绿时红（2026-11-09 撞上）。
    # 语义没变：点击之后页面在后台发请求，但界面上没有任何响应，仍必须上报。
    ("只有后台轮询",
     "window.__hb = 0;"
     "document.getElementById('btn').addEventListener('click', function(){"
     "setInterval(function(){ window.__hb += 1; fetch('/api/heartbeat'); }, 200); });",
     True, "window.__hb > 0"),
    ("试扫进行中（旧版假警现场）",
     "document.getElementById('btn').addEventListener('click', function(){"
     "var b=document.getElementById('btn'); b.disabled=true; b.textContent='检测中…';"
     "var d=document.createElement('div'); d.id='xp-scanfx-try'; d.textContent='正在初筛';"
     "document.body.appendChild(d); });", False, None),
    ("只新增一个没有文字的容器",
     "document.getElementById('btn').addEventListener('click', function(){"
     "var d=document.createElement('div'); d.className='xp-scanfx-try';"
     "document.body.appendChild(d); });", False, None),
    ("只更新已有区域的文字",
     "document.getElementById('btn').addEventListener('click', function(){"
     "document.getElementById('mount').textContent='已完成 3 条问题'; });", False, None),
    ("网址变化", "document.getElementById('btn').addEventListener('click', function(){ location.hash='#done'; });", False, None),
    ("开关只改自身状态",
     "document.getElementById('btn').addEventListener('click', function(){"
     "var b=document.getElementById('btn'); b.className='on'; b.style.opacity='0.9'; });", False, None),
    ("关闭按钮移除自己",
     "document.getElementById('btn').addEventListener('click', function(){ document.getElementById('btn').remove(); });", False, None),
    ("点击同拍发请求",
     "document.getElementById('btn').addEventListener('click', function(){ fetch('/api/try-scan', {method:'POST'}); });", False, None),
]


def find_chromium():
    env = os.environ.get("XP_CHROMIUM")
    if env and Path(env).is_file():
        return env
    cands = sorted(glob.glob("/home/ubuntu/.cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
    cands += sorted(glob.glob("/root/.cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
    return cands[-1] if cands else None


def import_playwright():
    """QA 以 root 跑时，用户级 playwright 不在 sys.path；找不到必须判红。"""
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        pass
    for pat in ("/home/ubuntu/.local/lib/python3.*/site-packages",
                "/usr/local/lib/python3.*/dist-packages"):
        for hit in glob.glob(pat):
            if hit not in sys.path:
                sys.path.insert(0, hit)
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        return None


def monitor_text(root):
    """从真实 main.js 里截出全局错误监控整个 IIFE（不读片段、不猜行号）。"""
    p = Path(root) / "static/js/main.js"
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8")
    i = text.find(MONITOR_MARK)
    if i < 0:
        return None
    j = text.find("(function() {", i)
    if j < 0:
        return None
    return text[j:]


def static_checks(text):
    errors = []
    if not text:
        return ["S1 监控段缺失或无法从 main.js 截出"]
    if OLD_CLASS_RE.search(text):
        errors.append("S2 旧判据复活：又在按 loading/弹窗 class 猜点击有没有响应")
    if OLD_EXCEPTION_RE.search(text):
        errors.append("S3 按钮例外清单复活：判据重新依赖具体组件名")
    hit = sum(1 for r in EVIDENCE_RES if r.search(text))
    if hit < 4:
        errors.append("S4 现场比对证据不足(%d/6)，判据退回了单点猜测" % hit)
    if not re.search(r"setTimeout\(function\(\) \{[\s\S]{0,1200}?\}, 3000\)", text):
        errors.append("S5 3 秒后复核的定时器不见了")
    if not re.search(r"addEventListener\('click'[\s\S]*?\}, true\);", text):
        errors.append("S6 点击监听必须在捕获阶段，否则快照拍到的是按钮改完之后")
    return errors


def run_scenarios(sp, text, chromium):
    """真浏览器逐个场景跑一遍，返回判红理由列表。"""
    errors = []
    if not text:
        return ["B0 没有可注入的监控脚本"]
    launch = dict(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
    if chromium:
        launch["executable_path"] = chromium
    with sp() as pw:
        browser = pw.chromium.launch(**launch)
        try:
            for item in SCENARIOS:
                name, scene, expect_report = item[0], item[1], item[2]
                check_js = item[3] if len(item) > 3 else None
                page = browser.new_page()
                try:
                    html = (PAGE_HEAD + STUB + "<script>" + text + "</script>"
                            + "<script>" + scene + "</script></body></html>")
                    page.set_content(html, wait_until="load")
                    page.evaluate("document.getElementById('btn').click()")
                    page.wait_for_timeout(600)
                    reports = page.evaluate(
                        "(window.__reports || []).filter(function(r){return r.type==='click_no_response'})")
                    got = len(reports) > 0
                    # 场景自己没跑起来就等于没测，不能当成通过
                    if check_js and not page.evaluate(check_js):
                        errors.append("B %s：场景本身没跑起来（%s 为假）" % (name, check_js))
                    if got != expect_report:
                        errors.append("B %s：期望%s，实际%s" % (
                            name, "上报" if expect_report else "不上报",
                            "上报" if got else "不上报"))
                except Exception as exc:                 # noqa: BLE001
                    errors.append("B %s：场景执行异常 %s" % (name, exc))
                finally:
                    page.close()
        finally:
            browser.close()
    return errors


def evaluate(root, override=None, sp=None, chromium=None):
    text = override if override is not None else monitor_text(root)
    errors = static_checks(text)
    if sp is None:
        sp = import_playwright()
    if sp is None:
        return errors + ["B 真浏览器依赖缺失（playwright 不可用），不能判绿"]
    if chromium is None:
        chromium = find_chromium()
    if not chromium:
        return errors + ["B 真浏览器可执行文件缺失，不能判绿"]
    errors += run_scenarios(sp, text, chromium)
    return errors


def self_test():
    sp = import_playwright()
    chromium = find_chromium()
    if sp is None or not chromium:
        print("FAIL 自检前提不成立：playwright / chromium 不可用")
        return 1

    # 按声明行做语义注入，不写死当前生产文件内容或任何固定临时文件
    def swap_decl(t, pattern, repl):
        out, n = re.subn(pattern, repl, t, count=1, flags=re.M)
        assert n == 1, "造坏注入点没命中: %s" % pattern
        return out

    cases = [
        ("干净样本必须判绿", lambda t: t, False),
        ("退回旧版按 loading class 判会判红",
         lambda t: swap_decl(t, r"var responded =[\s\S]*?before\.seq;",
                             "var responded = !!document.querySelector('.loading, .spinner');"), True),
        ("永远判有响应会判红",
         lambda t: swap_decl(t, r"var responded =[\s\S]*?before\.seq;",
                             "var responded = true;"), True),
        ("永远判没响应会判红",
         lambda t: swap_decl(t, r"var responded =[\s\S]*?before\.seq;",
                             "var responded = false;"), True),
        ("删掉上报调用会判红",
         lambda t: swap_decl(t, r"reportError\(\s*'click_no_response'[\s\S]*?\);",
                             "void 0;"), True),
        ("点击不再标记同拍会判红",
         lambda t: swap_decl(t, r"clickPending = true;", "clickPending = false;"), True),
        ("把后台轮询算成点击响应会判红",
         lambda t: swap_decl(t, r"function noteActivity\(\) \{[^}]*\}",
                             "function noteActivity() { activitySeq += 1; }"), True),
        ("不再比对被点元素自身状态会判红",
         lambda t: swap_decl(t, r"elementState\(before\.el\) !== before\.state \|\|", ""), True),
        ("不再比对可见文字会判红",
         lambda t: swap_decl(t, r"visibleTextHash\(\) !== before\.text \|\|", ""), True),
        ("不再比对节点数会判红",
         lambda t: swap_decl(t, r"document\.getElementsByTagName\('\*'\)\.length !== before\.nodes \|\|", ""), True),
        ("退回冒泡阶段（快照拍晚了）会判红",
         lambda t: swap_decl(t, r"\}, true\);", "});"), True),
    ]

    ok = 0
    failed = 0
    with tempfile.TemporaryDirectory(prefix="xp_click_") as td:
        root = Path(td)
        for name, mutate, want_red in cases:
            text = mutate(REF_MONITOR)
            errs = evaluate(root, override=text, sp=sp, chromium=chromium)
            red = bool(errs)
            good = (red == want_red)
            if good:
                ok += 1
                print("  OK  %s%s" % (name, "" if not red else "（判红 %d 项）" % len(errs)))
            else:
                failed += 1
                print("FAIL  %s：期望%s，实际%s；%s" % (
                    name, "判红" if want_red else "判绿",
                    "判红" if red else "判绿", "; ".join(errs[:3])))
    print("点击响应守卫自测: %d 项, 通过 %d, 失败 %d" % (len(cases), ok, failed))
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    errors = evaluate(args.root)
    if errors:
        for e in errors:
            print("FAIL " + e)
        print("点击响应守卫: %d 项不合格" % len(errors))
        return 1
    print("点击响应守卫: 静态判据 6 项 + 真浏览器 %d 场景全绿" % len(SCENARIOS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
