#!/usr/bin/env python3
"""
煋鉴 Xinpect CLI v2.0 - 命令行代码扫描工具
============================================

使用方法:
    xinpect-cli.py init                  # 初始化项目配置
    xinpect-cli.py scan                  # 扫描项目
    xinpect-cli.py scan --incremental    # 增量扫描（仅 git diff）
    xinpect-cli.py scan --local-only     # 离线本地检查
    xinpect-cli.py scan --output sarif   # SARIF 输出
    xinpect-cli.py scan --threshold 70 --fail-on-below
"""

import argparse
import json
import os
import sys
import re
import subprocess
import urllib.request
import urllib.error

__version__ = "2.0.0"
DEFAULT_API_URL = "https://xinpect.xingwangzhineng.com"
CONFIG_FILENAME = ".xinpect.json"
MAX_FILES = 200
MAX_FILE_KB = 500

SUPPORTED_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go',
    '.c', '.cpp', '.h', '.hpp', '.cs', '.rb', '.php',
    '.swift', '.kt', '.scala', '.rs', '.vue', '.svelte',
    '.html', '.css', '.scss', '.sql', '.sh', '.yaml', '.yml',
}
IGNORE_DIRS = {
    'node_modules', '.git', '__pycache__', '.venv', 'venv',
    'dist', 'build', '.next', '.nuxt', 'target', 'vendor',
    '.tox', '.mypy_cache', '.pytest_cache', 'coverage',
    '.github', '.gitlab', '.idea', '.vscode', '.svn', '.xinpect',
}

class Colors:
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'

def colored(text, color):
    if not sys.stdout.isatty():
        return text
    return f"{color}{text}{Colors.RESET}"

# ── 配置管理 ──
def find_config(start=None):
    path = start or os.getcwd()
    while True:
        p = os.path.join(path, CONFIG_FILENAME)
        if os.path.isfile(p):
            return p
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent

def load_config(path=None):
    p = path or find_config()
    if not p or not os.path.isfile(p):
        return {}
    with open(p, 'r', encoding='utf-8') as f:
        return json.load(f)

# ── init 命令 ──
def cmd_init(args):
    print(colored("🔧 煋鉴 Xinpect 项目初始化", Colors.BOLD))
    print()
    config_path = os.path.join(os.getcwd(), CONFIG_FILENAME)
    existing = {}
    if os.path.isfile(config_path):
        print(colored(f"  发现已有配置: {CONFIG_FILENAME}，将覆盖", Colors.YELLOW))
        with open(config_path, 'r') as f:
            existing = json.load(f)
        print()

    config = {}
    default_key = existing.get('api_key', '') or os.environ.get('XINPECT_API_KEY', '')
    default_url = existing.get('api_url', '') or os.environ.get('XINPECT_API_URL', DEFAULT_API_URL)
    default_mode = existing.get('scan_mode', '') or os.environ.get('XINPECT_SCAN_MODE', 'quick')
    default_threshold = existing.get('threshold', 60)
    default_ignore = existing.get('ignore', [])
    default_output = existing.get('output_format', 'text')
    default_scan_path = existing.get('scan_path', '.')

    if args.non_interactive:
        config = {
            'api_key': default_key, 'api_url': default_url,
            'scan_mode': default_mode, 'threshold': default_threshold,
            'ignore': default_ignore, 'output_format': default_output,
            'scan_path': default_scan_path,
        }
    else:
        key_in = input(f"  API Key [{default_key[:8]+'...' if default_key else '留空'}]: ").strip()
        config['api_key'] = key_in or default_key
        url_in = input(f"  API 地址 [{default_url}]: ").strip()
        config['api_url'] = url_in or default_url
        mode_in = input(f"  扫描档位 (free/quick/smart/deep) [{default_mode}]: ").strip()
        config['scan_mode'] = mode_in or default_mode
        thr_in = input(f"  门禁阈值 (0-100) [{default_threshold}]: ").strip()
        config['threshold'] = int(thr_in) if thr_in else default_threshold
        ign_in = input(f"  忽略目录 (逗号分隔) [{','.join(default_ignore)}]: ").strip()
        config['ignore'] = [x.strip() for x in ign_in.split(',') if x.strip()] if ign_in else default_ignore
        out_in = input(f"  输出格式 (text/json/sarif) [{default_output}]: ").strip()
        config['output_format'] = out_in or default_output
        path_in = input(f"  扫描路径 [{default_scan_path}]: ").strip()
        config['scan_path'] = path_in or default_scan_path

    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    rules_dir = os.path.join(os.getcwd(), '.xinpect', 'rules')
    os.makedirs(rules_dir, exist_ok=True)
    print()
    print(colored(f"  ✅ 配置已保存: {CONFIG_FILENAME}", Colors.GREEN))
    _write_builtin_rules(rules_dir)
    print(colored("  ✅ 离线规则已写入 .xinpect/rules/（31 条）", Colors.GREEN))
    print()
    print(colored("  接下来:", Colors.BOLD))
    print("    xinpect-cli.py scan                # 扫描项目")
    print("    xinpect-cli.py scan --incremental   # 增量扫描")
    print("    xinpect-cli.py scan --local-only    # 离线检查（无需网络）")
    print("    xinpect-cli.py scan --output sarif  # SARIF 输出")
    print()

