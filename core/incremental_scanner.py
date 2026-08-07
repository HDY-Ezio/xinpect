#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增量扫描引擎 (IncrementalScanner) - 煋鉴 v4.2

文件级 hash 缓存 + 结果缓存，只扫描改动过的文件。
与 v3.5 的 incremental.py（文件变更检测）不同，本引擎在此基础上增加：
1. 完整的扫描结果缓存（不仅是文件变更检测）
2. 规则版本号校验（规则集变了就全量重扫）
3. 结果合并（未变文件复用上次结果 + 变了的文件重新扫描）

缓存存储：
    {project_path}/.xinpect_cache/
        file_hash.json       - 文件状态缓存（mtime + size + hash）
        rule_version.txt     - 规则集版本标识
        results_cache.json   - 上次扫描的结果（按文件索引）

设计原则：
- 结果正确性优先：宁可全量重扫，不能漏报
- 缓存键 = 文件路径 + 大小 + mtime + 内容hash前8位 + 规则版本
- 缓存目录加入 .gitignore 概念

煋旺智能 / Xinpect
"""

import os
import json
import hashlib
import logging
from typing import Dict, List, Set, Tuple, Optional, Any
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

# 缓存目录名
CACHE_DIR_NAME = ".xinpect_cache"

# 缓存文件最大条目数
MAX_FILE_CACHE = 10000

# 缓存结果最大条目数（按结果条数计）
MAX_RESULT_CACHE = 50000


class IncrementalScanner:
    """增量扫描引擎

    文件级 hash 缓存 + 结果缓存，只扫描改动过的文件。
    在 RuleRunner.run_all() 中接入。

    使用方式：
        scanner = IncrementalScanner(project_path)
        changed, unchanged = scanner.get_changed_files(all_files)
        # ... 只对 changed_files 执行扫描 ...
        # 获取未变文件的缓存结果
        cached = scanner.get_cached_results(unchanged)
        # 合并结果，更新缓存
        scanner.update_cache(changed_files, new_results)
    """

    def __init__(self, project_path: str, rules_dir: str = None, enabled: bool = True):
        """
        Args:
            project_path: 项目根目录路径
            rules_dir: 规则目录路径（用于计算规则版本号）
            enabled: 是否启用增量扫描
        """
        self.project_path = os.path.abspath(project_path) if project_path else ""
        self.rules_dir = rules_dir
        self.enabled = enabled and bool(self.project_path)

        # 缓存目录
        self.cache_dir = os.path.join(self.project_path, CACHE_DIR_NAME) if self.project_path else ""

        # 文件 hash 缓存 {file_path: {size, mtime, hash}}
        self._file_cache: Dict[str, dict] = {}

        # 结果缓存 {file_path: [result_dict, ...]}
        self._result_cache: Dict[str, list] = {}

        # 规则版本号（规则集变化时失效缓存）
        self._rule_version: str = ""

        # 是否已加载缓存
        self._cache_loaded = False

        # 本次扫描统计
        self._stats = {
            "total_files": 0,
            "changed_files": 0,
            "unchanged_files": 0,
            "cached_results": 0,
            "new_results": 0,
            "mode": "full",  # "full" or "incremental"
            "cache_hit_rate": 0.0,
        }

    # ------------------------------------------------------------------
    # 缓存目录管理
    # ------------------------------------------------------------------

    def _ensure_cache_dir(self):
        """确保缓存目录存在"""
        if not self.cache_dir:
            return
        try:
            if not os.path.isdir(self.cache_dir):
                os.makedirs(self.cache_dir, exist_ok=True)
            # 创建 .gitignore（如果不存在）
            gitignore = os.path.join(self.cache_dir, ".gitignore")
            if not os.path.exists(gitignore):
                try:
                    with open(gitignore, "w") as f:
                        f.write("# 煋鉴增量扫描缓存目录\n*\n!.gitignore\n")
                except Exception:
                    pass
        except Exception:
            pass

    @property
    def _file_cache_path(self) -> str:
        return os.path.join(self.cache_dir, "file_hash.json")

    @property
    def _result_cache_path(self) -> str:
        return os.path.join(self.cache_dir, "results_cache.json")

    @property
    def _rule_version_path(self) -> str:
        return os.path.join(self.cache_dir, "rule_version.txt")

    # ------------------------------------------------------------------
    # 规则版本号计算
    # ------------------------------------------------------------------

    def _compute_rule_version(self) -> str:
        """计算规则集版本号（基于规则目录的修改时间 + 主要文件大小）

        规则集变化时缓存失效，确保规则更新后全量重扫。
        """
        if not self.rules_dir or not os.path.isdir(self.rules_dir):
            return "unknown"

        try:
            version_parts = []
            # 遍历规则目录，收集修改时间 + 大小
            for root, dirs, files in os.walk(self.rules_dir):
                # 跳过隐藏目录和__pycache__
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
                for fname in sorted(files):
                    if fname.startswith('_') or fname.endswith('.pyc'):
                        continue
                    fpath = os.path.join(root, fname)
                    try:
                        st = os.stat(fpath)
                        version_parts.append(f"{fname}:{st.st_size}:{int(st.st_mtime)}")
                    except Exception:
                        pass

            if version_parts:
                content = "|".join(version_parts)
                return hashlib.md5(content.encode()).hexdigest()[:12]
        except Exception:
            pass

        return "unknown"

    def _load_rule_version(self) -> str:
        """从缓存加载上次的规则版本号"""
        try:
            if os.path.exists(self._rule_version_path):
                with open(self._rule_version_path, "r") as f:
                    return f.read().strip()
        except Exception:
            pass
        return ""

    def _save_rule_version(self, version: str):
        """保存规则版本号"""
        try:
            with open(self._rule_version_path, "w") as f:
                f.write(version)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 缓存加载 / 保存
    # ------------------------------------------------------------------

    def _load_cache(self):
        """加载文件缓存和结果缓存"""
        if self._cache_loaded or not self.enabled:
            return
        self._cache_loaded = True

        if not self.cache_dir or not os.path.isdir(self.cache_dir):
            return

        # 检查规则版本
        current_version = self._compute_rule_version()
        self._rule_version = current_version
        cached_version = self._load_rule_version()

        rule_version_changed = (cached_version and cached_version != current_version)
        if rule_version_changed:
            # 规则集变了：清空结果缓存（需要重新扫描所有文件）
            # 但保留文件hash缓存（文件本身没变，只是规则变了）
            logger.info("[IncrementalScanner] 规则集已更新（版本 %s → %s），全量重扫",
                        cached_version[:8] if cached_version else "none",
                        current_version[:8])
            self._result_cache = {}
            # 注意：不return，继续加载文件缓存

        # 加载文件 hash 缓存
        try:
            if os.path.exists(self._file_cache_path):
                with open(self._file_cache_path, "r", encoding="utf-8") as f:
                    self._file_cache = json.load(f)
        except (json.JSONDecodeError, IOError):
            self._file_cache = {}

        # 如果规则版本没变，才加载结果缓存
        if not rule_version_changed:
            try:
                if os.path.exists(self._result_cache_path):
                    with open(self._result_cache_path, "r", encoding="utf-8") as f:
                        self._result_cache = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._result_cache = {}

    def _save_cache(self):
        """保存缓存到磁盘"""
        if not self.enabled or not self.cache_dir:
            return

        self._ensure_cache_dir()

        # 确保规则版本已计算
        if not self._rule_version:
            self._rule_version = self._compute_rule_version()

        # 限制缓存大小
        if len(self._file_cache) > MAX_FILE_CACHE:
            # 按最后检查时间排序，保留最新的
            sorted_items = sorted(
                self._file_cache.items(),
                key=lambda x: x[1].get('last_checked', 0),
                reverse=True,
            )
            self._file_cache = dict(sorted_items[:MAX_FILE_CACHE])

        # 结果缓存按条目数限制
        total_results = sum(len(v) for v in self._result_cache.values())
        if total_results > MAX_RESULT_CACHE:
            # 简单策略：只保留最近修改的文件结果
            sorted_files = sorted(
                self._result_cache.keys(),
                key=lambda f: self._file_cache.get(f, {}).get('last_checked', 0),
                reverse=True,
            )
            new_cache = {}
            count = 0
            for f in sorted_files:
                if count >= MAX_RESULT_CACHE:
                    break
                new_cache[f] = self._result_cache[f]
                count += len(self._result_cache[f])
            self._result_cache = new_cache

        # 保存文件缓存
        try:
            with open(self._file_cache_path, "w", encoding="utf-8") as f:
                json.dump(self._file_cache, f, ensure_ascii=False, indent=2)
        except IOError:
            pass

        # 保存结果缓存
        try:
            with open(self._result_cache_path, "w", encoding="utf-8") as f:
                json.dump(self._result_cache, f, ensure_ascii=False, indent=2)
        except IOError:
            pass

        # 保存规则版本
        if self._rule_version:
            self._save_rule_version(self._rule_version)

    # ------------------------------------------------------------------
    # 文件 hash 计算
    # ------------------------------------------------------------------

    def _fast_file_hash(self, filepath: str) -> Tuple[str, int, float]:
        """计算文件的快速哈希（仅读开头+结尾各64KB）

        对于大文件，不读全部内容，只取首尾各64KB + 文件大小 + mtime。
        对 < 1MB 的小文件，读全部内容。

        Returns:
            (hash_prefix, size, mtime)
        """
        try:
            st = os.stat(filepath)
            size = st.st_size
            mtime = st.st_mtime

            if size <= 1024 * 1024:  # <= 1MB，读全部
                with open(filepath, 'rb') as f:
                    content = f.read()
                full_hash = hashlib.md5(content).hexdigest()
            else:
                # 大文件：读开头64KB + 结尾64KB
                h = hashlib.md5()
                h.update(str(size).encode())
                with open(filepath, 'rb') as f:
                    h.update(f.read(64 * 1024))  # 开头64KB
                    if size > 128 * 1024:
                        f.seek(-64 * 1024, 2)  # 结尾64KB
                        h.update(f.read(64 * 1024))
                full_hash = h.hexdigest()

            return full_hash[:12], size, mtime
        except (IOError, OSError):
            return "", 0, 0.0

    # ------------------------------------------------------------------
    # 变更检测
    # ------------------------------------------------------------------

    def get_changed_files(self, files: List[str]) -> Tuple[List[str], List[str]]:
        """检查文件列表中哪些发生了变化

        Args:
            files: 文件路径列表

        Returns:
            (changed_files: List[str], unchanged_files: List[str])
        """
        if not self.enabled or not files:
            self._stats["total_files"] = len(files or [])
            self._stats["mode"] = "full"
            return list(files or []), []

        self._load_cache()
        self._stats["total_files"] = len(files)

        changed = []
        unchanged = []

        for filepath in files:
            if not os.path.exists(filepath):
                # 文件不存在，视为已删除（不算changed，但从缓存清掉）
                self._file_cache.pop(filepath, None)
                self._result_cache.pop(filepath, None)
                continue

            file_hash, file_size, file_mtime = self._fast_file_hash(filepath)
            if not file_hash:
                changed.append(filepath)
                continue

            cached = self._file_cache.get(filepath)

            # 缓存命中：大小 + mtime + hash 全部一致
            if (cached and
                cached.get("size") == file_size and
                cached.get("mtime") == file_mtime and
                cached.get("hash") == file_hash):
                unchanged.append(filepath)
            else:
                changed.append(filepath)
                # 更新文件缓存（记录当前状态，扫描完后再更新结果缓存）
                self._file_cache[filepath] = {
                    "size": file_size,
                    "mtime": file_mtime,
                    "hash": file_hash,
                    "last_checked": file_mtime,
                }

        self._stats["changed_files"] = len(changed)
        self._stats["unchanged_files"] = len(unchanged)
        self._stats["mode"] = "incremental" if unchanged else "full"
        self._stats["cache_hit_rate"] = (
            len(unchanged) / len(files) if files else 0.0
        )

        logger.info("[IncrementalScanner] 变更检测: %d 个文件中, %d 个变化, %d 个未变 (命中率 %.1f%%)",
                    len(files), len(changed), len(unchanged),
                    self._stats["cache_hit_rate"] * 100)

        return changed, unchanged

    # ------------------------------------------------------------------
    # 缓存结果读取
    # ------------------------------------------------------------------

    def get_cached_results(self, files: List[str]) -> List[dict]:
        """获取未改动文件的缓存结果

        Args:
            files: 未改动的文件路径列表

        Returns:
            result dict 列表（兼容 RuleCheckResult.to_dict() 格式）
        """
        if not self.enabled or not files:
            return []

        self._load_cache()

        results = []
        for f in files:
            cached = self._result_cache.get(f, [])
            results.extend(cached)

        self._stats["cached_results"] = len(results)
        return results

    def get_cached_results_by_module(self, files: List[str]) -> Dict[str, List[dict]]:
        """获取按模块分组的缓存结果（与run_all的输出格式一致）

        Returns:
            {module_id: [result_dict, ...]}
        """
        if not self.enabled or not files:
            return {}

        self._load_cache()

        grouped = defaultdict(list)
        for f in files:
            cached = self._result_cache.get(f, [])
            for r in cached:
                # 从location中推断module_id（如果缓存中没存）
                mid = r.get("module_id", r.get("category", "unknown"))
                grouped[mid].append(r)

        return dict(grouped)

    # ------------------------------------------------------------------
    # 缓存更新
    # ------------------------------------------------------------------

    def update_cache(self, files: List[str], results_by_file: Dict[str, list]):
        """更新缓存

        Args:
            files: 本次扫描的文件列表
            results_by_file: {file_path: [result_dict, ...]}
                            result_dict 需要包含所有 RuleCheckResult 的字段
        """
        if not self.enabled:
            return

        self._load_cache()

        for filepath in files:
            # 更新结果缓存
            file_results = results_by_file.get(filepath, [])
            if file_results:
                self._result_cache[filepath] = file_results
            else:
                # 文件没有问题，也记录空结果（避免下次重复扫描）
                self._result_cache[filepath] = []

            # 更新文件缓存的最后检查时间
            if filepath in self._file_cache:
                self._file_cache[filepath]["last_checked"] = os.path.getmtime(filepath) if os.path.exists(filepath) else 0

        self._stats["new_results"] = sum(
            len(v) for v in results_by_file.values()
        )

        # 保存到磁盘
        self._save_cache()

    def update_cache_from_results(self, results_by_module: Dict[str, list], all_scanned_files: List[str]):
        """从模块分组结果中按文件归类后更新缓存

        Args:
            results_by_module: {module_id: [RuleCheckResult, ...]}
            all_scanned_files: 本次扫描涉及的所有文件路径
        """
        if not self.enabled:
            return

        # 按文件重组结果
        results_by_file: Dict[str, list] = defaultdict(list)

        for module_id, result_list in results_by_module.items():
            for r in result_list:
                # 从 location 中提取文件路径
                location = getattr(r, 'location', {}) or {}
                file_path = location.get('file', location.get('file_path', ''))
                if not file_path:
                    continue

                # 转换为可序列化的dict
                if hasattr(r, 'to_dict'):
                    r_dict = r.to_dict()
                elif isinstance(r, dict):
                    r_dict = dict(r)
                else:
                    continue

                # 附带 module_id，便于结果合并时分类
                r_dict["module_id"] = str(module_id)
                results_by_file[file_path].append(r_dict)

        # 对所有扫描过但没有结果的文件，也登记为空
        for f in all_scanned_files:
            if f not in results_by_file:
                results_by_file[f] = []

        self.update_cache(all_scanned_files, dict(results_by_file))

    # ------------------------------------------------------------------
    # 缓存管理
    # ------------------------------------------------------------------

    def clear_cache(self):
        """清空所有缓存"""
        self._file_cache = {}
        self._result_cache = {}
        self._rule_version = ""
        self._cache_loaded = False

        if self.cache_dir and os.path.isdir(self.cache_dir):
            try:
                import shutil
                shutil.rmtree(self.cache_dir)
            except Exception:
                pass

        logger.info("[IncrementalScanner] 缓存已清空")

    def get_stats(self) -> dict:
        """获取统计信息"""
        return dict(self._stats)

    @property
    def is_incremental_mode(self) -> bool:
        """当前是否为增量模式（有缓存命中）"""
        return self._stats["unchanged_files"] > 0
