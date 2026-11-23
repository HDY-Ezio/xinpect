#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
煋鉴 Xinpect CLI - 代码质检命令行工具
用法:
  xinpect init              交互式初始化，生成 .xinpect.yml
  xinpect scan .            扫描当前目录
  xinpect scan --diff       增量扫描（只扫 git diff）
  xinpect watch .           边写边扫（保存即自动增量重扫）
  xinpect fix .             自动修复确定性安全问题（可选开 PR）
  xinpect status            查看账户状态
  xinpect rules update      更新本地规则缓存
  xinpect rules list        列出已缓存规则
  xinpect --version         版本号
"""

import argparse
import json
import os
import sys
import time
import hashlib
import subprocess
import fnmatch
import io
from datetime import datetime

try:
    from urllib.request import Request, urlopen
    from urllib.error import URLError, HTTPError
    from urllib.parse import urljoin
except ImportError:
    print("错误: 需要 Python 3.6+")
    sys.exit(1)

VERSION = "1.0.0"
DEFAULT_SERVER = "https://xinpect.xingwangzhineng.com"
CONFIG_FILENAME = ".xinpect.yml"
RULES_CACHE_DIR = os.path.expanduser("~/.xinpect/rules")
RULES_INDEX_FILE = os.path.join(RULES_CACHE_DIR, "index.json")

# ANSI 颜色码
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"
    ORANGE = "\033[38;5;208m"

# 严重级别到优先级的映射
PRIORITY_MAP = {
    "critical": "P0",
    "blocker": "P0",
    "high": "P1",
    "suspicious": "P1",
    "medium": "P2",
    "correctness": "P2",
    "restriction": "P2",
    "warning": "P2",
    "low": "P3",
    "style": "P3",
    "info": "P3",
    "minor": "P3",
}

SEVERITY_ICONS = {
    "P0": f"{C.RED}●{C.RESET}",
    "P1": f"{C.ORANGE}●{C.RESET}",
    "P2": f"{C.YELLOW}●{C.RESET}",
    "P3": f"{C.BLUE}●{C.RESET}",
}

SEVERITY_LABELS = {
    "P0": "严重",
    "P1": "高危",
    "P2": "中危",
    "P3": "低危",
}

# 代码文件扩展名
CODE_EXTS = {
    '.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.go', '.cpp', '.c',
    '.h', '.cs', '.php', '.rb', '.rs', '.swift', '.kt', '.wxml', '.wxss',
    '.vue', '.html', '.htm', '.scss', '.less', '.css', '.sass',
    '.json', '.yaml', '.yml', '.toml', '.ini', '.sh', '.bash',
    '.zsh', '.ps1', '.bat', '.sql', '.xml', '.md', '.txt',
    '.lua', '.r', '.scala', '.dart', '.elm', '.erl', '.ex', '.exs',
    '.hs', '.clj', '.jl', '.m', '.pl', '.pm',
}

# 默认忽略模式
DEFAULT_IGNORE = [".git", "node_modules", "__pycache__", "*.min.js", "vendor", "dist", "build"]

# 离线规则定义（基础 E1语法 + E2安全 + E4质量）
OFFLINE_RULES = [
    {
        "id": "XIN-E1-001",
        "brain_id": "1",
        "brain_name": "语法格式",
        "title": "TODO/FIXME/HACK 标记",
        "severity": "info",
        "pattern": r"(?:TODO|FIXME|HACK|XXX)\s*:?.*",
        "description": "代码中存在待处理标记",
        "suggestion": "及时清理 TODO/FIXME 标记，避免遗留技术债务",
    },
    {
        "id": "XIN-E1-002",
        "brain_id": "1",
        "brain_name": "语法格式",
        "title": "过长行（>120字符）",
        "severity": "style",
        "pattern": r".{121,}",
        "description": "代码行超过120字符，影响可读性",
        "suggestion": "将长行拆分为多行，保持每行不超过120字符",
    },
    {
        "id": "XIN-E2-001",
        "brain_id": "2",
        "brain_name": "安全与依赖审计",
        "title": "硬编码密钥/密码",
        "severity": "critical",
        "pattern": r"""(?i)(?:password|passwd|secret|api_key|apikey|token|access_key)\s*[=:]\s*['"][^'"]{8,}['"]""",
        "description": "疑似硬编码的密钥或密码，存在泄露风险",
        "suggestion": "使用环境变量 os.environ.get('API_KEY') 或配置文件管理敏感信息",
    },
    {
        "id": "XIN-E2-002",
        "brain_id": "2",
        "brain_name": "安全与依赖审计",
        "title": "SQL拼接注入风险",
        "severity": "critical",
        "pattern": r"""(?:execute|query|raw)\s*\(\s*["'].*%s.*["']\s*%|f["'].*SELECT.*\{|f["'].*INSERT.*\{|f["'].*UPDATE.*\{|f["'].*DELETE.*\{""",
        "description": "用户输入直接拼接到SQL语句中，存在注入风险",
        "suggestion": '使用参数化查询: db.execute("SELECT * FROM users WHERE id = ?", (user_id,))',
    },
    {
        "id": "XIN-E2-003",
        "brain_id": "2",
        "brain_name": "安全与依赖审计",
        "title": "eval/exec 危险函数调用",
        "severity": "critical",
        "pattern": r"\beval\s*\(|\bexec\s*\(",
        "description": "eval/exec 可执行任意代码，存在严重安全风险",
        "suggestion": "避免使用 eval/exec，改用 ast.literal_eval 或显式解析逻辑",
    },
    {
        "id": "XIN-E2-004",
        "brain_id": "2",
        "brain_name": "安全与依赖审计",
        "title": "调试模式未关闭",
        "severity": "high",
        "pattern": r"""(?:DEBUG|debug)\s*[=:]\s*(?:True|true|1|["']on["'])""",
        "description": "生产代码中不应开启调试模式",
        "suggestion": "将 DEBUG 设置为 False，或通过环境变量控制",
    },
    {
        "id": "XIN-E4-001",
        "brain_id": "6",
        "brain_name": "代码质量与测试",
        "title": "过长函数（>50行）",
        "severity": "medium",
        "pattern": r"(?:def|function|async\s+function)\s+\w+\s*\([^)]*\)\s*(?::\s*\w+\s*)?\{",
        "description": "函数定义检测到，请检查函数长度是否超过50行",
        "suggestion": "将长函数拆分为更小的、职责单一的函数",
    },
    {
        "id": "XIN-E4-002",
        "brain_id": "6",
        "brain_name": "代码质量与测试",
        "title": "空的 except 块",
        "severity": "high",
        "pattern": r"except\s*(?:Exception)?\s*:\s*\n\s*(?:pass|return\s*$)",
        "description": "空的异常捕获块会静默吞掉错误",
        "suggestion": "至少记录日志 logger.exception('...')，或捕获具体异常类型",
    },
    {
        "id": "XIN-E4-003",
        "brain_id": "6",
        "brain_name": "代码质量与测试",
        "title": "print 调试语句",
        "severity": "low",
        "pattern": r"^\s*print\s*\(",
        "description": "生产代码中不应使用 print 调试",
        "suggestion": "使用 logging 模块替代 print: import logging; logger = logging.getLogger(__name__)",
    },
    {
        "id": "XIN-E4-004",
        "brain_id": "6",
        "brain_name": "代码质量与测试",
        "title": "魔数（硬编码数字）",
        "severity": "low",
        "pattern": r"""(?<![\w.])(?:if|return|==|!=|>=|<=|>|<)\s*(?:[2-9]\d{2,}|[1-9]\d{3,})(?![\w.])""",
        "description": "代码中存在硬编码的数字常量（魔数）",
        "suggestion": "将魔数提取为命名常量: MAX_RETRY_COUNT = 3",
    },
]


# ============================================================
# 工具函数
# ============================================================

def _http_request(url, method="GET", data=None, headers=None, timeout=60):
    """发送 HTTP 请求，返回 (status_code, response_data)"""
    if headers is None:
        headers = {}
    
    if data is not None:
        if isinstance(data, dict):
            data = json.dumps(data, ensure_ascii=False).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        elif isinstance(data, str):
            data = data.encode("utf-8")
    
    req = Request(url, data=data, headers=headers, method=method)
    try:
        resp = urlopen(req, timeout=timeout)
        body = resp.read().decode("utf-8")
        try:
            return resp.status, json.loads(body)
        except json.JSONDecodeError:
            return resp.status, body
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body)
        except (json.JSONDecodeError, ValueError):
            return e.code, body
    except URLError as e:
        return 0, {"error": f"网络连接失败: {e.reason}"}
    except Exception as e:
        return 0, {"error": str(e)}


def _load_config(search_dir=None):
    """查找并加载 .xinpect.yml 配置"""
    if search_dir is None:
        search_dir = os.getcwd()
    
    # 向上查找配置文件
    current = os.path.abspath(search_dir)
    while True:
        config_path = os.path.join(current, CONFIG_FILENAME)
        if os.path.exists(config_path):
            return _parse_yaml_simple(config_path), current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    
    return None, None


def _parse_yaml_simple(filepath):
    """简单 YAML 解析器（不依赖 PyYAML，仅支持基本键值对和列表）"""
    config = {}
    current_list_key = None
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                
                # 列表项
                if stripped.startswith("- "):
                    if current_list_key:
                        val = stripped[2:].strip().strip('"').strip("'")
                        config.setdefault(current_list_key, []).append(val)
                    continue
                
                current_list_key = None
                
                # 键值对
                if ":" in stripped:
                    key, _, value = stripped.partition(":")
                    key = key.strip()
                    value = value.strip()
                    
                    if not value:
                        # 可能是嵌套键或列表开始
                        current_list_key = key
                        continue
                    
                    # 去掉引号
                    value = value.strip('"').strip("'")
                    
                    # 类型转换
                    if value.lower() == "true":
                        config[key] = True
                    elif value.lower() == "false":
                        config[key] = False
                    elif value.isdigit():
                        config[key] = int(value)
                    else:
                        # 处理带注释的值
                        if "  #" in value or "\t#" in value:
                            value = value.split("#")[0].strip().strip('"').strip("'")
                        # 处理 | 分隔的选项提示
                        if "|" in value:
                            value = value.split("|")[0].strip()
                        config[key] = value
    except Exception as e:
        print(f"{C.RED}配置文件解析失败: {e}{C.RESET}")
        return {}
    
    return config


def _collect_files(root_dir, ignore_patterns=None):
    """收集代码文件，根据 ignore 规则过滤"""
    if ignore_patterns is None:
        ignore_patterns = DEFAULT_IGNORE
    
    files = []
    root_dir = os.path.abspath(root_dir)
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # 过滤目录
        rel_dir = os.path.relpath(dirpath, root_dir)
        skip = False
        for pattern in ignore_patterns:
            if fnmatch.fnmatch(rel_dir, pattern) or fnmatch.fnmatch(os.path.basename(dirpath), pattern):
                skip = True
                break
        if skip:
            dirnames.clear()
            continue
        
        # 移除被忽略的子目录
        dirnames[:] = [
            d for d in dirnames
            if not any(fnmatch.fnmatch(d, p) for p in ignore_patterns)
        ]
        
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in CODE_EXTS:
                continue
            if any(fnmatch.fnmatch(fname, p) for p in ignore_patterns):
                continue
            
            filepath = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(filepath, root_dir)
            files.append((rel_path, filepath))
    
    return files


def _get_git_diff_files(root_dir):
    """获取 git diff 涉及的文件列表"""
    try:
        # 获取已修改和新增的文件
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=root_dir, capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            # 尝试获取未暂存的 diff
            result = subprocess.run(
                ["git", "diff", "--name-only"],
                cwd=root_dir, capture_output=True, text=True, timeout=10
            )
        
        if result.returncode == 0 and result.stdout.strip():
            return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        
        # 如果上面都不行，尝试 staged 文件
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=root_dir, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    return []


def _read_file_safe(filepath, max_size=50000):
    """安全读取文件内容"""
    try:
        size = os.path.getsize(filepath)
        if size > max_size:
            return None  # 跳过过大的文件
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except (IOError, OSError):
        return None


def _detect_language(files):
    """根据文件扩展名检测主要语言"""
    ext_counts = {}
    ext_to_lang = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".tsx": "typescript", ".jsx": "javascript", ".java": "java",
        ".go": "go", ".cpp": "cpp", ".c": "c", ".cs": "csharp",
        ".php": "php", ".rb": "ruby", ".rs": "rust", ".swift": "swift",
        ".kt": "kotlin", ".vue": "vue", ".html": "html", ".wxml": "miniprogram",
    }
    
    for rel_path, _ in files:
        ext = os.path.splitext(rel_path)[1].lower()
        lang = ext_to_lang.get(ext)
        if lang:
            ext_counts[lang] = ext_counts.get(lang, 0) + 1
    
    if ext_counts:
        return max(ext_counts, key=ext_counts.get)
    return "auto"


def _snapshot_files(scan_dir, ignore_patterns):
    """对扫描目录做内容快照：{相对路径: 内容sha1}，用于 watch 检测变更。

    与 git diff 无关——直接按文件内容哈希追踪，任何「保存」动作（含未 git add 的
    未暂存改动）都能被捕获，这才符合「边写边扫」的真实场景（开发者打字保存，
    不会每敲一下就 git add）。
    """
    snap = {}
    for rel_path, filepath in _collect_files(scan_dir, ignore_patterns):
        content = _read_file_safe(filepath)
        if content is not None:
            snap[rel_path] = hashlib.sha1(content.encode("utf-8")).hexdigest()
    return snap


def _diff_snapshots(old_snap, new_snap):
    """对比两次快照，返回新增/修改/删除的文件相对路径列表"""
    changed = []
    for path in set(old_snap) | set(new_snap):
        if old_snap.get(path) != new_snap.get(path):
            changed.append(path)
    return changed


def _scan_subset(scan_dir, changed_rel_paths, ignore_patterns, config, args):
    """只扫描发生变化的文件子集（watch 增量扫描核心）。

    复用 cmd_scan 的在线/离线扫描链路，但只把「变化文件」放进 code_files，
    避免 watch 场景下每次保存都全量扫描消耗积分。
    """
    all_files = _collect_files(scan_dir, ignore_patterns)
    files = [(rel, full) for rel, full in all_files if rel in set(changed_rel_paths)]
    if not files:
        return None

    code_files = {}
    for rel_path, filepath in files:
        content = _read_file_safe(filepath)
        if content is not None:
            code_files[rel_path] = content
    if not code_files:
        return None

    language = _detect_language(files)
    api_key = config.get("api_key", "")
    server = config.get("server", DEFAULT_SERVER)
    scan_mode = config.get("scan_mode", "quick")

    use_online = bool(api_key and not args.offline)
    result = None
    if use_online:
        result = _online_scan(code_files, api_key, server, language, scan_mode)
    if result is None:
        result = _offline_scan(code_files)
    return result


def cmd_watch(args):
    """watch 命令：监听目录文件变化，防抖后增量重扫（边写边扫）。

    首次全量扫一遍，之后轮询文件内容哈希，发现变化→防抖 1.5s→只扫变更文件。
    Ctrl+C 退出。默认走在线 API（增量只扫变化文件，积分消耗可控）；
    可用 --offline 走本地规则。
    """
    config, config_dir = _load_config()
    if config is None:
        print(f"{C.RED}❌ 未找到 {CONFIG_FILENAME} 配置文件{C.RESET}")
        print(f"   运行 {C.BOLD}xinpect init{C.RESET} 进行初始化")
        return 1

    ignore_patterns = config.get("ignore", DEFAULT_IGNORE)
    if isinstance(ignore_patterns, str):
        ignore_patterns = [ignore_patterns]

    scan_dir = os.path.abspath(args.path or ".")
    if not os.path.exists(scan_dir):
        print(f"{C.RED}❌ 目录不存在: {scan_dir}{C.RESET}")
        return 1

    debounce = args.debounce
    print(f"{C.CYAN}👁 煋鉴 watch 模式 - 监听 {scan_dir}{C.RESET}")
    print(f"{C.GRAY}   保存文件后 {debounce}s 自动增量重扫，Ctrl+C 退出{C.RESET}")
    print(f"{'━' * 40}")

    # 首次全量扫描
    print(f"{C.BOLD}🔍 首次全量扫描...{C.RESET}")
    first_args = argparse.Namespace(
        path=scan_dir, diff=False, format=args.format, output=None, offline=args.offline
    )
    cmd_scan(first_args)

    # 建立基准快照
    last_snap = _snapshot_files(scan_dir, ignore_patterns)
    last_scan_time = 0.0

    try:
        while True:
            time.sleep(1.0)  # 1s 轮询间隔
            new_snap = _snapshot_files(scan_dir, ignore_patterns)
            changed = _diff_snapshots(last_snap, new_snap)
            if not changed:
                continue

            # 防抖：距上次扫描不足 debounce 秒则继续等待（合并连续保存）
            now = time.time()
            if now - last_scan_time < debounce:
                continue
            # 变更后额外稳定 debounce 秒，避免「打字打到一半」就扫
            time.sleep(debounce)
            new_snap = _snapshot_files(scan_dir, ignore_patterns)
            changed = _diff_snapshots(last_snap, new_snap)
            if not changed:
                continue

            last_scan_time = time.time()
            print(f"\n{C.CYAN}⚡ 检测到 {len(changed)} 个文件变化，增量重扫...{C.RESET}")
            for p in sorted(changed):
                print(f"   {C.GRAY}{p}{C.RESET}")

            result = _scan_subset(scan_dir, changed, ignore_patterns, config, args)
            if result is None:
                print(f"{C.YELLOW}⚠ 变更文件无可扫内容（可能被 ignore 或过小）{C.RESET}")
            else:
                _print_text_report(result, 0.0)

            # 更新基准快照为「最新」而非「上次扫描时」，避免漏掉等待期间的新变化
            last_snap = _snapshot_files(scan_dir, ignore_patterns)
    except KeyboardInterrupt:
        print(f"\n{C.GRAY}👁 watch 已退出{C.RESET}")
        return 0


# ============================================================
# SARIF 输出
# ============================================================

def _to_sarif(result, version=VERSION):
    """将扫描结果转换为 SARIF 2.1.0 格式"""
    issues = result.get("issues", [])
    
    # 构建 rules 列表（去重）
    rules = []
    seen_rules = set()
    for issue in issues:
        rule_id = issue.get("check_id", issue.get("rule_id", "UNKNOWN"))
        if rule_id not in seen_rules:
            seen_rules.add(rule_id)
            rules.append({
                "id": rule_id,
                "shortDescription": {
                    "text": issue.get("title", issue.get("message", ""))
                },
                "properties": {
                    "brain_id": issue.get("brain_id", ""),
                    "brain_name": issue.get("brain_name", ""),
                }
            })
    
    # 构建 results
    sarif_results = []
    severity_to_level = {
        "critical": "error", "blocker": "error",
        "high": "warning", "suspicious": "warning",
        "medium": "warning", "correctness": "warning", "restriction": "warning", "warning": "warning",
        "low": "note", "style": "note", "info": "note", "minor": "note",
    }
    
    for issue in issues:
        sev = issue.get("severity", "info")
        entry = {
            "ruleId": issue.get("check_id", issue.get("rule_id", "UNKNOWN")),
            "level": severity_to_level.get(sev, "note"),
            "message": {"text": issue.get("message", issue.get("description", ""))},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": issue.get("file", "")},
                    "region": {"startLine": issue.get("line", 1)},
                }
            }],
        }
        if issue.get("suggestion"):
            entry["fixes"] = [{
                "description": {"text": issue["suggestion"]},
            }]
        sarif_results.append(entry)
    
    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "Xinpect",
                    "version": version,
                    "informationUri": DEFAULT_SERVER,
                    "rules": rules,
                }
            },
            "results": sarif_results,
        }]
    }


