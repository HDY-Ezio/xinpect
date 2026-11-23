# -*- coding: utf-8 -*-
"""代码语言识别 —— 让"自动识别"真的识别，而不是退化成 .txt。

背景（2026-11-04）：免注册试扫页的默认选项是「自动识别」，服务端在识别不出来时
把文件名定成 `sample.txt`，结果引擎拿不到语法信息，只能跑纯正则层的通用规则。
用同一段带 SQL 注入 + os.system 的 Python 实测：
    language=python → 检出 2 条高危（SQL注入、os.system 调用），健康度 40 / D
    language=auto   → 只检出 1 条中危（"数据库查询无慢查询监控"），健康度 92 / A
也就是说**默认路径下这个功能是废的**，而绝大多数人不会去动那个下拉框。

这里不写"白名单"——不是"这几种语言才算数"，而是给每种语言的**语法特征**打分，
取得分最高且与第二名拉开差距的那个；拉不开就老实说"认不出来"，让用户选。
任何语言识别器（GitHub Linguist、Pygments）本质都是这件事，区别只在特征表的质量。

对外只有一个函数：
    detect(code) -> (lang, score, runner_up_score)
    lang 为 None 表示认不准（分不够或第一二名咬得太紧）。
"""

import re

# 每种语言的特征：(正则, 权重)。权重按「这条特征有多少见」定，
# 越是被某语言独占的写法权重越高（System.out 只可能是 Java，defer 只可能是 Go）。
SIGNATURES = {
    'python': [
        (r'(?m)^\s*def\s+\w+\s*\([^)]*\)\s*(->[^:]+)?:\s*$', 4),
        (r'(?m)^\s*(from\s+[\w.]+\s+import|import\s+[\w.]+(\s+as\s+\w+)?)\s*$', 3),
        (r'(?m)^\s*(if|elif|else|for|while|try|except|finally|with|class)\b[^\n]*:\s*$', 2),
        (r'\bself\.', 2),
        (r'__name__\s*==', 5),
        (r'\bprint\s*\(', 1),
        (r'(?m)^\s*@\w+(\.\w+)*\s*$', 1),
        (r'\b(lambda|yield|None|True|False)\b', 1),
    ],
    'java': [
        (r'\bpublic\s+(final\s+|abstract\s+)?class\s+\w+', 5),
        (r'(?m)^\s*import\s+(static\s+)?java[x]?\.', 5),
        (r'\bSystem\.out\.print', 5),
        (r'\bpublic\s+static\s+void\s+main\s*\(\s*String\s*\[\s*\]', 5),
        (r'@Override\b', 4),
        (r'\bprivate\s+(final\s+)?[A-Z]\w*(<[^>]*>)?\s+\w+\s*[;=]', 2),
        (r'\bimplements\b|\bextends\b', 1),
    ],
    'javascript': [
        (r'\bconsole\.log\s*\(', 4),
        (r'\brequire\s*\(\s*[\'"]', 4),
        (r'\bmodule\.exports\b', 4),
        (r'\bdocument\.(getElementById|querySelector|addEventListener)', 4),
        (r'=>', 2),
        (r'\b(const|let)\s+\w+\s*=', 2),
        (r'\bfunction\s+\w*\s*\(', 2),
        (r'===', 1),
    ],
    'typescript': [
        (r'\bimport\s+type\b', 6),
        (r'\binterface\s+\w+\s*\{', 4),
        (r'\bexport\s+(const|interface|type|class|default)\b', 3),
        (r':\s*(string|number|boolean|any|void|unknown)\b', 3),
        (r'\b(as|implements)\s+[A-Z]\w*', 2),
        (r'<[A-Z]\w*(\[\])?>', 2),
    ],
    'go': [
        (r'(?m)^\s*package\s+\w+\s*$', 6),
        (r'\bfunc\s+(\(\w+\s+\*?\w+\)\s*)?\w+\s*\(', 4),
        (r'\bfmt\.\w+', 5),
        (r':=', 3),
        (r'(?m)^\s*import\s*\(', 4),
        (r'\bdefer\s+', 4),
        (r'\berr\s*!=\s*nil\b', 4),
    ],
    'php': [
        (r'<\?php', 8),
        (r'\$this->', 5),
        (r'\becho\s+\$', 3),
        (r'->\w+\s*\(', 2),
        (r'\bnamespace\s+[\w\\]+;', 2),
    ],
    'c': [
        (r'#include\s*[<"]', 3),
        (r'\bint\s+main\s*\(', 3),
        (r'\bprintf\s*\(', 3),
        (r'\bmalloc\s*\(|\bfree\s*\(', 3),
        (r'\bstruct\s+\w+\s*\{', 2),
        (r'\btypedef\s+', 3),
        (r'\bsizeof\s*\(', 2),
    ],
    'cpp': [
        (r'#include\s*<(iostream|vector|string|map|memory)>', 8),
        (r'\bstd::', 6),
        (r'\bcout\s*<<|\bcin\s*>>', 6),
        (r'\btemplate\s*<', 4),
        (r'\bclass\s+\w+\s*:\s*(public|private|protected)\s+', 4),
        (r'\bnullptr\b', 3),
        (r'\busing\s+namespace\s+std\b', 4),
    ],
    'csharp': [
        (r'\busing\s+System(\.\w+)*\s*;', 7),
        (r'\bConsole\.(Write|Read)', 7),
        (r'\bpublic\s+static\s+void\s+Main\s*\(\s*string\s*\[\s*\]', 7),
        (r'\[(HttpGet|HttpPost|Route|ApiController)', 4),
        (r'\bvar\s+\w+\s*=\s*new\s+[A-Z]', 2),
        (r'\bpublic\s+(async\s+)?Task(<[^>]*>)?\s+\w+\s*\(', 3),
    ],
    'ruby': [
        (r'(?m)^\s*end\s*$', 4),
        (r'\bputs\s+', 3),
        (r'\.each\s+do\s*\|', 5),
        (r'\bdo\s*\|\w+(\s*,\s*\w+)*\|', 4),
        (r'\brequire\s+[\'"]', 2),
        (r'(?m)^\s*def\s+\w+[!?]?\s*(\([^)]*\))?\s*$', 2),
        (r'\battr_(accessor|reader|writer)\b', 5),
    ],
    'swift': [
        (r'\bimport\s+(UIKit|Foundation|SwiftUI|Combine)\b', 7),
        (r'\bguard\s+.*\belse\b', 5),
        (r'\bfunc\s+\w+\s*\(', 2),
        (r'\blet\s+\w+\s*:\s*[A-Z]\w*', 3),
        (r'\bstruct\s+\w+\s*:\s*\w+', 3),
        (r'\b(weak\s+)?var\s+\w+\s*:\s*[A-Z]\w*\?', 3),
    ],
    'kotlin': [
        (r'\bfun\s+\w+\s*\(', 5),
        (r'\bimport\s+kotlin', 6),
        (r'\bdata\s+class\s+\w+', 5),
        (r'\bcompanion\s+object\b', 5),
        (r'\bval\s+\w+\s*(:|=)', 2),
        (r'\boverride\s+fun\b', 4),
    ],
    'scala': [
        (r'\bobject\s+\w+\s*(extends|\{)', 4),
        (r'\bcase\s+class\s+\w+', 6),
        (r'\bimplicit\s+', 5),
        (r'(?m)^\s*def\s+\w+\s*\(.*\)\s*:\s*[\w\[\]]+\s*=', 4),
        (r'\bval\s+\w+\s*:\s*[\w\[\]]+\s*=', 2),
    ],
    'rust': [
        (r'\bfn\s+\w+\s*\(', 4),
        (r'\blet\s+mut\b', 6),
        (r'\bprintln!\s*\(', 6),
        (r'\buse\s+std::', 5),
        (r'\bimpl\s+\w+', 4),
        (r'&mut\s+\w+', 3),
        (r'\bString::from\b', 3),
    ],
    'dart': [
        (r'\bimport\s+[\'"]package:', 7),
        (r'\bvoid\s+main\s*\(\s*\)', 4),
        (r'\bWidget\s+build\s*\(', 5),
        (r'@override\b', 2),
        (r'\bFuture<', 3),
    ],
}

