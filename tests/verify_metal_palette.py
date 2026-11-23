# -*- coding: utf-8 -*-
"""金属色门禁（QA 6p）：全站不许再出现橙黄，只许走金/银令牌。

为什么要有这条：
2026-11-09 之前模板里有 206 处橙黄（Tailwind 默认色板抄来的），同一个意思
五六种黄；换成金属色后如果不钉住，下次有人复制一段 AI 生成的样式就又回来了。

判据：
1. 模板与样式里出现色相 20-70、饱和 >=25%、明度 10%-85% 的颜色 → 判红。
   tokens.css 除外：那里是令牌定义处，金属金本身就在这个色相区间。
2. 引用 --color-v-<橙黄> 这种按值变量 → 判红（换成令牌，别再按色值抄）。
3. 金属令牌必须存在且真的被用（定义了没人用 = 死令牌，也是不整齐）。
"""
import colorsys
import os
import re
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
SITE = Path(os.environ.get('XP_SITE') or root)
TOKENS = 'static/css/tokens.css'

HEX = re.compile(r'#([0-9a-fA-F]{6})\b')
RGB = re.compile(r'rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})')
VARREF = re.compile(r'var\((--color-v-[0-9a-z]+)\)')
COMMENT = re.compile(r'/\*.*?\*/|<!--.*?-->', re.S)

REQUIRED_METALS = ['--color-metal-gold-deep', '--color-metal-gold',
                   '--color-metal-gold-bright', '--color-metal-gold-solid',
                   '--color-metal-gold-tint', '--color-metal-gold-tint-2',
                   '--color-metal-silver', '--color-metal-silver-bright']

# 语义色这一套是另一条腿：讲"严重度/状态"的地方必须用红绿黄，不许用金银。
# （2026-11-09 老板拍板：金银行，但只做装饰；带含义的颜色别为了统一而换掉。）
REQUIRED_SEMANTIC = ['--color-danger', '--color-warning', '--color-success',
                     '--color-sev-critical', '--color-sev-high',
                     '--color-sev-medium', '--color-sev-low',
                     '--color-sev-high-tint', '--color-sev-medium-tint']

SEMANTIC_SEL = re.compile(
    r'(severity|sev[-_]|status[-_]|grade|trend|risk|level)', re.I)


def is_orange(rgb):
    r, g, b = [v / 255 for v in rgb]
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return s >= 0.25 and 0.10 <= l <= 0.85 and 20 <= h * 360 <= 70


def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def var_is_orange(name):
    key = name.replace('--color-v-', '')[:6]
    if len(key) < 6 or any(c not in '0123456789abcdef' for c in key):
        return False
    return is_orange(hex_rgb(key))


def files(base=None):
    base = Path(base or SITE)
    out = []
    # 模板任意层级 + 样式 + 脚本：脚本里的色值同样会画到用户眼前
    for pat in ('templates/**/*.html', 'static/css/*.css', 'static/js/*.js'):
        out += sorted(Path(base).glob(pat))
    return [f for f in out if not f.name.endswith(('.bak', '.orig'))]


def strip_comments(text):
    """注释是给人看的说明，不是颜色用法；抹成等长空白，行号不动。

    不加这一步，写一句「以前这里抄的是 #FAAD14」都会被判红，
    久而久之大家就会去删注释而不是删坏色。
    """
    return COMMENT.sub(lambda m: re.sub(r'[^\n]', ' ', m.group(0)), text)


def check(base=None):
    base = Path(base or SITE)
    errs = []
    for f in files(base):
        rel = str(f.relative_to(base))
        if rel.replace('\\', '/') == TOKENS:
            continue
        try:
            text = strip_comments(f.read_text(encoding='utf-8'))
        except UnicodeDecodeError:
            continue
        except OSError as e:
            # 读不到就别判绿：看不见的文件里可能就藏着橙黄
            errs.append('%s 读不了（%s），不能算通过' % (rel, e))
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in HEX.finditer(line):
                if is_orange(hex_rgb(m.group(1))):
                    errs.append('%s:%d 还有橙黄裸色 #%s'
                                % (rel, lineno, m.group(1)))
            for m in RGB.finditer(line):
                if is_orange(tuple(int(x) for x in m.groups())):
                    errs.append('%s:%d 还有橙黄 rgba(%s)'
                                % (rel, lineno, m.group(0)[:24]))
            for m in VARREF.finditer(line):
                if var_is_orange(m.group(1)):
                    errs.append('%s:%d 又引用了按值橙黄变量 %s'
                                % (rel, lineno, m.group(1)))
            # 讲含义的地方不许用金属色：严重度/状态/等级要还是红绿黄
            if 'metal-' in line and SEMANTIC_SEL.search(line):
                errs.append('%s:%d 语义类样式用了金属色（严重度/状态要红绿黄）'
                            % (rel, lineno))
    return errs