# ============================================================
# 离线扫描
# ============================================================

def _offline_scan(code_files):
    """使用本地缓存规则执行基础扫描"""
    import re
    
    issues = []
    total_lines = 0
    
    # 加载缓存的规则
    rules = _load_cached_rules()
    if not rules:
        return None
    
    for filepath, content in code_files.items():
        lines = content.split("\n")
        total_lines += len([l for l in lines if l.strip()])
        
        for rule in rules:
            pattern = rule.get("pattern", "")
            if not pattern:
                continue
            try:
                regex = re.compile(pattern)
            except re.error:
                continue
            
            for line_num, line in enumerate(lines, 1):
                if regex.search(line):
                    issues.append({
                        "rule_id": rule["id"],
                        "check_id": rule["id"],
                        "brain_id": rule.get("brain_id", ""),
                        "brain_name": rule.get("brain_name", ""),
                        "title": rule.get("title", ""),
                        "severity": rule.get("severity", "low"),
                        "file": filepath,
                        "line": line_num,
                        "message": rule.get("description", ""),
                        "suggestion": rule.get("suggestion", ""),
                        "description": rule.get("description", ""),
                    })
    
    # 简单评分
    score = 100
    for issue in issues:
        sev = issue.get("severity", "low")
        if sev in ("critical", "blocker"):
            score -= 10
        elif sev in ("high", "suspicious"):
            score -= 5
        elif sev in ("medium", "correctness", "restriction"):
            score -= 3
        else:
            score -= 0.5
    score = max(0, min(100, score))
    
    # 计算等级
    if score >= 95:
        grade = "S"
    elif score >= 80:
        grade = "A"
    elif score >= 60:
        grade = "B"
    elif score >= 30:
        grade = "C"
    else:
        grade = "D"
    
    # 统计
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for issue in issues:
        sev = issue.get("severity", "low")
        if sev in ("blocker",):
            sev = "critical"
        elif sev in ("suspicious",):
            sev = "high"
        elif sev in ("correctness", "restriction", "warning"):
            sev = "medium"
        elif sev in ("style", "minor"):
            sev = "low"
        if sev in severity_counts:
            severity_counts[sev] += 1
    
    return {
        "score": int(score),
        "grade": grade,
        "total_issues": len(issues),
        "severity_counts": severity_counts,
        "issues": issues,
        "file_count": len(code_files),
        "total_lines": total_lines,
        "scan_mode": "offline",
        "offline": True,
    }


