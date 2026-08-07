"""
项目上下文与架构检测
负责项目类型识别、项目画像构建、架构风格检测
为规则执行提供上下文信息

v3 - 按3S骨架优化：
- AST 相关方法 → core.ast_context.AstContextMixin (Mixin继承)
- 项目类型检测 → core.project_type_detector (模块函数)
- ProjectProfile 类 → core.project_profiler (导入)
- build_profile → 转发到 project_profiler._build_project_profile
"""

import os
import re
import json
import threading
from typing import Dict, List, Optional, Any

# 从拆分模块导入（保持向后兼容）
from core.project_type_detector import (
    PROJECT_TYPE_NAMES,
    MODULE_APPLICABILITY,
    detect_project_type as _detect_type_fn,
)
from core.project_profiler import ProjectProfile
from core.ast_context import AstContextMixin


class QAContext(AstContextMixin):
    """QA检查上下文
    包含项目路径、配置、项目类型、项目画像等所有检查所需的上下文信息
    """
    
    def __init__(
        self,
        project_path: str = "",
        backend_path: str = "",
        config: dict = None,
        project_type: str = "auto",
        mode: str = "quick",  # quick / advanced
    ):
        self.project_path = project_path
        self.backend_path = backend_path
        self.config = config or {}
        self.mode = mode

        # 文件缓存
        self._walk_lock = threading.Lock()  # 保护 _ensure_walk_cache 的线程安全
        self._file_cache = {}
        self._ast_cache = {}  # v2.9.1 P3: AST tree cache (cross-rule sharing)
        self._ast_summary = {}  # v2.9.2 P4: AST summary cache (pre-computed per file)
        self._files_by_ext = {}
        self._all_walk_cache = None  # 完整 os.walk 结果缓存（一次遍历，多次过滤）
        self._scan_exclude_files = None  # None=未检查, set=已检查结果, 懒加载避免初始化时全量文件IO
        # v4.6.1 零磁盘IO改造：规则执行阶段只查内存集合
        self._cached_file_set = None  # frozenset, 所有扫描范围内的文件绝对路径
        self._cached_dir_set = None   # frozenset, 所有扫描范围内的目录绝对路径

        # v3.5: 增量检查模式 - 设置后find_files只返回变更文件
        self.incremental_files: Optional[set] = None  # None=全量, set=增量过滤

        # 项目类型检测
        if project_type == "auto":
            self.project_type = self._detect_project_type_v2()
        else:
            self.project_type = project_type
        
        # 项目画像
        self.project_profile = ProjectProfile()
        
        # 架构信息（懒加载）
        self._arch_info = None
    
    @property
    def project_type_name(self) -> str:
        return PROJECT_TYPE_NAMES.get(self.project_type, self.project_type)
    
    @property
    def project_root(self) -> str:
        """Alias for project_path for compatibility with rules that use project_root."""
        return self.project_path

    # ===== 项目类型检测（转发到 project_type_detector，零行为变更） =====
    
    def _classify_file(self, filename: str, filepath: str, flags: dict) -> None:
        """分类单个文件（转发到 project_type_detector.classify_file）"""
        from core.project_type_detector import classify_file
        classify_file(filename, filepath, flags, self.safe_read)

    def _has_real_frontend(self, flags: dict) -> bool:
        """判断是否存在真正的前端框架文件（转发）"""
        from core.project_type_detector import has_real_frontend
        return has_real_frontend(flags)

    def _has_backend_framework(self, flags: dict) -> bool:
        """判断是否存在后端框架（转发）"""
        from core.project_type_detector import has_backend_framework
        return has_backend_framework(flags)

    def _resolve_project_type(self, flags: dict) -> str:
        """根据flags判定项目类型（转发）"""
        from core.project_type_detector import resolve_project_type
        return resolve_project_type(flags)

    def _resolve_project_type_v2(self, flags: dict) -> str:
        """改进版类型判定（转发）"""
        from core.project_type_detector import resolve_project_type_v2
        return resolve_project_type_v2(flags)

    def _detect_project_type(self) -> str:
        """自动检测项目类型（旧版，转发）"""
        # 为保持零行为变更，直接调用新版 detect_project_type
        return _detect_type_fn(
            self.project_path,
            self.backend_path,
            safe_read_fn=self.safe_read,
            verbose=False,
        )
    
    def _detect_project_type_v2(self) -> str:
        """v3.5.1: 改进版类型检测（转发到 project_type_detector）"""
        return _detect_type_fn(
            self.project_path,
            self.backend_path,
            safe_read_fn=self.safe_read,
            verbose=True,
        )

    def is_module_applicable(self, module_id: str) -> bool:
        """检查模块是否适用于当前项目类型"""
        applicable = MODULE_APPLICABILITY.get(module_id, "all")
        if applicable == "all":
            return True
        return self.project_type in applicable
    
    def is_web_frontend(self) -> bool:
        """判断项目是否为Web前端（非小程序）"""
        if self.project_type in ("web", "electron"):
            return True
        if self.project_type in ("mixed", "mixed_electron"):
            wxml_files = self.find_files([".wxml"])
            tsx_files = self.find_files([".tsx", ".jsx"])
            return len(tsx_files) > 0 and len(wxml_files) == 0
        return False
    
    def is_electron(self) -> bool:
        return self.project_type in ("electron", "mixed_electron")
    
    def safe_read(self, file_path: str) -> str:
        """安全读取文件内容，带缓存"""
        if file_path in self._file_cache:
            return self._file_cache[file_path]
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
        except Exception as e:  # noqa: broad exception handling
            content = ""
        
        self._file_cache[file_path] = content
        return content

    def is_file_in_project(self, file_path: str) -> bool:
        """判断文件是否在项目扫描范围内（零磁盘IO，O(1) 内存查找）

        v4.6.1 性能优化：替代 os.path.isfile，规避远程文件系统 I/O 抖动导致的随机卡死。
        注意：只对扫描范围内的文件有效；扫描范围外的路径一律返回 False。
        """
        self._ensure_walk_cache()
        return file_path in self._cached_file_set

    def is_dir_in_project(self, dir_path: str) -> bool:
        """判断目录是否在项目扫描范围内（零磁盘IO，O(1) 内存查找）

        v4.6.1 性能优化：替代 os.path.isdir，规避远程文件系统 I/O 抖动导致的随机卡死。
        注意：只对扫描范围内的目录有效；扫描范围外的路径一律返回 False。
        """
        self._ensure_walk_cache()
        # 规范化路径分隔符
        d = dir_path.rstrip('/\\')
        return d in self._cached_dir_set
    
    def _ensure_walk_cache(self):
        """确保完整目录遍历结果已缓存（只遍历一次，线程安全）"""
        if self._all_walk_cache is not None:
            return
        
        # 双重检查锁：避免多线程重复 os.walk
        with self._walk_lock:
            if self._all_walk_cache is not None:
                return
            
            # 默认排除目录（精确匹配）
            default_exclude_dirs = {
                '__pycache__', '.git', 'node_modules', '.venv', 'venv',
                'miniprogram_npm', '.pymysql', 'ec-canvas', '.mypy_cache',
                '.pytest_cache', '.ruff_cache', 'dist', 'build', '.eggs',
                'rules', 'skills', '.skills', 'backups', 'backup',
                '.tox', '.nox', '.coverage', 'site-packages',
                # 煋鉴自身缓存/历史目录（v4.2.1修复：避免缓存文件被扫描导致增量失效）
                '.xinpect_cache', '.qa_history',
            }
            # 前缀匹配排除（v4.2.2修复：backup_20260725等带后缀的备份目录）
            _EXCLUDE_PREFIXES = ('backup', 'bak', '_backup', 'old_', '.backup')
            
            all_files = []  # [(fpath, rel_to_search_path, filename)]
            search_paths = []
            if self.project_path and os.path.isdir(self.project_path):
                search_paths.append(self.project_path)
            if self.backend_path and self.backend_path != self.project_path and os.path.isdir(self.backend_path):
                search_paths.append(self.backend_path)
            
            for search_path in search_paths:
                for root, dirs, files in os.walk(search_path):
                    dirs[:] = [d for d in dirs 
                               if d not in default_exclude_dirs 
                               and not d.startswith(_EXCLUDE_PREFIXES)]
                    for f in files:
                        fpath = os.path.join(root, f)
                        rel = os.path.relpath(fpath, search_path)
                        # 跳过规则定义文件
                        if rel.startswith('rules' + os.sep):
                            continue
                        # 跳过煋鉴自身缓存文件（v4.2.1修复）
                        if f == '.qa_cache.json':
                            continue
                        all_files.append((fpath, rel, f))
            
            self._all_walk_cache = all_files
            # v4.6.1 零磁盘IO改造：基于 walk 结果派生文件/目录集合
            # 规则执行阶段用 O(1) 内存查找替代 os.path.isfile/isdir 系统调用
            file_set = set()
            dir_set = set()
            for fpath, rel, f in all_files:
                file_set.add(fpath)
                # 逐级加入所有父目录
                d = os.path.dirname(fpath)
                while d and d not in dir_set:
                    dir_set.add(d)
                    parent = os.path.dirname(d)
                    if parent == d:  # 到达根目录
                        break
                    d = parent
            self._cached_file_set = frozenset(file_set)
            self._cached_dir_set = frozenset(dir_set)
            # SCAN_EXCLUDE 改为懒加载，避免初始化时全量文件IO
            # 由 _ensure_scan_exclude() 在需要时按需检查

    def _ensure_scan_exclude(self):
        """懒加载检查 [SCAN_EXCLUDE] 标记文件，只在首次访问时检查

        优化 1：只检查代码/配置类文件（有实际内容的文件），
        跳过图片、字体、二进制等不可能包含标记的文件，大幅减少IO。
        优化 2：使用 ThreadPoolExecutor 并行读取文件头，
        362 个文件的串行 IO 6.4s 优化为 < 0.5s。
        """
        if self._scan_exclude_files is not None:
            return
        with self._walk_lock:
            if self._scan_exclude_files is not None:
                return
            # 只检查可能包含文本标记的文件扩展名
            _checkable_exts = {
                '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs',
                '.c', '.cpp', '.h', '.hpp', '.cs', '.php', '.rb', '.swift', '.kt',
                '.json', '.yaml', '.yml', '.xml', '.html', '.css', '.vue',
                '.md', '.txt', '.conf', '.cfg', '.ini', '.env', '.sh',
                '.wxml', '.wxss', '.json5', '.toml',
            }
            # 预筛选待检查文件（扩展名过滤，零IO）
            candidate_files = []
            for fpath, rel, f in self._all_walk_cache or []:
                dot_idx = f.rfind('.')
                if dot_idx < 0:
                    continue
                ext = f[dot_idx:].lower()
                if ext not in _checkable_exts:
                    continue
                candidate_files.append(fpath)

            scan_exclude_set = set()
            if candidate_files:
                import concurrent.futures

                # v4.6.1 优化：优先复用 _file_cache 中已预读的内容，
                # 避免 prefetch_all_files 之后又重复磁盘 IO
                def _check_cached(fp):
                    """优先查内存缓存，命中则零IO判断"""
                    cached = self._file_cache.get(fp)
                    if cached is not None:
                        return fp if '[SCAN_EXCLUDE]' in cached[:200] else None
                    # 未命中缓存才读磁盘（只读 200 字节）
                    try:
                        with open(fp, 'r', encoding='utf-8', errors='ignore') as fh:
                            header = fh.read(200)
                            if '[SCAN_EXCLUDE]' in header:
                                return fp
                    except Exception:
                        pass
                    return None

                # 先用缓存快速过滤（零 IO），未命中的再走磁盘并行
                cached_hits = 0
                need_disk = []
                for fp in candidate_files:
                    cached = self._file_cache.get(fp)
                    if cached is not None:
                        cached_hits += 1
                        if '[SCAN_EXCLUDE]' in cached[:200]:
                            scan_exclude_set.add(fp)
                    else:
                        need_disk.append(fp)

                if need_disk:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
                        for result in executor.map(_check_cached, need_disk):
                            if result is not None:
                                scan_exclude_set.add(result)
            self._scan_exclude_files = scan_exclude_set

    def get_all_files(self, exclude_dirs: set = None) -> list:
        """获取所有文件路径列表（基于缓存，避免重复os.walk）"""
        self._ensure_walk_cache()
        self._ensure_scan_exclude()
        extra_exclude = exclude_dirs or set()
        results = []
        for fpath, rel, f in self._all_walk_cache:
            if fpath in self._scan_exclude_files:
                continue
            if extra_exclude:
                path_parts = rel.replace('\\', '/').split('/')
                if any(part in extra_exclude for part in path_parts[:-1]):
                    continue
            results.append(fpath)
        return results

    def get_all_files_with_size(self, exclude_dirs: set = None) -> list:
        """获取所有文件路径和大小（基于缓存，文件大小也缓存）"""
        self._ensure_walk_cache()
        self._ensure_scan_exclude()
        extra_exclude = exclude_dirs or set()
        
        # 文件大小缓存（首次访问时一次性统计，后续直接复用）
        if not hasattr(self, '_file_size_cache'):
            self._file_size_cache = {}
            # 一次性批量获取所有文件大小
            for fpath, rel, f in self._all_walk_cache:
                try:
                    self._file_size_cache[fpath] = os.path.getsize(fpath)
                except Exception:
                    self._file_size_cache[fpath] = 0
        
        results = []
        for fpath, rel, f in self._all_walk_cache:
            if fpath in self._scan_exclude_files:
                continue
            if extra_exclude:
                path_parts = rel.replace('\\', '/').split('/')
                if any(part in extra_exclude for part in path_parts[:-1]):
                    continue
            results.append((fpath, self._file_size_cache.get(fpath, 0)))
        return results

    def find_files_by_glob(self, pattern: str) -> List[str]:
        """Find files matching a glob pattern (e.g. '**/*.test.*', '.github/workflows/*.yml').
        
        v4.6.1 优化：基于 _all_walk_cache 过滤，避免每次调用 glob.glob(recursive=True)
        多次调用时从 O(N*M) 降到 O(N)，N=文件数，M=调用次数
        """
        import fnmatch
        self._ensure_walk_cache()
        self._ensure_scan_exclude()
        
        # 将 glob 模式转为相对路径匹配
        # **/ 开头的模式匹配任意深度
        pat = pattern
        if pat.startswith('**/'):
            # 匹配任意层级，用 basename 或任意路径段匹配
            suffix_pat = pat[3:]  # 去掉 **/
            results = []
            for fpath, rel, f in self._all_walk_cache:
                if fpath in self._scan_exclude_files:
                    continue
                # 用相对路径匹配
                rel_fwd = rel.replace('\\', '/')
                if fnmatch.fnmatch(rel_fwd, suffix_pat) or fnmatch.fnmatch(rel_fwd, '*/' + suffix_pat):
                    results.append(fpath)
                elif fnmatch.fnmatch(f, suffix_pat):
                    # 也匹配纯文件名模式（如 *.test.ts）
                    results.append(fpath)
            return results
        else:
            # 固定开头的模式，直接匹配相对路径
            results = []
            for fpath, rel, f in self._all_walk_cache:
                if fpath in self._scan_exclude_files:
                    continue
                rel_fwd = rel.replace('\\', '/')
                if fnmatch.fnmatch(rel_fwd, pat):
                    results.append(fpath)
            return results

    def find_files(self, extensions: list, exclude_dirs: list = None, exclude_files: list = None) -> List[str]:
        """查找指定扩展名的文件（基于缓存过滤，避免重复os.walk）"""
        # 确保完整遍历已缓存
        self._ensure_walk_cache()
        # SCAN_EXCLUDE 检查（懒加载，只调用一次）
        self._ensure_scan_exclude()
        
        # 构建排除集合
        extra_exclude_dirs = set(exclude_dirs or self.config.get("exclude_dirs", []))
        extra_exclude_files = set(exclude_files or self.config.get("exclude_files", []))
        
        results = []
        for fpath, rel, f in self._all_walk_cache:
            # [SCAN_EXCLUDE] 检查
            if fpath in self._scan_exclude_files:
                continue
            # 额外排除文件
            if f in extra_exclude_files:
                continue
            # 额外排除目录（检查路径中是否包含排除的目录名）
            if extra_exclude_dirs:
                path_parts = rel.replace('\\', '/').split('/')
                if any(part in extra_exclude_dirs for part in path_parts[:-1]):
                    continue
            # 扩展名过滤
            if any(f.endswith(ext) for ext in extensions):
                results.append(fpath)
        
        # 缓存无过滤条件的结果
        if not extra_exclude_dirs and not extra_exclude_files and self.incremental_files is None:
            cache_key = tuple(sorted(extensions))
            self._files_by_ext[cache_key] = results

        # v3.5: 增量模式过滤
        if self.incremental_files is not None:
            results = [f for f in results if f in self.incremental_files]

        # v1.1.3: 版本限制 - max_files 文件数上限
        max_files = self.config.get("max_files", 0)
        if max_files and max_files > 0 and len(results) > max_files:
            # 优先保留关键文件（入口文件、配置文件）
            priority_keywords = ['app', 'main', 'index', 'config', 'server', 'api']
            priority_files = []
            other_files = []
            for f in results:
                basename = os.path.basename(f).lower()
                if any(kw in basename for kw in priority_keywords):
                    priority_files.append(f)
                else:
                    other_files.append(f)
            results = (priority_files + other_files)[:max_files]

        return results
    
    # ===== v2.9.1 性能优化：FileRegistry预处理层 =====
    def prefetch_all_files(self, extensions: list = None) -> int:
        """一次性并行预读所有文件到缓存，后续safe_read()全部命中内存"""
        import concurrent.futures
        if extensions is None:
            extensions = [".py", ".js", ".ts", ".jsx", ".tsx", ".wxml", ".wxss",
                         ".json", ".html", ".css", ".vue", ".java", ".go", ".rs",
                         ".c", ".cpp", ".cs", ".php", ".rb", ".swift", ".kt"]
        all_files = self.find_files(extensions)
        to_read = [f for f in all_files if f not in self._file_cache]
        if not to_read:
            return len(all_files)
        def _read_one(fpath):
            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                    return fpath, f.read()
            except Exception as e:  # noqa: broad exception handling
                return fpath, ""
        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
            for fpath, content in executor.map(_read_one, to_read):
                self._file_cache[fpath] = content
        return len(all_files)

    # ===== 文件预筛选（按大脑类型） =====
    _BRAIN_FILE_FILTERS = {
        "business_security": {
            "include_keywords": ["model", "view", "controller", "service", "api", "route",
                "handler", "endpoint", "auth", "permission", "payment", "order", "user",
                "admin", "manage", "crud", "dao", "repository", "schema", "validator",
                "middleware", "urls", "forms", "serializer", "resource"],
            "include_exts": [".py", ".js", ".ts", ".java", ".go"],
            "exclude_keywords": ["test_", "_test", "conftest", "migration", "migrate",
                "__init__", "setup.py", "manage.py", "wsgi", "asgi", ".min."],
            "exclude_dirs": ["test", "tests", "migrations", "fixtures", "static",
                "assets", "docs", "scripts"],
        },
        "security": {
            "include_exts": [".py", ".js", ".ts", ".jsx", ".tsx", ".vue", ".java", ".go", ".php", ".html"],
            "exclude_keywords": [".min.", "vendor", "node_modules"],
            "exclude_dirs": ["node_modules", "dist", "build", "vendor"],
        },
        "frontend": {
            "include_exts": [".wxml", ".wxss", ".vue", ".jsx", ".tsx", ".css", ".scss", ".less", ".html"],
            "exclude_keywords": [".min.", "vendor"],
            "exclude_dirs": ["node_modules", "dist", "build", "vendor"],
        },
        "performance": {
            "include_exts": [".py", ".js", ".ts", ".jsx", ".tsx", ".vue", ".java", ".go"],
            "exclude_keywords": [".min.", "vendor", "node_modules", "test_", "_test"],
            "exclude_dirs": ["node_modules", "dist", "build", "test", "tests"],
        },
        "dependency": {
            "include_exts": [".py", ".js", ".ts", ".json", ".toml", ".yaml", ".yml", ".lock"],
            "exclude_keywords": [".min.", "vendor"],
            "exclude_dirs": ["node_modules", "dist", "build", "vendor"],
        },
        "architecture": {
            "include_exts": [".py", ".js", ".ts", ".jsx", ".tsx", ".vue", ".java", ".go"],
            "exclude_keywords": [".min.", "vendor"],
            "exclude_dirs": ["node_modules", "dist", "build", "vendor"],
        },
    }

    def get_filtered_files(self, filter_name: str) -> list:
        """按大脑/规则类别获取预筛选文件（带缓存）"""
        cache_key = "_filtered_" + filter_name
        cached = self._file_cache.get(cache_key)
        if cached is not None:
            return cached
        filt = self._BRAIN_FILE_FILTERS.get(filter_name)
        if not filt:
            result = self.find_files([".py", ".js", ".ts"])
            self._file_cache[cache_key] = result
            return result
        all_files = self.find_files(filt["include_exts"])
        include_kw = set(filt.get("include_keywords", []))
        exclude_kw = set(filt.get("exclude_keywords", []))
        exclude_dirs = set(filt.get("exclude_dirs", []))
        result = []
        for fpath in all_files:
            rel = os.path.relpath(fpath, self.project_path).replace(os.sep, '/').lower()
            basename = os.path.basename(rel)
            path_parts = rel.split('/')
            if any(d in path_parts[:-1] for d in exclude_dirs):
                continue
            if any(ek in basename for ek in exclude_kw):
                continue
            if include_kw and not any(ik in basename for ik in include_kw):
                continue
            result.append(fpath)
        self._file_cache[cache_key] = result
        return result

    def get_backend_py_files(self) -> List[str]:
        """获取所有后端.py文件"""
        if not self.backend_path:
            return []
        exclude_files = set(self.config.get("backend_exclude_files", []))
        if os.path.isfile(self.backend_path):
            return [self.backend_path]
        all_files = self.find_files([".py"])
        # 只返回backend_path下的文件
        result = []
        for f in all_files:
            if not f.startswith(self.backend_path):
                continue
            basename = os.path.basename(f)
            if basename in exclude_files or basename == "__init__.py":
                continue
            result.append(f)
        return result
    
    def get_backend_content(self) -> str:
        """获取主后端文件内容"""
        if not self.backend_path:
            return ""
        if os.path.isfile(self.backend_path):
            return self.safe_read(self.backend_path)
        candidate = os.path.join(self.backend_path, "index_v2.py")
        if os.path.isfile(candidate):
            return self.safe_read(candidate)
        # 找主入口文件
        for name in ("app.py", "main.py", "server.py", "__init__.py"):
            candidate = os.path.join(self.backend_path, name)
            if os.path.isfile(candidate):
                return self.safe_read(candidate)
        # 找第一个.py文件
        py_files = self.get_backend_py_files()
        if py_files:
            return self.safe_read(py_files[0])
        return ""
    
    def get_all_backend_content(self) -> str:
        """获取所有后端Python文件内容拼接"""
        parts = []
        for f in self.get_backend_py_files():
            content = self.safe_read(f)
            if content:
                parts.append(f"# === {os.path.basename(f)} ===\n{content}")
        return "\n\n".join(parts)

    # ===== 项目画像构建（转发到 project_profiler，保持接口不变） =====
    def build_profile(self):
        """构建项目画像（转发到 project_profiler._build_project_profile）"""
        from core.project_profiler import _build_project_profile
        profile = _build_project_profile(
            self.project_path,
            self.backend_path,
            self.config,
            self.project_type,
        )
        self.project_profile = profile
        return profile
    
    def _get_subpkg_roots(self) -> set:
        """从app.json中解析子包根目录集合"""
        app_json_path = os.path.join(self.project_path, "app.json")
        if not os.path.isfile(app_json_path):
            return set()
        try:
            aj = json.loads(self.safe_read(app_json_path))
            return {sp["root"].rstrip("/") for sp in aj.get("subpackages", []) if sp.get("root")}
        except Exception as e:  # noqa: broad exception handling
            return set()

    def _sum_dir_size(self, dir_path: str, exclude_dirs: list) -> int:
        """递归计算目录大小（字节）"""
        total = 0
        for root, dirs, files in os.walk(dir_path):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for fn in files:
                try:
                    total += os.path.getsize(os.path.join(root, fn))
                except Exception as e:  # noqa: broad exception handling
                    pass
        return total

    def _estimate_main_package_size(self) -> float:
        """估算小程序主包大小（MB）"""
        try:
            subpkg_roots = self._get_subpkg_roots()
            exclude_dirs = self.config.get("exclude_dirs", [])
            total_size = 0

            for item in os.listdir(self.project_path):
                if item in subpkg_roots or item in exclude_dirs:
                    continue
                item_path = os.path.join(self.project_path, item)
                if os.path.isdir(item_path):
                    total_size += self._sum_dir_size(item_path, exclude_dirs)
                elif os.path.isfile(item_path):
                    try:
                        total_size += os.path.getsize(item_path)
                    except Exception as e:  # noqa: broad exception handling
                        pass

            return round(total_size / (1024 * 1024), 2)
        except Exception as e:  # noqa: broad exception handling
            return 0.0
    
    def _estimate_total_package_size(self) -> float:
        """估算小程序总包大小（MB）"""
        try:
            total_size = 0
            exclude_dirs = self.config.get("exclude_dirs", [])
            for root, dirs, files in os.walk(self.project_path):
                dirs[:] = [d for d in dirs if d not in exclude_dirs]
                for fn in files:
                    fp = os.path.join(root, fn)
                    try:
                        total_size += os.path.getsize(fp)
                    except Exception as e:  # noqa: broad exception handling
                        pass
            return round(total_size / (1024 * 1024), 2)
        except Exception as e:  # noqa: broad exception handling
            return 0.0
