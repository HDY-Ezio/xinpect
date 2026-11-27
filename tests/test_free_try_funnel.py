#!/usr/bin/env python3
"""免注册试扫「漏斗」守卫。

背景（2026-11-04）：/try 页面 2026-10-28 就做完了、接口也是通的，
但整整一周**没有一个真人走到它面前**：
  - 全站导航第 4 项「快速体验」指向 /upload，未登录 302 到登录页 → 第一道墙
  - 定价页免费档按钮同样指向 /upload → 第二道墙
  - sitemap.xml 里列的是 /upload（登录墙），/try 根本没被搜索引擎看见
  - 登录页/注册页底部只有「立即注册」，没有「先试试」的退路

所以真正要守的不是"页面存在"，而是**"从任何一页都走得进去"**：
  1. 匿名状态下，导航给的入口必须是 /try（不是 /upload）
  2. 定价页免费档、登录页、注册页都必须有 /try 的退路
  3. sitemap 只收匿名可见的页（收录登录墙等于把爬虫往墙上撞）
  4. /try 页与 /api/try-scan 必须**真能跑出结果**——不是"有路由"，是"能出数"
  5. 试扫结果必须仍是"摘要"：只能有 category/name/severity，不能漏行号和代码

跑法（服务器没装 pytest，两种都支持；需要 website.env 里的扫描器配置）：
    sudo bash -c 'set -a; . /etc/xinpect/website.env; set +a; python3 tests/test_free_try_funnel.py'
    pytest tests/test_free_try_funnel.py -q
"""

import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(BASE, 'templates')

# 摘要字段白名单：多一个字段就等于把「完整报告」免费送了
SUMMARY_ITEM_KEYS = {'category', 'name', 'severity'}


def _client():
    sys.path.insert(0, BASE)
    from app import app
    app.config['TESTING'] = True
    # 埋点不走测试请求，避免污染访客数据（与 test_retention 同一开关）
    app.config['VISITOR_ANALYTICS_ALLOW_TESTING'] = False
    # 造坏自检要能立刻读到改过的模板。TESTING 模式下 Jinja 默认缓存模板，
    # 造了坏却读到旧模板 = 自检假绿（这个坑踩过）。
    app.jinja_env.auto_reload = True
    return app, app.test_client()