def _load_cached_rules():
    """加载本地缓存的规则"""
    if not os.path.exists(RULES_INDEX_FILE):
        return None
    
    try:
        with open(RULES_INDEX_FILE, "r", encoding="utf-8") as f:
            index = json.load(f)
        rules = []
        for entry in index.get("files", []):
            rule_path = os.path.join(RULES_CACHE_DIR, entry)
            if os.path.exists(rule_path):
                with open(rule_path, "r", encoding="utf-8") as rf:
                    rule_data = json.load(rf)
                    if isinstance(rule_data, list):
                        rules.extend(rule_data)
                    elif isinstance(rule_data, dict):
                        rules.append(rule_data)
        return rules if rules else None
    except Exception:
        return None


# ============================================================
# 命令：init
# ============================================================

def cmd_init(args):
    """交互式初始化，生成 .xinpect.yml"""
    target_dir = os.getcwd()
    config_path = os.path.join(target_dir, CONFIG_FILENAME)
    
    # 检查是否已存在
    if os.path.exists(config_path):
        if not args.non_interactive:
            print(f"{C.YELLOW}⚠ 当前目录已存在 {CONFIG_FILENAME}{C.RESET}")
            resp = input(f"  是否覆盖? (y/N): ").strip().lower()
            if resp != "y":
                print("已取消。")
                return 0
        else:
            print(f"{C.YELLOW}⚠ 已存在 {CONFIG_FILENAME}，非交互模式将覆盖{C.RESET}")
    
    # 获取配置值
    if args.non_interactive:
        api_key = args.api_key or ""
        scan_mode = args.mode or "quick"
        output_format = args.format or "text"
        ignore_list = DEFAULT_IGNORE[:]
    else:
        print(f"\n{C.BOLD}🔧 煋鉴 Xinpect 项目初始化{C.RESET}")
        print(f"{'━' * 40}\n")
        
        api_key = input(f"  API Key (从 {DEFAULT_SERVER}/dashboard 获取): ").strip()
        if not api_key:
            api_key = ""
            print(f"  {C.YELLOW}跳过，稍后在配置文件中填写{C.RESET}")
        
        print()
        print("  扫描模式:")
        print("    1) quick    - 快速扫描（E1语法 + E2安全）")
        print("    2) standard - 标准扫描（E1-E7 全引擎）")
        print("    3) full     - 完整扫描（含语义分析）")
        mode_input = input("  选择扫描模式 [1/2/3] (默认 1): ").strip()
        mode_map = {"1": "quick", "2": "standard", "3": "full", "quick": "quick", "standard": "standard", "full": "full"}
        scan_mode = mode_map.get(mode_input, "quick")
        
        print()
        ignore_input = input(f"  忽略文件模式 (逗号分隔，默认 {','.join(DEFAULT_IGNORE)}): ").strip()
        if ignore_input:
            ignore_list = [p.strip() for p in ignore_input.split(",") if p.strip()]
        else:
            ignore_list = DEFAULT_IGNORE[:]
        
        print()
        print("  输出格式:")
        print("    1) text  - 终端文本")
        print("    2) json  - JSON 格式")
        print("    3) sarif - SARIF 2.1.0 标准")
        fmt_input = input("  选择输出格式 [1/2/3] (默认 1): ").strip()
        fmt_map = {"1": "text", "2": "json", "3": "sarif", "text": "text", "json": "json", "sarif": "sarif"}
        output_format = fmt_map.get(fmt_input, "text")
    
    # 生成配置文件
    ignore_yaml = "\n".join(f'  - "{p}"' for p in ignore_list)
    
    config_content = f"""# 煋鉴 Xinpect 配置文件
# 文档: {DEFAULT_SERVER}/docs/api
api_key: "{api_key}"
server: "{DEFAULT_SERVER}"
scan_mode: "{scan_mode}"  # quick | standard | full
output_format: "{output_format}"  # text | json | sarif
ignore:
{ignore_yaml}
gate:
  enabled: false
  threshold: 60
  block_on: "P1"  # P0 | P1 | P2
"""
    
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(config_content)
    
    print(f"\n{C.GREEN}✅ 配置文件已生成: {CONFIG_FILENAME}{C.RESET}")
    
    # 下载规则缓存
    if api_key:
        print(f"\n📦 正在下载规则缓存...")
        _download_rules(api_key, DEFAULT_SERVER)
    else:
        # 使用内置离线规则
        print(f"\n📦 正在初始化离线规则缓存...")
        _save_builtin_rules()
    
    print(f"\n{C.CYAN}🎉 初始化完成！{C.RESET}")
    print(f"   运行 {C.BOLD}xinpect scan .{C.RESET} 开始扫描")
    return 0


