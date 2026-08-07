#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI增强缓存管理器 v1.0
=====================
为AI增强模块提供缓存能力，大幅降低API调用成本：
- 文件哈希计算（SHA256）：相同内容不重复调LLM
- 增量检测（git diff）：只分析变更的文件
- 缓存生命周期管理：TTL过期、容量上限、LRU淘汰

缓存结构：
    .xinpect/cache/
      brain1/
        {file_hash}.json   # Brain 1的AI分析结果
      brain2/
        {file_hash}.json
      brain6/
        {file_hash}.json
      metadata.json         # 缓存元数据（创建时间、命中统计等）

缓存失效策略：
    1. 文件内容变化（哈希不匹配）
    2. 超过TTL（默认7天）
    3. 超过容量上限（默认1000个文件，LRU淘汰）
    4. 手动清理（--no-cache 或 clean_cache()）

使用方式：
    from core.cache_manager import CacheManager

    cache = CacheManager(project_path, config)
    cached = cache.load(brain_id, file_hash)
    if cached is None:
        result = call_llm(...)
        cache.save(brain_id, file_hash, result)
"""

import os
import sys
import json
import hashlib
import logging
import time
import subprocess
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_CACHE_CONFIG = {
    "enabled": True,
    "ttl_days": 7,
    "max_files": 1000,
    "cache_dir": ".xinpect/cache",
}


class CacheManager:
    """AI增强缓存管理器

    管理AI分析结果的本地缓存，支持：
    - 按大脑ID + 文件哈希 存储/读取缓存
    - 自动过期清理（TTL）
    - 容量控制（LRU淘汰最旧条目）
    - git增量检测（只分析变更文件）
    - 缓存命中统计
    """

    def __init__(self, project_path: str, config: dict = None):
        """初始化缓存管理器

        Args:
            project_path: 被扫描项目的根路径
            config: qa_config配置字典
        """
        self.project_path = os.path.abspath(project_path)
        self.config = config or {}

        # 读取缓存配置
        cache_cfg = self.config.get("cache", {})
        self.enabled = cache_cfg.get("enabled", DEFAULT_CACHE_CONFIG["enabled"])
        self.ttl_seconds = cache_cfg.get("ttl_days", DEFAULT_CACHE_CONFIG["ttl_days"]) * 86400
        self.max_files = cache_cfg.get("max_files", DEFAULT_CACHE_CONFIG["max_files"])
        cache_dir_rel = cache_cfg.get("cache_dir", DEFAULT_CACHE_CONFIG["cache_dir"])

        # 缓存根目录（相对于项目路径）
        if os.path.isabs(cache_dir_rel):
            self.cache_root = cache_dir_rel
        else:
            self.cache_root = os.path.join(self.project_path, cache_dir_rel)

        # 统计计数器
        self._stats = {
            "hits": 0,
            "misses": 0,
            "writes": 0,
            "evictions": 0,
            "expired": 0,
        }

        # 确保缓存目录存在
        if self.enabled:
            self._ensure_dirs()

    # ===== 公共API =====

    def is_enabled(self) -> bool:
        """缓存是否启用"""
        return self.enabled

    def compute_file_hash(self, file_path: str) -> Optional[str]:
        """计算单个文件的SHA256哈希

        Args:
            file_path: 文件路径（绝对或相对项目路径均可）

        Returns:
            SHA256哈希字符串，文件不可读时返回None
        """
        abs_path = self._resolve_path(file_path)
        try:
            hasher = hashlib.sha256()
            with open(abs_path, "rb") as f:
                # 分块读取，支持大文件
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    hasher.update(chunk)
            return hasher.hexdigest()
        except (OSError, IOError) as e:
            logger.debug(f"无法计算文件哈希: {abs_path} - {e}")
            return None

    def compute_batch_hashes(self, file_paths: List[str]) -> Dict[str, str]:
        """批量计算文件哈希

        Args:
            file_paths: 文件路径列表

        Returns:
            {file_path: hash} 字典，跳过不可读文件
        """
        result = {}
        for fp in file_paths:
            h = self.compute_file_hash(fp)
            if h:
                result[fp] = h
        return result

    def compute_project_hashes(
        self,
        extensions: Optional[set] = None,
        max_files: int = 0,
    ) -> Dict[str, str]:
        """扫描项目目录，计算所有代码文件的哈希

        Args:
            extensions: 要包含的文件扩展名集合，默认常见代码文件
            max_files: 最大文件数，0=不限

        Returns:
            {relative_path: hash} 字典
        """
        if extensions is None:
            extensions = {
                ".py", ".js", ".jsx", ".ts", ".tsx", ".vue",
                ".java", ".go", ".rs", ".rb", ".php", ".cs",
                ".c", ".cpp", ".h", ".hpp", ".swift", ".kt",
                ".wxml", ".wxss", ".css", ".scss", ".less",
                ".html", ".json", ".yaml", ".yml", ".toml",
            }

        skip_dirs = {
            "node_modules", ".git", "__pycache__", "venv", ".venv",
            "dist", "build", ".xinpect", ".qa_history", ".pymysql",
            "pymysql", "codeact", "archived", "ec-canvas", "pkg",
            "miniprogram_npm", "backup", "bak", "v52",
            "rules", "skills", ".skills",
        }

        result = {}
        try:
            for root, dirs, files in os.walk(self.project_path):
                # 过滤排除目录
                dirs[:] = [d for d in dirs if d not in skip_dirs]

                for fname in files:
                    ext = os.path.splitext(fname)[1].lower()
                    if ext not in extensions:
                        continue

                    abs_path = os.path.join(root, fname)
                    rel_path = os.path.relpath(abs_path, self.project_path)

                    h = self.compute_file_hash(abs_path)
                    if h:
                        result[rel_path] = h

                    if max_files > 0 and len(result) >= max_files:
                        return result
        except OSError as e:
            logger.warning(f"扫描项目目录失败: {e}")

        return result

    def get_changed_files(self, since: str = "HEAD~1") -> Optional[List[str]]:
        """通过git diff获取变更文件列表

        Args:
            since: git对比基准，默认 HEAD~1

        Returns:
            变更文件路径列表（相对路径），非git仓库返回None
        """
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", since],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return None

            files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
            return files if files else None
        except (subprocess.SubprocessError, FileNotFoundError):
            return None

    def get_changed_file_hashes(self, since: str = "HEAD~1") -> Optional[Dict[str, str]]:
        """获取变更文件的哈希（增量模式）

        Args:
            since: git对比基准

        Returns:
            {file_path: hash} 字典，非git仓库返回None
        """
        changed = self.get_changed_files(since)
        if changed is None:
            return None  # 非git仓库

        return self.compute_batch_hashes(changed)

    # ===== 缓存读写 =====

    def load(self, brain_id: str, file_hash: str) -> Optional[Dict[str, Any]]:
        """从缓存加载AI分析结果

        Args:
            brain_id: 大脑ID（"1"-"7"）
            file_hash: 文件SHA256哈希

        Returns:
            缓存的分析结果字典，缓存未命中返回None
        """
        if not self.enabled:
            self._stats["misses"] += 1
            return None

        cache_path = self._cache_file_path(brain_id, file_hash)
        if not os.path.isfile(cache_path):
            self._stats["misses"] += 1
            return None

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                entry = json.load(f)

            # 检查TTL过期
            created_at = entry.get("_created_at", 0)
            if time.time() - created_at > self.ttl_seconds:
                # 过期，删除缓存文件
                try:
                    os.remove(cache_path)
                except OSError:  # noqa: intentional empty handler
                    pass
                self._stats["expired"] += 1
                self._stats["misses"] += 1
                return None

            # 缓存命中
            self._stats["hits"] += 1
            # 更新访问时间（用于LRU淘汰）
            entry["_last_accessed"] = time.time()
            entry["_access_count"] = entry.get("_access_count", 0) + 1
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(entry, f, ensure_ascii=False)
            except OSError:
                pass  # 更新访问时间失败不影响主流程

            return entry.get("data")

        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.debug(f"缓存读取失败: brain={brain_id}, hash={file_hash[:12]}... - {e}")
            self._stats["misses"] += 1
            return None

    def load_batch(
        self, brain_id: str, file_hashes: Dict[str, str]
    ) -> Tuple[Dict[str, Dict], Dict[str, str]]:
        """批量加载缓存

        Args:
            brain_id: 大脑ID
            file_hashes: {file_path: hash} 字典

        Returns:
            (cached_results, uncached_files)
            cached_results: {file_path: 分析结果} — 命中的
            uncached_files: {file_path: hash} — 未命中的，需要调LLM
        """
        cached_results = {}
        uncached_files = {}

        for file_path, file_hash in file_hashes.items():
            result = self.load(brain_id, file_hash)
            if result is not None:
                cached_results[file_path] = result
            else:
                uncached_files[file_path] = file_hash

        return cached_results, uncached_files

    def save(self, brain_id: str, file_hash: str, data: Dict[str, Any],
             file_path: str = "") -> bool:
        """保存AI分析结果到缓存

        Args:
            brain_id: 大脑ID
            file_hash: 文件SHA256哈希
            data: 要缓存的分析结果
            file_path: 原始文件路径（用于元数据记录）

        Returns:
            是否保存成功
        """
        if not self.enabled:
            return False

        # 容量检查，必要时淘汰旧条目
        self._enforce_capacity()

        cache_path = self._cache_file_path(brain_id, file_hash)

        entry = {
            "_created_at": time.time(),
            "_last_accessed": time.time(),
            "_access_count": 0,
            "_brain_id": brain_id,
            "_file_hash": file_hash,
            "_file_path": file_path,
            "data": data,
        }

        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(entry, f, ensure_ascii=False, indent=2)
            self._stats["writes"] += 1
            return True
        except OSError as e:
            logger.warning(f"缓存写入失败: {cache_path} - {e}")
            return False

    def save_batch(
        self, brain_id: str, results: Dict[str, Tuple[str, Dict]]
    ) -> int:
        """批量保存缓存

        Args:
            brain_id: 大脑ID
            results: {file_path: (file_hash, analysis_data)} 字典

        Returns:
            成功保存的数量
        """
        saved = 0
        for file_path, (file_hash, data) in results.items():
            if self.save(brain_id, file_hash, data, file_path=file_path):
                saved += 1
        return saved

    def invalidate(self, brain_id: str, file_hash: str) -> bool:
        """使指定缓存失效

        Args:
            brain_id: 大脑ID
            file_hash: 文件哈希

        Returns:
            是否成功删除
        """
        cache_path = self._cache_file_path(brain_id, file_hash)
        try:
            if os.path.isfile(cache_path):
                os.remove(cache_path)
                return True
        except OSError:  # noqa: intentional empty handler
            pass
        return False

    def clean_cache(self, brain_id: str = "") -> int:
        """清理缓存

        Args:
            brain_id: 指定大脑ID则只清理该大脑的缓存；空字符串=清理所有

        Returns:
            清理的文件数量
        """
        removed = 0
        if brain_id:
            target_dir = os.path.join(self.cache_root, f"brain{brain_id}")
        else:
            target_dir = self.cache_root

        if not os.path.isdir(target_dir):
            return 0

        for root, dirs, files in os.walk(target_dir):
            for fname in files:
                if fname.endswith(".json"):
                    try:
                        os.remove(os.path.join(root, fname))
                        removed += 1
                    except OSError:  # noqa: intentional empty handler
                        pass

        logger.info(f"缓存清理完成: 移除{removed}个文件 (brain={brain_id or 'all'})")
        return removed

    def clean_expired(self) -> int:
        """清理过期缓存

        Returns:
            清理的文件数量
        """
        removed = 0
        now = time.time()

        for root, dirs, files in os.walk(self.cache_root):
            for fname in files:
                if not fname.endswith(".json") or fname == "metadata.json":
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        entry = json.load(f)
                    created_at = entry.get("_created_at", 0)
                    if now - created_at > self.ttl_seconds:
                        os.remove(fpath)
                        removed += 1
                except (json.JSONDecodeError, OSError, KeyError):
                    # 损坏的缓存文件也清理掉
                    try:
                        os.remove(fpath)
                        removed += 1
                    except OSError:  # noqa: intentional empty handler
                        pass

        if removed > 0:
            logger.info(f"过期缓存清理: 移除{removed}个文件")
        return removed

    # ===== 统计与元数据 =====

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息

        Returns:
            统计字典，包含命中率、文件数等
        """
        total_files = self._count_cache_files()
        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total_requests * 100) if total_requests > 0 else 0.0

        return {
            "enabled": self.enabled,
            "cache_dir": self.cache_root,
            "total_cached_files": total_files,
            "max_files": self.max_files,
            "ttl_days": self.ttl_seconds // 86400,
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "writes": self._stats["writes"],
            "evictions": self._stats["evictions"],
            "expired": self._stats["expired"],
            "hit_rate": round(hit_rate, 1),
        }

    def get_cache_summary(self) -> str:
        """获取人类可读的缓存摘要（用于报告展示）

        Returns:
            格式化的摘要字符串
        """
        stats = self.get_stats()
        if not stats["enabled"]:
            return "[缓存] 已禁用"

        parts = [
            f"[缓存] 命中{stats['hits']}次, 未命中{stats['misses']}次",
        ]
        if stats["hits"] + stats["misses"] > 0:
            parts.append(f"命中率{stats['hit_rate']}%")
        if stats["writes"] > 0:
            parts.append(f"写入{stats['writes']}条")
        if stats["evictions"] > 0:
            parts.append(f"淘汰{stats['evictions']}条")
        if stats["expired"] > 0:
            parts.append(f"过期{stats['expired']}条")
        parts.append(f"缓存文件{stats['total_cached_files']}/{stats['max_files']}")

        return " | ".join(parts)

    def save_metadata(self):
        """保存缓存元数据到metadata.json"""
        metadata_path = os.path.join(self.cache_root, "metadata.json")
        metadata = {
            "version": "1.0",
            "updated_at": datetime.now().isoformat(),
            "project_path": self.project_path,
            "stats": self.get_stats(),
        }
        try:
            os.makedirs(self.cache_root, exist_ok=True)
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.debug(f"元数据保存失败: {e}")

    # ===== 内部方法 =====

    def _resolve_path(self, file_path: str) -> str:
        """解析文件路径为绝对路径"""
        if os.path.isabs(file_path):
            return file_path
        return os.path.join(self.project_path, file_path)

    def _cache_file_path(self, brain_id: str, file_hash: str) -> str:
        """构造缓存文件路径

        格式: {cache_root}/brain{brain_id}/{file_hash}.json
        """
        brain_dir = os.path.join(self.cache_root, f"brain{brain_id}")
        return os.path.join(brain_dir, f"{file_hash}.json")

    def _ensure_dirs(self):
        """确保缓存目录结构存在"""
        try:
            os.makedirs(self.cache_root, exist_ok=True)
            # 预创建常见大脑的缓存子目录（可选，懒创建也行）
            for bid in ["1", "2", "3", "4", "5", "6", "7"]:
                brain_dir = os.path.join(self.cache_root, f"brain{bid}")
                os.makedirs(brain_dir, exist_ok=True)
        except OSError as e:
            logger.warning(f"缓存目录创建失败: {e}")
            self.enabled = False

    def _count_cache_files(self) -> int:
        """统计当前缓存文件总数"""
        count = 0
        if not os.path.isdir(self.cache_root):
            return 0
        for root, dirs, files in os.walk(self.cache_root):
            for fname in files:
                if fname.endswith(".json") and fname != "metadata.json":
                    count += 1
        return count

    def _enforce_capacity(self):
        """容量控制：超过上限时按LRU淘汰最旧条目"""
        current_count = self._count_cache_files()
        if current_count < self.max_files:
            return

        # 需要淘汰的数量：保留90%容量，避免频繁触发
        to_evict = current_count - int(self.max_files * 0.9)
        if to_evict <= 0:
            to_evict = 1

        # 收集所有缓存文件及其最后访问时间
        entries = []
        for root, dirs, files in os.walk(self.cache_root):
            for fname in files:
                if not fname.endswith(".json") or fname == "metadata.json":
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        entry = json.load(f)
                    last_accessed = entry.get("_last_accessed", entry.get("_created_at", 0))
                    entries.append((last_accessed, fpath))
                except (json.JSONDecodeError, OSError, KeyError):
                    # 损坏的文件优先淘汰
                    entries.append((0, fpath))

        # 按最后访问时间升序排列（最旧的在前）
        entries.sort(key=lambda x: x[0])

        # 淘汰最旧的
        evicted = 0
        for _, fpath in entries[:to_evict]:
            try:
                os.remove(fpath)
                evicted += 1
            except OSError:  # noqa: intentional empty handler
                pass

        self._stats["evictions"] += evicted
        if evicted > 0:
            logger.info(f"缓存容量淘汰: 移除{evicted}个最旧条目")


