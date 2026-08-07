#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
扫描历史分析器 (Scan History Analyzer)
v3.0.0 新增 - 煋鉴生态闭环第6层

分析扫描历史趋势，发现项目质量变化模式，
识别改善和恶化的领域，追踪长期未解决问题。

数据来源：output/qa_report_*.md 报告文件 + .qa_history/ 快照
"""

import os
import re
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import defaultdict


class ScanHistoryAnalyzer:
    """分析扫描历史趋势，发现项目质量变化模式"""

    def __init__(self, output_dir: str = None):
        self.output_dir = output_dir or os.path.join(
            os.path.dirname(__file__), '..', 'output'
        )

    def parse_report(self, report_path: str) -> dict:
        """解析单个QA报告文件，提取关键数据"""
        if not os.path.isfile(report_path):
            return {}

        try:
            with open(report_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:  # noqa: broad exception handling
            return {}

        result = {
            "timestamp": self._extract_timestamp(content, report_path),
            "score": self._extract_score(content),
            "total_issues": self._extract_total_issues(content),
            "by_severity": self._extract_by_severity(content),
            "by_category": self._extract_by_category(content),
            "project_type": self._extract_project_type(content),
            "file_count": self._extract_file_count(content),
            "total_checks": self._extract_total_checks(content),
        }
        return result

    def analyze_trend(self, project_path: str = None) -> dict:
        """分析扫描趋势"""
        reports = self._find_all_reports()

        if not reports:
            return {}

        parsed = []
        for rp in reports:
            data = self.parse_report(rp)
            if data and data.get("timestamp"):
                parsed.append(data)

        if not parsed:
            return {}

        # 按时间排序
        parsed.sort(key=lambda x: x["timestamp"])

        # 评分趋势
        score_trend = [
            (d["timestamp"][:10], d["score"])
            for d in parsed if d["score"] is not None
        ]

        # 问题数趋势
        issue_trend = [
            (d["timestamp"][:10], d["total_issues"])
            for d in parsed if d["total_issues"] is not None
        ]

        # 分析改善/恶化的类别
        improving, degrading = self._analyze_category_trends(parsed)

        # 持久化问题 & 已解决问题（基于相邻报告对比）
        persistent, resolved = self._analyze_issue_lifecycle(parsed)

        return {
            "score_trend": score_trend,
            "issue_trend": issue_trend,
            "improving_categories": improving,
            "degrading_categories": degrading,
            "persistent_issues": persistent,
            "resolved_issues": resolved,
            "report_count": len(parsed),
            "date_range": f"{parsed[0]['timestamp'][:10]} ~ {parsed[-1]['timestamp'][:10]}",
        }

    def generate_trend_report(self) -> str:
        """生成趋势分析报告"""
        trend = self.analyze_trend()
        if not trend:
            return (
                "## 📈 扫描趋势分析\n\n"
                "⚠️ 还没有扫描历史，请先运行几次扫描（`scan .`）后再查看。"
            )

        lines = []
        lines.append("## 📈 扫描趋势分析")
        lines.append("")
        lines.append(f"> 报告数量: {trend.get('report_count', 0)} 份 | 时间范围: {trend.get('date_range', 'N/A')}")
        lines.append("")

        # 评分趋势
        score_trend = trend.get("score_trend", [])
        if score_trend:
            lines.append("### 评分趋势")
            lines.append("")
            lines.append("| 日期 | 评分 |")
            lines.append("|------|------|")
            for date, score in score_trend[-20:]:  # 最近20条
                bar = "█" * max(1, score // 5) if score else ""
                lines.append(f"| {date} | {score}/100 {bar} |")

            if len(score_trend) >= 2:
                first_score = score_trend[0][1]
                last_score = score_trend[-1][1]
                diff = last_score - first_score
                emoji = "📈" if diff > 0 else ("📉" if diff < 0 else "➡️")
                lines.append("")
                lines.append(f"**趋势**: {emoji} 评分变化 {diff:+d} ({first_score} → {last_score})")
            lines.append("")

        # 问题数趋势
        issue_trend = trend.get("issue_trend", [])
        if issue_trend:
            lines.append("### 问题数趋势")
            lines.append("")
            lines.append("| 日期 | 问题数 |")
            lines.append("|------|--------|")
            for date, count in issue_trend[-20:]:
                lines.append(f"| {date} | {count} |")
            lines.append("")

        # 改善/恶化
        improving = trend.get("improving_categories", [])
        degrading = trend.get("degrading_categories", [])
        if improving or degrading:
            lines.append("### 类别变化")
            lines.append("")
            if improving:
                lines.append(f"- 📈 **改善**: {', '.join(improving)}")
            if degrading:
                lines.append(f"- 📉 **恶化**: {', '.join(degrading)}")
            lines.append("")

        # 持久化问题
        persistent = trend.get("persistent_issues", [])
        resolved = trend.get("resolved_issues", [])
        if persistent:
            lines.append("### 长期未解决问题")
            lines.append("")
            for p in persistent[:10]:
                lines.append(f"- `{p}`")
            lines.append("")
        if resolved:
            lines.append("### 已解决问题 ✅")
            lines.append("")
            for r in resolved[:10]:
                lines.append(f"- ~~`{r}`~~")
            lines.append("")

        return "\n".join(lines)

    # ===== 内部解析方法 =====

    def _extract_timestamp(self, content: str, filepath: str) -> str:
        """提取时间戳"""
        # 先从文件名提取
        m = re.search(r'qa_report_(\d{8}_\d{6})', os.path.basename(filepath))
        if m:
            dt_str = m.group(1)
            try:
                dt = datetime.strptime(dt_str, "%Y%m%d_%H%M%S")
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:  # noqa: intentional empty handler
                pass
        # 从内容提取
        m = re.search(r'检查时间\s*\|\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', content)
        if m:
            return m.group(1)
        # fallback: 文件修改时间
        try:
            mtime = os.path.getmtime(filepath)
            return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:  # noqa: broad exception handling
            return ""

    def _extract_score(self, content: str) -> Optional[int]:
        """提取综合评分"""
        m = re.search(r'综合评分.*?\*\*(\d+)/100\*\*', content)
        if m:
            return int(m.group(1))
        m = re.search(r'总质量评分:\s*(\d+)/100', content)
        if m:
            return int(m.group(1))
        return None

    def _extract_total_issues(self, content: str) -> Optional[int]:
        """提取问题总数"""
        m = re.search(r'问题合计.*?\*\*(\d+)\*\*', content)
        if m:
            return int(m.group(1))
        m = re.search(r'总计.*?\*\*(\d+)\*\*', content)
        if m:
            return int(m.group(1))
        return None

    def _extract_by_severity(self, content: str) -> dict:
        """按严重程度提取"""
        result = {"high": 0, "medium": 0, "low": 0}
        m = re.search(r'高危.*?(\d+)', content)
        if m:
            result["high"] = int(m.group(1))
        m = re.search(r'中危.*?(\d+)', content)
        if m:
            result["medium"] = int(m.group(1))
        m = re.search(r'低危.*?(\d+)', content)
        if m:
            result["low"] = int(m.group(1))
        return result

    def _extract_by_category(self, content: str) -> dict:
        """按类别提取"""
        result = {"bug": 0, "code_smell": 0, "engineering": 0}
        # 匹配 "🐛 Bug... | x |" 等模式
        for m in re.finditer(r'Bug.*?(\d+)', content):
            result["bug"] += int(m.group(1))
            break
        for m in re.finditer(r'Code Smell.*?(\d+)', content):
            result["code_smell"] += int(m.group(1))
            break
        for m in re.finditer(r'工程成熟度.*?(\d+)', content):
            result["engineering"] += int(m.group(1))
            break
        return result

    def _extract_project_type(self, content: str) -> str:
        """提取项目类型"""
        m = re.search(r'项目类型\s*\|\s*(.+?)\s*\|', content)
        if m:
            return m.group(1).strip()
        return "unknown"

    def _extract_file_count(self, content: str) -> int:
        """提取文件数"""
        m = re.search(r'文件数.*?(\d+)', content)
        if m:
            return int(m.group(1))
        return 0

    def _extract_total_checks(self, content: str) -> int:
        """提取总检查项"""
        m = re.search(r'总检查项.*?(\d+)', content)
        if m:
            return int(m.group(1))
        return 0

    def _find_all_reports(self) -> list:
        """查找所有报告文件"""
        reports = []
        if not os.path.isdir(self.output_dir):
            return reports
        for f in os.listdir(self.output_dir):
            if f.startswith("qa_report_") and f.endswith(".md"):
                reports.append(os.path.join(self.output_dir, f))
        reports.sort()
        return reports

    def _analyze_category_trends(self, parsed: list) -> tuple:
        """分析类别趋势"""
        if len(parsed) < 2:
            return [], []

        first = parsed[0].get("by_category", {})
        last = parsed[-1].get("by_category", {})

        improving = []
        degrading = []
        category_names = {"bug": "Bug", "code_smell": "Code Smell", "engineering": "工程成熟度"}

        for cat, name in category_names.items():
            diff = last.get(cat, 0) - first.get(cat, 0)
            if diff < 0:
                improving.append(name)
            elif diff > 0:
                degrading.append(name)

        return improving, degrading

    def _analyze_issue_lifecycle(self, parsed: list) -> tuple:
        """简单分析问题的持续性（基于报告级别的问题数量变化）"""
        # 简化实现：如果问题持续存在多份报告，视为持久化
        if len(parsed) < 2:
            return [], []

        first_issues = parsed[0].get("total_issues", 0) or 0
        last_issues = parsed[-1].get("total_issues", 0) or 0

        persistent = []
        resolved = []

        if first_issues > 0 and last_issues > 0:
            persistent.append(f"问题从 {first_issues} 个变为 {last_issues} 个（持续存在）")
        elif first_issues > 0 and last_issues == 0:
            resolved.append(f"全部 {first_issues} 个问题已解决")
        elif first_issues == 0 and last_issues > 0:
            persistent.append(f"新增 {last_issues} 个问题")

        return persistent, resolved
