"""
LLM 增强桥接
管理 AI 二次验证功能

从 runner.py 拆出，职责：
  - LLMBridge: 封装 LLM 增强层的完整生命周期
    - 初始化（配置读取、客户端创建、edition 控制）
    - AI 二次校验（LLM 误报过滤）
    - 修复建议生成（仅对 active 高危/中危问题）
    - 统计信息暴露
"""

import os
import logging
from typing import Dict, List, Optional, Any

from .rule_loader import RuleCheckResult

logger = logging.getLogger(__name__)


# ====================================================================
# LLM 模块延迟导入
# ====================================================================

def _import_llm_enhancement():
    """延迟导入 LLM 增强模块，避免循环依赖"""
    try:
        import importlib
        llm_pkg = importlib.import_module("..llm_enhancement", __name__)
        llm_client_mod = importlib.import_module("..core.llm_client", __name__)
        return llm_pkg, llm_client_mod
    except (ImportError, ValueError):
        try:
            import sys
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            import llm_enhancement as llm_pkg
            from core import llm_client as llm_client_mod
            return llm_pkg, llm_client_mod
        except ImportError:
            return None, None


# ====================================================================
# LLMBridge
# ====================================================================

class LLMBridge:
    """LLM 增强桥接，管理 AI 二次验证功能"""

    def __init__(self, config: dict = None):
        self._config = config or {}

        # 内部状态
        self._llm_client = None
        self._llm_fp_filter = None
        self._llm_fix_generator = None
        self._llm_enabled = False
        self._llm_model_name = ""
        self._smart_router = None  # v3.5.1: 多模型层级路由

        # 结果引用（由 init 或外部设置）
        self._results: Dict[str, List[RuleCheckResult]] = {}

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def init(
        self,
        enable_override: Optional[bool] = None,
        results_ref: Optional[Dict[str, List[RuleCheckResult]]] = None,
    ) -> None:
        """初始化 LLM 增强层

        Args:
            enable_override: 强制覆盖开关，None 则从配置读取
            results_ref:     结果字典引用，后续增强直接修改
        """
        if results_ref is not None:
            self._results = results_ref

        try:
            config = self._config
            llm_cfg = config.get("llm_enhancement", {})

            # v1.1.3: edition 控制 - 免费版强制禁用 LLM
            edition = config.get("edition", "pro")
            free_editions = [
                "free", "free_miniprogram", "free_python",
                "free_hardcode", "free_ai_detector",
            ]
            if edition in free_editions:
                if enable_override is not None:
                    enable_override = False
                llm_cfg["enabled"] = False

            # 判断是否启用
            if enable_override is not None:
                enabled = enable_override
            else:
                enabled = llm_cfg.get("enabled", False)

            if not enabled:
                self._llm_enabled = False
                return

            api_base = llm_cfg.get("api_base", "")
            api_key = llm_cfg.get("api_key", "")
            model = llm_cfg.get("model", "")

            if not (api_base and api_key and model):
                self._llm_enabled = False
                return

            llm_pkg, llm_client_mod = _import_llm_enhancement()
            if not llm_pkg or not llm_client_mod:
                self._llm_enabled = False
                return

            self._llm_client = llm_client_mod.create_llm_client(config, brain_id="")
            self._llm_model_name = model

            # v3.5.1: SmartRouter
            self._smart_router = None
            try:
                self._smart_router = llm_client_mod.create_smart_router(config)
            except Exception:  # noqa: intentional catch-all
                self._smart_router = None

            if llm_cfg.get("false_positive_filter", True):
                self._llm_fp_filter = llm_pkg.LLMFalsePositiveFilter(
                    llm_client=self._llm_client,
                    config=llm_cfg,
                    smart_router=self._smart_router,
                )

            if llm_cfg.get("fix_suggestion", True):
                self._llm_fix_generator = llm_pkg.FixSuggestionGenerator(
                    llm_client=self._llm_client,
                    config=llm_cfg,
                )

            self._llm_enabled = True

        except Exception as e:  # noqa: intentional catch-all
            logger.warning("[LLM] 初始化失败，自动降级: %s", e)
            self._llm_enabled = False
            self._llm_client = None
            self._llm_fp_filter = None
            self._llm_fix_generator = None

    # ------------------------------------------------------------------
    # 核心操作
    # ------------------------------------------------------------------

    def apply_enhancement(self, project_path: str = "", backend_path: str = "") -> None:
        """应用 LLM 增强层（误报过滤 + 修复建议）

        在规则执行完成、服务层误报过滤之后调用。
        所有异常静默处理，不影响主流程。
        """
        if not self.enabled:
            return

        # 第一步：AI 二次校验
        if self._llm_fp_filter and self._llm_fp_filter.is_available:
            try:
                logger.info("[AI校验] 正在执行AI二次校验（使用 %s 模型）...", self._llm_fp_filter._llm_tier)
                self._llm_fp_filter.filter_results(
                    self._results,
                    project_path=project_path,
                    backend_path=backend_path,
                )
                stats = self._llm_fp_filter.stats
                logger.info(
                    "[AI校验] 完成: 检查%d个问题, AI确认%d个真实问题, "
                    "过滤%d个误报, LLM调用%d次(失败%d)",
                    stats.get('total_checked', 0), stats.get('verified_active', 0),
                    stats.get('filtered', 0), stats.get('llm_calls', 0),
                    stats.get('llm_failures', 0),
                )
            except Exception as e:  # noqa: intentional catch-all
                logger.warning("[AI校验] 异常: %s", e)

        # 第二步：智能修复建议
        if self._llm_fix_generator and self._llm_fix_generator.is_available:
            try:
                logger.info("[LLM] 正在生成修复建议...")
                self._llm_fix_generator.generate_for_all(
                    self._results,
                    project_path=project_path,
                    backend_path=backend_path,
                )
                stats = self._llm_fix_generator.stats
                logger.info(
                    "[LLM] 修复建议完成: 请求%d, 成功%d, 失败%d",
                    stats.get('total_requested', 0), stats.get('success', 0),
                    stats.get('failed', 0),
                )
            except Exception as e:  # noqa: intentional catch-all
                logger.warning("[LLM] 修复建议异常: %s", e)

    # ------------------------------------------------------------------
    # Properties / 查询
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """LLM 增强是否已启用"""
        return self._llm_enabled and self._llm_client is not None

    @property
    def model_name(self) -> str:
        """当前使用的 LLM 模型名"""
        return self._llm_model_name

    @property
    def fp_count(self) -> int:
        """LLM 确认的误报数量（需外部设置 _results）"""
        return sum(
            1 for r in self._iter_results()
            if getattr(r, 'status', 'active') == 'llm_fp'
        )

    @property
    def fp_results(self) -> List:
        """获取 LLM 确认的误报结果"""
        return [
            r for r in self._iter_results()
            if getattr(r, 'status', 'active') == 'llm_fp'
        ]

    @property
    def stats(self) -> dict:
        """获取 LLM 增强层统计信息"""
        return {
            "enabled": self.enabled,
            "model": self._llm_model_name,
            "fp_filter": {
                "available": self._llm_fp_filter.is_available if self._llm_fp_filter else False,
                "stats": self._llm_fp_filter.stats if self._llm_fp_filter else {},
            },
            "fix_suggestion": {
                "available": self._llm_fix_generator.is_available if self._llm_fix_generator else False,
                "stats": self._llm_fix_generator.stats if self._llm_fix_generator else {},
            },
        }

    @property
    def ai_verification_stats(self) -> dict:
        """v3.5.1: AI 二次校验统计信息"""
        if not self._llm_fp_filter:
            return {
                "enabled": False, "total_checked": 0, "verified_active": 0,
                "filtered_fp": 0, "llm_calls": 0, "llm_failures": 0,
            }
        fp_stats = self._llm_fp_filter.stats
        return {
            "enabled": self._llm_fp_filter.is_available,
            "total_checked": fp_stats.get("total_checked", 0),
            "verified_active": fp_stats.get("verified_active", 0),
            "filtered_fp": fp_stats.get("filtered", 0),
            "llm_calls": fp_stats.get("llm_calls", 0),
            "llm_failures": fp_stats.get("llm_failures", 0),
        }

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _iter_results(self):
        """遍历所有结果"""
        for module_results in self._results.values():
            yield from module_results