def check_tokens(base=None):
    base = Path(base or SITE)
    p = base / TOKENS
    if not p.is_file():
        return ['%s 不见了' % TOKENS]
    text = p.read_text(encoding='utf-8')
    errs = []
    for name in REQUIRED_METALS:
        if re.search(re.escape(name) + r'\s*:', text) is None:
            errs.append('金属令牌缺了 %s' % name)
    # 定义在、但全站没人引用 = 死令牌
    blob = '\n'.join(f.read_text(encoding='utf-8', errors='ignore')
                     for f in files(base) if f.is_file())
    for name in REQUIRED_METALS:
        if re.search(r'var\(' + re.escape(name) + r'\)', blob) is None:
            errs.append('金属令牌 %s 定义了但没人用' % name)
    # 语义色那一套必须在，而且真的被引用：不然后人一"统一配色"就又把它换掉了
    for name in REQUIRED_SEMANTIC:
        if re.search(re.escape(name) + r'\s*:', text) is None:
            errs.append('语义色令牌缺了 %s（严重度/状态要靠它）' % name)
        elif re.search(r'var\(' + re.escape(name) + r'\)', blob) is None:
            errs.append('语义色令牌 %s 定义了但没人用' % name)
    return errs


# ---------------------------------------------------------------- 自检
CLEAN_HTML = """<html><head><style>
body{background:var(--color-surface-page);color:var(--color-text-primary)}
.gold{color:var(--color-metal-gold-deep)}
.card{background:var(--color-surface-card);border:1px solid var(--color-metal-gold)}
</style></head><body><div class="card gold">一段正文</div></body></html>"""

CLEAN_TOKENS = '\n'.join(
    '%s: #123456;' % n for n in REQUIRED_METALS + REQUIRED_SEMANTIC) + '\n'


def _mk(tmp, html=None, tokens=None):
    base = Path(tmp)
    (base / 'templates').mkdir(parents=True, exist_ok=True)
    (base / 'static/css').mkdir(parents=True, exist_ok=True)
    (base / 'templates/x.html').write_text(html or CLEAN_HTML,
                                           encoding='utf-8')
    names = '\n'.join('.u%d{color:var(%s)}' % (i, n)
                      for i, n in enumerate(REQUIRED_METALS
                                            + REQUIRED_SEMANTIC))
    (base / 'static/css/style.css').write_text(names, encoding='utf-8')
    (base / TOKENS).write_text(tokens or CLEAN_TOKENS, encoding='utf-8')
    return base


