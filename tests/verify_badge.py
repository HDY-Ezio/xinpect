#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""徽章接口守卫（QA 6o，2026-11-09）

/api/badge/<scan_id>.svg 是给 GitHub README 贴分数用的徽章。以前这里没有守卫，
三档用了 #4c1 / #FF6B35 / #e05d44，白字压在上面只有 2.12 / 2.84 / 3.61 ——
绿色那档基本等于看不见（白字压在亮草绿上）。而且 scan 查不到时返回「0 需改进」，
把「没有这条记录」说成「评测过、极差」，是两件事。

判据：
  1. 三档白字对比度都 >= 4.5:1
  2. 三档颜色互不相同（否则徽章分不出等级，等于废掉）
  3. 三档色值必须来自 tokens.css（不许在 Python 里手写第二份色表）
  4. 查不到的 scan 必须写「未知」，不许冒充任何等级
  5. 降级色只能是中性灰（不许换成有色彩冒充等级）
自带造坏自检；藏守卫即套件不能绿。
"""

import ast
import io
import os
import re
import sqlite3
import sys
import urllib.request
import urllib.error

SITE = os.environ.get('XP_SITE', '/opt/xinpect-website')
BASE = os.environ.get('XP_BASE', 'http://127.0.0.1:8621').rstrip('/')

CI_PY = os.path.join(SITE, 'modules', 'ci.py')
TOKENS_CSS = os.path.join(SITE, 'static', 'css', 'tokens.css')

GRADE_WORDS = ('优秀', '良好', '需改进')
UNKNOWN_WORD = '未知'

problems = []


def fail(msg):
    problems.append(msg)


# ---------------------------------------------------------------- 颜色工具
def _rgb(hexstr):
    h = hexstr.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    if len(h) != 6:
        return None
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def rel_lum(hexstr):
    rgb = _rgb(hexstr)
    if rgb is None:
        return None
    vals = []
    for c in rgb:
        s = c / 255.0
        vals.append(s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4)
    return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]


def contrast(a, b):
    la, lb = rel_lum(a), rel_lum(b)
    if la is None or lb is None:
        return 0.0
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def is_neutral_grey(hexstr):
    """灰阶：三通道极差 <= 24。用来确认降级色没有偷带颜色。"""
    rgb = _rgb(hexstr)
    if rgb is None:
        return False
    return max(rgb) - min(rgb) <= 24


# ---------------------------------------------------------------- 解析
def parse_badge(svg):
    """从一个徽章 SVG 里取出：(左侧底板色, 右侧状态色, 可见文字)。"""
    plate = re.search(r'<rect width="106"[^>]*fill="(#[0-9A-Fa-f]{3,8})"', svg)
    state = re.search(r'<rect x="106"[^>]*fill="(#[0-9A-Fa-f]{3,8})"', svg)
    text = re.search(r'<text x="146"[^>]*>([^<]*)</text>', svg)
    return (plate.group(1) if plate else None,
            state.group(1) if state else None,
            text.group(1).strip() if text else None)


def inspect_badge(svg, token_colors):
    """纯判据：输入一枚徽章 SVG，输出问题列表。造坏自检直接喂坏样本给它。"""
    out = []
    plate, state, text = parse_badge(svg)
    if not plate or not state or text is None:
        return ['徽章 SVG 结构不对：取不到左块/右块/文字']

    ratio = contrast('#ffffff', state)
    if ratio < 4.5:
        out.append('状态块 %s 上白字只有 %.2f:1（要 >= 4.5）' % (state, ratio))

    pratio = contrast('#ffffff', plate)
    if pratio < 4.5:
        out.append('底板 %s 上白字只有 %.2f:1（要 >= 4.5）' % (plate, pratio))

    m = re.search(r'<title>[^<]*</title>', svg)
    if not m:
        out.append('缺 <title>，读屏软件念不出分数')
    elif text not in m.group(0):
        out.append('<title> 与可见文字不一致：%r vs %r' % (m.group(0), text))

    known = [c.lower() for c in token_colors if c]
    if state.lower() not in known:
        out.append('状态色 %s 不在 tokens.css 里，说明是手写的第二份色表' % state)
    return out


# ---------------------------------------------------------------- 静态
def read(path):
    try:
        with io.open(path, encoding='utf-8') as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def token_defs():
    css = read(TOKENS_CSS)
    if css is None:
        fail('读不到 tokens.css: %s' % TOKENS_CSS)
        return {}
    out = {}
    for m in re.finditer(r'--([\w-]+)\s*:\s*(#[0-9A-Fa-f]{3,8})\s*;', css):
        out[m.group(1)] = m.group(2)
    return out


def check_source():
    """三档必须指向 token 名，且这些名在 tokens.css 里真有定义。"""
    src = read(CI_PY)
    if src is None:
        fail('读不到 %s' % CI_PY)
        return
    # 用 AST 取值，不靠正则——正则会被元组里第一个右括号截断
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        fail('ci.py 语法错误，解析不了：%s' % e)
        return

    literals = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in (
                        '_BADGE_GRADES', '_BADGE_NEUTRAL'):
                    try:
                        literals[t.id] = ast.literal_eval(node.value)
                    except ValueError:
                        fail('%s 不是字面量，守卫读不出档位' % t.id)

    grades = literals.get('_BADGE_GRADES')
    if not grades:
        fail('ci.py 里找不到 _BADGE_GRADES，徽章取色结构被改掉了')
        return
    if len(grades) != 3:
        fail('_BADGE_GRADES 应该正好三档，实际 %d 档' % len(grades))
        return

    defs = token_defs()
    for item in grades:
        if not isinstance(item, tuple) or len(item) != 3:
            fail('_BADGE_GRADES 的档位格式不对：%r' % (item,))
            continue
        _floor, token, label = item
        if not str(token).startswith('color-'):
            fail('档位 %s 用的是字面值 %r，不是 tokens 里的变量名' % (label, token))
            continue
        if token not in defs:
            fail('档位 %s 指向的 --%s 在 tokens.css 里没有定义' % (label, token))

    labels = [g[2] for g in grades if isinstance(g, tuple) and len(g) == 3]
    for w in GRADE_WORDS:
        if w not in labels:
            fail('三档标签里缺「%s」，实际为 %s' % (w, labels))

    neutral = literals.get('_BADGE_NEUTRAL')
    if not neutral:
        fail('找不到 _BADGE_NEUTRAL（降级色）')
    elif not is_neutral_grey(str(neutral)):
        fail('降级色 %s 不是中性灰，带色彩就等于在冒充等级' % neutral)


# ---------------------------------------------------------------- 动态
def find_db():
    cand = os.path.join(SITE, 'xinpect.db')
    if os.path.exists(cand):
        return cand
    for name in sorted(os.listdir(SITE)):
        p = os.path.join(SITE, name)
        if name.endswith('.db') and os.path.isfile(p):
            try:
                con = sqlite3.connect('file:%s?mode=ro' % p, uri=True)
                if con.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='scans'"
                ).fetchone():
                    con.close()
                    return p
                con.close()
            except sqlite3.Error:
                continue
    return None


def pick_samples(db_path):
    """每档挑一条真实 scan_id。"""
    con = sqlite3.connect('file:%s?mode=ro' % db_path, uri=True)
    out = {}
    for key, cond in (('high', 'score >= 80'),
                      ('mid', 'score >= 60 AND score < 80'),
                      ('low', 'score < 60')):
        row = con.execute('SELECT scan_id, score FROM scans WHERE %s '
                          'AND scan_id IS NOT NULL '
                          'ORDER BY created_at DESC LIMIT 1' % cond).fetchone()
        if row:
            out[key] = row
    con.close()
    return out


def fetch_badge(scan_id):
    url = '%s/api/badge/%s.svg' % (BASE, scan_id)
    req = urllib.request.Request(url, headers={'User-Agent': 'xinpect-qa/badge'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.getcode(), r.headers.get('Content-Type', ''), r.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, '', ''
    except Exception as e:
        return None, '', str(e)


def check_live(samples):
    defs = token_defs()
    token_values = list(defs.values())

    if len(samples) < 3:
        fail('数据库里凑不齐三档样本（实际 %d 档），无法验证分档' % len(samples))
        return

    seen = {}
    for key in ('high', 'mid', 'low'):
        scan_id, score = samples[key]
        code, ctype, body = fetch_badge(scan_id)
        if code != 200:
            fail('%s 档（score=%s）请求失败：code=%s %s'
                 % (key, score, code, body[:80]))
            continue
        if 'svg' not in ctype:
            fail('%s 档 Content-Type 不是 svg：%s' % (key, ctype))
        for p in inspect_badge(body, token_values):
            fail('%s 档（score=%s）%s' % (key, score, p))
        _, state, text = parse_badge(body)
        seen[key] = (state, text)
        expected = ('优秀' if score >= 80 else '良好' if score >= 60 else '需改进')
        if expected not in (text or ''):
            fail('%s 档 score=%s 应显示「%s」，实际显示 %r'
                 % (key, score, expected, text))

    states = [v[0] for v in seen.values() if v[0]]
    if len(states) == 3 and len(set(s.lower() for s in states)) != 3:
        fail('三档颜色有重复 %s，徽章分不出等级' % states)

    # 查不到的 scan：必须说「未知」，不许冒充等级
    ghost = '0' * 64
    code, _, body = fetch_badge(ghost)
    if code != 200:
        fail('不存在的 scan 请求失败：code=%s' % code)
    else:
        _, gstate, gtext = parse_badge(body)
        if gtext is None:
            fail('不存在的 scan 返回的 SVG 取不到文字')
        else:
            if UNKNOWN_WORD not in gtext:
                fail('不存在的 scan 应写「未知」，实际 %r（把查不到说成了等级）' % gtext)
            for w in GRADE_WORDS:
                if w in gtext:
                    fail('不存在的 scan 显示了等级「%s」' % w)
        for p in inspect_badge(body, token_values):
            fail('不存在的 scan：%s' % p)


# ---------------------------------------------------------------- 自检
def selftest():
    """造坏样本必须全部判红。样本是手写的 SVG，判据函数直接吃。"""
    defs = token_defs()
    values = list(defs.values())
    ok_color = defs.get('color-success', '#17795C')
    plate = defs.get('color-accent-blue', '#1A2B4A')

    def svg(plate_c, state_c, text, title=None):
        title = text if title is None else title
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="186" height="20" role="img">'
            '<title>煋鉴评分: %s</title>'
            '<clipPath id="r"><rect width="186" height="20" rx="3" fill="#fff"/></clipPath>'
            '<g clip-path="url(#r)">'
            '<rect width="106" height="20" fill="%s"/>'
            '<rect x="106" width="80" height="20" fill="%s"/>'
            '</g><g fill="#fff" text-anchor="middle" font-size="11">'
            '<text x="53" y="14">煋鉴评分</text>'
            '<text x="146" y="14">%s</text>'
            '</g></svg>' % (title, plate_c, state_c, text)
        )

    cases = [
        # 这三个是史上真用过的值，关键词对齐判据的报错口径
        ('白字压亮草绿要判红', svg(plate, '#44cc11', '95 优秀'), '白字只有'),
        ('白字压橙要判红', svg(plate, '#FF6B35', '75 良好'), '白字只有'),
        ('白字压浅红要判红', svg(plate, '#e05d44', '42 需改进'), '白字只有'),
        ('状态色不在 tokens 里要判红',
         svg(plate, '#123456', '95 优秀'), '第二份色表'),
        ('title 与可见文字不一致要判红',
         svg(plate, ok_color, '95 优秀', title='42 需改进'), '不一致'),
    ]

    results = []
    for label, bad_svg, keyword in cases:
        got = inspect_badge(bad_svg, values)
        hit = any(keyword in g for g in got)
        results.append((label, hit, got))

    # 正向对照：好徽章不许误报（否则判据只会乱叫）
    good = svg(plate, ok_color, '95 优秀')
    gate = inspect_badge(good, values)
    results.append(('合格的徽章不许误报', not gate, gate))

    # 灰阶判据
    results.append(('降级色必须是灰阶', is_neutral_grey('#333333')
                    and not is_neutral_grey('#884422'),
                    []))

    bad = [r for r in results if not r[1]]
    for label, passed, got in results:
        print('  %s %s' % ('OK ' if passed else 'BAD', label))
        if not passed and got:
            print('      实际报出: %s' % got[:2])
    print('徽章守卫自测: %d 项, 通过 %d, 失败 %d'
          % (len(results), len(results) - len(bad), len(bad)))
    if bad:
        raise AssertionError('自检失败，这些坏样本没被判红: %s'
                             % ', '.join(b[0] for b in bad))


# ---------------------------------------------------------------- main
def main():
    if '--self-test' in sys.argv:
        try:
            selftest()
            return 0
        except AssertionError as e:
            print('❌ %s' % e)
            return 1

    check_source()

    db = find_db()
    if not db:
        fail('找不到数据库，无法取三档样本')
    else:
        samples = pick_samples(db)
        check_live(samples)

    if problems:
        print('❌ 徽章接口守卫不通过：%d 个问题' % len(problems))
        for p in problems[:30]:
            print('  -', p)
        return 1
    print('✅ 徽章接口守卫通过：三档白字 >= 4.5:1、三档分得开、'
          '色值取自 tokens.css、查不到的 scan 不冒充等级')
    return 0


if __name__ == '__main__':
    sys.exit(main())