class IncrementalAnalyzer:
    """增量分析协调器

    结合git diff和缓存管理，只分析真正需要分析的文件。
    这是降本的核心：相同文件不重新分析 + 只分析变更文件。
    """

    def __init__(self, project_path: str, config: dict = None):
        self.project_path = project_path
        self.config = config or {}
        self.cache = CacheManager(project_path, config)

    def get_files_to_analyze(
        self,
        brain_id: str,
        incremental_only: bool = False,
        git_since: str = "HEAD~1",
        extensions: Optional[set] = None,
    ) -> Tuple[Dict[str, str], Dict[str, Dict]]:
        """确定需要调用LLM分析的文件

        决策流程：
        1. 获取目标文件列表（全量 or git变更）
        2. 计算每个文件的哈希
        3. 查缓存，筛出未命中的文件
        4. 返回：(需要分析的文件, 已缓存的结果)

        Args:
            brain_id: 大脑ID
            incremental_only: 是否只分析git变更文件
            git_since: git对比基准
            extensions: 文件扩展名过滤

        Returns:
            (files_to_analyze, cached_results)
            files_to_analyze: {file_path: file_hash} — 需要调LLM的
            cached_results: {file_path: cached_data} — 缓存命中的
        """
        # Step 1: 获取目标文件
        if incremental_only:
            changed_hashes = self.cache.get_changed_file_hashes(git_since)
            if changed_hashes is not None:
                # git仓库，只分析变更文件
                all_hashes = changed_hashes
            else:
                # 非git仓库，fallback到全量
                all_hashes = self.cache.compute_project_hashes(extensions=extensions)
        else:
            all_hashes = self.cache.compute_project_hashes(extensions=extensions)

        if not all_hashes:
            return {}, {}

        # Step 2: 批量查缓存
        cached_results, uncached = self.cache.load_batch(brain_id, all_hashes)

        # uncached 就是需要调LLM的文件
        return uncached, cached_results

    def get_summary(self) -> str:
        """获取增量分析摘要"""
        return self.cache.get_cache_summary()
