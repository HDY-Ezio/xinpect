#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""煋鉴 Xinpect MCP Server / Xinpect MCP Server

把煋鉴的代码扫描能力接到 Claude Code / Cursor / Windsurf 等 MCP 客户端里。
纯 Python 标准库，不需要 pip install 任何东西，Python 3.8+ 直接跑。

用法（客户端配置里）：
    {
      "mcpServers": {
        "xinpect": {
          "command": "python3",
          "args": ["/绝对路径/xinpect_mcp_server.py"],
          "env": {"XINPECT_API_KEY": "xk_你的密钥"}
        }
      }
    }

环境变量 / Environment:
    XINPECT_API_KEY   必填 / required
    XINPECT_API_BASE  可选，默认 https://xinpect.xingwangzhineng.com
    XINPECT_LANG      输出语言 zh / en，默认 zh
"""

import fnmatch
import json
import os
import sys
import time
import urllib.error
import urllib.request

API_BASE = os.environ.get('XINPECT_API_BASE', 'https://xinpect.xingwangzhineng.com').rstrip('/')
API_KEY = (os.environ.get('XINPECT_API_KEY') or '').strip()
LANG = (os.environ.get('XINPECT_LANG') or 'zh').strip().lower()[:2]
if LANG not in ('zh', 'en'):
    LANG = 'zh'

PROTOCOL_VERSION = '2024-11-05'
SERVER_NAME = 'xinpect'
SERVER_VERSION = '1.1.0'

MAX_FILES = 500
MAX_BYTES = 10 * 1024 * 1024
MAX_FILE_BYTES = 2 * 1024 * 1024
POLL_INTERVAL = 5
POLL_TIMEOUT = 1800

SKIP_DIRS = {
    '.git', '.svn', '.hg', 'node_modules', '__pycache__', '.venv', 'venv', 'env',
    'dist', 'build', 'target', 'vendor', '.idea', '.vscode', '.next', '.nuxt',
    'coverage', '.pytest_cache', '.mypy_cache', 'bower_components',
}

EXT_LANG = {
    '.py': 'python', '.pyw': 'python',
    '.js': 'javascript', '.jsx': 'javascript', '.mjs': 'javascript', '.cjs': 'javascript',
    '.ts': 'typescript', '.tsx': 'typescript',
    '.java': 'java', '.go': 'go', '.php': 'php', '.rb': 'ruby',
    '.c': 'c', '.h': 'c', '.cc': 'cpp', '.cpp': 'cpp', '.cxx': 'cpp', '.hpp': 'cpp',
    '.rs': 'rust', '.cs': 'csharp', '.kt': 'kotlin', '.swift': 'swift',
    '.vue': 'vue', '.sql': 'sql',
}

SEV_ORDER = ['blocker', 'critical', 'high', 'medium', 'low', 'info']

MSG = {
    'zh': {
        'sev': {'blocker': '致命', 'critical': '严重', 'high': '高危',
                'medium': '中等', 'low': '低', 'info': '提示'},
        'done': '煋鉴扫描完成 · %s 分 %s 级',
        'meta': '文件 %d 个 / %d 行 / 用时 %.1f 秒',
        'issues': '问题 %d 条',
        'clean': '这套规则下没查出问题。注意这是已知规则的初筛，不等于代码绝对干净。',
        'more': '…… 还有 %d 条同类，完整清单看后台扫描报告',
        'rule': '规则 %s',
        'tool_code': ('扫描一段代码里的安全漏洞、质量缺陷、性能问题，返回评分和问题清单。'
                      '用户说「帮我检查这段代码」「这段有没有安全问题」「审一下这个函数」时调用。'
                      '注意：只检查你传进来的代码，不读本地文件。'),
        'tool_files': '一次扫描多个文件，适合用户已经贴了多段代码，或者你从对话里整理了多个文件的情况。',
        'tool_path': ('扫描本地目录或单个文件（在本机读取，整包上传给煋鉴分析）。'
                      '用户说「扫一下这个项目」「检查我的 src 目录」时调用。'
                      '会自动跳过 node_modules、.git、venv、dist 这类目录；单次上限 500 个文件 / 10MB。'),
    },
    'en': {
        'sev': {'blocker': 'blocker', 'critical': 'critical', 'high': 'high',
                'medium': 'medium', 'low': 'low', 'info': 'info'},
        'done': 'Xinpect scan finished · %s/100 · grade %s',
        'meta': '%d files / %d lines / %.1fs',
        'issues': '%d issues',
        'clean': 'No issues found by the current rule set. This is a first-pass check against known rules, not a guarantee the code is clean.',
        'more': '... %d more of the same kind; open the dashboard report for the full list',
        'rule': 'rule %s',
        'tool_code': ('Scan a code snippet for security vulnerabilities, quality defects and performance issues. '
                      'Returns a score plus an issue list. Use when the user says things like '
                      '"check this code", "is this safe", "review this function". '
                      'Only scans the code you pass in; it does not read local files.'),
        'tool_files': 'Scan multiple files in one request. Use when the user pasted several files or you have assembled them from the conversation.',
        'tool_path': ('Scan a local directory or a single file (read on this machine, uploaded as a whole for analysis). '
                      'Use when the user says "scan this project" or "check my src folder". '
                      'Skips node_modules, .git, venv, dist automatically; up to 500 files / 10MB per call.'),
    },
}


def m(key):
    return MSG[LANG].get(key) or MSG['zh'][key]


def log(msg):
    """日志只能走 stderr —— stdout 是 JSON-RPC 通道，混进一个字符客户端就崩。"""
    sys.stderr.write('[xinpect] %s\n' % msg)
    sys.stderr.flush()


class ApiError(Exception):
    def __init__(self, message, hint=''):
        Exception.__init__(self, message)
        self.hint = hint


def http_json(method, path, body=None, timeout=300):
    url = path if path.startswith('http') else API_BASE + path
    data = None
    headers = {'X-API-Key': API_KEY, 'User-Agent': 'xinpect-mcp/%s' % SERVER_VERSION}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', 'replace')
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {'error': raw[:300]}
        msg = payload.get('error') or payload.get('message') or ('HTTP %d' % e.code)
        if e.code == 401:
            if LANG == 'en':
                raise ApiError('Invalid or disabled API key',
                               'Copy a fresh xk_ key from the dashboard and set XINPECT_API_KEY.')
            raise ApiError('密钥无效或已停用', '到后台「扫描密钥」页重新复制一个，填进 XINPECT_API_KEY。')
        if e.code == 402:
            if LANG == 'en':
                raise ApiError('Not enough credits: %s' % msg, 'Top up in the dashboard and retry.')
            raise ApiError('积分不足：%s' % msg, '到后台充值后再试。')
        if e.code == 429:
            raise ApiError('Too many requests: %s' % msg if LANG == 'en' else '请求太频繁：%s' % msg,
                           'Wait a minute and retry.' if LANG == 'en' else '等一分钟再试。')
        if e.code == 413:
            if LANG == 'en':
                raise ApiError('Payload too large: %s' % msg, 'Narrow the scope or split the scan.')
            raise ApiError('提交内容超限：%s' % msg, '缩小扫描范围，或分批提交。')
        raise ApiError(str(msg), 'HTTP %d' % e.code)
    except urllib.error.URLError as e:
        if LANG == 'en':
            raise ApiError('Cannot reach the Xinpect server',
                           'Check your network, and confirm XINPECT_API_BASE (currently %s). Reason: %s'
                           % (API_BASE, e.reason))
        raise ApiError('连不上煋鉴服务器', '检查网络；或者确认 XINPECT_API_BASE 填对了（当前 %s）。原因：%s' % (API_BASE, e.reason))


def poll_until_done(payload):
    """大项目会返回 queued/processing，得轮着问，直到出结果。"""
    status = str(payload.get('status') or '').lower()
    poll_url = payload.get('poll_url')
    if status not in ('queued', 'processing', 'pending') or not poll_url:
        return payload

    started = time.time()
    last_note = ''
    while time.time() - started < POLL_TIMEOUT:
        time.sleep(POLL_INTERVAL)
        cur = http_json('GET', poll_url, timeout=120)
        status = str(cur.get('status') or '').lower()
        if status == 'completed':
            return cur
        if status == 'failed':
            reason = cur.get('error') or ('unknown' if LANG == 'en' else '未知原因')
            if LANG == 'en':
                raise ApiError('Scan failed: %s' % reason, 'Credits for this run were refunded.')
            raise ApiError('扫描失败：%s' % reason, '本次积分已自动退还。')
        note = cur.get('progress_text') or ''
        if note and note != last_note:
            last_note = note
            log('%s%% %s' % (cur.get('progress', '?'), note))
    if LANG == 'en':
        raise ApiError('No result after %d seconds' % POLL_TIMEOUT,
                       'The job may still be running; check Scan history in the dashboard later.')
    raise ApiError('等了 %d 秒还没出结果' % POLL_TIMEOUT,
                   '任务可能还在跑，稍后到后台「扫描历史」看结果。')


def guess_language(path):
    return EXT_LANG.get(os.path.splitext(path)[1].lower(), 'auto')


def collect_dir(root, pattern=None):
    root = os.path.abspath(os.path.expanduser(root))
    if not os.path.isdir(root):
        if LANG == 'en':
            raise ApiError('Directory not found: %s' % root, 'Pass an absolute path, or a path relative to the current directory.')
        raise ApiError('目录不存在：%s' % root, '传绝对路径，或者传当前项目根目录。')

    files = {}
    total = 0
    skipped_big = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith('.')]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() not in EXT_LANG:
                continue
            if pattern and not fnmatch.fnmatch(fn, pattern):
                continue
            full = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(full)
                if size > MAX_FILE_BYTES:
                    skipped_big += 1
                    continue
                with open(full, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
            except Exception:
                continue
            if not content.strip():
                continue
            total += len(content.encode('utf-8'))
            if total > MAX_BYTES:
                if LANG == 'en':
                    raise ApiError('Code exceeds 10MB', 'Narrow to a subdirectory, e.g. only src/ or services/.')
                raise ApiError('代码总量超过 10MB', '缩小到单个子目录，比如只扫 src/ 或 services/。')
            if len(files) >= MAX_FILES:
                if LANG == 'en':
                    raise ApiError('More than %d files' % MAX_FILES,
                                   'Use the pattern argument to limit file types, e.g. "*.py", or scan a subdirectory.')
                raise ApiError('文件数超过 %d 个' % MAX_FILES,
                               '加 pattern 参数只扫某类文件，比如 "*.py"，或者只扫子目录。')
            files[os.path.relpath(full, root).replace(os.sep, '/')] = content

    if skipped_big:
        log('skip %d files over 2MB' % skipped_big if LANG == 'en' else '跳过 %d 个超过 2MB 的文件' % skipped_big)
    if not files:
        if LANG == 'en':
            raise ApiError('No scannable source files in this directory',
                           'Supported extensions include: ' + ', '.join(sorted(EXT_LANG)[:14]))
        raise ApiError('这个目录里没找到可扫描的代码文件', '支持的扩展名：' + ', '.join(sorted(EXT_LANG)[:14]) + ' 等。')
    return files


def run_scan(code_files, language='auto'):
    payload = http_json('POST', '/api/v1/scan',
                        {'code_files': code_files, 'language': language}, timeout=600)
    return poll_until_done(payload)


def render(result, files_scanned, lines, seconds):
    issues = result.get('issues') or []
    score = result.get('score')
    grade = result.get('grade') or ''
    counts = {}
    for it in issues:
        sev = str(it.get('severity') or 'low').lower()
        counts[sev] = counts.get(sev, 0) + 1

    sev_label = MSG[LANG]['sev']
    out = []
    out.append(m('done') % (score if score is not None else '?', grade))
    out.append(m('meta') % (files_scanned, lines, seconds))
    dist = ' · '.join('%s %d' % (sev_label[k], counts[k]) for k in SEV_ORDER if counts.get(k))
    if dist:
        out.append(m('issues') % len(issues) + (': ' if LANG == 'en' else '：') + dist)
    else:
        out.append(m('issues') % len(issues))

    if not issues:
        out.append('')
        out.append(m('clean'))
        return '\n'.join(out)

    for sev in SEV_ORDER:
        group = [i for i in issues if str(i.get('severity') or 'low').lower() == sev]
        if not group:
            continue
        out.append('')
        out.append('[%s] %d' % (sev_label[sev], len(group)) if LANG == 'en'
                   else '【%s】%d 条' % (sev_label[sev], len(group)))
        for it in group[:12]:
            loc = '%s:%s' % (it.get('file') or '?', it.get('line') or '?')
            out.append('- %s  %s' % (it.get('name') or it.get('check_id') or 'issue', loc))
            msg = (it.get('message') or '').strip()
            if msg:
                out.append('  ' + msg.replace('\n', ' ')[:220])
            rule = it.get('check_id')
            if rule:
                out.append('  ' + (m('rule') % rule))
        if len(group) > 12:
            out.append('  ' + (m('more') % (len(group) - 12)))
    return '\n'.join(out)


def tool_scan_code(args):
    code = args.get('code') or ''
    if not code.strip():
        if LANG == 'en':
            raise ApiError('code is empty', 'Put the code to check into the code argument.')
        raise ApiError('code 是空的', '把要检查的代码放进 code 参数。')
    filename = args.get('filename') or 'snippet%s' % {
        'python': '.py', 'javascript': '.js', 'typescript': '.ts', 'java': '.java',
        'go': '.go', 'php': '.php', 'ruby': '.rb', 'c': '.c', 'cpp': '.cpp', 'rust': '.rs',
    }.get(args.get('language') or 'python', '.py')
    language = args.get('language') or guess_language(filename)

    t0 = time.time()
    result = run_scan({filename: code}, language)
    lines = sum(1 for ln in code.split('\n') if ln.strip())
    return render(result, 1, lines, time.time() - t0)


def tool_scan_files(args):
    raw = args.get('files') or []
    if not isinstance(raw, list) or not raw:
        if LANG == 'en':
            raise ApiError('files is empty', 'Pass a list: [{"path": "a.py", "content": "..."}]')
        raise ApiError('files 是空的', '传一个列表：[{"path": "a.py", "content": "..."}]')
    code_files = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        path = item.get('path') or item.get('filename')
        content = item.get('content')
        if not path or not isinstance(content, str):
            continue
        code_files[path] = content
    if not code_files:
        if LANG == 'en':
            raise ApiError('No usable entries', 'Each entry needs both path and content.')
        raise ApiError('没有可用的文件项', '每项要有 path 和 content 两个字段。')
    if len(code_files) > MAX_FILES:
        raise ApiError('Too many files: %d' % len(code_files) if LANG == 'en'
                       else '文件超过 %d 个' % MAX_FILES,
                       'Split into batches.' if LANG == 'en' else '分批提交。')

    language = args.get('language') or 'auto'
    t0 = time.time()
    result = run_scan(code_files, language)
    lines = sum(sum(1 for ln in c.split('\n') if ln.strip()) for c in code_files.values())
    return render(result, len(code_files), lines, time.time() - t0)


def tool_scan_path(args):
    path = args.get('path') or '.'
    pattern = args.get('pattern') or None
    code_files = collect_dir(path, pattern)
    language = args.get('language') or 'auto'
    log('collected %d files, scanning' % len(code_files) if LANG == 'en'
        else '收集到 %d 个文件，开始扫描' % len(code_files))
    t0 = time.time()
    result = run_scan(code_files, language)
    lines = sum(sum(1 for ln in c.split('\n') if ln.strip()) for c in code_files.values())
    return render(result, len(code_files), lines, time.time() - t0)


def build_tools():
    code_props = {
        'code': {'type': 'string', 'description': 'Code to check' if LANG == 'en' else '要检查的代码内容'},
        'filename': {'type': 'string',
                     'description': 'File name with extension, used to infer language, e.g. app.py'
                     if LANG == 'en' else '文件名（含扩展名），用来判断语言，例如 app.py'},
        'language': {'type': 'string',
                     'description': 'Language: python/javascript/typescript/java/go/php/ruby/c/cpp/rust'
                     if LANG == 'en' else '语言，可选：python/javascript/typescript/java/go/php/ruby/c/cpp/rust'},
    }
    return [
        {
            'name': 'scan_code',
            'description': m('tool_code'),
            'inputSchema': {'type': 'object', 'properties': code_props, 'required': ['code']},
        },
        {
            'name': 'scan_files',
            'description': m('tool_files'),
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'files': {
                        'type': 'array',
                        'description': 'Files' if LANG == 'en' else '文件列表',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'path': {'type': 'string',
                                         'description': 'Relative path, e.g. src/app.py'
                                         if LANG == 'en' else '相对路径，例如 src/app.py'},
                                'content': {'type': 'string',
                                            'description': 'File content' if LANG == 'en' else '文件内容'},
                            },
                            'required': ['path', 'content'],
                        },
                    },
                    'language': {'type': 'string',
                                 'description': 'Force one language; leave empty to auto-detect'
                                 if LANG == 'en' else '统一指定语言；留空自动判断'},
                },
                'required': ['files'],
            },
        },
        {
            'name': 'scan_path',
            'description': m('tool_path'),
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string',
                             'description': 'Absolute path, or a path relative to the current directory; defaults to .'
                             if LANG == 'en' else '绝对路径或相对当前目录的路径，默认 .'},
                    'pattern': {'type': 'string',
                                'description': 'Only scan file names matching this, e.g. "*.py"; optional'
                                if LANG == 'en' else '只扫匹配的文件名，例如 "*.py"，可选'},
                    'language': {'type': 'string',
                                 'description': 'Force one language; leave empty to auto-detect'
                                 if LANG == 'en' else '统一指定语言；留空自动判断'},
                },
                'required': [],
            },
        },
    ]


TOOL_HANDLERS = {
    'scan_code': tool_scan_code,
    'scan_files': tool_scan_files,
    'scan_path': tool_scan_path,
}


def rpc_ok(mid, result):
    return {'jsonrpc': '2.0', 'id': mid, 'result': result}


def rpc_err(mid, code, message):
    return {'jsonrpc': '2.0', 'id': mid, 'error': {'code': code, 'message': message}}


def handle(req):
    mid = req.get('id')
    method = req.get('method') or ''
    params = req.get('params') or {}

    if method == 'initialize':
        return rpc_ok(mid, {
            'protocolVersion': PROTOCOL_VERSION,
            'capabilities': {'tools': {}},
            'serverInfo': {'name': SERVER_NAME, 'version': SERVER_VERSION},
        })

    if method == 'tools/list':
        return rpc_ok(mid, {'tools': build_tools()})

    if method == 'tools/call':
        name = params.get('name')
        args = params.get('arguments') or {}
        handler = TOOL_HANDLERS.get(name)
        if not handler:
            return rpc_err(mid, -32602, 'Unknown tool: %s' % name if LANG == 'en' else '未知工具：%s' % name)
        if not API_KEY:
            text = ('No API key configured. Put the xk_ key from the dashboard into '
                    'env.XINPECT_API_KEY and restart the client.') if LANG == 'en' else (
                    '没配置密钥。把后台「扫描密钥」页的 xk_ 开头的字符串填进 MCP 配置的 '
                    'env.XINPECT_API_KEY，然后重启客户端。')
            return rpc_ok(mid, {'content': [{'type': 'text', 'text': text}], 'isError': True})
        try:
            text = handler(args)
            return rpc_ok(mid, {'content': [{'type': 'text', 'text': text}]})
        except ApiError as e:
            msg = str(e)
            if e.hint:
                msg = '%s\n%s' % (msg, e.hint)
            return rpc_ok(mid, {'content': [{'type': 'text', 'text': msg}], 'isError': True})
        except Exception as e:
            log('tool %s raised %r' % (name, e))
            return rpc_ok(mid, {'content': [{'type': 'text', 'text':
                                             ('Internal error: %s' % e) if LANG == 'en'
                                             else ('内部错误：%s' % e)}], 'isError': True})

    if method in ('notifications/initialized', 'notifications/cancelled'):
        return None

    if method == 'ping':
        return rpc_ok(mid, {})

    if mid is None:
        return None
    return rpc_err(mid, -32601, 'Unsupported method: %s' % method if LANG == 'en' else '不支持的方法：%s' % method)


def main():
    if not API_KEY:
        log('warning: XINPECT_API_KEY not set' if LANG == 'en' else '警告：没有设置 XINPECT_API_KEY，调用工具时会提示配置。')
    log('ready (lang=%s, api=%s)' % (LANG, API_BASE))

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            log('ignored non-JSON input: %s' % line[:120])
            continue

        try:
            resp = handle(req)
        except Exception as e:
            log('request handling raised %r' % e)
            resp = rpc_err(req.get('id'), -32603, 'internal error')

        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + '\n')
            sys.stdout.flush()


if __name__ == '__main__':
    main()
