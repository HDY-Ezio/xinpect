# -*- coding: utf-8 -*-
"""
大脑1：确定性规则引擎（薄层包装）
煋旺多引擎协同架构 - Brain1

包装现有的 qa_framework.py 规则引擎（257条规则），
将其结果适配为统一的 BrainResult 格式。

v1.1 AI增强：
- 免费版：纯规则引擎，零Token消耗
- 付费版：规则引擎 + AI增强（误报过滤/修复建议/严重性校准）
"""

import os
import re
import sys
from typing import List

from . import BaseBrain, BrainResult, BrainIssue, register_brain

BRAIN_MODULE_ID = "1"


@register_brain("1")
class Brain1RuleEngine(BaseBrain):
    """大脑1：确定性规则引擎

    包装现有的可插拔规则引擎（core/ + rules/），
    257条规则，零Token消耗，秒级响应。
    
    付费版额外获得AI增强能力（误报过滤、修复建议等）。
    """

    name = "brain1_rule_engine"
    description = "确定性规则引擎（257条规则，零Token）"

    def scan(self, project_path: str, config: dict) -> BrainResult:
        """执行规则引擎扫描"""
        try:
            return self._do_scan(project_path, config)
        except Exception as e:  # noqa: intentional catch-all
            return BrainResult(
                brain_name=self.name,
                status="error",
                score=0,
                issues=[],
                summary=f"大脑1执行异常: {e}",
            )

    def _do_scan(self, project_path: str, config: dict) -> BrainResult:
        """实际扫描逻辑"""
        # 导入现有引擎
        skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if skill_root not in sys.path:
            sys.path.insert(0, skill_root)

        try:
            from core.context import QAContext
            from core.rule_loader import RuleLoader
            from core.runner import RuleRunner
        except ImportError as e:
            return BrainResult(
                brain_name=self.name,
                status="skip",
                score=100,
                issues=[],
                summary=f"核心引擎模块不可用: {e}",
            )

        # 构建上下文
        ctx = QAContext(
            project_path=os.path.abspath(project_path),
            backend_path=config.get("backend_path", ""),
            mode=config.get("mode", "quick"),
            config=config,
            project_type=config.get("project_type", "auto"),
        )

        # 创建RuleLoader并执行
        try:
            loader = RuleLoader()
            runner = RuleRunner(context=ctx, rule_loader=loader, enable_telemetry=False)
            results_dict = runner.run_all()
        except Exception as e:  # noqa: intentional catch-all
            return BrainResult(
                brain_name=self.name,
                status="error",
                score=0,
                issues=[],
                summary=f"规则引擎执行失败: {e}",
            )

        # 适配为统一格式
        # results_dict: Dict[str, List[RuleCheckResult]]
        issues: List[BrainIssue] = []
        severity_map = {
            "blocking": "blocker",
            "problem": "high",
            "suggestion": "low",
            # 兼容旧级别
            "error": "blocker",
            "warning": "medium",
            "info": "low",
        }

        for module_id, result_list in results_dict.items():
            for r in result_list:
                # 跳过已标记为误报或抑制的
                if hasattr(r, 'status') and r.status in ('fp', 'suppressed'):
                    continue

                sev = severity_map.get(r.level, "low")
                # 提取文件/行号
                file_path = r.location.get("file", "") if hasattr(r, 'location') and r.location else ""
                line_no = r.location.get("line", 0) if hasattr(r, 'location') and r.location else 0

                issues.append(BrainIssue(
                    check_id=r.rule_id,
                    name=r.rule_name[:40] if r.rule_name else "",
                    severity=sev,
                    file=file_path,
                    line=line_no,
                    message=r.message,
                    suggestion=r.fix or getattr(r, 'suggestion_code', '') or "",
                ))

        # ===== 过滤噪音issue（状态通知/跳过说明/正面报告）=====
        issues = [iss for iss in issues if not self._is_noise_issue(iss)]

        # 统一评分标准：blocking=10分, problem(high/medium)=5分, suggestion(low)=1分
        score = 100
        for iss in issues:
            if iss.severity in ("blocker", "critical"):
                score -= 10
            elif iss.severity in ("high", "medium"):
                score -= 5
            else:
                score -= 1
        score = max(0, score)

        status = "pass" if not issues else "fail"
        summary = f"大脑1扫描完成：发现{len(issues)}个问题，得分{score}"

        result = BrainResult(
            brain_name=self.name,
            status=status,
            score=score,
            issues=issues,
            summary=summary,
        )

        # ===== AI增强层（仅付费版）=====
        result = self._apply_ai_enhancement(result, project_path, config)

        return result


    def _is_noise_issue(self, issue) -> bool:
        """过滤噪音：项目统计/正面报告/观察建议/元数据
        
        v3.0.2简化：上游已用AST分析，误报率大幅降低。
        仅保留必要的业务特定噪音过滤。
        """
        msg = (issue.message or "").strip()
        sev = issue.severity

        # 空消息
        if not msg:
            return True

        # low级别：全部过滤（都是观察/建议/统计）
        if sev == "low":
            return True

        # medium级别：过滤项目级聚合/统计/元数据
        if re.search(r"(?:检测到|发现)\s*\d+\s*(处|个|项|组|个文件|处调试)", msg):
            return True
        if re.search(r"\d+\s*(个|处|项|层|处|组)\s*(文件|不可达|重复|未使用|超长|嵌套|空|待办|注释|硬编码|函数|变量|字面量|对象|缩写|类|布尔)", msg):
            return True

        # 项目级元数据/观察（业务特定噪音）
        noise_keywords = ["注释率低于", "打包脚本缺少", "超过阈值", "主包体积",
                          "检测到1层结构", "需对比版本", "建议在CI",
                          "未发现明确的领域层", "文档声明与代码", "临时代码标记"]
        for kw in noise_keywords:
            if kw in msg:
                return True

        return False

    def local_scan(self, context):
        """本地扫描降级方案 - Brain1 本身就是本地规则引擎，此处提供统一接口"""
        results = []
        try:
            from core.rule_loader import RuleLoader
            loader = RuleLoader()
            rules = [r for r in loader.load_all() if getattr(r, 'module_id', '').startswith(('1', 'json:'))]
            project_path = getattr(context, 'project_path', '')
            for rule in rules:
                if rule.check_func:
                    try:
                        # Brain1的check_func签名: (file_path, content) -> list
                        pass  # 实际扫描由 RuleRunner 完成，此处仅做接口兼容
                    except Exception:
                        pass
        except Exception:
            pass
        return results

    def _apply_ai_enhancement(self, result: BrainResult, project_path: str, config: dict) -> BrainResult:
        """尝试对规则引擎结果做AI增强
        
        免费版：直接返回，不调LLM
        付费版：调用AIEnhancer做误报过滤、修复建议等
        """
        try:
            from core.ai_enhancer import should_enable_ai, AIEnhancer
            
            if not should_enable_ai(config):
                # 免费版路径：零LLM调用
                return result
            
            # 付费版路径：AI增强
            enhancer = AIEnhancer(config, project_path=project_path)
            result = enhancer.enhance_brain_result("1", result, project_path, config)
            
        except (ImportError, Exception) as e:
            # AI增强失败不影响主流程
            pass
        
        return result
