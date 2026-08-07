"""
JS/WXML AST Analyzer - Python side

Provides AST-level analysis for JavaScript/TypeScript and WXML files by
bridging to a persistent Node.js subprocess that uses @babel/parser and
htmlparser2.

If Node.js or the required packages are not available, all methods
gracefully return None, allowing callers to fall back to regex-based rules.

Usage:
    analyzer = get_js_ast_analyzer()
    
    # Parse a JS file
    js_data = analyzer.parse_js_file(file_path)
    if js_data:
        # js_data.functions, js_data.calls, js_data.imports, etc.
        method_names = {f['name'] for f in js_data['functions']}
    
    # Parse a WXML file
    wxml_data = analyzer.parse_wxml_file(file_path)
    if wxml_data:
        # wxml_data.bindings, wxml_data.wxForTags, wxml_data.images, etc.
        for b in wxml_data['bindings']:
            print(f"{b['method']} bound at line {b['line']}")
"""

import os
import sys
import json
import subprocess
import threading
from typing import List, Dict, Any, Optional
from pathlib import Path


# Node.js executable path
_NODE_EXE = None

def _find_node_exe():
    """Find Node.js executable"""
    global _NODE_EXE
    if _NODE_EXE:
        return _NODE_EXE
    
    # Try managed Node.js first
    candidates = [
        os.path.expanduser("~/.workbuddy/binaries/node/versions/22.22.2/node.exe"),
        os.path.expanduser("~/.workbuddy/binaries/node/versions/22.22.2/node"),
        "node",  # System PATH
    ]
    
    for candidate in candidates:
        try:
            result = subprocess.run(
                [candidate, "--version"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                _NODE_EXE = candidate
                return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    
    return None


# Path to the bridge script
_BRIDGE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ast_bridge.js")

# Node.js workspace path (where node_modules with @babel/parser etc. are installed)
_NODE_WORKSPACE = os.path.expanduser("~/.workbuddy/binaries/node/workspace")


class JSASTAnalyzer:
    """JS/WXML AST Analyzer backed by a persistent Node.js subprocess.
    
    The subprocess is started lazily on first use and kept alive for
    the lifetime of the analyzer. Communication uses newline-delimited
    JSON over stdin/stdout.
    """
    
    def __init__(self):
        self._process = None
        self._lock = threading.Lock()
        self._request_id = 0
        self._available = None  # None = not checked, True/False
        self._file_cache = {}  # {file_path: (mtime, result)}
        self._has_babel = False
        self._has_htmlparser2 = False
    
    def _ensure_process(self) -> bool:
        """Start the Node.js subprocess if not already running.
        
        Returns True if the process is ready, False if unavailable.
        """
        if self._process and self._process.poll() is None:
            return True  # Already running
        
        if self._available is False:
            return False  # Previously determined unavailable
        
        node_exe = _find_node_exe()
        if not node_exe:
            self._available = False
            return False
        
        if not os.path.isfile(_BRIDGE_SCRIPT):
            self._available = False
            return False
        
        try:
            env = os.environ.copy()
            # Set NODE_PATH so the bridge can find packages in the workspace
            node_modules_path = os.path.join(_NODE_WORKSPACE, "node_modules")
            if os.path.isdir(node_modules_path):
                env["NODE_PATH"] = node_modules_path
            
            self._process = subprocess.Popen(
                [node_exe, _BRIDGE_SCRIPT],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=_NODE_WORKSPACE,
                text=True,
                bufsize=1,  # Line buffered
            )
            
            # Read the ready signal
            ready_line = self._process.stdout.readline()
            if not ready_line:
                self._available = False
                return False
            
            ready = json.loads(ready_line)
            if ready.get("ok") and ready.get("data", {}).get("ready"):
                self._has_babel = ready.get("data", {}).get("hasBabel", False)
                self._has_htmlparser2 = ready.get("data", {}).get("hasHtmlparser2", False)
                self._has_ast_rules = ready.get("data", {}).get("hasAstRules", False)
                self._available = True
                return True
            else:
                self._available = False
                return False
                
        except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
            self._available = False
            return False
    
    @property
    def is_available(self) -> bool:
        """Check if the AST analyzer is available (Node.js + packages)."""
        if self._available is not None:
            return self._available
        return self._ensure_process()
    
    @property
    def has_babel(self) -> bool:
        """Whether @babel/parser is available."""
        if self._available is None:
            self._ensure_process()
        return self._has_babel
    
    @property
    def has_htmlparser2(self) -> bool:
        """Whether htmlparser2 is available."""
        if self._available is None:
            self._ensure_process()
        return self._has_htmlparser2
    
    @property
    def has_ast_rules(self) -> bool:
        """Whether the JS AST rules engine is available."""
        if self._available is None:
            self._ensure_process()
        return getattr(self, '_has_ast_rules', False)
    
    def _send_command(self, cmd: dict) -> Optional[dict]:
        """Send a command to the Node.js process and get the response."""
        with self._lock:
            if not self._ensure_process():
                return None
            
            self._request_id += 1
            cmd["id"] = self._request_id
            
            try:
                self._process.stdin.write(json.dumps(cmd) + "\n")
                self._process.stdin.flush()
                
                response_line = self._process.stdout.readline()
                if not response_line:
                    # Process died
                    self._available = False
                    self._process = None
                    return None
                
                response = json.loads(response_line)
                if not response.get("ok"):
                    return None
                
                return response.get("data")
                
            except (BrokenPipeError, json.JSONDecodeError, OSError):
                self._available = False
                self._process = None
                return None
    
    def _get_file_content(self, file_path: str) -> Optional[str]:
        """Read file content with encoding handling."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except (OSError, IOError):
            return None
    
    def _get_cached(self, file_path: str) -> Optional[dict]:
        """Get cached result if file hasn't changed."""
        try:
            mtime = os.path.getmtime(file_path)
        except OSError:
            return None
        
        cached = self._file_cache.get(file_path)
        if cached and cached[0] == mtime:
            return cached[1]
        return None
    
    def _set_cached(self, file_path: str, result: dict):
        """Cache result with current mtime."""
        try:
            mtime = os.path.getmtime(file_path)
            self._file_cache[file_path] = (mtime, result)
        except OSError:  # noqa: intentional empty handler
            pass
    
    # ===== Public API =====
    
    def parse_js_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Parse a JS/TS file and return AST analysis results.
        
        Returns None if the analyzer is unavailable or parsing failed.
        
        Result structure:
            functions: [{name, line, endLine, params, isAsync, isArrow, isEmpty, isMethod, parentName}]
            calls: [{name, full_name, line, col, args_count, is_member, member_obj}]
            imports: [{source, line, is_default, specifiers, is_require}]
            consoleCalls: [{method, line, col}]
            emptyFunctions: [{name, line, hasTodo}]
            setDataCalls: [{line, keys: [...]}]
            memberAssignments: [{obj, prop, full_chain, line}]
        """
        if not self.has_babel:
            return None
        
        # Check cache
        cached = self._get_cached(file_path)
        if cached is not None:
            return cached
        
        content = self._get_file_content(file_path)
        if not content:
            return None
        
        result = self._send_command({
            "type": "js",
            "content": content,
            "filename": os.path.basename(file_path),
        })
        
        if result:
            self._set_cached(file_path, result)
        
        return result
    
    def parse_wxml_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Parse a WXML file and return structured analysis results.
        
        Returns None if the analyzer is unavailable or parsing failed.
        
        Result structure:
            tags: [{name, line, attrs: {key: value}, selfClosing}]
            bindings: [{event, method, raw, line, tag}]
            wxForTags: [{line, hasKey, keyName, list_expr, tag}]
            images: [{line, hasLazyLoad, src}]
            mustacheCount: {open, close}
        """
        if not self.has_htmlparser2:
            return None
        
        # Check cache
        cached = self._get_cached(file_path)
        if cached is not None:
            return cached
        
        content = self._get_file_content(file_path)
        if not content:
            return None
        
        result = self._send_command({
            "type": "wxml",
            "content": content,
        })
        
        if result:
            self._set_cached(file_path, result)
        
        return result
    
    # ===== High-level helper methods =====
    
    def get_js_method_names(self, file_path: str) -> Optional[set]:
        """Get all method names defined in a JS file.
        
        This is more accurate than regex because it understands:
        - ES6 shorthand methods: { onTap(e) {} }
        - Async methods: { async fetchData() {} }
        - Arrow functions: { handler: (e) => {} }
        - Class methods
        - Function declarations
        
        Returns None if AST unavailable (caller should fall back to regex).
        """
        data = self.parse_js_file(file_path)
        if not data:
            return None
        
        # JS keywords and config keys that are not methods
        JS_KEYWORDS = {
            'if', 'for', 'while', 'switch', 'catch', 'with', 'return',
            'function', 'typeof', 'void', 'delete', 'new', 'do', 'else',
            'try', 'finally', 'class', 'super', 'yield', 'await', 'async',
            'data', 'properties', 'methods', 'lifetimes',
            'pageLifetimes', 'observers', 'options', 'behaviors',
            'externalClasses', 'relations', 'attached', 'detached',
            'created', 'ready', 'moved', 'import', 'export', 'default',
            'const', 'let', 'var', 'require', 'module', 'exports',
        }
        
        methods = set()
        for func in data.get("functions", []):
            name = func.get("name", "")
            if name and name not in JS_KEYWORDS:
                methods.add(name)
        
        return methods
    
    def get_js_imports(self, file_path: str) -> Optional[List[Dict]]:
        """Get all import/require statements from a JS file.
        
        Returns None if AST unavailable.
        """
        data = self.parse_js_file(file_path)
        if not data:
            return None
        
        return data.get("imports", [])
    
    def get_js_console_calls(self, file_path: str) -> Optional[List[Dict]]:
        """Get all console.log/debug/trace calls from a JS file.
        
        Returns None if AST unavailable.
        """
        data = self.parse_js_file(file_path)
        if not data:
            return None
        
        return data.get("consoleCalls", [])
    
    def get_js_empty_functions(self, file_path: str) -> Optional[List[Dict]]:
        """Get all empty function bodies (with TODO markers) from a JS file.
        
        Returns None if AST unavailable.
        """
        data = self.parse_js_file(file_path)
        if not data:
            return None
        
        return data.get("emptyFunctions", [])
    
    def get_wxml_bindings(self, file_path: str) -> Optional[List[Dict]]:
        """Get all event bindings (bind*/catch*) from a WXML file.
        
        Returns None if AST unavailable.
        """
        data = self.parse_wxml_file(file_path)
        if not data:
            return None
        
        return data.get("bindings", [])
    
    def get_wxml_for_tags(self, file_path: str) -> Optional[List[Dict]]:
        """Get all wx:for tags and whether they have wx:key.
        
        Returns None if AST unavailable.
        """
        data = self.parse_wxml_file(file_path)
        if not data:
            return None
        
        return data.get("wxForTags", [])
    
    def get_wxml_images(self, file_path: str) -> Optional[List[Dict]]:
        """Get all image tags and whether they have lazy-load.
        
        Returns None if AST unavailable.
        """
        data = self.parse_wxml_file(file_path)
        if not data:
            return None
        
        return data.get("images", [])
    
    def get_wxml_mustache_count(self, file_path: str) -> Optional[Dict]:
        """Get {{ }} count for mustache syntax validation.
        
        Returns None if AST unavailable.
        """
        data = self.parse_wxml_file(file_path)
        if not data:
            return None
        
        return data.get("mustacheCount", {})
    
    # ===== v4.4 JS/TS AST 规则引擎 =====
    
    def run_ast_rules(self, file_path: str, rule_ids: Optional[List[str]] = None,
                       content: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """运行 JS/TS AST 规则引擎，返回问题列表。
        
        Args:
            file_path: 文件路径（用于缓存和文件名推断）
            rule_ids: 要运行的规则 ID 列表，None 或空列表表示运行所有规则
            content: 可选，直接传入文件内容。若为 None 则从 file_path 读取
        
        Returns:
            issue 列表，格式：
            [{
                'ruleId': 'HOOKS-001',
                'message': '...',
                'line': 1,
                'col': 1,
                'endLine': 1,
                'endCol': 10,
                'severity': 'error'|'warning'|'info',
                'fix': '...',
                'snippet': '...',
            }]
            
            引擎不可用时返回 None。
        """
        if not self.has_ast_rules:
            return None
        
        if content is None:
            content = self._get_file_content(file_path)
            if not content:
                return []
        
        # 使用内容哈希做缓存（比 mtime 更精确）
        import hashlib
        cache_key = f"ast_rules:{file_path}:{hashlib.md5(content.encode()).hexdigest()}:{','.join(rule_ids or [])}"
        
        # 复用 file_cache 机制
        cached = self._file_cache.get(cache_key)
        if cached is not None:
            return cached
        
        result = self._send_command({
            "type": "js_ast_rules",
            "content": content,
            "filename": os.path.basename(file_path),
            "ruleIds": rule_ids or [],
        })
        
        if result is None:
            return None
        
        issues = result.get("issues", [])
        self._file_cache[cache_key] = issues
        return issues
    
    def run_ast_rules_on_content(self, content: str, filename: str = "inline.js",
                                   rule_ids: Optional[List[str]] = None) -> Optional[List[Dict[str, Any]]]:
        """直接对代码内容运行 AST 规则（无需文件）。
        
        Args:
            content: JS/TS 代码字符串
            filename: 文件名（影响解析器插件选择，如 .tsx .js）
            rule_ids: 要运行的规则 ID 列表
        
        Returns:
            issue 列表，引擎不可用时返回 None
        """
        if not self.has_ast_rules:
            return None
        
        result = self._send_command({
            "type": "js_ast_rules",
            "content": content,
            "filename": filename,
            "ruleIds": rule_ids or [],
        })
        
        if result is None:
            return None
        
        return result.get("issues", [])
    
    def clear_cache(self):
        """Clear the file cache."""
        self._file_cache.clear()
    
    def close(self):
        """Close the Node.js subprocess."""
        if self._process:
            try:
                self._process.stdin.close()
                self._process.terminate()
                self._process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    self._process.kill()
                except OSError:  # noqa: intentional empty handler
                    pass
            self._process = None


# ===== Global singleton =====

_analyzer = None
_analyzer_lock = threading.Lock()


def get_js_ast_analyzer() -> JSASTAnalyzer:
    """Get the global JSASTAnalyzer singleton."""
    global _analyzer
    if _analyzer is None:
        with _analyzer_lock:
            if _analyzer is None:
                _analyzer = JSASTAnalyzer()
    return _analyzer


def is_ast_available() -> bool:
    """Quick check if AST analysis is available (without starting the process).
    
    Checks if Node.js exists and the bridge script is in place.
    Does not guarantee that @babel/parser or htmlparser2 are installed.
    """
    node_exe = _find_node_exe()
    if not node_exe:
        return False
    if not os.path.isfile(_BRIDGE_SCRIPT):
        return False
    node_modules = os.path.join(_NODE_WORKSPACE, "node_modules")
    return os.path.isdir(node_modules)