# ============================================================
# 命令：scan
# ============================================================

def cmd_scan(args):
    """扫描代码"""
    start_time = time.time()
    
    # 加载配置
    config, config_dir = _load_config()
    if config is None:
        print(f"{C.RED}❌ 未找到 {CONFIG_FILENAME} 配置文件{C.RESET}")
        print(f"   运行 {C.BOLD}xinpect init{C.RESET} 进行初始化")
        return 1
    
    api_key = config.get("api_key", "")
    server = config.get("server", DEFAULT_SERVER)
    scan_mode = config.get("scan_mode", "quick")
    output_format = args.format or config.get("output_format", "text")
    ignore_patterns = config.get("ignore", DEFAULT_IGNORE)
    
    if isinstance(ignore_patterns, str):
        ignore_patterns = [ignore_patterns]
    
    # 确定扫描目录
    scan_dir = args.path or "."
    scan_dir = os.path.abspath(scan_dir)
    
    if not os.path.exists(scan_dir):
        print(f"{C.RED}❌ 目录不存在: {scan_dir}{C.RESET}")
        return 1
    
    # 收集文件
    if args.diff:
        # 增量扫描
        diff_files = _get_git_diff_files(scan_dir)
        if not diff_files:
            print(f"{C.YELLOW}⚠ 没有检测到 git diff 变更{C.RESET}")
            return 0
        
        all_files = _collect_files(scan_dir, ignore_patterns)
        files = [(rel, full) for rel, full in all_files if rel in diff_files]
        
        if not files:
            print(f"{C.YELLOW}⚠ diff 文件不在扫描范围内{C.RESET}")
            return 0
    else:
        files = _collect_files(scan_dir, ignore_patterns)
    
    if not files:
        print(f"{C.YELLOW}⚠ 没有找到可扫描的代码文件{C.RESET}")
        return 0
    
    # 读取文件内容
    code_files = {}
    for rel_path, filepath in files:
        content = _read_file_safe(filepath)
        if content is not None:
            code_files[rel_path] = content
    
    if not code_files:
        print(f"{C.YELLOW}⚠ 没有可读取的代码文件{C.RESET}")
        return 0
    
    # 检测语言
    language = _detect_language(files)
    
    # 判断是否在线扫描
    use_online = bool(api_key and not args.offline)
    result = None
    
    if use_online:
        # 在线扫描
        result = _online_scan(code_files, api_key, server, language, scan_mode)
    
    if result is None:
        # 离线扫描
        result = _offline_scan(code_files)
        if result is None:
            # 没有缓存规则，使用内置规则
            _save_builtin_rules()
            result = _offline_scan(code_files)
            if result is None:
                print(f"{C.RED}❌ 离线扫描失败，请检查规则缓存{C.RESET}")
                return 1
    
    elapsed = time.time() - start_time
    
    # 输出结果
    if args.output:
        # 保存文件
        _save_result(result, args.output, output_format, elapsed)
        print(f"{C.GREEN}✅ 结果已保存: {args.output}{C.RESET}")
    else:
        # 终端输出
        if output_format == "sarif" or args.format == "sarif":
            sarif = _to_sarif(result)
            print(json.dumps(sarif, ensure_ascii=False, indent=2))
        elif output_format == "json" or args.format == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            _print_text_report(result, elapsed)
    
    # 质量门禁检查
    gate = config.get("gate", {})
    if isinstance(gate, dict) and gate.get("enabled"):
        return _check_quality_gate(result, gate)
    
    return 0