def _write_builtin_rules(rules_dir):
    """写入内置离线规则（4语言 31条）"""
    rules = {
        "python": {"language":"python","version":"2.0.0","rules":[
            {"id":"PY-LOCAL-001","severity":"warning","pattern":"exec\\s*\\(","message":"exec() 存在代码注入风险","suggestion":"使用 ast.literal_eval()"},
            {"id":"PY-LOCAL-002","severity":"warning","pattern":"eval\\s*\\(","message":"eval() 存在代码注入风险","suggestion":"使用 ast.literal_eval()"},
            {"id":"PY-LOCAL-003","severity":"warning","pattern":"os\\.system\\s*\\(","message":"os.system() 存在命令注入风险","suggestion":"使用 subprocess.run() + shell=False"},
            {"id":"PY-LOCAL-004","severity":"warning","pattern":"subprocess\\.call\\s*\\(.*shell\\s*=\\s*True","message":"shell=True 存在命令注入风险","suggestion":"使用 subprocess.run() + shell=False"},
            {"id":"PY-LOCAL-005","severity":"info","pattern":"except\\s*:","message":"裸 except 捕获所有异常","suggestion":"使用 except Exception as e"},
            {"id":"PY-LOCAL-006","severity":"info","pattern":"import\\s+pickle","message":"pickle 反序列化存在 RCE 风险","suggestion":"使用 json 或 msgpack"},
            {"id":"PY-LOCAL-007","severity":"warning","pattern":"password\\s*=\\s*[\"'][^\"']+[\"']","message":"硬编码密码","suggestion":"使用环境变量"},
            {"id":"PY-LOCAL-008","severity":"warning","pattern":"api_key\\s*=\\s*[\"'][^\"']+[\"']","message":"硬编码 API Key","suggestion":"使用 os.environ.get()"},
            {"id":"PY-LOCAL-009","severity":"warning","pattern":"secret\\s*=\\s*[\"'][^\"']+[\"']","message":"硬编码密钥","suggestion":"使用环境变量或密钥管理服务"},
            {"id":"PY-LOCAL-010","severity":"info","pattern":"TODO|FIXME|HACK|XXX","message":"待处理标记","suggestion":"及时处理 TODO/FIXME"},
        ]},
        "javascript": {"language":"javascript","version":"2.0.0","rules":[
            {"id":"JS-LOCAL-001","severity":"warning","pattern":"eval\\s*\\(","message":"eval() 存在代码注入风险","suggestion":"使用 JSON.parse()"},
            {"id":"JS-LOCAL-002","severity":"warning","pattern":"innerHTML\\s*=","message":"innerHTML 存在 XSS 风险","suggestion":"使用 textContent 或 DOMPurify"},
            {"id":"JS-LOCAL-003","severity":"warning","pattern":"document\\.write\\s*\\(","message":"避免 document.write()","suggestion":"使用 DOM API"},
            {"id":"JS-LOCAL-004","severity":"info","pattern":"console\\.log\\s*\\(","message":"生产代码残留 console.log","suggestion":"移除调试输出"},
            {"id":"JS-LOCAL-005","severity":"warning","pattern":"\\bvar\\s+","message":"使用 var 声明","suggestion":"使用 const/let"},
            {"id":"JS-LOCAL-006","severity":"warning","pattern":"password\\s*[:=]\\s*[\"'][^\"']+[\"']","message":"硬编码密码","suggestion":"使用环境变量"},
            {"id":"JS-LOCAL-007","severity":"warning","pattern":"api[_-]?key\\s*[:=]\\s*[\"'][^\"']+[\"']","message":"硬编码 API Key","suggestion":"使用环境变量"},
            {"id":"JS-LOCAL-008","severity":"warning","pattern":"dangerouslySetInnerHTML","message":"React XSS 风险","suggestion":"使用 DOMPurify"},
            {"id":"JS-LOCAL-009","severity":"info","pattern":"TODO|FIXME|HACK|XXX","message":"待处理标记","suggestion":"及时处理"},
            {"id":"JS-LOCAL-010","severity":"warning","pattern":"localStorage\\.setItem","message":"localStorage 敏感数据泄露风险","suggestion":"使用 httpOnly cookie"},
        ]},
        "java": {"language":"java","version":"2.0.0","rules":[
            {"id":"JAVA-LOCAL-001","severity":"warning","pattern":"Runtime\\.getRuntime\\(\\)\\.exec","message":"命令注入风险","suggestion":"使用 ProcessBuilder + 验证输入"},
            {"id":"JAVA-LOCAL-002","severity":"warning","pattern":"ObjectInputStream","message":"反序列化 RCE 风险","suggestion":"白名单过滤可反序列化类"},
            {"id":"JAVA-LOCAL-003","severity":"warning","pattern":"password\\s*=\\s*\"[^\"]+\"","message":"硬编码密码","suggestion":"使用环境变量"},
            {"id":"JAVA-LOCAL-004","severity":"info","pattern":"TODO|FIXME|HACK|XXX","message":"待处理标记","suggestion":"及时处理"},
            {"id":"JAVA-LOCAL-005","severity":"warning","pattern":"catch\\s*\\(\\s*Exception\\s","message":"异常捕获过宽","suggestion":"捕获具体异常类型"},
            {"id":"JAVA-LOCAL-006","severity":"info","pattern":"\\.printStackTrace\\s*\\(","message":"使用 printStackTrace","suggestion":"使用 SLF4J/Logback"},
            {"id":"JAVA-LOCAL-007","severity":"warning","pattern":"@CrossOrigin.*\"\\*\"","message":"CORS 允许所有来源","suggestion":"指定具体域名"},
            {"id":"JAVA-LOCAL-008","severity":"warning","pattern":"MD5|SHA1","message":"弱哈希算法","suggestion":"使用 SHA-256"},
            {"id":"JAVA-LOCAL-009","severity":"info","pattern":"System\\.out\\.print","message":"System.out 输出","suggestion":"使用日志框架"},
            {"id":"JAVA-LOCAL-010","severity":"warning","pattern":"api[_]?key\\s*=\\s*\"[^\"]+\"","message":"硬编码 API Key","suggestion":"使用配置中心"},
            {"id":"JAVA-LOCAL-011","severity":"warning","pattern":"Class\\.forName\\s*\\(","message":"动态类加载安全风险","suggestion":"白名单验证类名"},
        ]},
        "go": {"language":"go","version":"2.0.0","rules":[
            {"id":"GO-LOCAL-001","severity":"warning","pattern":"exec\\.Command\\s*\\(","message":"命令执行需验证输入","suggestion":"严格验证命令参数"},
            {"id":"GO-LOCAL-002","severity":"warning","pattern":"password\\s*[:=]\\s*\"[^\"]+\"","message":"硬编码密码","suggestion":"使用环境变量"},
            {"id":"GO-LOCAL-003","severity":"info","pattern":"TODO|FIXME|HACK|XXX","message":"待处理标记","suggestion":"及时处理"},
            {"id":"GO-LOCAL-004","severity":"info","pattern":"fmt\\.Print","message":"fmt.Print 输出","suggestion":"使用 log 包"},
            {"id":"GO-LOCAL-005","severity":"warning","pattern":"defer\\s+.*\\.Close\\(\\)","message":"defer Close() 忽略错误","suggestion":"处理 Close 返回的错误"},
        ]},
    }
    for lang, data in rules.items():
        with open(os.path.join(rules_dir, f"{lang}.json"), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

# ── 文件收集 ──
def collect_files(path, ignore_patterns=None):
    ignore_patterns = ignore_patterns or []
    files = {}
    for root, dirs, filenames in os.walk(path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith('.')]
        for pat in ignore_patterns:
            dirs[:] = [d for d in dirs if pat not in d]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            fp = os.path.join(root, fn)
            rp = os.path.relpath(fp, path)
            if any(p in rp for p in ignore_patterns):
                continue
            try:
                sz = os.path.getsize(fp)
                if sz > MAX_FILE_KB * 1024 or sz == 0:
                    continue
                with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                if content.strip():
                    files[rp] = content
            except Exception:
                continue
            if len(files) >= MAX_FILES:
                break
        if len(files) >= MAX_FILES:
            break
    return files

def collect_git_diff_files(path, base='main'):
    """增量扫描：只收集 git diff 变更的代码文件"""
    if not os.path.isdir(os.path.join(path, '.git')):
        return None, "不是 Git 仓库"
    try:
        r = subprocess.run(['git','diff','--name-only',base,'--diff-filter=ACMR'],
                           capture_output=True, text=True, cwd=path, timeout=30)
        if r.returncode != 0:
            r = subprocess.run(['git','diff','--name-only','HEAD~1','--diff-filter=ACMR'],
                               capture_output=True, text=True, cwd=path, timeout=30)
        if r.returncode != 0:
            return None, f"git diff 失败: {r.stderr.strip()}"
        changed = [f.strip() for f in r.stdout.strip().split('\n') if f.strip()]
        code_files = {}
        for fp in changed:
            ext = os.path.splitext(fp)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            full = os.path.join(path, fp)
            if not os.path.isfile(full):
                continue
            try:
                sz = os.path.getsize(full)
                if sz > MAX_FILE_KB * 1024 or sz == 0:
                    continue
                with open(full, 'r', encoding='utf-8', errors='ignore') as f:
                    code_files[fp] = f.read()
            except Exception:
                continue
        return code_files, f"基于 {base}，{len(changed)} 个变更文件，{len(code_files)} 个代码文件"
    except Exception as e:
        return None, str(e)

# ── 离线规则检查 ──
def run_local_rules(files, rules_dir):
    lang_map = {'.py':'python','.js':'javascript','.jsx':'javascript','.ts':'javascript',
                '.tsx':'javascript','.vue':'javascript','.java':'java','.go':'go'}
    cache = {}
    if os.path.isdir(rules_dir):
        for fn in os.listdir(rules_dir):
            if fn.endswith('.json'):
                lang = fn[:-5]
                with open(os.path.join(rules_dir, fn), 'r', encoding='utf-8') as f:
                    cache[lang] = json.load(f)
    issues = []
    for filepath, content in files.items():
        lang = lang_map.get(os.path.splitext(filepath)[1].lower())
        if not lang or lang not in cache:
            continue
        for rule in cache[lang].get('rules', []):
            pat = rule.get('pattern', '')
            if not pat:
                continue
            try:
                rx = re.compile(pat, re.IGNORECASE)
                for ln, line in enumerate(content.split('\n'), 1):
                    if rx.search(line):
                        issues.append({
                            'rule_id': rule['id'], 'severity': rule.get('severity','info'),
                            'title': rule.get('message',''), 'description': rule.get('message',''),
                            'file': filepath, 'line': ln, 'column': 0,
                            'code_snippet': line.strip()[:200],
                            'suggestion': rule.get('suggestion',''), 'engine': 'local',
                        })
            except re.error:
                continue
    return issues

# ── SARIF 输出 ──
def to_sarif(result, local_issues=None):
    issues = local_issues or []
    sev_map = {'critical':'error','P1':'error','high':'error','warning':'warning',
               'P2':'warning','P3':'warning','suspicious':'warning','correctness':'warning',
               'info':'note','P4':'note','low':'note','style':'note'}
    rules = {}
    results = []
    for i in issues:
        rid = i.get('rule_id', i.get('rule', 'UNKNOWN'))
        if rid not in rules:
            rules[rid] = {'id':rid,'name':i.get('title',rid),
                          'shortDescription':{'text':i.get('title',rid)},
                          'fullDescription':{'text':i.get('description','')}}
        sev = i.get('severity','info').lower()
        results.append({
            'ruleId': rid, 'level': sev_map.get(sev,'note'),
            'message': {'text': i.get('title', i.get('description',''))},
            'locations': [{'physicalLocation': {
                'artifactLocation': {'uri': i.get('file','unknown')},
                'region': {'startLine': i.get('line',1), 'startColumn': max(1, i.get('column',1))}
            }}],
        })
    return {
        '$schema': 'https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json',
        'version': '2.1.0',
        'runs': [{'tool': {'driver': {
            'name':'Xinpect','version':__version__,
            'informationUri':'https://xinpect.xingwangzhineng.com',
            'rules': list(rules.values())}},
            'results': results,
            'properties': {'score': result.get('score',0), 'scan_mode': result.get('scan_mode',''),
                           'file_count': result.get('file_count',0)}}]
    }

# ── API 调用 ──
def submit_scan(code_files, api_key, api_url, scan_mode, threshold,
                repo=None, branch=None, commit_sha=None):
    payload = json.dumps({
        'code_files': code_files, 'scan_mode': scan_mode,
        'threshold': threshold, 'repo': repo or '',
        'branch': branch or '', 'commit_sha': commit_sha or '',
    }).encode('utf-8')
    req = urllib.request.Request(f'{api_url}/api/ci/scan', data=payload,
        headers={'Content-Type':'application/json','X-API-Key':api_key,'X-Requested-With':'XMLHttpRequest'})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())

