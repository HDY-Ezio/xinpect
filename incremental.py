# -*- coding: utf-8 -*-
"""
增量审查模块（顶层入口）
煋旺智能 QA Code Expert

功能：
- 通过 git diff 获取变更文件列表（--incremental 模式）
- 支持 --since 参数指定对比分支（默认 HEAD~1）
- 只返回需要检查的文件列表
- 如果不在git仓库，fallback到全量扫描并提示
- 支持 --diff-only 只检查diff内容（更精准但更慢）

注意：本模块是增量审查的顶层入口，核心增量检查器在 core/incremental.py。
本模块提供更高层次的git diff集成，服务于大脑调度层。
"""

import os
import subprocess
from typing import List, Set, Optional, Dict, Tuple


# 支持的代码文件扩展名
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".vue", ".wxml", ".wxss",
    ".html", ".css", ".scss", ".less", ".json", ".yaml", ".yml",
    ".go", ".java", ".rs", ".cpp", ".c", ".h", ".hpp",
    ".rb", ".php", ".swift", ".kt", ".dart",
}

# 默认排除目录
EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".git", "venv", "dist", "build",
    ".next", ".nuxt", "coverage", ".cache", "miniprogram_npm",
}


class IncrementalScanner:
    """增量扫描器 - 基于git diff获取变更文件"""

    def __init__(self, project_path: str, since: str = "HEAD~1", diff_only: bool = False):
        """
        初始化增量扫描器

        Args:
            project_path: 项目根目录
            since: 对比基准（git ref），默认 HEAD~1
            diff_only: 是否只返回diff内容（而非整个文件）
        """
        self.project_path = os.path.abspath(project_path)
        self.since = since
        self.diff_only = diff_only
        self._is_git_repo: Optional[bool] = None

    def is_git_repo(self) -> bool:
        """检测是否是git仓库"""
        if self._is_git_repo is not None:
            return self._is_git_repo

        try:
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self._is_git_repo = (result.returncode == 0 and result.stdout.strip() == "true")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            self._is_git_repo = False

        return self._is_git_repo

    def get_changed_files(self) -> Tuple[List[str], str]:
        """
        获取变更文件列表

        Returns:
            (changed_files, mode) 元组
            - changed_files: 变更文件的绝对路径列表
            - mode: 'git' | 'fallback' 标记使用了哪种模式
        """
        if self.is_git_repo():
            files = self._git_diff_files()
            if files is not None:
                return (files, "git")

        # 非git仓库或git命令失败，fallback到全量扫描
        files = self._all_code_files()
        return (files, "fallback")

    def get_changed_files_with_diff(self) -> Tuple[List[Dict], str]:
        """
        获取变更文件及其diff内容（用于diff-only模式）

        Returns:
            (file_diffs, mode) 元组
            - file_diffs: [{"file": path, "diff": diff_content, "added_lines": [line_nums]}]
            - mode: 'git' | 'fallback'
        """
        if not self.is_git_repo():
            # fallback: 返回所有文件，无diff信息
            files = self._all_code_files()
            return (
                [{"file": f, "diff": "", "added_lines": []} for f in files],
                "fallback",
            )

        return (self._git_diff_with_content(), "git")

    def _git_diff_files(self) -> Optional[List[str]]:
        """通过git diff获取变更文件列表"""
        changed = set()

        try:
            # 1. 已提交但未推送的变更（对比 since）
            result = subprocess.run(
                ["git", "diff", "--name-only", self.since],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if line:
                        full_path = os.path.join(self.project_path, line)
                        if os.path.exists(full_path) and self._is_code_file(full_path):
                            changed.add(full_path)

            # 2. 工作区未提交的变更
            result2 = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result2.returncode == 0:
                for line in result2.stdout.strip().split("\n"):
                    line = line.strip()
                    if line:
                        full_path = os.path.join(self.project_path, line)
                        if os.path.exists(full_path) and self._is_code_file(full_path):
                            changed.add(full_path)

            # 3. 暂存区（staged）的变更
            result3 = subprocess.run(
                ["git", "diff", "--name-only", "--cached"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result3.returncode == 0:
                for line in result3.stdout.strip().split("\n"):
                    line = line.strip()
                    if line:
                        full_path = os.path.join(self.project_path, line)
                        if os.path.exists(full_path) and self._is_code_file(full_path):
                            changed.add(full_path)

            # 4. 未跟踪的新文件
            result4 = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result4.returncode == 0:
                for line in result4.stdout.strip().split("\n"):
                    line = line.strip()
                    if line:
                        full_path = os.path.join(self.project_path, line)
                        if os.path.exists(full_path) and self._is_code_file(full_path):
                            changed.add(full_path)

            return list(changed)

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None

    def _git_diff_with_content(self) -> List[Dict]:
        """获取变更文件及其diff内容"""
        results = []
        changed_files = self._git_diff_files()
        if changed_files is None:
            return results

        for file_path in changed_files:
            rel_path = os.path.relpath(file_path, self.project_path)
            diff_content = ""
            added_lines = []

            try:
                # 获取该文件的diff
                diff_result = subprocess.run(
                    ["git", "diff", self.since, "--", rel_path],
                    cwd=self.project_path,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if diff_result.returncode == 0:
                    diff_content = diff_result.stdout

                    # 解析diff获取新增行号
                    added_lines = self._parse_diff_added_lines(diff_content)

            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):  # noqa: intentional empty handler
                pass

            results.append({
                "file": file_path,
                "diff": diff_content,
                "added_lines": added_lines,
            })

        return results

    @staticmethod
    def _parse_diff_added_lines(diff_text: str) -> List[int]:
        """
        解析unified diff格式，提取新增行的行号

        Args:
            diff_text: git diff输出文本

        Returns:
            新增行号列表
        """
        added_lines = []
        current_line = 0

        for line in diff_text.split("\n"):
            # 解析hunk header: @@ -old_start,old_count +new_start,new_count @@
            if line.startswith("@@"):
                parts = line.split()
                for part in parts:
                    if part.startswith("+") and not part.startswith("+++"):
                        try:
                            new_range = part[1:]
                            if "," in new_range:
                                current_line = int(new_range.split(",")[0])
                            else:
                                current_line = int(new_range)
                        except ValueError:  # noqa: intentional empty handler
                            pass
                        break
            elif line.startswith("+") and not line.startswith("+++"):
                added_lines.append(current_line)
                current_line += 1
            elif line.startswith("-") and not line.startswith("---"):
                pass  # 删除行不增加行号
            else:
                current_line += 1

        return added_lines

    def _all_code_files(self) -> List[str]:
        """扫描所有代码文件（fallback模式）"""
        files = []
        if not os.path.isdir(self.project_path):
            return files

        for root, dirs, filenames in os.walk(self.project_path):
            # 排除不需要的目录
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for fn in filenames:
                full_path = os.path.join(root, fn)
                if self._is_code_file(full_path):
                    files.append(full_path)

        return files

    @staticmethod
    def _is_code_file(file_path: str) -> bool:
        """判断是否为代码文件"""
        ext = os.path.splitext(file_path)[1].lower()
        return ext in CODE_EXTENSIONS


def get_incremental_files(
    project_path: str,
    since: str = "HEAD~1",
    diff_only: bool = False,
) -> Tuple[List[str], str]:
    """
    便捷函数：获取增量审查的文件列表

    Args:
        project_path: 项目路径
        since: 对比基准
        diff_only: 是否只检查diff内容

    Returns:
        (files, mode) - 文件列表和使用的模式
    """
    scanner = IncrementalScanner(project_path, since=since, diff_only=diff_only)
    return scanner.get_changed_files()
