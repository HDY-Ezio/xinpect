# -*- coding: utf-8 -*-
"""浅底版面守卫（QA 6n）：页面 / 卡片 / 内嵌 三级面有没有塌，卡片撑不撑得起来。

为什么要有这一条
----------------
以前全站只有 --color-bg-primary 一个值，它同时当「页面底色」和「白字颜色」，
于是页面白、卡片也白，卡片只能靠一条 1.17:1 的边撑着。人眼看到的就是「平」。
这里钉住四件事：

1. 令牌齐不齐：surface-page / surface-card / surface-inset / border 三档 / shadow-card
   都在 tokens.css 里，而且三级之间真的能分开（亮度比 >= 1.05）。
2. 页面不许再自己抄色：浅底模板里 background* / border* 不许出现裸色值。
3. 一个令牌不许两个意思：不许再写 color: var(--color-bg-primary)。
4. 真渲染：页面底 = surface-page、卡片底 = surface-card、卡片有投影、
   卡片上的字对比度 >= 4.5（渐变底算不出来，跳过并计数，不假装通过）。

只看「吃 tokens.css 的页面」——判断依据是渲染出来的页面底色等于 surface-page，
不是手写清单。首页是另一套「纸面」设计（--paper 米白），不归这条管。

自带造坏自检：--self-test 会造 8 个坏副本，每一个都必须判红。
"""
import glob
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SITE = Path(os.environ.get('XP_SITE', '/opt/xinpect-website'))
TOKENS = SITE / 'static/css/tokens.css'
STYLE = SITE / 'static/css/style.css'
TEMPLATES = SITE / 'templates'

# 深色版面 / 独立设计系统的文件，不吃浅底这套（各有各的出处）
SKIP_FILES = {'report_shared.html', 'scan-fx.css', 'cool-fx.css',
              'index.html', 'monitor.html',
              'tokens.css'}   # 令牌文件本身就是色值的唯一出处

SURFACE_KEYS = ['--color-surface-page', '--color-surface-card',
                '--color-surface-inset', '--color-border',
                '--color-border-strong', '--shadow-card']

PAGES = ['/', '/pricing', '/try', '/login', '/register', '/help',
         '/changelog', '/blog', '/sample-report', '/license',
         '/terms', '/whitepaper']

BASE = os.environ.get('XP_BASE', 'http://127.0.0.1:8621')

bad = []


def fail(msg):
    bad.append(msg)