# shebang 是最硬的证据，直接给满
SHEBANG = [
    (r'^#!.*\bpython', 'python'),
    (r'^#!.*\bnode\b', 'javascript'),
    (r'^#!.*\bruby', 'ruby'),
    (r'^#!.*\bphp', 'php'),
]

# 认出这个分数且甩开第二名这么多才算数，否则宁可让用户选
MIN_SCORE = 3
MIN_MARGIN = 2

_COMPILED = {
    lang: [(re.compile(pat, re.M), w) for pat, w in sigs]
    for lang, sigs in SIGNATURES.items()
}


def score(code):
    """给每种语言打分，返回 {lang: score}（只在大于 0 时出现）。"""
    result = {}
    for lang, pats in _COMPILED.items():
        total = 0
        for pat, weight in pats:
            if pat.search(code):
                total += weight
        if total > 0:
            result[lang] = total
    return result


def detect(code):
    """识别代码语言。

    返回 (lang, top_score, runner_up_score)。lang 为 None 表示认不准：
    要么分数不够（太短的片段），要么第一二名差距不足（Python/Ruby 这种同族写法）。
    """
    code = code or ''
    if not code.strip():
        return None, 0, 0

    # C# 和 Java 都写 public static void Main，但大小写不同（string[] vs String[]），
    # 上面两条特征已经分开；这里只补 shebang。
    head = code.lstrip()[:200]
    for pat, lang in SHEBANG:
        if re.match(pat, head):
            s = score(code)
            return lang, s.get(lang, 0) + 10, 0

    s = score(code)
    if not s:
        return None, 0, 0

    ranked = sorted(s.items(), key=lambda kv: kv[1], reverse=True)
    top_lang, top_score = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0

    if top_score < MIN_SCORE or (top_score - second) < MIN_MARGIN:
        return None, top_score, second
    return top_lang, top_score, second


def explain(code):
    """给人看的诊断（排障用，不参与业务判断）。"""
    s = score(code)
    ranked = sorted(s.items(), key=lambda kv: kv[1], reverse=True)
    lang, top, second = detect(code)
    return {
        'detected': lang,
        'top': top,
        'second': second,
        'ranking': ranked[:5],
    }