def _online_scan(code_files, api_key, server, language, scan_mode):
    """在线扫描，调用服务器 API"""
    url = f"{server.rstrip('/')}/api/v1/scan"
    
    payload = {
        "code_files": code_files,
        "language": language,
    }
    
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }
    
    print(f"🔍 正在扫描 {len(code_files)} 个文件...", end="", flush=True)
    
    status, data = _http_request(url, method="POST", data=payload, headers=headers, timeout=120)
    
    print(f"\r{' ' * 50}\r", end="")  # 清除进度行
    
    if status == 0:
        error_msg = data.get("error", "网络错误") if isinstance(data, dict) else str(data)
        print(f"{C.YELLOW}⚠ 在线扫描失败: {error_msg}{C.RESET}")
        print(f"{C.GRAY}  尝试离线扫描...{C.RESET}")
        return None
    
    if status == 401:
        print(f"{C.RED}❌ API Key 无效或已过期{C.RESET}")
        print(f"   请检查 {CONFIG_FILENAME} 中的 api_key 配置")
        return None
    
    if status == 402:
        error_msg = "积分不足" if isinstance(data, dict) else ""
        print(f"{C.RED}❌ {error_msg}，请充值后重试{C.RESET}")
        return None
    
    if status == 403:
        print(f"{C.RED}❌ 无权限访问，API Key 可能已禁用{C.RESET}")
        return None
    
    if status >= 400:
        error_msg = data.get("error", f"HTTP {status}") if isinstance(data, dict) else f"HTTP {status}"
        print(f"{C.RED}❌ 扫描失败: {error_msg}{C.RESET}")
        return None
    
    if isinstance(data, dict):
        return data
    
    return None


def _print_text_report(result, elapsed):
    """打印文本格式的扫描报告"""
    score = result.get("score", 0)
    grade = result.get("grade", "?")
    file_count = result.get("file_count", 0)
    total_lines = result.get("total_lines", 0)
    issues = result.get("issues", [])
    severity_counts = result.get("severity_counts", {})
    is_offline = result.get("offline", False)
    
    # 颜色化评分
    if score >= 90:
        score_color = C.GREEN
    elif score >= 60:
        score_color = C.YELLOW
    else:
        score_color = C.RED
    
    # 等级颜色
    grade_colors = {"S": C.GREEN, "A": C.GREEN, "B": C.CYAN, "C": C.YELLOW, "D": C.RED}
    grade_color = grade_colors.get(grade, C.GRAY)
    
    print(f"\n{C.BOLD}🔍 煋鉴 Xinpect 代码质检报告{C.RESET}")
    if is_offline:
        print(f"{C.GRAY}   [离线模式 - 仅基础规则]{C.RESET}")
    print(f"{'━' * 40}")
    print(f"文件数: {file_count} | 代码行: {total_lines:,} | 耗时: {elapsed:.1f}s")
    print(f"综合评分: {score_color}{C.BOLD}{score}/100 ({grade}){C.RESET}")
    
    # 问题统计
    p_counts = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    for issue in issues:
        sev = issue.get("severity", "low")
        priority = PRIORITY_MAP.get(sev, "P3")
        p_counts[priority] = p_counts.get(priority, 0) + 1
    
    print(f"\n问题统计:")
    print(f"  {SEVERITY_ICONS.get('P0', '')} {C.RED}严重 (P0): {p_counts['P0']}{C.RESET}")
    print(f"  {SEVERITY_ICONS.get('P1', '')} {C.ORANGE}高危 (P1): {p_counts['P1']}{C.RESET}")
    print(f"  {SEVERITY_ICONS.get('P2', '')} {C.YELLOW}中危 (P2): {p_counts['P2']}{C.RESET}")
    print(f"  {SEVERITY_ICONS.get('P3', '')} {C.BLUE}低危 (P3): {p_counts['P3']}{C.RESET}")
    
    # 问题列表
    if issues:
        print(f"\n问题列表:")
        
        # 按优先级排序
        priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        sorted_issues = sorted(
            issues,
            key=lambda x: priority_order.get(PRIORITY_MAP.get(x.get("severity", "low"), "P3"), 3)
        )
        
        for issue in sorted_issues[:50]:  # 最多显示50个
            sev = issue.get("severity", "low")
            priority = PRIORITY_MAP.get(sev, "P3")
            icon = SEVERITY_ICONS.get(priority, "")
            title = issue.get("title", issue.get("message", ""))
            filepath = issue.get("file", "")
            line = issue.get("line", 0)
            description = issue.get("description", issue.get("message", ""))
            suggestion = issue.get("suggestion", "")
            
            # 优先用 check_id 展示
            check_id = issue.get("check_id", issue.get("rule_id", ""))
            
            print(f"\n  {icon} {C.BOLD}[{priority}]{C.RESET} {title} {C.GRAY}- {filepath}:{line}{C.RESET}")
            if description and description != title:
                print(f"       {description}")
            if suggestion:
                print(f"       {C.GREEN}修复: {suggestion}{C.RESET}")
        
        if len(issues) > 50:
            print(f"\n  {C.GRAY}... 还有 {len(issues) - 50} 个问题，使用 --output 参数导出完整报告{C.RESET}")
    
    print()


