# -*- coding: utf-8 -*-
"""
大脑2：安全漏洞扫描引擎
煋旺机械章鱼架构 - Brain2

v2.0 真实本地扫描能力：
- 本地模式：基于 rules/brain2_security/ JSON规则执行关键词匹配扫描
- 远端模式：调用微服务（如果可用）
- 自动降级：远端不可用时自动切换到本地扫描

职责：OWASP/CWE全覆盖安全扫描
  - 通用安全规则（SQL注入/XSS/CSRF/硬编码密钥等）
  - 分发安全（影子实现/过期API/死代码暴露面）
  - 供应链攻击（恶意包/版本劫持/依赖投毒）
  - CI/CD管道安全（密钥泄露/权限过大/镜像漏洞）
  - 多平台安全（Web/Electron/iOS/Android/RN/Flutter）
"""
import os
import sys
from typing import List, Dict

try:
    from . import BaseBrain, BrainResult, BrainIssue, register_brain
except ImportError:
    try:
        from brains import BaseBrain, BrainResult, BrainIssue, register_brain
    except ImportError:
        BaseBrain = object
        BrainResult = None
        BrainIssue = None
        def register_brain(x):
            return lambda cls: cls

BRAIN_MODULE_ID = "2"

# 安全相关的规则目录（多个目录映射到Brain2）
_SECURITY_RULE_DIRS = [
    "brain2_security",
    "distribution_security",
]


@register_brain("2")
class Brain2SecurityEngine(BaseBrain):
    """Brain 2: 安全漏洞扫描引擎（含分发安全/供应链/CI-CD/多平台）"""
    name = "brain2_security_engine"
    description = "安全漏洞扫描引擎（OWASP/CWE全覆盖 + 分发安全 + 供应链 + CI/CD + 多平台）"
    priority = 90
    cost_level = "medium"

    _CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".java", ".go", ".rb",
                  ".php", ".c", ".cpp", ".cs", ".swift", ".kt", ".dart"}
    _SKIP_DIRS = {
        "node_modules", "__pycache__", ".git", ".venv", "venv", "env",
        ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", ".eggs",
        ".idea", ".vscode", "vendor", "third_party", "third-party",
        "migrations", "migration", "rules", "skills", ".skills",
    }

    _SEC_MODULES = {
        "security", "dist_sec", "distribution_security", "supply_chain",
        "ci_cd", "web_security", "electron_security", "ios_security",
        "android_security", "rn_security", "flutter_security",
    }

    def scan(self, project_path: str, config: dict) -> BrainResult:
        """执行安全扫描：先尝试远端，失败则降级到本地扫描"""
        try:
            from core.license_gate import check_brain_access
        except ImportError:
            try:
                sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                from core.license_gate import check_brain_access
            except ImportError:
                return BrainResult(
                    brain_name=self.name, status="error", score=0, issues=[],
                    summary="License module unavailable",
                )

        allowed, denied = check_brain_access(["2"], config)
        if "2" in denied:
            return BrainResult(
                brain_name=self.name, status="skip", score=100, issues=[],
                summary="B2 requires License. Contact: hdyabcd@163.com",
            )

        # 先尝试远端微服务
        try:
            from core.brain_client import call_brain_service
            result = call_brain_service("2", 8612, project_path, config, self._CODE_EXTS, self._SKIP_DIRS)
            if result.get("success"):
                return self._parse_service_result(result)
        except (ImportError, Exception):
            pass

        # 远端不可用，降级为本地扫描
        return self._scan_local(project_path, config)

    def local_scan(self, context):
        """本地扫描降级方案 - 使用 RuleLoader 加载 Brain2 的安全规则"""
        results = []
        try:
            from core.b4b7_local_scanner import LocalRuleScanner
            skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            for rule_dir_name in _SECURITY_RULE_DIRS:
                rules_path = os.path.join(skill_root, "rules", rule_dir_name)
                if os.path.isdir(rules_path):
                    scanner = LocalRuleScanner(rules_path, "2")
                    project_path = getattr(context, 'project_path', '')
                    if project_path and os.path.isdir(project_path):
                        findings = scanner.scan_directory(project_path, max_files=200)
                        results.extend(findings)
        except Exception:
            pass
        return results

    def _scan_local(self, project_path: str, config: dict) -> BrainResult:
        """本地规则引擎扫描（微服务降级方案）"""
        issues: List[BrainIssue] = []
        try:
            from core.b4b7_local_scanner import LocalRuleScanner
            skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

            for rule_dir_name in _SECURITY_RULE_DIRS:
                rules_path = os.path.join(skill_root, "rules", rule_dir_name)
                if not os.path.isdir(rules_path):
                    continue
                scanner = LocalRuleScanner(rules_path, "2")
                findings = scanner.scan_directory(project_path, max_files=200)
                for f in findings:
                    issues.append(BrainIssue(
                        check_id=f.get("check_id", "B2-SEC"),
                        name=f.get("name", ""),
                        severity=f.get("severity", "medium"),
                        file=f.get("file", ""),
                        line=f.get("line", 0),
                        message=f.get("message", ""),
                        suggestion=f.get("suggestion", ""),
                    ))
        except Exception as e:
            return BrainResult(
                brain_name=self.name, status="error", score=0, issues=[],
                summary=f"B2 local scan error: {e}",
            )

        # 统一评分：blocking/high=10, problem/medium=5, suggestion/low=1
        score = 100
        for iss in issues:
            sev = getattr(iss, "severity", "low")
            if sev in ("blocker", "critical", "high"):
                score -= 10
            elif sev == "medium":
                score -= 5
            else:
                score -= 1
        score = max(0, score)

        status = "pass" if not issues else "fail"
        summary = f"B2 security scan (local): {len(issues)} issues found"

        return BrainResult(
            brain_name=self.name, status=status, score=score,
            issues=issues, summary=summary,
        )

    def _parse_service_result(self, result: dict) -> BrainResult:
        """解析微服务返回结果"""
        issues = []
        for item in result.get("findings", []):
            sev = item.get("severity", "medium")
            if sev == "error":
                sev = "high"
            elif sev == "warning":
                sev = "medium"
            issues.append(BrainIssue(
                check_id=item.get("rule_id", "B2-unknown"),
                name=item.get("name", ""),
                severity=sev,
                file=item.get("file", ""),
                line=item.get("line", 0),
                message=item.get("message", ""),
                suggestion=item.get("suggestion", ""),
            ))

        score = result.get("score", 100 - len(issues) * 2)
        return BrainResult(
            brain_name=self.name,
            status="ok" if not issues else "fail",
            score=max(0, score),
            issues=issues,
            summary=f"B2 security scan (service): {len(issues)} issues found",
        )