# ── 结果输出 ──
def print_result(result, fail_on_below=False, local_issues=None):
    score = result.get('score', 0)
    passed = result.get('passed', False)
    report_url = result.get('report_url', '')
    issues = result.get('issues', {})
    elapsed = result.get('elapsed', 0)
    file_count = result.get('file_count', 0)
    scan_mode = result.get('scan_mode', '')
    is_local = result.get('local_only', False)
    local_count = len(local_issues) if local_issues else 0

    print()
    print(colored("=" * 55, Colors.CYAN))
    title = "🔒 离线检查结果" if is_local else "🔍 代码扫描报告"
    print(colored(f"  煋鉴 Xinpect · {title}", Colors.BOLD))
    print(colored("=" * 55, Colors.CYAN))
    print()

    if score >= 80: sc, grade = Colors.GREEN, "优秀"
    elif score >= 60: sc, grade = Colors.YELLOW, "良好"
    elif score >= 40: sc, grade = Colors.YELLOW, "需改进"
    else: sc, grade = Colors.RED, "高风险"

    if not is_local:
        print(f"  质量评分:  {colored(f'{score}/100 ({grade})', sc)}")
        print(f"  扫描档位:  {scan_mode}")
        print(f"  扫描耗时:  {elapsed}s")
    print(f"  扫描文件:  {file_count} 个")
    if is_local:
        print(colored("  检查模式:  离线本地检查", Colors.DIM))
    print()

    total = issues.get('total',0) if not is_local else local_count
    critical = issues.get('critical',0) if not is_local else sum(1 for i in local_issues if i['severity'] in ('critical','high','P1'))
    warning = issues.get('warning',0) if not is_local else sum(1 for i in local_issues if i['severity'] in ('warning','P2','P3','suspicious'))
    info = issues.get('info',0) if not is_local else sum(1 for i in local_issues if i['severity'] in ('info','P4','low','style'))

    print(f"  问题统计:")
    print(f"    总计:     {total}")
    print(f"    严重:     {colored(str(critical), Colors.RED) if critical else critical}")
    print(f"    警告:     {colored(str(warning), Colors.YELLOW) if warning else warning}")
    print(f"    提示:     {info}")
    print()

    if not is_local:
        print(f"  门禁状态:  {colored('✅ 通过', Colors.GREEN) if passed else colored('❌ 未通过', Colors.RED)}")
    if report_url:
        print(f"  详细报告:  {report_url}")

    if local_issues:
        print()
        print(colored("  ── 问题详情（前20条） ──", Colors.BOLD))
        for i, iss in enumerate(local_issues[:20]):
            sev = iss.get('severity','info')
            sev_c = Colors.RED if sev in ('critical','high','P1') else (Colors.YELLOW if sev in ('warning','P2','P3','suspicious') else Colors.CYAN)
            print(f"  {colored(sev.upper(), sev_c):8s} {iss.get('rule_id',''):16s} {iss.get('title','')}")
            print(f"           📁 {iss.get('file','')}:{iss.get('line',0)}")
            if iss.get('suggestion'):
                print(f"           💡 {iss['suggestion']}")
            print()
        if len(local_issues) > 20:
            print(f"  ... 还有 {len(local_issues)-20} 个问题，用 --output json/sarif 查看完整列表")

    print()
    print(colored("=" * 55, Colors.CYAN))
    if fail_on_below and not passed:
        print(colored("  ⚠️  质量门禁未通过，CI 将失败", Colors.RED))
        return 1
    return 0