def _save_result(result, output_path, output_format, elapsed):
    """保存扫描结果到文件"""
    if output_format == "sarif":
        data = _to_sarif(result)
    else:
        data = result
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _check_quality_gate(result, gate_config):
    """检查质量门禁"""
    threshold = gate_config.get("threshold", 60)
    block_on = gate_config.get("block_on", "P1")
    score = result.get("score", 0)
    issues = result.get("issues", [])
    
    # 检查是否有阻断级别的问题
    blocked = False
    if block_on == "P0":
        blocked = any(PRIORITY_MAP.get(i.get("severity", ""), "P3") == "P0" for i in issues)
    elif block_on == "P1":
        blocked = any(PRIORITY_MAP.get(i.get("severity", ""), "P3") in ("P0", "P1") for i in issues)
    elif block_on == "P2":
        blocked = any(PRIORITY_MAP.get(i.get("severity", ""), "P3") in ("P0", "P1", "P2") for i in issues)
    
    if score < threshold:
        print(f"{C.RED}❌ 质量门禁未通过: 评分 {score} < 阈值 {threshold}{C.RESET}")
        return 1
    
    if blocked:
        print(f"{C.RED}❌ 质量门禁未通过: 存在 {block_on} 级别问题{C.RESET}")
        return 1
    
    print(f"{C.GREEN}✅ 质量门禁通过{C.RESET}")
    return 0


# ============================================================
# 命令：fix（自动修复 + 可选 PR）
# ============================================================

def _apply_unified_diff(file_path, patch_text):
    """把 unified diff 应用到本地文件（用系统 patch 命令，最稳）。

    返回 (ok, error_msg)。
    用 -d 指定文件所在目录 + -p1 剥掉 a/ b/ 前缀，确保 patch 在正确目录找文件。
    """
    if not patch_text:
        return False, "空补丁"
    import subprocess as _sp
    file_dir = os.path.dirname(os.path.abspath(file_path))
    try:
        r = _sp.run(
            ["patch", "-p1", "--forward", "--batch", "-d", file_dir],
            input=patch_text, text=True, capture_output=True, timeout=30,
        )
        if r.returncode == 0:
            return True, ""
        # --forward 若已应用会返回非0，此时视为「已应用」也算成功
        if "previously applied" in (r.stderr or "") or "Reversed (or previously applied)" in (r.stderr or ""):
            return True, "已应用过，跳过"
        return False, (r.stderr or r.stdout or "patch 失败")[:200]
    except FileNotFoundError:
        return False, "系统缺少 patch 命令"
    except Exception as e:
        return False, str(e)


def _collect_fix_patches(result):
    """从扫描结果里提取「确定性可应用」的补丁，按文件归组。

    返回 {file_path: [(line, patch_text, before, after, explanation), ...]}
    """
    by_file = {}
    for issue in result.get("issues", []):
        fp = issue.get("fix_patch") or {}
        if not fp.get("applicable"):
            continue
        fpath = issue.get("file", "")
        if not fpath:
            continue
        by_file.setdefault(fpath, []).append(
            (fp.get("line", issue.get("line", 0)), fp.get("patch", ""),
             fp.get("before", ""), fp.get("after", ""), fp.get("explanation", ""))
        )
    # 每文件按行号排序，去重（同行同补丁只留一条）
    for fpath in by_file:
        seen = set()
        deduped = []
        for item in sorted(by_file[fpath], key=lambda x: x[0]):
            key = (item[0], item[1])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        by_file[fpath] = deduped
    return by_file


def _git_is_repo(root_dir):
    import subprocess as _sp
    r = _sp.run(["git", "rev-parse", "--is-inside-work-tree"],
                cwd=root_dir, capture_output=True, text=True, timeout=10)
    return r.returncode == 0


