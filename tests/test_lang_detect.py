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

from lang_detect import detect, score  # noqa: E402

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