# ── 主入口 ──
def main():
    parser = argparse.ArgumentParser(description='煋鉴 Xinpect CLI v2.0')
    sub = parser.add_subparsers(dest='command')

    # init
    ip = sub.add_parser('init', help='初始化项目配置')
    ip.add_argument('--non-interactive', action='store_true')

    # scan
    sp = sub.add_parser('scan', help='扫描代码')
    sp.add_argument('--api-key', default=None)
    sp.add_argument('--api-url', default=None)
    sp.add_argument('--path', default=None)
    sp.add_argument('--mode', default=None, choices=['free','quick','smart','deep'])
    sp.add_argument('--threshold', type=int, default=None)
    sp.add_argument('--fail-on-below', action='store_true', default=None)
    sp.add_argument('--ignore', default=None)
    sp.add_argument('--output', default=None, choices=['text','json','sarif'])
    sp.add_argument('--incremental', action='store_true')
    sp.add_argument('--base', default='main')
    sp.add_argument('--local-only', action='store_true')
    sp.add_argument('--repo', default='')
    sp.add_argument('--branch', default='')
    sp.add_argument('--commit', default='')

    args = parser.parse_args()

    # 兼容旧版：无子命令时默认 scan
    if not args.command:
        args = parser.parse_args(['scan'] + sys.argv[1:])

    if args.command == 'init':
        cmd_init(args)
        return

    if args.command == 'scan':
        config = load_config()
        api_key = args.api_key or config.get('api_key','') or os.environ.get('XINPECT_API_KEY','')
        api_url = args.api_url or config.get('api_url','') or os.environ.get('XINPECT_API_URL', DEFAULT_API_URL)
        scan_path = os.path.abspath(args.path or config.get('scan_path','.'))
        scan_mode = args.mode or config.get('scan_mode','') or os.environ.get('XINPECT_SCAN_MODE','quick')
        threshold = args.threshold if args.threshold is not None else config.get('threshold', 60)
        fail_on_below = args.fail_on_below if args.fail_on_below is not None else config.get('fail_on_below', False)
        output_fmt = args.output or config.get('output_format','') or os.environ.get('XINPECT_OUTPUT','text')
        ignore_str = args.ignore or ','.join(config.get('ignore',[]))
        ignore_patterns = [p.strip() for p in ignore_str.split(',') if p.strip()]

        if not os.path.isdir(scan_path):
            print(colored(f"错误: 目录不存在: {scan_path}", Colors.RED))
            sys.exit(1)

        # ── 离线模式 ──
        if args.local_only:
            _log = print if output_fmt == "text" else lambda *a, **k: print(*a, file=sys.stderr, **k)
            _log(f"🔒 煋鉴离线检查")
            _log(f"   路径: {scan_path}")
            files = collect_files(scan_path, ignore_patterns)
            if not files:
                _log(colored("未找到代码文件", Colors.YELLOW))
                sys.exit(0)
            tl = sum(c.count('\n')+1 for c in files.values())
            _log(f"   文件: {len(files)} 个, {tl} 行")

            # 多路径查找规则目录
            cfg_path = find_config()
            if cfg_path:
                rules_dir = os.path.join(os.path.dirname(cfg_path), '.xinpect', 'rules')
            else:
                # 没配置文件，尝试扫描目录下或CLI安装目录
                rules_dir = os.path.join(scan_path, '.xinpect', 'rules')
                if not os.path.isdir(rules_dir):
                    cli_dir = os.path.dirname(os.path.abspath(__file__))
                    rules_dir = os.path.join(cli_dir, '.xinpect', 'rules')
                if not os.path.isdir(rules_dir):
                    # 最后兜底：临时创建内置规则
                    rules_dir = os.path.join(scan_path, '.xinpect', 'rules')
                    os.makedirs(rules_dir, exist_ok=True)
                    _write_builtin_rules(rules_dir)
            local_issues = run_local_rules(files, rules_dir)

            result = {
                'score': max(0, 100 - len(local_issues)*2),
                'passed': len([i for i in local_issues if i['severity'] in ('critical','high','P1')]) == 0,
                'issues': {'total':len(local_issues),
                           'critical':sum(1 for i in local_issues if i['severity'] in ('critical','high','P1')),
                           'warning':sum(1 for i in local_issues if i['severity'] in ('warning','P2','P3')),
                           'info':sum(1 for i in local_issues if i['severity'] in ('info','P4','low','style'))},
                'file_count':len(files), 'scan_mode':'local', 'local_only':True,
            }
            if output_fmt == 'json':
                result['issues_list'] = local_issues
                print(json.dumps(result, ensure_ascii=False, indent=2))
            elif output_fmt == 'sarif':
                print(json.dumps(to_sarif(result, local_issues), ensure_ascii=False, indent=2))
            else:
                sys.exit(print_result(result, fail_on_below, local_issues))
            return

        # ── 增量扫描 ──
        if args.incremental:
            print(f"📦 增量扫描")
            diff_files, msg = collect_git_diff_files(scan_path, args.base)
            if diff_files is None:
                print(colored(f"  ⚠️  {msg}，回退全量扫描", Colors.YELLOW))
                files = collect_files(scan_path, ignore_patterns)
            elif not diff_files:
                print(colored("  ✅ 无代码变更，跳过扫描", Colors.GREEN))
                sys.exit(0)
            else:
                print(f"  {msg}")
                files = diff_files
        else:
            print(f"🔍 煋鉴代码扫描")
            print(f"   路径: {scan_path}")
            print(f"   档位: {scan_mode} | 门禁: {threshold}")
            files = collect_files(scan_path, ignore_patterns)

        if not files:
            print(colored("未找到代码文件", Colors.YELLOW))
            sys.exit(0)

        tl = sum(c.count('\n')+1 for c in files.values())
        _log(f"   文件: {len(files)} 个, {tl} 行")
        print("   扫描中...")

        if not api_key:
            print(colored("错误: 需要 API Key", Colors.RED))
            print("  xinpect-cli.py init  或  export XINPECT_API_KEY=xxx")
            sys.exit(1)

        try:
            result = submit_scan(files, api_key, api_url, scan_mode, threshold,
                                 args.repo, args.branch, args.commit)
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8','replace')
            print(colored(f"\n失败: HTTP {e.code}", Colors.RED))
            try:
                err = json.loads(body)
                print(f"  {err.get('message', body)}")
            except:
                print(f"  {body[:500]}")
            sys.exit(1)
        except Exception as e:
            print(colored(f"\n失败: {e}", Colors.RED))
            sys.exit(1)

        if output_fmt == 'json':
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif output_fmt == 'sarif':
            print(json.dumps(to_sarif(result), ensure_ascii=False, indent=2))
        else:
            sys.exit(print_result(result, fail_on_below))

if __name__ == '__main__':
    main()
