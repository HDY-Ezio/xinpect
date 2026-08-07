#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增量检查模式 - QA质检框架v3.5

基于 git diff + 文件哈希缓存，只扫描变更文件。
全量扫描从分钟级降到秒级。

两种模式：
1. Git模式：项目是git仓库时，用 git diff --name-only 获取变更文件
2. 哈希模式：非git项目时，用文件内容哈希+mtime对比缓存

缓存文件：{project_path}/.qa_cache.json
"""

import os
import json
import hashlib
import subprocess
from typing import List, Set, Optional, Dict
from pathlib import Path


# 缓存文件名
CACHE_FILENAME = ".qa_cache.json"

# 哈希缓存最大文件数（超过则清理旧条目）
MAX_CACHE_ENTRIES = 5000


class IncrementalChecker:
    """增量检查器"""

    def __init__(self, project_path: str, enabled: bool = True):
        self.project_path = os.path.abspath(project_path)
        self.enabled = enabled
        self._cache: Dict[str, dict] = {}
        self._cache_loaded = False
        self._is_git_repo = self._check_git_repo()

    def _check_git_repo(self) -> bool:
        """检测项目是否是git仓库"""
        if not self.enabled:
            return False
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--is-inside-work-tree'],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0 and result.stdout.strip() == 'true'
        except Exception as e:  # noqa: broad exception handling
            return False

    @property
    def cache_path(self) -> str:
        """缓存文件路径"""
        return os.path.join(self.project_path, CACHE_FILENAME)

    def _load_cache(self):
        """加载文件哈希缓存"""
        if self._cache_loaded:
            return
        self._cache_loaded = True
        try:
            if os.path.exists(self.cache_path):
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    self._cache = json.load(f)
        except (json.JSONDecodeError, IOError):
            self._cache = {}

    def _save_cache(self):
        """保存文件哈希缓存"""
        try:
            # 清理过多的缓存条目
            if len(self._cache) > MAX_CACHE_ENTRIES:
                # 按最后检查时间排序，保留最新的
                sorted_items = sorted(
                    self._cache.items(),
                    key=lambda x: x[1].get('last_checked', 0),
                    reverse=True,
                )
                self._cache = dict(sorted_items[:MAX_CACHE_ENTRIES])

            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except IOError:  # noqa: intentional empty handler
            pass

    def _file_hash(self, filepath: str) -> Optional[str]:
        """计算文件内容的SHA256哈希（用于增量缓存校验）"""
        try:
            with open(filepath, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()
        except (IOError, OSError):
            return None

    def _get_git_changed_files(self, base: str = 'HEAD') -> Set[str]:
        """通过git diff获取变更文件列表"""
        changed = set()
        try:
            # 获取工作区相对HEAD的变更（包括未提交的）
            result = subprocess.run(
                ['git', 'diff', '--name-only', base, '--relative'],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    line = line.strip()
                    if line:
                        full_path = os.path.join(self.project_path, line)
                        if os.path.exists(full_path):
                            changed.add(full_path)

            # 也获取暂存区变更
            result2 = subprocess.run(
                ['git', 'diff', '--name-only', '--cached', '--relative'],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result2.returncode == 0:
                for line in result2.stdout.strip().split('\n'):
                    line = line.strip()
                    if line:
                        full_path = os.path.join(self.project_path, line)
                        if os.path.exists(full_path):
                            changed.add(full_path)

            # 获取未跟踪的新文件
            result3 = subprocess.run(
                ['git', 'ls-files', '--others', '--exclude-standard'],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result3.returncode == 0:
                for line in result3.stdout.strip().split('\n'):
                    line = line.strip()
                    if line:
                        full_path = os.path.join(self.project_path, line)
                        if os.path.exists(full_path):
                            changed.add(full_path)

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):  # noqa: intentional empty handler
            pass
        return changed

    def _get_hash_changed_files(self, all_files: List[str]) -> Set[str]:
        """通过文件哈希对比缓存获取变更文件列表"""
        self._load_cache()
        changed = set()

        for filepath in all_files:
            if not os.path.exists(filepath):
                # 文件不存在，从缓存中移除
                self._cache.pop(filepath, None)
                continue

            # 快速检查：mtime未变则跳过
            stat = os.stat(filepath)
            mtime = stat.st_mtime
            cached = self._cache.get(filepath)

            if cached and cached.get('mtime') == mtime:
                # mtime一致，文件未修改
                continue

            # mtime变了，检查哈希
            file_hash = self._file_hash(filepath)
            if file_hash is None:
                changed.add(filepath)
                continue

            if cached and cached.get('hash') == file_hash:
                # 哈希一致（可能只是touch了一下），更新mtime
                self._cache[filepath] = {
                    'mtime': mtime,
                    'hash': file_hash,
                    'last_checked': mtime,
                }
                continue

            # 哈希也变了，文件确实修改了
            changed.add(filepath)
            self._cache[filepath] = {
                'mtime': mtime,
                'hash': file_hash,
                'last_checked': mtime,
            }

        return changed

    def _filter_changed_against_allowed(self, changed: list, all_files: list) -> set:
        """Filter changed files against allowed file list or known extensions."""
        _ALLOWED_EXTS = {'.py', '.js', '.ts', '.jsx', '.tsx', '.wxml', '.wxss',
                         '.json', '.html', '.css', '.vue', '.go', '.java', '.rs', '.cpp', '.c'}
        filtered = set()
        for f in changed:
            # Check if file matches any allowed file
            matched = False
            for af in all_files:
                try:
                    if os.path.exists(f) and os.path.exists(af) and os.path.samefile(f, af):
                        matched = True
                        break
                except OSError:  # noqa: intentional empty handler
                    pass
            if matched:
                filtered.add(f)
            elif os.path.splitext(f)[1] in _ALLOWED_EXTS:
                filtered.add(f)
        return filtered

    def get_changed_files(self, all_files: List[str] = None) -> tuple:
        """
        获取需要检查的变更文件列表

        返回: (changed_files, total_files, mode)
        - changed_files: 需要检查的文件列表
        - total_files: 总文件数
        - mode: 'git' | 'hash' | 'full'
        """
        if not self.enabled:
            return (all_files or [], len(all_files or []), 'full')

        # 优先使用git diff
        if self._is_git_repo:
            changed = self._get_git_changed_files()
            if all_files:
                # 过滤：只保留在all_files中的变更文件
                # 同时保留扩展名匹配
                changed_filtered = self._filter_changed_against_allowed(changed, all_files)

                if changed_filtered:
                    return (list(changed_filtered), len(all_files or changed_filtered), 'git')

            # git无变更时，也要检查缓存中未变文件是否已被删除
            if all_files and not changed:
                # 验证缓存中已删除的文件
                self._load_cache()
                for f in list(self._cache.keys()):
                    if not os.path.exists(f):
                        self._cache.pop(f, None)
                return ([], len(all_files), 'git')

        # 降级到哈希模式
        if all_files:
            changed = self._get_hash_changed_files(all_files)
            return (list(changed), len(all_files), 'hash')

        return (all_files or [], len(all_files or []), 'full')

    def update_cache_after_check(self, checked_files: List[str]):
        """检查完成后更新缓存"""
        if not self.enabled or self._is_git_repo:
            # git模式下不需要哈希缓存
            return

        self._load_cache()
        for filepath in checked_files:
            if os.path.exists(filepath):
                stat = os.stat(filepath)
                file_hash = self._file_hash(filepath)
                if file_hash:
                    self._cache[filepath] = {
                        'mtime': stat.st_mtime,
                        'hash': file_hash,
                        'last_checked': stat.st_mtime,
                    }

        self._save_cache()

    def clear_cache(self):
        """清除缓存"""
        self._cache = {}
        try:
            if os.path.exists(self.cache_path):
                os.remove(self.cache_path)
        except IOError:  # noqa: intentional empty handler
            pass


# 全局单例
_incremental_checker_instances: Dict[str, IncrementalChecker] = {}


def get_incremental_checker(project_path: str, enabled: bool = True) -> IncrementalChecker:
    """获取增量检查器单例"""
    abs_path = os.path.abspath(project_path)
    if abs_path not in _incremental_checker_instances:
        _incremental_checker_instances[abs_path] = IncrementalChecker(abs_path, enabled)
    return _incremental_checker_instances[abs_path]