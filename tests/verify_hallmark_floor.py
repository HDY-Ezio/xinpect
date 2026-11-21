#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""煋鉴官网 UI 验收门禁守卫（2026-11-06，QA 第 6d 段）

治的是什么：Hallmark 的 sloplint 一次报 791 条 FAIL，其中大半是它的英文落地页口味
或中文站误判。拿「总 FAIL 数」当 KPI 会逼人把品牌改歪；反过来，完全不看又会退回
「首页挂旧口径、动画每帧重排、主按钮白字看不清」。本守卫建一个单一事实来源：
  design.md（锁品牌与中文豁免） + hallmark_floor_gates.json（必须 0 命中的门禁）
  + 固定版本的 sloplint.mjs（不联网拉上游） + static/css/tokens.css（颜色字体唯一来源）
只判门禁清单里的命中，不判总数。

2026-11-06 第二批：把「全站动画、命名、可读性、文案、颜色字体字面量」全部收口后，
静态检查从三个对外页扩到全站活跃模板；新规矩同样用造坏副本证明会判红。

用法：
  /usr/bin/python3 tests/verify_hallmark_floor.py
  /usr/bin/python3 tests/verify_hallmark_floor.py --self-test

--root 可覆盖（默认环境变量 XINPECT_WEB_ROOT，再默认 /opt/xinpect-website），
守卫不写死绿版路径。正常模式必须官网在线（抓 8621 渲染页）；失败 raise AssertionError。
"""
import argparse
import json
import os
import re

# 首页实测声明按语义判：同一句里要有实测样本数与「漏报 123」条数。
# 2026-11-08 用户拍板：口径改为「误报 0 条 + 漏报 123 条」，不再宣称 0 漏报。
# 不写死具体文案——数字条改写时曾因写死旧句子假红、造坏静默失效。
ZERO_FN_SEMANTIC = re.compile(r'2,740[^<]{0,42}漏报\s*123|漏报\s*123[^<]{0,42}2,740')
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

DEFAULT_ROOT = os.environ.get('XINPECT_WEB_ROOT', '/opt/xinpect-website')
DEFAULT_URL = 'http://127.0.0.1:8621'
LEDGER_REL = 'scripts/hallmark_floor_gates.json'
CHECKER_REL = 'scripts/vendor/sloplint.mjs'
TOKENS_REL = 'static/css/tokens.css'
BLOG_REL = 'content/blog/2026-11-04-false-positive-rate-2740-projects.md'
LLMS_REL = 'static/llms.txt'
PUBLIC_TEMPLATES = ('templates/index.html', 'templates/try.html',
                    'templates/pricing.html', 'templates/base.html')
KEY_FILES = [
    'design.md', LEDGER_REL, CHECKER_REL, TOKENS_REL,
    'templates/index.html', 'templates/base.html', 'templates/try.html',
    'templates/pricing.html', 'templates/changelog.html',
    'templates/seo_detect.html', 'static/css/style.css',
    'static/css/scan-fx.css', 'static/js/scan-fx.js',
    'static/llms.txt', BLOG_REL, 'static/css/blog.css',
]
BAD_GRADES = ('FAIL', 'WARN', 'REFLEX')
COLOR_LIT = re.compile(r'#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(|oklch\(')
FONT_LIT = re.compile(r'(?<![\w-])font-family\s*:\s*([^;}]+)', re.I)
GENERIC_FONTS = ('serif', 'sans-serif', 'monospace', 'cursive', 'fantasy',
                 'system-ui', 'ui-monospace', 'ui-serif', 'ui-sans-serif',
                 'ui-rounded', 'math', 'emoji', 'fangsong', 'inherit',
                 'initial', 'unset')
EMOJI = re.compile('[\U0001F300-\U0001FAFF]\uFE0F?')


# ---------------------------------------------------------------- 小工具
def read(root, rel):
    p = Path(root) / rel
    if not p.is_file():
        return None
    return p.read_text(encoding='utf-8', errors='replace').replace('\r\n', '\n')


def climate_note_on_top(blog):
    """口径说明必须真的在正文开头，且三个数字齐全。

    2026-11-14 修正：旧判据把「本文数字就是现行口径」这句原文钉死，又只看
    「字符串在不在」——声明挂在文末它照样绿。读者先读到 91.3%、翻到最后才
    看到「那个数字不可比」，等于声明没起作用。现在按位置判：口径说明必须
    出现在第一个二级标题之前；声明一旦被挪到文末就不算数。
    """
    idx = blog.find('口径说明')
    if idx < 0:
        return False
    body_start = blog.find('---', 4)
    first_h2 = blog.find('\n## ', body_start if body_start >= 0 else 0)
    if first_h2 >= 0 and idx > first_h2:
        return False
    return all(k in blog for k in ('1,415', '1,292', '123'))


def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode('utf-8'))


def luminance(color):
    h = color.lstrip('#')
    ch = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    ch = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in ch]
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


def contrast(fg, bg):
    a, b = luminance(fg), luminance(bg)
    a, b = max(a, b), min(a, b)
    return (a + 0.05) / (b + 0.05)


def resolve_value(value, pool, depth=0):
    """把 --foo: var(--bar) 递归解析到真实色值；变量收敛后守卫仍能算对比度。"""
    if depth > 8:
        return None
    v = value.strip()
    hm = re.match(r'^(#[0-9a-fA-F]{6})\b', v)
    if hm:
        return hm.group(1)
    vm = re.match(r'^var\(\s*(--[\w-]+)', v)
    if vm:
        m = re.search(r'--%s\s*:\s*([^;]+);' % re.escape(vm.group(1)[2:]), pool)
        if m:
            return resolve_value(m.group(1), pool, depth + 1)
    return None


def css_var(text, name, tokens=''):
    m = re.search(r'--%s\s*:\s*([^;]+);' % re.escape(name), text)
    if not m:
        return None
    return resolve_value(m.group(1), text + '\n' + tokens)


def drop_decl(css, name):
    """按**声明名**删掉一条自定义属性，不认具体色值。

    1109 的教训：造坏用例原来写死 `--color-text-on-subtle: #52637a;`，
    那档颜色改深成 #4B5A70 之后替换锚点失配，坏副本根本没造出来，
    自检却报「没判红」——看着像守卫坏了，其实是造坏用例坏了。
    规矩：造坏一律按声明名注入，颜色值怎么调都不用改守卫。
    """
    return re.sub(r'^[ \t]*%s[ \t]*:[^;]*;[ \t]*\r?\n?' % re.escape(name),
                  '', css, flags=re.M)


def keyframe_blocks(text):
    out = []
    for m in re.finditer(r'@keyframes[^{]*\{', text):
        start = m.end() - 1
        depth = 0
        for j in range(start, len(text)):
            if text[j] == '{':
                depth += 1
            elif text[j] == '}':
                depth -= 1
                if depth == 0:
                    out.append(text[start:j + 1])
                    break
    return out


def strip_defs(text):
    """去掉注释、:root 定义块、url() 与 content 声明，剩下的才是「消费方」。"""
    t = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    t = re.sub(r':root\s*\{[^}]*\}', '', t, flags=re.S)
    t = re.sub(r'url\s*\([^)]*\)', '', t, flags=re.I)
    t = re.sub(r'(?<![\w-])content\s*:\s*[^;}]+;', '', t, flags=re.I)
    return t


def active_site_files(root):
    out = []
    for pat in ('templates/**/*.html', 'static/css/*.css'):
        for p in sorted(Path(root).glob(pat)):
            s = p.as_posix()
            if any(k in s for k in ('backup', '.bak', 'vendor', '_archive')):
                continue
            out.append(p)
    return out


# ---------------------------------------------------------------- 静态检查
def static_checks(root):
    c = {}
    index = read(root, 'templates/index.html') or ''
    base = read(root, 'templates/base.html') or ''
    pricing = read(root, 'templates/pricing.html') or ''
    style = read(root, 'static/css/style.css') or ''
    fx = read(root, 'static/css/scan-fx.css') or ''
    fxjs = read(root, 'static/js/scan-fx.js') or ''
    tokens = read(root, TOKENS_REL) or ''
    design = read(root, 'design.md') or ''
    ledger_raw = read(root, LEDGER_REL)

    c['design_md_exists'] = bool(design)
    c['design_md_locks_brand'] = all(k in design for k in
                                     ('#1A2B4A', '覆盖主题', '禁止', '0 误报'))
    c['design_md_has_zh_waivers'] = all(k in design for k in
                                        ('中文站豁免', 'E1', '67', '破折号'))
    c['design_md_batch_b_closed'] = '第二批已收口' in design
    try:
        ledger = json.loads(ledger_raw) if ledger_raw else None
        c['gate_ledger_valid'] = bool(ledger and ledger.get('zero_hit_gates')
                                     and ledger.get('contrast_must_be_zero'))
    except (ValueError, TypeError):
        c['gate_ledger_valid'] = False
    checker = Path(root) / CHECKER_REL
    c['vendor_checker_pinned'] = checker.is_file() and checker.stat().st_size > 100000

    # 旧口径：当前对外承诺载体（顶层模板 + AI 爬虫说明）不许再出现 91.3
    # 旧样本百分比不止一种写法：91.3% 检出率、1.7% 误报率都是停用口径。
    # 按「数字 + 百分号」的语义判，不按文件名开白名单。
    banned = ['91.3', '1.7%']
    hits = []
    for p in sorted(Path(root, 'templates').glob('*.html')):
        t = p.read_text(encoding='utf-8', errors='replace')
        if any(b in t for b in banned):
            hits.append(p.name)
    llms = read(root, LLMS_REL) or ''
    if any(b in llms for b in banned):
        hits.append(LLMS_REL)
    c['no_legacy_91_3'] = not hits
    c['no_legacy_1_7'] = not hits
    c['llms_txt_current'] = ('漏报 123' in llms) and ('误报 0' in llms) \
        and not any(b in llms for b in banned)
    blog = read(root, BLOG_REL) or ''
    # 只要这篇在，口径说明就必须在正文最前面，且 1,415 / 1,292 / 123 都在。
    # 不再钉某一句原文（换措辞就误报），也不只看「字符串在不在」（挪到文末
    # 也恒绿）。位置判据见 climate_note_on_top。
    c['blog_legacy_marked'] = (not blog) or climate_note_on_top(blog)
    c['home_states_zero_fn'] = bool(ZERO_FN_SEMANTIC.search(index))

    # 动画：A 方案只管三个对外页，B 批次扩到全站活跃模板
    shared = base + pricing
    c['no_transition_all'] = not re.search(r'transition\s*:\s*all', shared, re.I)
    c['no_transition_width'] = not re.search(r'transition\s*:\s*width', style + fx, re.I)
    c['no_keyframe_top'] = not any(re.search(r'\btop\s*:', b, re.I)
                                   for b in keyframe_blocks(index + fx))
    c['overflow_clip_html_body'] = (
        style.count('overflow-x: clip') >= 2
        and index.count('overflow-x:clip') >= 2
        and 'overflow-x: clip' in base
    )
    site = active_site_files(root)
    site_text = '\n'.join(p.read_text(encoding='utf-8', errors='replace')
                         for p in site)
    c['site_files_present'] = len(site) >= 5 and all(
        (Path(root) / f).is_file() for f in
        ('static/css/style.css', 'static/css/scan-fx.css', TOKENS_REL))
    c['no_transition_all_sitewide'] = not re.search(
        r'transition\s*:\s*all', site_text, re.I)
    c['no_transition_width_sitewide'] = not re.search(
        r'transition\s*:\s*width', site_text, re.I)
    c['no_orange_varname'] = not re.search(r'--[\w-]*orange[\w-]*', site_text, re.I)
    c['accent_steel_named'] = '--color-accent-steel' in style

    # 变量单一事实来源：tokens.css 必须存在，消费方不许再有裸颜色/裸字体
    c['tokens_css_exists'] = len(tokens) > 10000 and tokens.count(':root') >= 1
    c['tokens_css_has_definitions'] = len(re.findall(r'^\s*--[\w-]+\s*:', tokens, re.M)) >= 400
    # 扫「站点实际发出的每一份样式表」，不是写死的两份。原来只看 style.css + fx.css，
    # 于是把内联样式搬进新建的 blog.css 就能绕过去（2026-11-22 差点这么绕）。
    # tokens.css 里的 `--xxx: #fff` 属于定义行，strip_defs 已剥掉，不影响结论。
    all_css = [p for p in site if p.suffix == '.css']
    # 前置判据：别让「一份都没扫到」伪装成「都合格」。不数总数（自测沙箱只搬
    # KEY_FILES，真站是 6 份，数总数会逼着两个环境用不同阈值），只认两份必有的：
    # 路径一旦对错，这两个名字就凑不齐，直接报红。
    c['css_stylesheets_found'] = {'style.css', 'tokens.css'} <= {
        p.name for p in all_css}
    consumed = strip_defs('\n'.join(
        p.read_text(encoding='utf-8', errors='replace') for p in all_css))
    c['no_bare_colour_in_css'] = bool(all_css) and not COLOR_LIT.search(consumed)
    bare_fonts = [m.group(1).strip() for m in FONT_LIT.finditer(consumed)
                  if 'var(' not in m.group(1)
                  and m.group(1).strip().lower() not in GENERIC_FONTS]
    c['no_bare_font_in_css'] = bool(all_css) and not bare_fonts
    inline_colours = []
    for p in site:
        if p.suffix != '.html':
            continue
        t = p.read_text(encoding='utf-8', errors='replace')
        for m in re.finditer(r'style\s*=\s*["\']([^"\']*)["\']', t, re.I):
            if COLOR_LIT.search(m.group(1)):
                inline_colours.append(p.name)
        for sm in re.finditer(r'<style[^>]*>(.*?)</style>', t, re.I | re.S):
            if COLOR_LIT.search(strip_defs(sm.group(1))):
                inline_colours.append(p.name + ':style')
    c['no_bare_colour_in_templates'] = not inline_colours
    c['public_pages_load_tokens'] = all(
        ('tokens.css' in (read(root, f) or '')) or
        re.search(r'\{%\s*extends', (read(root, f) or ''))
        for f in PUBLIC_TEMPLATES)

    # 可读性：浅底上的次要文字必须来自可读 token
    # 底色也不写死（原来是 #f5f7fa，浅底改版后当页底已不是它）：
    # 取 --color-surface-page，是浅色面里最深的一档，对深色字最不利。
    readable = css_var(tokens, 'color-text-on-subtle')
    page_bg = css_var(tokens, 'color-surface-page')
    c['readable_token_ok'] = bool(readable and page_bg
                                  and contrast(readable, page_bg) >= 4.5)
    c['readable_token_used'] = style.count('var(--color-text-on-subtle)') >= 5
    c['accent_contrast_ok'] = bool(
        css_var(index, 'accent', tokens) and css_var(index, 'accent-hover', tokens)
        and contrast('#ffffff', css_var(index, 'accent', tokens)) >= 4.5
        and contrast('#ffffff', css_var(index, 'accent-hover', tokens)) >= 4.5
    )
    xp = css_var(fx, 'xp-text', tokens)
    c['xp_text_contrast_ok'] = bool(xp and contrast(xp, '#f6f8fc') >= 4.5)

    # 文案与层级
    c['no_emoji_in_public'] = not any(EMOJI.search(read(root, f) or '')
                                      for f in PUBLIC_TEMPLATES)
    c['no_arrow_cta'] = all(k not in (read(root, 'templates/try.html') or '')
                            for k in ('开始免费检测 →', '解锁完整报告 →'))
    c['heading_levels_fixed'] = (
        '<h4>' not in index and '<h5>' not in index and '<h4>' not in base
        and '.step h3{' in index and '.footer h3{' in index)
    c['finish_balance_and_tabular'] = ('text-wrap:balance' in index
                                       and 'tabular-nums' in index)
    backups = [p for p in Path(root, 'templates').rglob('*')
               if '.bak' in p.name or 'backup' in p.name.lower()]
    c['no_template_backups'] = not backups

    # 真进度红线不能被 UI 改造碰坏
    c['progress_bar_uses_scaleX'] = 'scaleX(' in fxjs and '.style.width' not in fxjs
    c['progress_truth_untouched'] = not any(
        k in fxjs for k in ('setInterval', 'Math.random', 'pct +=', 'prog +=')
    )
    return c


# ---------------------------------------------------------------- 动态检查
def fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=12) as r:
            if r.status != 200:
                return None
            return r.read().decode('utf-8', errors='replace').replace('\r\n', '\n')
    except Exception:
        return None


def inline_css(root, html):
    def repl(m):
        href = m.group(1).split('?')[0].lstrip('/')
        if not href.startswith('static/'):
            return m.group(0)
        p = Path(root) / href
        if p.is_file():
            return '<style>\n' + p.read_text(encoding='utf-8', errors='replace') + '\n</style>'
        return m.group(0)
    return re.sub(r'<link[^>]+rel=["\']stylesheet["\'][^>]*href=["\']([^"\']+)["\'][^>]*>',
                  repl, html)


def parse_findings(text):
    out = []
    for line in text.splitlines():
        m = re.match(r'^\s+(FAIL|WARN|REFLEX|WAIVED|NOTE|DISMISSED|WAIVER)\s+(\S+)\s+:(\d+)\s*(.*)$', line)
        if m:
            out.append({'grade': m.group(1), 'gate': m.group(2),
                        'line': int(m.group(3)), 'evidence': m.group(4)})
    return out


def run_lint(root, html, tag):
    checker = (Path(root) / CHECKER_REL).resolve()
    node = shutil.which('node') or '/usr/bin/node'
    with tempfile.TemporaryDirectory(prefix='xp_hm_floor_') as td:
        page = Path(td) / ('%s.html' % tag)
        page.write_text(html, encoding='utf-8')
        try:
            p = subprocess.run([node, str(checker), str(page)],
                               cwd=td, capture_output=True, text=True, timeout=90)
            return parse_findings(p.stdout + '\n' + p.stderr), None
        except Exception as e:
            return [], str(e)


def dynamic_checks(root, base_url, ledger):
    c = {}
    for key, meta in ledger['pages'].items():
        html = fetch(base_url.rstrip('/') + meta['path'])
        ok_key = 'fetch_%s_200' % key
        c[ok_key] = html is not None
        if html is None:
            for g in ledger['zero_hit_gates']:
                if key in g['pages']:
                    c['%s_%s_zero' % (g['gate'], key)] = False
            continue
        findings, err = run_lint(root, inline_css(root, html), key)
        c['lint_%s_runs' % key] = err is None and bool(findings)
        bad = [f for f in findings if f['grade'] in BAD_GRADES]
        for g in ledger['zero_hit_gates']:
            if key not in g['pages']:
                continue
            hits = [f for f in bad if f['gate'] == g['gate']]
            c['%s_%s_zero' % (g['gate'], key)] = (err is None and not hits)
        for rule in ledger['contrast_must_be_zero']:
            if rule['page'] != key:
                continue
            for sel in rule['selectors']:
                hits = [f for f in bad if f['gate'] == '40' and sel in f['evidence']]
                c['40_%s_%s_zero' % (key, sel.replace('.', '').replace(' ', '_'))] = (
                    err is None and not hits)
    return c


# ---------------------------------------------------------------- 自测：造坏副本判红
def make_bad_root(root):
    td = tempfile.mkdtemp(prefix='xp_hm_bad_')
    for rel in KEY_FILES:
        src = Path(root) / rel
        dst = Path(td) / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_file():
            shutil.copy2(str(src), str(dst))
    return td


def _climate_note_span(lines):
    """定位口径说明所在段落：从含「口径说明」的行起，到下一个空行止。

    不钉格式、不钉具体文案。2026-11-17 实证：上一版把锚点写死成
    `line.startswith('**口径说明**')`，而正文实际是
    `**口径说明（2026-11-08，先读这段）**`，于是两个造坏用例从来没造出
    坏副本——自测报的是「锚点失配」，但人看到的是「守卫没判红」，方向全错。
    文案会改，判据不该跟着改。
    """
    for i, line in enumerate(lines):
        if '口径说明' in line:
            j = i
            while j < len(lines) and lines[j].strip():
                j += 1
            return i, j
    return None


def _move_climate_note_to_end(text):
    """造坏：把口径说明整段搬到文末。

    位置判据必须判红——声明在，但读者先看到数字、翻到最后才知道口径，
    等于声明没起作用。
    """
    lines = text.split('\n')
    span = _climate_note_span(lines)
    if span is None:
        return text  # 锚点失配，交给 noop 机制报错
    i, j = span
    block = lines[i:j]
    rest = lines[:i] + lines[j:]
    while rest and not rest[-1].strip():
        rest.pop()
    return '\n'.join(rest + ['', ''] + block) + '\n'


def _drop_climate_note(text):
    """造坏：整段删掉口径说明，正文里再也找不到它。"""
    lines = text.split('\n')
    span = _climate_note_span(lines)
    if span is None:
        return text
    i, j = span
    return '\n'.join(lines[:i] + lines[j:])


def self_test(root):
    results = {}
    good = make_bad_root(root)
    try:
        base_ok = static_checks(good)
        results['好副本静态检查全绿'] = all(base_ok.values())
        if not all(base_ok.values()):
            print('好副本失败项:', [k for k, v in base_ok.items() if not v])

        cases = [
            ('旧口径 91.3 复活会判红', 'templates/index.html',
             lambda t: ZERO_FN_SEMANTIC.sub('91.3% 检出率', t), 'no_legacy_91_3'),
            ('首页漏报口径消失会判红', 'templates/index.html',
             lambda t: ZERO_FN_SEMANTIC.sub('检出率百分比', t), 'home_states_zero_fn'),
            ('transition: all 复活会判红', 'templates/base.html',
             lambda t: t.replace('/* 列明真正会变的属性',
                                 'div{transition:all .2s}\n/* 列明真正会变的属性'),
             'no_transition_all_sitewide'),
            ('过渡 width 复活会判红', 'static/css/style.css',
             lambda t: t.replace('/* 宽度由模板一次性渲染',
                                 '.bad{transition:width .3s}\n/* 宽度由模板一次性渲染'),
             'no_transition_width_sitewide'),
            ('keyframes 动 top 复活会判红', 'templates/index.html',
             lambda t: t + '\n@keyframes bad { from { top: 0%; } to { top: 90%; } }\n',
             'no_keyframe_top'),
            ('横向溢出保护被删会判红', 'static/css/style.css',
             lambda t: t.replace('overflow-x: clip;', ''), 'overflow_clip_html_body'),
            ('主按钮退回低对比色会判红', 'templates/index.html',
             lambda t: re.sub(r'--accent\s*:\s*[^;]+;', '--accent:#c2703d;',
                              t, count=1),
             'accent_contrast_ok'),
            ('等待组件文字退回低对比色会判红', 'static/css/scan-fx.css',
             lambda t: t.replace('--xp-text: var(--color-text-on-subtle);',
                                 '--xp-text: #6B7B94;'),
             'xp_text_contrast_ok'),
            ('进度条退回动画 width 会判红', 'static/js/scan-fx.js',
             lambda t: t.replace('scaleX(', '.style.width = '), 'progress_bar_uses_scaleX'),
            ('AI 爬虫说明退回旧口径会判红', LLMS_REL,
             lambda t: t.replace('漏报 123 条', '真问题抓到 91.3%'), 'no_legacy_91_3'),
            ('AI 爬虫说明不带现行结论会判红', LLMS_REL,
             lambda t: t.replace('漏报 123 条', '实测数据'), 'llms_txt_current'),
            ('AI 爬虫说明复活 1.7% 旧误报率会判红', LLMS_REL,
             lambda t: t.replace('误报 0 条', '1.7%（误报率）'), 'no_legacy_1_7'),
            ('博客把口径说明挪到文末会判红', BLOG_REL,
             _move_climate_note_to_end, 'blog_legacy_marked'),
            ('博客删掉口径说明会判红', BLOG_REL,
             _drop_climate_note, 'blog_legacy_marked'),
            # ---- B 批次新增规矩 ----
            ('裸颜色回写样式表会判红', 'static/css/style.css',
             lambda t: t.replace('/* 藏青主题', '.bad{color:#ff0000}\n/* 藏青主题'),
             'no_bare_colour_in_css'),
            ('裸字体回写样式表会判红', 'static/css/style.css',
             lambda t: t.replace('/* 藏青主题',
                                 '.bad{font-family:"Comic Sans MS",sans-serif}\n/* 藏青主题'),
             'no_bare_font_in_css'),
            ('裸颜色回写内联样式会判红', 'templates/index.html',
             lambda t: t.replace('<body', '<div style="color:#ff0000">x</div>\n<body'),
             'no_bare_colour_in_templates'),
            ('样式搬进新 css 文件也要被扫到', 'static/css/blog.css',
             lambda t: t + '\n/* 造坏：新样式表里的裸颜色 */\n'
                           '.bad{color:#ff0000}\n',
             'no_bare_colour_in_css'),
            ('orange 变量名复活会判红', 'static/css/style.css',
             # 造坏不能依赖被检文件里恰好有某段文字：1108 删掉 style.css 的
             # :root 副本后，原来的 replace 锚点消失，坏例没造出来却判了绿。
             # 改成末尾追加注入，无论文件长什么样都能造出坏副本。
             lambda t: t + '\n/* 造坏：orange 变量名复活 */\n'
                           '.bad-orange{--color-accent-orange: var(--color-accent-steel);}\n',
             'no_orange_varname'),
            ('可读文字 token 被删会判红', TOKENS_REL,
             lambda t: drop_decl(t, '--color-text-on-subtle'),
             'readable_token_ok'),
            ('emoji 图标复活会判红', 'templates/base.html',
             lambda t: t.replace('<body', '<span>🎁 推荐有礼</span>\n<body'),
             'no_emoji_in_public'),
            ('箭头标签复活会判红', 'templates/try.html',
             lambda t: t.replace('开始免费检测', '开始免费检测 →', 1),
             'no_arrow_cta'),
            ('标题层级跳级复活会判红', 'templates/index.html',
             lambda t: t.replace('<h3>上传代码</h3>', '<h4>上传代码</h4>'),
             'heading_levels_fixed'),
            ('规矩本退回 A 方案会判红', 'design.md',
             lambda t: t.replace('第二批已收口', '待办排期中'),
             'design_md_batch_b_closed'),
        ]
        # 造坏用例本身也要被查：如果 mutate 一个字都没改动（锚点失配，
        # 典型是写死了某个色值、后来那色值改了），那就不是「守卫没判红」，
        # 而是「坏副本没造出来」。两种失败要分开报，否则下次还是照着
        # 假线索去改守卫。
        noop = []
        for label, rel, mutate, key in cases:
            bad = make_bad_root(root)
            try:
                orig = read(bad, rel)
                if orig is None:
                    results[label] = False
                    continue
                mutated = mutate(orig)
                if mutated == orig:
                    noop.append(label)
                    results[label] = False
                    continue
                write(bad, rel, mutated)
                got = static_checks(bad)
                results[label] = (got.get(key) is False)
            finally:
                shutil.rmtree(bad, ignore_errors=True)

        # 变量文件整个消失会判红
        bad = make_bad_root(root)
        try:
            (Path(bad) / TOKENS_REL).unlink(missing_ok=True)
            got = static_checks(bad)
            results['变量文件缺失会判红'] = (got['tokens_css_exists'] is False
                                          and got['public_pages_load_tokens'] is True)
        finally:
            shutil.rmtree(bad, ignore_errors=True)

        # 模板目录里重新出现备份文件会判红
        bad = make_bad_root(root)
        try:
            (Path(bad) / 'templates/index.html.bak_old').write_text('x', encoding='utf-8')
            results['模板目录备份复活会判红'] = static_checks(bad)['no_template_backups'] is False
        finally:
            shutil.rmtree(bad, ignore_errors=True)

        # 尺子本身还灵不灵
        probe = ('<html><head><style>.b{transition:width .3s}'
                 '@keyframes k{from{top:0}to{top:9%}}button{transition:all .2s}'
                 '.c{color:#ff0000}</style></head><body><button class="b">x</button>'
                 '</body></html>')
        findings, err = run_lint(root, probe, 'probe')
        results['检查器仍能检出 10a/48'] = err is None and any(
            f['gate'] == '10a' and f['grade'] in BAD_GRADES for f in findings) and any(
            f['gate'] == '48' and f['grade'] in BAD_GRADES for f in findings)

        bad = make_bad_root(root)
        try:
            (Path(bad) / LEDGER_REL).unlink(missing_ok=True)
            results['门禁清单缺失会判红'] = static_checks(bad)['gate_ledger_valid'] is False
        finally:
            shutil.rmtree(bad, ignore_errors=True)
    finally:
        shutil.rmtree(good, ignore_errors=True)

    failed = [k for k, v in results.items() if not v]
    for k, v in results.items():
        print('  %s %s' % ('OK ' if v else 'BAD', k))
    print('守卫自测: %d 项, 通过 %d, 失败 %d' %
          (len(results), len(results) - len(failed), len(failed)))
    if noop:
        raise AssertionError(
            '这些造坏用例没改动任何内容（锚点失配），坏副本根本没造出来: %s'
            % ', '.join(noop))
    if failed:
        raise AssertionError('守卫自测失败，这些坏副本没被判红: %s' % ', '.join(failed))
    return 0


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=DEFAULT_ROOT)
    ap.add_argument('--base-url', default=DEFAULT_URL)
    ap.add_argument('--self-test', action='store_true')
    a = ap.parse_args()
    root = a.root
    if a.self_test:
        return self_test(root)
    ledger_raw = read(root, LEDGER_REL)
    try:
        ledger = json.loads(ledger_raw) if ledger_raw else None
    except ValueError:
        ledger = None
    if not ledger:
        raise AssertionError('门禁清单不可读: %s' % (Path(root) / LEDGER_REL))
    checks = {}
    checks.update(static_checks(root))
    checks.update(dynamic_checks(root, a.base_url, ledger))
    bad = [k for k, v in checks.items() if not v]
    for k in sorted(checks):
        print('  %s %s' % ('OK ' if checks[k] else 'BAD', k))
    print('官网 UI 验收门禁: %d 项, 通过 %d, 失败 %d' %
          (len(checks), len(checks) - len(bad), len(bad)))
    if bad:
        raise AssertionError('官网 UI 门禁未通过: %s' % ', '.join(sorted(bad)))
    print('✅ 门禁全绿（只看清单命中，不看总 FAIL 数）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