def _html(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, '%s 返回 %d（期望 200）' % (path, resp.status_code)
    return resp.get_data(as_text=True)


def test_try_page_anonymous_open():
    """匿名打开 /try 必须是 200 的页面，不能被登录墙挡住。"""
    app, client = _client()
    resp = client.get('/try')
    assert resp.status_code == 200, '/try 匿名访问返回 %d，登录墙把入口挡死了' % resp.status_code
    html = resp.get_data(as_text=True)
    assert 'code-input' in html, '/try 页面里没有代码输入框（code-input）'
    assert '/api/try-scan' in html, '/try 页面的前端没有调用 /api/try-scan'
    print('    /try 匿名可开，输入框与接口调用都在')


def test_nav_entry_points_to_try():
    """匿名访客在任何页面的导航里，都必须能直接点到 /try。

    2026-11-22 改判据：导航已经收成唯一一份（templates/_nav.html），首页不再
    自带一套。原判据写死了 `<a href="/try">免费试扫</a>` 这个精确写法，导航
    换结构就假红，而且只覆盖「首页 + 定价页」两页。
    现在按渲染结果判：三页都必须有导航容器，容器里都必须有 /try，且不能有
    /upload（匿名点了会 302 到登录页）。判「有没有」，不判「怎么写」。
    """
    app, client = _client()

    for path in ('/', '/pricing', '/blog'):
        html = _html(client, path)
        m = re.search(r'<nav[^>]*xp-nav-links[^>]*>(.*?)</nav>', html, re.S)
        assert m, '%s 找不到全站导航容器（xp-nav-links）' % path
        nav = m.group(1)
        assert 'href="/try"' in nav, '%s 的导航里没有 /try' % path
        assert '/upload' not in nav, '%s 的导航指向 /upload（匿名会 302 到登录页）' % path
    print('    导航：三个页面同一份，匿名 → /try，没有再撞登录墙')


def test_pricing_offers_free_try():
    """定价页的免费档必须给「先试扫」的退路，而不是直接推注册。"""
    app, client = _client()
    html = _html(client, '/pricing')
    assert 'href="/try"' in html, '定价页没有 /try 入口'
    assert '免注册' in html, '定价页没有说明可以免注册试扫'
    print('    定价页免费档已挂 /try')


def test_auth_pages_offer_way_out():
    """登录/注册/找回密码三个页面都要给「不想注册先试扫」的退路。"""
    app, client = _client()
    for path in ('/login', '/register'):
        html = _html(client, path)
        assert 'href="/try"' in html, '%s 没有 /try 退路' % path
    print('    登录页、注册页都有 /try 退路')


def test_sitemap_points_at_anonymous_pages():
    """sitemap 只能收匿名可见的页；登录墙（/upload）收进去等于浪费爬虫预算。"""
    app, client = _client()
    resp = client.get('/sitemap.xml')
    assert resp.status_code == 200
    xml = resp.get_data(as_text=True)
    assert '<loc>https://xinpect.xingwangzhineng.com/try</loc>' in xml, 'sitemap 里没有 /try'
    assert '/upload' not in xml, 'sitemap 里仍然有 /upload（未登录 302 到登录页，爬虫抓到的是墙）'
    print('    sitemap：收录 /try，不再收录 /upload')


def test_auth_pages_brand_consistent():
    """三个认证页曾经是手搓「X」方块 + 「煋鉴 Xinpect」双写，必须统一成品牌图。"""
    app, client = _client()
    for path in ('/login', '/register', '/forgot-password'):
        html = _html(client, path)
        assert 'logo-icon' not in html, '%s 里还有手搓的字母 X 图标（logo-icon）' % path
        assert 'xinpect-mark-wide-128.png' in html, '%s 没有引用品牌图 xinpect-mark-wide-128.png' % path
    print('    三个认证页品牌图已统一')


def test_referral_modal_not_for_anonymous():
    """推荐弹窗不许拦还没账号的人。

    实测（2026-11-04 截图）：匿名打开定价页，第一眼就被「推荐有礼 双方得利」
    全屏盖住，而弹窗里的按钮写着「获取我的推荐链接」→ 点进去是登录页。
    对一个还没注册的人谈"拉朋友"，等于第一次见面先递会员卡。
    治本：弹窗只对登录用户自动弹；匿名态只留顶部可关闭的横幅。
    """
    app, client = _client()
    html = _html(client, '/pricing')
    assert 'var loggedIn = false' in html, '匿名态渲染出的 loggedIn 不是 false（弹窗会拦新访客）'
    # 匿名态下弹窗里的 CTA 必须指向注册，而不是「我的推荐链接」后台页
    modal = re.search(r'<div id="referral-modal".*?</div>\s*</div>\s*</div>', html, re.S)
    assert modal, '找不到推荐弹窗结构'
    assert '/dashboard/account' not in modal.group(0), '匿名态弹窗仍然把访客指向「我的推荐链接」（会跳登录页）'
    print('    推荐弹窗：匿名不自动弹，CTA 指向注册')


def test_try_scan_really_returns_summary():
    """真跑一次试扫：必须出结果，且结果只能是摘要。

    引擎地址不是环境变量，是 modules.constants 里的常量（默认指本机绿版），
    所以这里不在 os.environ 里找，直接问常量——"有路由"不算通，"能出数"才算通。
    """
    app, client = _client()
    from modules.constants import SCANNER_URL
    assert SCANNER_URL, 'modules.constants.SCANNER_URL 是空的，试扫必然打不通'
    # 额度按访客 id 记账（不再是进程内计数、也不按 IP），而 _client() 每次都是
    # 全新的 test_client，拿到的是全新的 vid，天生满额 3 次，不需要手动清理。
    code = (
        'import os\n'
        'import sqlite3\n'
        'def q(uid):\n'
        '    conn = sqlite3.connect("a.db")\n'
        '    cur = conn.cursor()\n'
        '    cur.execute("SELECT * FROM users WHERE id=" + uid)\n'
        '    return cur.fetchall()\n'
        'def run(cmd):\n'
        '    os.system(cmd)\n'
    )
    resp = client.post('/api/try-scan', json={'code': code, 'language': 'python'})
    assert resp.status_code == 200, '试扫接口返回 %d：%s' % (resp.status_code, resp.get_data(as_text=True)[:200])
    data = resp.get_json()
    assert data.get('status') == 'ok', '试扫没返回 ok：%s' % data
    summary = data.get('summary') or {}
    total = summary.get('total_issues')
    assert total and total >= 1, '这段有明显 SQL 注入和命令执行的代码，试扫检出 %s 条' % total
    assert summary.get('severity_breakdown'), '结果里没有严重度分布'
    assert (summary.get('health') or {}).get('grade'), '结果里没有健康度评级'

    # 摘要边界：多给一个字段就等于把完整报告免费送出去
    for item in summary.get('highlights') or []:
        extra = set(item) - SUMMARY_ITEM_KEYS
        assert not extra, '试扫摘要泄漏了字段 %s（只允许 category/name/severity）' % extra
    print('    真跑通过：检出 %d 条，评级 %s，摘要无泄漏' % (total, summary['health']['grade']))


# ---- 「手上没代码」：一键示例（2026-11-24）-------------------------------
# 实况：近 14 天 23 个真人打开 /try，14 个一页没往下看就走了、一个动作都没有。
# 他们不是被语言识别挡住的（全历史 need_language 只有 10 次，6 次还是同一个人
# 在同一晚连续粘 7~19 字节的半行代码），是手上没有可分的东西。

def test_try_page_offers_sample_for_people_without_code():
    """试扫页必须给「不知道粘什么」的人一条活路：一个一键填示例的按钮。

    示例内容来自服务端（free_try.SAMPLE_CODE + tojson 注入）。前端写死一份的话，
    测试验的那段和用户真填的那段会漂成两份——这跟语言表和特征表各改各的是同一个病。
    """
    app, client = _client()
    html = _html(client, '/try')
    assert 'onclick="loadSampleCode()"' in html, '试扫页没有「用示例试试」按钮'
    assert 'function loadSampleCode()' in html, '按钮 onclick 指向 loadSampleCode，但页面上没有这个函数（点了会全无反应）'
    assert 'sample_code|tojson' not in html, '模板变量没渲染，页面上出现 {{ sample_code|tojson }} 字面量'
    print('    示例按钮在页面上，且内容走服务端注入')


def test_sample_code_really_yields_issues():
    """示例代码必须真扫得出问题。

    填进去给一份「0 条问题」的空报告，比不给示例更糟——用户会以为这工具什么都查不出来。
    所以这里真跑一次接口（走自动识别，跟用户点按钮是同一条路径），不看字符串在不在。
    """
    app, client = _client()
    from modules.free_try import SAMPLE_CODE, TRY_LANGS
    from modules.lang_detect import detect

    assert SAMPLE_CODE and SAMPLE_CODE.count('\n') >= 5, \
        '示例代码只有 %d 行，太短了，自动识别必然认不出' % (SAMPLE_CODE.count('\n') + 1)
    guessed, top, second = detect(SAMPLE_CODE)
    assert guessed, '示例代码自动识别不出来（top=%r second=%r）' % (top, second)
    supported = {v for v, _label, _ext in TRY_LANGS}
    assert guessed in supported, '示例代码识别成 %r，但试扫语言表里没有这门（认出来也用不了）' % guessed

    resp = client.post('/api/try-scan', json={'code': SAMPLE_CODE, 'language': 'auto'})
    assert resp.status_code == 200, \
        '示例代码走自动识别被拒（%d）：%s' % (resp.status_code, resp.get_data(as_text=True)[:200])
    data = resp.get_json() or {}
    summary = data.get('summary') or {}
    total = summary.get('total_issues')
    assert total and total >= 2, \
        '示例代码只扫出 %s 条问题——它同时含 SQL 注入和命令注入，少于 2 条说明规则没覆盖到' % total
    print('    示例 %d 行 → 识别 %s → 检出 %d 条，评级 %s'
          % (SAMPLE_CODE.count('\n') + 1, guessed, total, (summary.get('health') or {}).get('grade')))


def test_home_hero_ctas_are_alive():
    """首页 hero 上的按钮指向必须匿名可达。

    守的是「别指到 404」，不是「必须推哪个」——主推换不换是产品决策，会变；
    死链不会变对。本轮主推从「免费试扫」换成了「先看一份真实报告」，
    唯一被数据证明有转化的路径就是 /sample-report → /try。
    """
    app, client = _client()
    html = _html(client, '/')
    m = re.search(r'<div class="hero-actions">(.*?)</div>', html, re.S)
    assert m, '首页找不到 hero-actions 区块'
    hrefs = re.findall(r'href="(/[^"]*)"', m.group(1))
    assert hrefs, 'hero 区一个链接都没有'
    for h in hrefs:
        r = client.get(h)
        assert r.status_code == 200, 'hero 上的 %s 匿名访问返回 %d' % (h, r.status_code)
    print('    hero 链接全部 200：%s' % ', '.join(hrefs))



# ---- 短碎片必须有明确答复（2026-11-27）-----------------------------------
# 实况：有人拿 "1"、"a = 1"、"int a = 1;" 来试工具——就想看看这东西到底行不行。
# 旧逻辑一门语言都没识别出来时，塞 4 个兜底语言按钮，点下去就拿 "1" 去扫，
# 回一张「0 问题 / A 级」的空报告。用「扫了没事」冒充「没检查」，
# 用户会直接判定这东西是假的——他无从知道我们根本没看。
# 现在：明确说「这次没有执行扫描 + 为什么 + 接下来怎么办」，且不再猜语言。


def test_short_fragment_gets_a_verdict_not_a_guess():
    """零特征输入必须得到「没有执行扫描」的明确答复，不许让人在语言里猜。

    判据三条，缺一不可：
      1) 说清了「没扫」：not_scannable + checked=False + 文案里有「没有执行扫描」
      2) 没有 candidates：零特征时给按钮，就是在假装我们知道它是哪门语言
      3) 带事实（字符数/行数）：用户要能从回复里看出「系统确实看了我发的东西」

    造坏自检：把 not_cand 分支改回塞 4 个兜底语言，这条必须变红。
    """
    app, client = _client()
    for payload in ('1', '0', 'a = 1', 'int a = 1;', 'hello', '\u4f60\u597d'):
        resp = client.post('/api/try-scan', json={'code': payload, 'language': 'auto'})
        data = resp.get_json() or {}
        assert resp.status_code == 400, \
            '「%s」返回 %d，应为 400：明确拒绝，不能用 200 冒充检查过' % (payload, resp.status_code)
        assert data.get('not_scannable') is True, \
            '「%s」没标 not_scannable，前端只能当普通错误渲染：%r' % (payload, data)
        assert data.get('checked') is False, '「%s」声称检查过了' % payload
        assert not data.get('candidates'), \
            '「%s」又给了语言候选：零特征时给按钮等于假装认出来了：%r' % (payload, data.get('candidates'))
        assert '没有执行扫描' in (data.get('error') or ''), \
            '「%s」的回复没说清「没扫」，用户会读成「检查通过」或「系统坏了」：%r' % (
                payload, data.get('error'))
        assert data.get('size') == len(payload), \
            '「%s」没报出实际字符数（应为 %d，实得 %r）' % (payload, len(payload), data.get('size'))
        assert data.get('lines') == 1, \
            '「%s」没报出实际行数（应为 1，实得 %r）' % (payload, data.get('lines'))
    print('    6 种碎片全部得到「没检查」的明确答复，且不再猜语言')


def test_not_scannable_never_burns_a_free_try():
    """拒绝不许扣免费次数——额度账本是 `try.ok` 事件，这条分支在扫描之前返回。

    用 spy 盯着埋点调用本身，不看计数：计数依赖落库，测试环境关了埋点会假绿。
    造坏自检：在 not_code 分支里补一句 _track('try.ok')，这条必须变红。
    """
    app, client = _client()
    from modules import free_try as ft

    seen = []
    calls = []
    orig = ft._track

    def spy(name, **props):
        seen.append(name)
        calls.append((name, props))
        return True

    ft._track = spy
    try:
        for _ in range(4):
            resp = client.post('/api/try-scan', json={'code': '1', 'language': 'auto'})
            assert resp.status_code == 400, \
                '第 %d 次拒绝返回了 %d（429 说明被当成用掉次数了）' % (len(seen), resp.status_code)
    finally:
        ft._track = orig

    assert seen.count('try.fail') == 4, '4 次拒绝应记 4 条 try.fail，实际 %r' % (seen,)
    assert 'try.ok' not in seen, '拒绝分支写了 try.ok —— 等于白扣用户一次免费额度'
    reasons = [p.get('reason') for n, p in calls if n == 'try.fail']
    assert set(reasons) == {'not_code'}, \
        '拒绝原因应记 not_code（与「认不准」的 need_language 分开），实际 %r' % (reasons,)
    print('    4 次拒绝零扣费，且原因记为 not_code')


def test_ambiguous_language_still_offers_candidates():
    """有特征但拿不准时仍给候选按钮——别为了「不瞎猜」把这条路也砍了。

    `$("#id").click(() => {});` 是 jQuery：`=>` 给 js 记 2 分，`$(` 又撞上
    shell 的命令替换特征（3 分），第一名第二名只差 1 分 → 机器认不准。
    这种才是 need_language 该管的场景：把算出来的前几名摊开让人一键点选，
    比替他拍板安全（认错语言的漏报是静默的）。

    注意这条测试只断言「有候选、有展示名」，不断言首位是谁：`$(` 归 shell
    是特征表本身的既有问题（jQuery 会被算成 shell），单独修，不在这里固化。
    零特征（"1"、"a = 1"）走的是另一条路（not_scannable），两者不能混。
    """
    app, client = _client()
    ambiguous = '$("#id").click(() => {});'
    resp = client.post('/api/try-scan', json={'code': ambiguous, 'language': 'auto'})
    data = resp.get_json() or {}

    assert resp.status_code == 400, '歧义输入应返回 400，实得 %d' % resp.status_code
    assert data.get('need_language') is True, '歧义输入没走 need_language 分支：%r' % (data,)
    assert not data.get('not_scannable'), '有语言特征的输入被当成「不是代码」拒了'
    cands = data.get('candidates') or []
    assert len(cands) >= 2, '这段同时命中 shell 和 js，候选不该只有 %d 个' % len(cands)
    assert all(c.get('value') and c.get('label') for c in cands), \
        '候选缺 value/label，前端会渲染出空按钮：%r' % (cands,)
    print('    歧义输入给出 %d 个候选：%s'
          % (len(cands), '、'.join(c['label'] for c in cands)))


def test_not_scannable_renderer_owns_its_dom_lookup():
    """结论卡渲染函数必须自己取 DOM，不许引用 doTryScan 的局部变量。

    2026-11-27 真事：showNotScannable 里写的是 errBox.innerHTML，而 errBox 是
    doTryScan 内部的 const（第 316 行）——函数体根本拿不到，运行时抛
    ReferenceError，被 fetch 的 catch 吞成「网络错误，请稍后再试」。
    后端测试全绿、JS 语法检查 rc=0，只有在浏览器里真点一次才现形。
    """
    app, client = _client()
    html = _html(client, '/try')
    start = html.index('function showNotScannable(')
    end = html.index('function loadCodeFromFile(', start)
    body = html[start:end]
    # 只判代码，不判注释：注释里解释「为什么不能引用 errBox」正是要留下的信息。
    # （判据的字面量会自伤——这条曾被自己写的注释判红过一次。）
    import re as _re
    code_only = _re.sub(r'//[^\n]*', '', body)

    assert 'errBox' not in code_only, \
        'showNotScannable 引用了 doTryScan 的局部变量 errBox，点了只会看到「网络错误」'
    assert "getElementById('result-error')" in body, \
        'showNotScannable 没有自己取结果区 DOM，靠外部变量就会踩作用域'
    assert 'data.error' in body, \
        '结论文案必须用后端返回的 error，前端另写一份就成了两个事实来源'
    print('    结论卡渲染函数自取 DOM，不依赖 doTryScan 的局部变量')


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    failed = 0
    for fn in tests:
        try:
            print('[RUN] %s' % fn.__name__)
            fn()
            print('  OK\n')
        except AssertionError as e:
            failed += 1
            print('  FAIL: %s\n' % e)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print('  ERROR: %s: %s\n' % (type(e).__name__, e))
    print('=' * 50)
    print('%d 项通过, %d 项失败' % (len(tests) - failed, failed))
    sys.exit(1 if failed else 0)