def cmd_fix(args):
    """fix 命令：扫描 → 应用确定性补丁 → 提交 → 可选开 PR。

    只修「替换结果唯一确定」的规则（yaml.load→safe_load、pickle→json、
    MD5→SHA256、裸 except 等），不确定的一律跳过（诚实不硬造补丁）。
    默认只做本地 commit；加 --pr 尝试用 gh 建分支并开 PR（需已 gh auth login）。
    """
    config, config_dir = _load_config()
    if config is None:
        print(f"{C.RED}❌ 未找到 {CONFIG_FILENAME} 配置文件{C.RESET}")
        print(f"   运行 {C.BOLD}xinpect init{C.RESET} 进行初始化")
        return 1

    scan_dir = os.path.abspath(args.path or ".")
    if not os.path.exists(scan_dir):
        print(f"{C.RED}❌ 目录不存在: {scan_dir}{C.RESET}")
        return 1

    # 1) 扫描（复用 cmd_scan，拿到带 fix_patch 的 issue）
    print(f"{C.BOLD}🔍 扫描并生成可应用补丁...{C.RESET}")
    scan_args = argparse.Namespace(
        path=scan_dir, diff=False, format=args.format or "json",
        output=None, offline=args.offline,
    )
    # 直接跑 cmd_scan 会打印报告，这里改为静默拿结果：复制 cmd_scan 核心
    ignore_patterns = config.get("ignore", DEFAULT_IGNORE)
    if isinstance(ignore_patterns, str):
        ignore_patterns = [ignore_patterns]

    all_files = _collect_files(scan_dir, ignore_patterns)
    code_files = {}
    for rel_path, filepath in all_files:
        content = _read_file_safe(filepath)
        if content is not None:
            code_files[rel_path] = content
    if not code_files:
        print(f"{C.YELLOW}⚠ 没有可扫描的代码文件{C.RESET}")
        return 0

    language = _detect_language(all_files)
    api_key = config.get("api_key", "")
    server = config.get("server", DEFAULT_SERVER)
    scan_mode = config.get("scan_mode", "quick")

    result = None
    use_online = bool(api_key and not args.offline)
    if use_online:
        result = _online_scan(code_files, api_key, server, language, scan_mode)
    if result is None:
        print(f"{C.YELLOW}⚠ 在线扫描不可用，离线规则不含 fix_patch，无法自动修复{C.RESET}")
        return 1

    # 2) 提取可应用补丁
    patches_by_file = _collect_fix_patches(result)
    total = sum(len(v) for v in patches_by_file.values())
    if not total:
        print(f"{C.GREEN}✅ 没有可确定性自动修复的问题（其余需人工判断）{C.RESET}")
        return 0

    print(f"{C.CYAN}🎯 发现 {total} 处可自动修复（涉及 {len(patches_by_file)} 个文件）{C.RESET}")
    for fpath, items in patches_by_file.items():
        for line, patch, before, after, expl in items:
            print(f"   {fpath}:{line}  {before.strip()}  →  {after.strip()}")
            if expl:
                print(f"      {C.GRAY}{expl}{C.RESET}")

    if args.dry_run:
        print(f"\n{C.GRAY}--dry-run：仅预览，不应用{C.RESET}")
        return 0

    # 3) 应用补丁
    applied = 0
    for fpath, items in patches_by_file.items():
        full = os.path.join(scan_dir, fpath)
        for line, patch, before, after, expl in items:
            ok, msg = _apply_unified_diff(full, patch)
            if ok:
                applied += 1
                print(f"{C.GREEN}✅ 已修复 {fpath}:{line}{C.RESET}")
            else:
                print(f"{C.YELLOW}⚠ {fpath}:{line} 应用失败: {msg}{C.RESET}")

    if applied == 0:
        print(f"{C.YELLOW}⚠ 没有补丁被成功应用{C.RESET}")
        return 0

    print(f"\n{C.GREEN}✅ 共修复 {applied} 处{C.RESET}")

    # 4) 提交（若在 git 仓库内）
    if not _git_is_repo(scan_dir):
        print(f"{C.YELLOW}⚠ 当前目录不是 git 仓库，跳过提交（补丁已直接应用到文件）{C.RESET}")
        return 0

    if args.no_commit:
        print(f"{C.GRAY}--no-commit：补丁已应用，未提交{C.RESET}")
        return 0

    import subprocess as _sp
    branch = args.branch or f"xinpect-fix-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    try:
        # 建分支并提交
        _sp.run(["git", "checkout", "-b", branch], cwd=scan_dir, capture_output=True, text=True, timeout=30)
        changed_files = list(patches_by_file.keys())
        _sp.run(["git", "add"] + changed_files, cwd=scan_dir, capture_output=True, text=True, timeout=30)
        commit_msg = args.message or "fix: 煋鉴自动修复确定性安全问题"
        r = _sp.run(["git", "commit", "-m", commit_msg], cwd=scan_dir, capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            print(f"{C.GREEN}✅ 已提交到分支 {branch}{C.RESET}")
        else:
            print(f"{C.YELLOW}⚠ 提交失败（可能无变更或需配置 git 身份）: {r.stderr.strip()[:200]}{C.RESET}")
            return 0
    except Exception as e:
        print(f"{C.YELLOW}⚠ git 操作异常: {e}{C.RESET}")
        return 0

    # 5) 开 PR（可选）
    if args.pr:
        if _sp.run(["git", "push", "-u", "origin", branch], cwd=scan_dir,
                   capture_output=True, text=True, timeout=120).returncode != 0:
            print(f"{C.YELLOW}⚠ push 失败，请手动 push 后用 gh pr create{C.RESET}")
            return 0
        pr_r = _sp.run(
            ["gh", "pr", "create", "--title", args.pr_title or "煋鉴自动安全修复",
             "--body", args.pr_body or "由煋鉴 CLI 自动生成的安全修复补丁（确定性规则）"],
            cwd=scan_dir, capture_output=True, text=True, timeout=60,
        )
        if pr_r.returncode == 0:
            print(f"{C.GREEN}✅ PR 已创建：{pr_r.stdout.strip()}{C.RESET}")
        elif "gh: command not found" in (pr_r.stderr or ""):
            print(f"{C.YELLOW}⚠ 未安装 GitHub CLI（gh），请安装后运行：gh pr create{C.RESET}")
        else:
            print(f"{C.YELLOW}⚠ PR 创建失败: {pr_r.stderr.strip()[:200]}{C.RESET}")
            print(f"{C.GRAY}   分支已 push，可手动：gh pr create --title \"煋鉴自动安全修复\"{C.RESET}")

    return 0


# ============================================================
# 命令：status
# ============================================================

def cmd_status(args):
    """查看账户状态"""
    config, _ = _load_config()
    if config is None:
        print(f"{C.RED}❌ 未找到 {CONFIG_FILENAME} 配置文件{C.RESET}")
        print(f"   运行 {C.BOLD}xinpect init{C.RESET} 进行初始化")
        return 1
    
    api_key = config.get("api_key", "")
    server = config.get("server", DEFAULT_SERVER)
    
    if not api_key:
        print(f"{C.YELLOW}⚠ 未配置 API Key{C.RESET}")
        print(f"   请编辑 {CONFIG_FILENAME} 填写 api_key")
        return 1
    
    # 调用 status API（复用 scan API 的 GET 方法）
    url = f"{server.rstrip('/')}/api/v1/scan"
    headers = {"X-API-Key": api_key}
    
    status_code, data = _http_request(url, method="GET", headers=headers, timeout=15)
    
    print(f"\n{C.BOLD}📊 煋鉴账户状态{C.RESET}")
    print(f"{'━' * 30}")
    print(f"服务器: {server}")
    
    if status_code == 200 and isinstance(data, dict):
        print(f"状态:   {C.GREEN}正常{C.RESET}")
        print(f"API:    {data.get('endpoint', '/api/v1/scan')}")
    elif status_code == 401 or status_code == 403:
        print(f"状态:   {C.RED}API Key 无效{C.RESET}")
    elif status_code == 0:
        error_msg = data.get("error", "") if isinstance(data, dict) else str(data)
        print(f"状态:   {C.RED}连接失败{C.RESET}")
        print(f"原因:   {error_msg}")
    else:
        print(f"状态:   {C.YELLOW}未知 (HTTP {status_code}){C.RESET}")
    
    # 显示本地配置信息
    print(f"\n本地配置:")
    print(f"  扫描模式: {config.get('scan_mode', 'quick')}")
    print(f"  输出格式: {config.get('output_format', 'text')}")
    
    # 规则缓存状态
    if os.path.exists(RULES_INDEX_FILE):
        try:
            with open(RULES_INDEX_FILE, "r", encoding="utf-8") as f:
                idx = json.load(f)
            rule_count = idx.get("rule_count", 0)
            updated = idx.get("updated_at", "未知")
            print(f"\n规则缓存:")
            print(f"  规则数: {rule_count}")
            print(f"  更新时间: {updated}")
        except Exception:
            print(f"\n规则缓存: {C.YELLOW}索引损坏{C.RESET}")
    else:
        print(f"\n规则缓存: {C.YELLOW}未缓存{C.RESET}")
    
    print()
    return 0


# ============================================================
# 命令：rules
# ============================================================

def cmd_rules(args):
    """规则管理"""
    config, _ = _load_config()
    api_key = ""
    server = DEFAULT_SERVER
    if config:
        api_key = config.get("api_key", "")
        server = config.get("server", DEFAULT_SERVER)
    
    if args.rules_action == "update":
        return _download_rules(api_key, server)
    elif args.rules_action == "list":
        return _list_rules()
    else:
        print(f"{C.RED}未知规则命令: {args.rules_action}{C.RESET}")
        print("可用命令: update, list")
        return 1


def _download_rules(api_key, server):
    """从服务器下载规则包"""
    os.makedirs(RULES_CACHE_DIR, exist_ok=True)
    
    # 尝试从服务器下载
    if api_key:
        url = f"{server.rstrip('/')}/api/v1/rules"
        headers = {"X-API-Key": api_key}
        status, data = _http_request(url, headers=headers, timeout=15)
        
        if status == 200 and isinstance(data, dict) and "rules" in data:
            rules = data["rules"]
            _save_rules_to_cache(rules)
            print(f"{C.GREEN}✅ 规则缓存已更新: {len(rules)} 条规则{C.RESET}")
            return 0
        
        if status == 404:
            print(f"{C.GRAY}  服务器暂无规则 API，使用内置规则{C.RESET}")
    
    # 使用内置规则
    _save_builtin_rules()
    print(f"{C.GREEN}✅ 内置规则已缓存: {len(OFFLINE_RULES)} 条{C.RESET}")
    return 0


def _save_builtin_rules():
    """保存内置规则到缓存"""
    os.makedirs(RULES_CACHE_DIR, exist_ok=True)
    _save_rules_to_cache(OFFLINE_RULES)


def _save_rules_to_cache(rules):
    """将规则列表保存到缓存目录"""
    # 按 brain_id 分组保存
    groups = {}
    for rule in rules:
        brain_id = rule.get("brain_id", "0")
        groups.setdefault(brain_id, []).append(rule)
    
    file_list = []
    for brain_id, group_rules in groups.items():
        filename = f"rules_e{brain_id}.json"
        filepath = os.path.join(RULES_CACHE_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(group_rules, f, ensure_ascii=False, indent=2)
        file_list.append(filename)
    
    # 保存索引
    index = {
        "files": file_list,
        "rule_count": len(rules),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "version": VERSION,
    }
    with open(RULES_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def _list_rules():
    """列出已缓存的规则"""
    if not os.path.exists(RULES_INDEX_FILE):
        print(f"{C.YELLOW}⚠ 规则缓存为空{C.RESET}")
        print(f"   运行 {C.BOLD}xinpect rules update{C.RESET} 下载规则")
        return 1
    
    try:
        with open(RULES_INDEX_FILE, "r", encoding="utf-8") as f:
            index = json.load(f)
    except Exception:
        print(f"{C.RED}❌ 规则索引损坏{C.RESET}")
        return 1
    
    print(f"\n{C.BOLD}📋 煋鉴规则缓存{C.RESET}")
    print(f"{'━' * 35}")
    print(f"规则数: {index.get('rule_count', 0)}")
    print(f"更新时间: {index.get('updated_at', '未知')}")
    print(f"缓存路径: {RULES_CACHE_DIR}")
    print()
    
    # 按引擎分组显示
    brain_names = {
        "1": "E1 语法格式", "2": "E2 安全与依赖审计", "3": "E3 AI语义分析",
        "4": "E4 性能与可靠性", "5": "E5 可观测性", "6": "E6 代码质量与测试",
        "7": "E7 架构与数据合规", "8": "E8 业务安全", "9": "E9 专项引擎",
    }
    
    for filename in index.get("files", []):
        filepath = os.path.join(RULES_CACHE_DIR, filename)
        if not os.path.exists(filepath):
            continue
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                rules = json.load(f)
            
            if isinstance(rules, list) and rules:
                brain_id = rules[0].get("brain_id", "?")
                brain_name = brain_names.get(brain_id, f"引擎 {brain_id}")
                print(f"  {C.BOLD}{brain_name}{C.RESET} ({len(rules)} 条规则)")
                
                for rule in rules:
                    sev = rule.get("severity", "low")
                    priority = PRIORITY_MAP.get(sev, "P3")
                    icon = SEVERITY_ICONS.get(priority, "")
                    title = rule.get("title", "")
                    rule_id = rule.get("id", "")
                    print(f"    {icon} [{priority}] {rule_id}: {title}")
                print()
        except Exception:
            continue
    
    return 0


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        prog="xinpect",
        description="煋鉴 Xinpect - AI 代码质检 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
示例:
  xinpect init                      交互式初始化
  xinpect init --non-interactive    非交互模式
  xinpect scan .                    扫描当前目录
  xinpect scan --diff               增量扫描
  xinpect scan --format sarif       SARIF 格式输出
  xinpect scan --output report.json 保存结果
  xinpect scan --offline            离线扫描（本地规则）
  xinpect watch .                   边写边扫（保存即自动增量重扫）
  xinpect watch --offline           边写边扫（本地规则，不消耗积分）
  xinpect fix .                     自动修复确定性安全问题（本地 commit）
  xinpect fix . --dry-run           预览补丁不应用
  xinpect fix . --pr                自动修复并 push + 开 PR
  xinpect status                    查看账户状态
  xinpect rules update              更新规则缓存
  xinpect rules list                查看已缓存规则
  
文档: {DEFAULT_SERVER}/docs/api
"""
    )
    
    parser.add_argument("--version", action="version", version=f"煋鉴 Xinpect CLI v{VERSION}")
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # init 命令
    init_parser = subparsers.add_parser("init", help="初始化项目配置")
    init_parser.add_argument("--api-key", dest="api_key", help="API Key")
    init_parser.add_argument("--mode", choices=["quick", "standard", "full"], help="扫描模式")
    init_parser.add_argument("--format", choices=["text", "json", "sarif"], help="输出格式")
    init_parser.add_argument("--non-interactive", action="store_true", help="非交互模式")
    
    # scan 命令
    scan_parser = subparsers.add_parser("scan", help="扫描代码")
    scan_parser.add_argument("path", nargs="?", default=".", help="扫描目录 (默认: 当前目录)")
    scan_parser.add_argument("--diff", action="store_true", help="增量扫描（仅 git diff）")
    scan_parser.add_argument("--format", choices=["text", "json", "sarif"], help="输出格式")
    scan_parser.add_argument("--output", "-o", help="输出文件路径")
    scan_parser.add_argument("--offline", action="store_true", help="强制离线扫描")
    
    # status 命令
    subparsers.add_parser("status", help="查看账户状态")

    # watch 命令（边写边扫）
    watch_parser = subparsers.add_parser("watch", help="边写边扫（保存即自动增量重扫）")
    watch_parser.add_argument("path", nargs="?", default=".", help="监听目录 (默认: 当前目录)")
    watch_parser.add_argument("--debounce", type=float, default=1.5, help="防抖秒数 (默认: 1.5)")
    watch_parser.add_argument("--format", choices=["text", "json", "sarif"], help="输出格式")
    watch_parser.add_argument("--offline", action="store_true", help="强制离线扫描")

    # fix 命令（自动修复 + 可选 PR）
    fix_parser = subparsers.add_parser("fix", help="自动修复确定性安全问题（可选开 PR）")
    fix_parser.add_argument("path", nargs="?", default=".", help="扫描目录 (默认: 当前目录)")
    fix_parser.add_argument("--dry-run", action="store_true", help="只预览补丁，不应用")
    fix_parser.add_argument("--no-commit", action="store_true", help="只应用补丁，不提交")
    fix_parser.add_argument("--pr", action="store_true", help="push 并用 gh 开 PR")
    fix_parser.add_argument("--branch", help="分支名 (默认自动生成 xinpect-fix-时间戳)")
    fix_parser.add_argument("--message", "-m", help="提交信息")
    fix_parser.add_argument("--pr-title", help="PR 标题")
    fix_parser.add_argument("--pr-body", help="PR 正文")
    fix_parser.add_argument("--format", choices=["text", "json", "sarif"], help="输出格式")
    fix_parser.add_argument("--offline", action="store_true", help="强制离线扫描")

    # rules 命令
    rules_parser = subparsers.add_parser("rules", help="规则管理")
    rules_parser.add_argument("rules_action", choices=["update", "list"], help="规则操作")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    # 路由命令
    if args.command == "init":
        return cmd_init(args)
    elif args.command == "scan":
        return cmd_scan(args)
    elif args.command == "watch":
        return cmd_watch(args)
    elif args.command == "fix":
        return cmd_fix(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "rules":
        return cmd_rules(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        print(f"\n{C.GRAY}已取消{C.RESET}")
        sys.exit(130)
    except Exception as e:
        print(f"\n{C.RED}❌ 异常: {e}{C.RESET}")
        sys.exit(1)