# ------------------------------------------------------------ 颜色工具
def hex2rgb(h):
    h = h.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lum(rgb):
    def f(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return .2126 * f(rgb[0]) + .7152 * f(rgb[1]) + .0722 * f(rgb[2])


def ratio(a, b):
    la, lb = lum(hex2rgb(a)), lum(hex2rgb(b))
    return (max(la, lb) + .05) / (min(la, lb) + .05)


def read_tokens(text=None):
    t = text if text is not None else TOKENS.read_text(encoding='utf-8')
    out = {}
    for m in re.finditer(r'(--[a-z0-9-]+)\s*:\s*([^;]+);', t):
        out[m.group(1)] = m.group(2).strip()
    return out


# ------------------------------------------------------------ 静态检查
def check_tokens(text=None):
    tk = read_tokens(text)
    for k in SURFACE_KEYS:
        if k not in tk:
            fail('tokens.css 缺令牌 %s' % k)

    def val(k):
        v = tk.get(k, '')
        return v if re.fullmatch(r'#[0-9a-fA-F]{6}', v) else None

    page, card, inset = (val('--color-surface-page'),
                         val('--color-surface-card'),
                         val('--color-surface-inset'))
    if page and card:
        r = ratio(page, card)
        if r < 1.05:
            fail('页面底和卡片底分不开：%s vs %s = %.3f（要 >=1.05）'
                 % (page, card, r))
    if inset and card:
        r = ratio(inset, card)
        if r < 1.08:
            fail('内嵌面和卡片底分不开：%s vs %s = %.3f（要 >=1.08）'
                 % (inset, card, r))
    bd = val('--color-border')
    if bd and card:
        r = ratio(bd, card)
        if r < 1.2:
            fail('边框在卡片上看不清：%s vs %s = %.3f（要 >=1.20）'
                 % (bd, card, r))
    if '--shadow-card' in tk and 'rgba' not in tk['--shadow-card']:
        fail('--shadow-card 不像一条投影：%s' % tk['--shadow-card'])


LITERAL = re.compile(r'#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)')
PROP = re.compile(r'(?P<prop>background(?:-color)?|border(?:-(?:top|right|'
                  r'bottom|left))?(?:-color)?)\s*:\s*(?P<val>[^;{}]+)', re.I)


def light_files(root=None):
    root = root or SITE
    files = []
    for pat in ('templates/*.html', 'templates/*/*.html', 'static/css/*.css'):
        files += sorted(Path(root).glob(pat))
    return [f for f in files if f.name not in SKIP_FILES
            and not f.name.endswith(('.bak', '.orig'))]


def check_no_literal(root=None):
    for f in light_files(root):
        try:
            text = f.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        for m in PROP.finditer(text):
            val = m.group('val')
            if LITERAL.search(val):
                fail('%s 里 %s 用了裸色值：%s'
                     % (f.relative_to(root or SITE), m.group('prop'),
                        val.strip()[:40]))


def check_no_dual_use(root=None):
    """--color-bg-primary 只许当白底，不许再当白字。"""
    root = root or SITE
    pat = re.compile(r'(?<![-\w])color\s*:\s*var\(--color-bg-primary\)')
    for f in light_files(root):
        try:
            text = f.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        if pat.search(text):
            fail('%s 用 bg-primary 当字色（应写 --color-text-inverse）'
                 % f.relative_to(root))


def check_decorative_scope(root=None):
    """aria-hidden="true" 只许圈装饰，不许把正文骨架整块藏起来。

    动态检查会跳过 aria-hidden 子树（装饰不按正文尺子量），
    这条是它的对偶：谁想靠「整页声明成装饰」把对比度门禁关掉，这里判红。
    """
    root = root or SITE
    SKELETON = {'body', 'main', 'article', 'nav', 'header', 'footer',
                'section', 'html', 'form', 'table'}
    tag_re = re.compile(r'<(\w+)[^>]*\baria-hidden\s*=\s*["\']true["\']', re.I)
    for f in (Path(root) / 'templates').rglob('*.html'):
        try:
            text = f.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        for m in tag_re.finditer(text):
            tag = m.group(1).lower()
            if tag in SKELETON:
                fail('%s 把正文骨架 <%s> 声明成装饰（aria-hidden），会连带关掉对比度门禁'
                     % (f.relative_to(root), tag))


# 模板里写 ?v={{ asset_v }} 时的哨兵值。版本号已收敛到 constants.ASSET_VERSION
# 一处，变量形式的引用天然不会出现「两张表版本对不上」，不必也不能拿它比字面量。
_ASSET_VAR_RE = re.compile(r'\?v=\{\{\s*asset_v\s*\}\}')
# 哨兵只能用版本号正则允许的字符（字母数字点）。用下划线会让
# (?v=([0-9A-Za-z.]+))? 这条可选组整个匹配失败，于是「带了版本号」被判成「没带」。
_ASSET_VAR_TAG = '?v=assetvar'


def check_asset_version(root=None):
    """样式表必须带 ?v=，且 tokens/style 用同一个版本号。"""
    root = root or SITE
    toks = re.findall(r'css/tokens\.css\?v=([0-9A-Za-z.]+)',
                      _ASSET_VAR_RE.sub(_ASSET_VAR_TAG,
                                        (Path(root) / 'templates/base.html')
                                        .read_text(encoding='utf-8')))
    vers = set()
    for f in (Path(root) / 'templates').rglob('*.html'):
        text = _ASSET_VAR_RE.sub(_ASSET_VAR_TAG, f.read_text(encoding='utf-8'))
        # url_for 写法：filename='css/style.css')}}?v=xxx
        text = re.sub(r"filename='(css/[a-z-]+\.css)'\)\s*\}\}\?v=([0-9A-Za-z.]+)",
                      r'\1?v=\2', text)
        for m in re.finditer(r'css/([a-z-]+\.css)(\?v=([0-9A-Za-z.]+))?', text):
            name, has_v, ver = m.group(1), m.group(2), m.group(3)
            if not has_v:
                fail('%s 引用 %s 没带 ?v=，老访客会走缓存看旧样式'
                     % (f.name, name))
                continue
            if name in ('tokens.css', 'style.css'):
                vers.add(ver)
    if toks:
        vers.add(toks[0])
    if len(vers) > 1:
        fail('tokens.css / style.css 版本号不一致：%s' % sorted(vers))


# ------------------------------------------------------------ 真渲染
JS = r"""() => {
  function parse(c) {
    const m = (c || '').match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map(parseFloat);
    return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1};
  }
  function lum(c) {
    const f = v => { v /= 255; return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); };
    return 0.2126*f(c.r) + 0.7152*f(c.g) + 0.0722*f(c.b);
  }
  function ratio(a, b) {
    const l1 = lum(a), l2 = lum(b);
    return (Math.max(l1,l2)+0.05) / (Math.min(l1,l2)+0.05);
  }
  function hex(c) {
    return c ? '#' + [c.r,c.g,c.b].map(v => Math.round(v).toString(16).padStart(2,'0')).join('') : null;
  }
  function effBg(el) {
    let n = el;
    while (n && n.nodeType === 1) {
      const cs = getComputedStyle(n);
      const c = parse(cs.backgroundColor);
      if (c && c.a > 0.5) return c;
      if (cs.backgroundImage && cs.backgroundImage !== 'none') {
        // 渐变：取第一个色标当近似值（本站的渐变都是同色系微差，
        // 深底按钮 = #1A2B4A→更深的藏青，取第一站不冤）。取不到才算不了。
        if (cs.backgroundImage.indexOf('url(') === 0) return null;   // 图片算不了
        const g = cs.backgroundImage.match(/rgba?\([^)]+\)/);
        if (g) {
          const gc = parse(g[0]);
          if (gc && gc.a > 0.3) return gc;
        }
        // 半透明渐变叠加（如 0.06 的藏青蒙层）：看不见的，继续往上找实底
      }
      n = n.parentElement;
    }
    return {r:255,g:255,b:255,a:1};
  }
  function visible(el) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    if (parseFloat(cs.opacity) < 0.15) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  const low = [], cards = [];
  let unmeasurable = 0, total = 0;
  // 什么叫「卡片」：够大、装得下内容、不是控件。
  // 按钮/下拉/输入框/折叠栏/行内代码本来就该有自己的一块色，那不是卡片。
  const NOT_CARD = ['BUTTON','INPUT','SELECT','TEXTAREA','DETAILS','SUMMARY',
                    'CODE','SPAN','EM','STRONG','I','LABEL','IMG','SVG',
                    'PATH','TD','TH','P','LI','PRE','BLOCKQUOTE'];
  // 作者显式声明为装饰的子树（aria-hidden="true"）不按正文字号量对比度：
  // 假代码流光、扫描光带这类东西本来就该压暗，量了只会逼人把装饰提亮到抢内容。
  // 防滥用见静态检查 decorative_scope_sane：正文骨架不许整体声明成装饰。
  const decorative = el => el.closest('[aria-hidden="true"]') !== null;
  for (const el of document.querySelectorAll('body *')) {
    if (!visible(el)) continue;
    if (decorative(el)) continue;
    total++;
    const cs = getComputedStyle(el);
    const own = parse(cs.backgroundColor);
    const radius = parseFloat(cs.borderTopLeftRadius) || 0;
    const r = el.getBoundingClientRect();
    const bigEnough = r.width >= 240 && r.height >= 90;
    const hasText = (el.textContent || '').trim().length > 20 || el.children.length > 0;
    const isCard = bigEnough && hasText && radius >= 4 &&
                   !NOT_CARD.includes(el.tagName) &&
                   !el.classList.contains('btn');
    if (isCard && own && own.a > 0.5 && el.parentElement) {
      const pb = effBg(el.parentElement);
      if (pb && hex(pb) !== hex(own)) {
        cards.push({el: el.tagName.toLowerCase() + '.' +
                    (el.className || '').toString().trim().split(/\s+/)[0],
                    bg: hex(own), shadow: cs.boxShadow !== 'none',
                    radius: radius});
      }
    }
    const txt = Array.from(el.childNodes)
      .filter(n => n.nodeType === 3 && n.textContent.trim().length > 0)
      .map(n => n.textContent.trim()).join('');
    if (txt) {
      const bg = effBg(el);
      const fg = parse(cs.color);
      if (!bg) { unmeasurable++; }
      else if (fg) {
        const r = ratio(fg, bg);
        if (r < 4.5) low.push({el: el.tagName.toLowerCase(), text: txt.slice(0,20),
                               color: cs.color, bg: hex(bg),
                               ratio: Math.round(r*100)/100});
      }
    }
  }
  return {body: hex(parse(getComputedStyle(document.body).backgroundColor)),
          cards: cards.slice(0, 40), low, unmeasurable, total};
}"""


def import_playwright():
    """QA 以 root 跑，用户级装的 playwright 不在 sys.path。"""
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        pass
    for base in ('/home/*/.local/lib/python3*/site-packages',
                 '/root/.local/lib/python3*/site-packages'):
        for d in sorted(glob.glob(base)):
            if d not in sys.path and (Path(d) / 'playwright').is_dir():
                sys.path.insert(0, d)
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        return None


def launch(p, exe=None):
    return p.chromium.launch(headless=True, executable_path=exe,
                             args=['--no-sandbox'])


def find_chromium():
    env = os.environ.get('XP_CHROMIUM')
    if env and Path(env).is_file():
        return env
    cands = sorted(glob.glob(
        '/home/ubuntu/.cache/ms-playwright/chromium-*/chrome-linux64/chrome'))
    cands += sorted(glob.glob(
        '/root/.cache/ms-playwright/chromium-*/chrome-linux64/chrome'))
    return cands[-1] if cands else None


def check_render(sync_playwright, exe, base=None):
    base = base or BASE
    tk = read_tokens()
    page_hex = tk.get('--color-surface-page', '').lower()
    card_hex = tk.get('--color-surface-card', '').lower()
    inset_hex = tk.get('--color-surface-inset', '').lower()
    any_cards = False
    with sync_playwright() as p:
        b = launch(p, exe)
        ctx = b.new_context(viewport={'width': 1440, 'height': 1000})
        for url in PAGES:
            pg = ctx.new_page()
            try:
                r = pg.goto(base + url, wait_until='networkidle', timeout=30000)
                if r is None or r.status >= 400:
                    fail('%s 打不开（%s）' % (url, r.status if r else '?'))
                    pg.close()
                    continue
                d = pg.evaluate(JS)
            except Exception as e:
                fail('%s 渲染失败：%s' % (url, str(e)[:80]))
                pg.close()
                continue
            pg.close()
            # 管辖判断：页面底就是 surface-page 才归这条管
            if d['body'] != page_hex:
                print('  %-16s 页面底 %s 不是 surface-page，不归本守卫管'
                      % (url, d['body']))
                continue
            any_cards = any_cards or bool(d['cards'])
            if not d['cards']:
                print('  %-16s 本页没有卡片型容器（不算错）' % url)
            for c in d['cards']:
                if c['bg'] == page_hex:
                    fail('%s %s 的底色等于页面底，等于没浮起来' % (url, c['el']))
                elif c['bg'] == inset_hex:
                    continue        # 内嵌面：靠边框和底色说明层级，不用投影
                elif not c['shadow']:
                    fail('%s %s 没有投影，只靠边框撑' % (url, c['el']))
            for x in d['low']:
                fail('%s 文字对比度 %.2f 不足：%s「%s」在 %s 上'
                     % (url, x['ratio'], x['el'], x['text'], x['bg']))
            print('  %-16s 卡片 %2d 个、文字不足 %d 处、渐变底跳过 %d 个'
                  % (url, len(d['cards']), len(d['low']), d['unmeasurable']))
        b.close()
    if not any_cards:
        fail('全站一个浮起的卡片都没有：页面底和卡片底是同一个值')


# ------------------------------------------------------------ 自检
SELF_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="tokens.css"><link rel="stylesheet" href="style.css">
<style>body{background:var(--color-surface-page);margin:0}</style>
</head><body>
<div class="card-test" style="padding:24px;border-radius:12px;
     background:var(--color-surface-card);border:1px solid var(--color-border);
     box-shadow:var(--shadow-card);max-width:420px;min-height:140px;margin:40px;">
  <div style="color:var(--color-text-primary);font-size:16px;">卡片标题一段话</div>
  <div style="color:var(--color-text-muted);font-size:13px;">次要说明文字一段</div>
</div></body></html>"""


def self_test(sync_playwright, exe):
    """造坏副本必须判红。坏样本按「声明行正则注入」，不写死当前色值。"""
    cases = []

    def run_static(name, mutate):
        global bad
        saved = bad
        bad = []
        mutate()
        hit = bool(bad)
        bad = saved
        cases.append((name, hit, bad[0] if bad else ''))

    tok_text = TOKENS.read_text(encoding='utf-8')

    def m_collapse():
        t = re.sub(r'(--color-surface-page\s*:\s*)(#[0-9a-fA-F]{6})',
                   r'\1#FFFFFF', tok_text, count=1)
        check_tokens(t)

    def m_no_scale():
        t = re.sub(r'\n\s*--color-surface-inset\s*:[^;]+;', '\n', tok_text)
        check_tokens(t)

    def m_border_light():
        t = re.sub(r'(--color-border\s*:\s*)(#[0-9a-fA-F]{6})',
                   r'\1#F7FAFD', tok_text, count=1)
        check_tokens(t)

    run_static('页面底塌回白', m_collapse)
    run_static('删掉内嵌面令牌', m_no_scale)
    run_static('边框淡到看不见', m_border_light)

    # 文件级：用临时目录造一份坏模板
    tmp = Path(tempfile.mkdtemp(prefix='surf_'))
    (tmp / 'templates' / 't.css').parent.mkdir(parents=True, exist_ok=True)

    def m_literal():
        d = Path(tempfile.mkdtemp(prefix='surf_lit_'))
        (d / 'templates').mkdir(parents=True, exist_ok=True)
        (d / 'static' / 'css').mkdir(parents=True, exist_ok=True)
        (d / 'templates' / 'x.html').write_text(
            '<div style="background:#FFFFFF;border:1px solid #e0e6ed">x</div>',
            encoding='utf-8')
        check_no_literal(d)

    def m_dual():
        d = Path(tempfile.mkdtemp(prefix='surf_dual_'))
        (d / 'templates').mkdir(parents=True, exist_ok=True)
        (d / 'static' / 'css').mkdir(parents=True, exist_ok=True)
        (d / 'templates' / 'x.html').write_text(
            '<span style="color:var(--color-bg-primary)">白字</span>',
            encoding='utf-8')
        check_no_dual_use(d)

    def m_no_ver():
        d = Path(tempfile.mkdtemp(prefix='surf_ver_'))
        (d / 'templates').mkdir(parents=True, exist_ok=True)
        (d / 'templates' / 'base.html').write_text(
            '<link href="/static/css/tokens.css?v=1">', encoding='utf-8')
        (d / 'templates' / 'a.html').write_text(
            '<link href="/static/css/style.css">', encoding='utf-8')
        (d / 'templates' / 'b.html').write_text(
            '<link href="/static/css/tokens.css?v=1">', encoding='utf-8')
        check_asset_version(d)

    def m_mix_ver():
        d = Path(tempfile.mkdtemp(prefix='surf_ver2_'))
        (d / 'templates').mkdir(parents=True, exist_ok=True)
        (d / 'templates' / 'base.html').write_text(
            '<link href="/static/css/tokens.css?v=1">'
            '<link href="/static/css/style.css?v=2">', encoding='utf-8')
        check_asset_version(d)

    def m_body_decorative():
        d = Path(tempfile.mkdtemp(prefix='surf_dec_'))
        (d / 'templates').mkdir(parents=True, exist_ok=True)
        (d / 'templates' / 'page.html').write_text(
            '<html><body aria-hidden="true"><p>正文全藏</p></body></html>',
            encoding='utf-8')
        check_decorative_scope(d)

    def m_section_decorative():
        d = Path(tempfile.mkdtemp(prefix='surf_dec2_'))
        (d / 'templates').mkdir(parents=True, exist_ok=True)
        (d / 'templates' / 'page.html').write_text(
            '<html><body><section aria-hidden="true"><p>整个区块藏起来</p>'
            '</section></body></html>',
            encoding='utf-8')
        check_decorative_scope(d)

    run_static('把 body 声明成装饰要判红', m_body_decorative)
    run_static('把 section 声明成装饰要判红', m_section_decorative)

    run_static('模板里写裸色值', m_literal)
    run_static('bg-primary 又当字色', m_dual)
    run_static('样式表没带缓存版本号', m_no_ver)
    run_static('两个样式表版本号不一致', m_mix_ver)

    # 渲染级：造一张同色卡片和一段看不见的字
    with sync_playwright() as p:
        b = launch(p, exe)
        pg = b.new_page()
        html = SELF_HTML
        d = Path(tempfile.mkdtemp(prefix='surf_render_'))
        (d / 'tokens.css').write_text(tok_text, encoding='utf-8')
        (d / 'style.css').write_text(STYLE.read_text(encoding='utf-8'),
                                     encoding='utf-8')
        good = d / 'good.html'
        good.write_text(html, encoding='utf-8')
        pg.goto(good.as_uri())
        ok = pg.evaluate(JS)
        cases.append(('干净样本必须过：卡片有投影、文字清晰',
                      ok['cards'] and all(c['shadow'] for c in ok['cards'])
                      and not ok['low'], json_note(ok)))

        d2 = good.with_name('nos.html')
        d2.write_text(html.replace('box-shadow:var(--shadow-card);', ''),
                      encoding='utf-8')
        pg.goto(d2.as_uri())
        r = pg.evaluate(JS)
        cases.append(('卡片去掉投影要判红',
                      any(not c['shadow'] for c in r['cards']), json_note(r)))

        d3 = good.with_name('lowc.html')
        d3.write_text(html.replace('color:var(--color-text-muted)',
                                   'color:#E6ECF3'), encoding='utf-8')
        pg.goto(d3.as_uri())
        r = pg.evaluate(JS)
        cases.append(('次要文字淡到看不见要判红', bool(r['low']), json_note(r)))

        # 同一段暗字放两处：一处包在装饰容器里、一处直接露在页面上。
        # 期望恰好只报 1 条（露在外面的那条），证明豁免认容器、不认颜色。
        FAINT = 'color:#E6ECF3'   # 浅底上几乎看不见的淡字，与上面那条同一档
        deco = html.replace('</body>',
            '<div aria-hidden="true"><span style="%s">装饰淡字样本</span></div>'
            '<div><span id="exposed" style="%s">露在外面的淡字样本</span></div>'
            '</body>' % (FAINT, FAINT))
        d4 = good.with_name('deco.html')
        d4.write_text(deco, encoding='utf-8')
        pg.goto(d4.as_uri())
        r = pg.evaluate(JS)
        exposed = [x for x in r['low'] if '露在外面的淡字样本' in (x.get('text') or '')]
        hidden = [x for x in r['low'] if '装饰淡字样本' in (x.get('text') or '')]
        cases.append(('装饰子树里的淡字被跳过', not hidden, json_note(r)))
        cases.append(('同一档淡字露在外面照样判红', bool(exposed), json_note(r)))
        b.close()

    print('\n造坏自检：')
    red = 0
    for name, hit, note in cases:
        print('  %-30s %s %s' % (name, '✅ 判红' if hit else '❌ 没判红',
                                 '' if hit else note))
        if hit:
            red += 1
    print('  %d/%d 条按预期' % (red, len(cases)))
    return red == len(cases)


def json_note(d):
    return '（卡片 %d 个，文字不足 %d 处）' % (len(d['cards']), len(d['low']))


# ------------------------------------------------------------ main
def main():
    self_test_only = '--self-test' in sys.argv
    exe = find_chromium()
    sync_playwright = import_playwright()

    if not self_test_only:
        check_tokens()
        check_no_literal()
        check_no_dual_use()
        check_decorative_scope()
        check_asset_version()
        print('静态检查：令牌 %d 项、模板 %d 个'
              % (len(SURFACE_KEYS), len(light_files())))
        if sync_playwright and exe:
            check_render(sync_playwright, exe)
        else:
            print('跳过真渲染（没找到浏览器或 playwright）')

    ok = True
    if self_test_only:
        if not (sync_playwright and exe):
            print('没浏览器，自检跑不了')
            return 2
        ok = self_test(sync_playwright, exe)
    else:
        if bad:
            print('\n❌ 发现 %d 个问题：' % len(bad))
            for b in bad[:30]:
                print('  -', b)
            ok = False
        else:
            print('\n✅ 浅底版面层级通过')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