def self_test():
    ok = fail = 0

    def case(name, mutator, want_fail):
        nonlocal ok, fail
        with tempfile.TemporaryDirectory() as td:
            base = _mk(td)
            mutator(base)
            errs = check(base) + check_tokens(base)
            hit = bool(errs)
            if hit == want_fail:
                ok += 1
                print('  OK   %s（%s）' % (name, '判红' if hit else '判绿'))
            else:
                fail += 1
                print('  FAIL %s：期望%s，实际%s %s'
                      % (name, '判红' if want_fail else '判绿',
                         '判红' if hit else '判绿', (errs or [''])[0][:60]))

    case('干净样本必须判绿', lambda b: None, False)

    def m_hex(b):
        p = b / 'templates/x.html'
        p.write_text(CLEAN_HTML.replace('</style>',
                                        '.x{color:#f59e0b}</style>'),
                     encoding='utf-8')
    case('模板里写 Tailwind 橙必须判红', m_hex, True)

    def m_rgb(b):
        p = b / 'templates/x.html'
        p.write_text(CLEAN_HTML.replace('</style>',
                                        '.x{background:rgba(251,191,36,.2)}'
                                        '</style>'), encoding='utf-8')
    case('rgba 橙黄也要抓', m_rgb, True)

    def m_var(b):
        p = b / 'static/css/style.css'
        p.write_text(p.read_text(encoding='utf-8')
                     + '\n.v{color:var(--color-v-f59e0b)}\n',
                     encoding='utf-8')
    case('回头引用按值橙黄变量必须判红', m_var, True)

    def m_token(b):
        p = b / TOKENS
        p.write_text(p.read_text(encoding='utf-8')
                     + '--color-v-fbbf24: #fbbf24;\n', encoding='utf-8')
    case('tokens 里定义金是允许的（定义处豁免）', m_token, False)

    def m_missing(b):
        p = b / TOKENS
        p.write_text(CLEAN_TOKENS.replace(
            '--color-metal-gold-bright: #123456;\n', ''), encoding='utf-8')
    case('金属令牌被删必须判红', m_missing, True)

    def m_dead(b):
        p = b / 'static/css/style.css'
        p.write_text('\n'.join('.d{color:red}')
                     .replace('.d{color:red}',
                              '.d{color:var(--color-metal-silver)}'),
                     encoding='utf-8')
    case('令牌没人用也要判红', m_dead, True)

    def m_dark(b):
        p = b / 'templates/x.html'
        p.write_text(CLEAN_HTML.replace('</style>',
                                        '.y{border-color:#FF8C00}</style>'),
                     encoding='utf-8')
    case('橙色边框也抓（不是只看文字）', m_dark, True)

    def m_comment(b):
        p = b / 'templates/x.html'
        p.write_text(CLEAN_HTML.replace(
            '</style>',
            '/* 以前这里抄的是 #FAAD14，已废 */\n'
            '<!-- 另一种注释写法 #f59e0b -->\n'
            '</style>'), encoding='utf-8')
    case('注释里提到的旧色值不算用法', m_comment, False)

    def m_after_comment(b):
        p = b / 'templates/x.html'
        p.write_text(CLEAN_HTML.replace('</style>',
                                        '/* 说明 */ .z{color:#f59e0b}</style>'),
                     encoding='utf-8')
    case('注释后面的真样式照样抓', m_after_comment, True)

    def m_sev_metal(b):
        p = b / 'static/css/style.css'
        p.write_text(p.read_text(encoding='utf-8')
                     + '\n.issue-severity.high{background:var(--color-metal-gold-tint)}\n',
                     encoding='utf-8')
    case('严重度/状态用金属色必须判红', m_sev_metal, True)

    def m_sev_token(b):
        p = b / TOKENS
        p.write_text(CLEAN_TOKENS.replace(
            '--color-sev-high: #123456;\n', ''), encoding='utf-8')
    case('语义色令牌被删必须判红', m_sev_token, True)

    # 判绿那条路要能真的走完：签名写错了只有"全绿"时才炸（11-09 撞过）
    with tempfile.TemporaryDirectory() as td:
        base = _mk(td)
        n = len(files(base))
        if n:
            ok += 1
            print('  OK   判绿路径不崩（数出 %d 个待扫文件）' % n)
        else:
            fail += 1
            print('  FAIL 判绿路径数不出文件（函数签名/默认根目录有问题）')

    print('金属色门禁自检: %d 项，通过 %d，失败 %d' % (ok + fail, ok, fail))
    return 1 if fail else 0


def main():
    if '--self-test' in sys.argv:
        return self_test()
    errs = check() + check_tokens()
    if errs:
        for e in errs[:20]:
            print('FAIL ' + e)
        if len(errs) > 20:
            print('  …还有 %d 条' % (len(errs) - 20))
        print('金属色门禁: %d 项不合格' % len(errs))
        return 1
    n = len(files())
    print('配色门禁通过：%d 个模板/样式文件里没有橙黄裸色；'
          '装饰走金/银，严重度/状态仍走红绿黄' % n)
    return 0


if __name__ == '__main__':
    sys.exit(main())
