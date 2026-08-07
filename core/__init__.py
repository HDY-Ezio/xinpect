"""
QA框架核心引擎 - 可插拔规则引擎架构 v2.1
核心引擎是未来远端化的主体，rules/是本地规则集
支持快速模式（本地规则）和高级模式（远端引擎+增强规则）

服务层集成：
- 误报过滤服务 (FalsePositiveService)
- 深度诊断服务 (DeepDiagnosisService)
- 评分计算服务 (ScoringService)
- 匿名埋点服务 (TelemetryService) - v2.1新增

章鱼架构v2.0整合新增：
- 8大架构模块（契约/去重/协同/检查点/消息/成本/路由/知识库）
- get_architecture() 便捷入口
"""

__version__ = "4.2.0"

# v4.6.1 性能优化：所有重型模块懒加载
# 规则加载阶段（load_all）仅导入纯工具模块，不触发 core/__init__.py 级联导入
import importlib as _importlib


def _lazy_import(mod_name, attr_names=None):
    """懒加载工具：首次访问时才真正导入子模块并提取属性。
    
    用法：
        QAContext = _lazy_import('core.context', ['QAContext'])['QAContext']
    
    但为了支持 from core import xxx 的用法，我们用 __getattr__ 机制。
    """
    return getattr(_importlib.import_module(mod_name), attr_names[0]) if attr_names else _importlib.import_module(mod_name)


def __getattr__(name):
    """模块级 __getattr__：首次访问某属性时才导入对应子模块。
    
    这让规则文件中的 `from core.code_context_utils import ...`
    不会触发完整的 core 包初始化。
    """
    # 映射 name -> (模块路径, 属性名 or None=模块本身)
    _LAZY_ATTRS = {
        # context
        'QAContext': ('core.context', 'QAContext'),
        'ProjectProfile': ('core.context', 'ProjectProfile'),
        # rule_loader
        'RuleLoader': ('core.rule_loader', 'RuleLoader'),
        'Rule': ('core.rule_loader', 'Rule'),
        'RuleCheckResult': ('core.rule_loader', 'RuleCheckResult'),
        # runner
        'RuleRunner': ('core.runner', 'RuleRunner'),
        'get_check_category': ('core.runner', 'get_check_category'),
        'CATEGORY_NAMES': ('core.runner', 'CATEGORY_NAMES'),
        'CATEGORY_ICONS': ('core.runner', 'CATEGORY_ICONS'),
        # reporter
        'ResultReporter': ('core.reporter', 'ResultReporter'),
        # module_adapter
        'OldModuleRuleAdapter': ('core.module_adapter', 'OldModuleRuleAdapter'),
        # rule_pruner
        'RulePruner': ('core.rule_pruner', 'RulePruner'),
        # incremental_scanner
        'IncrementalScanner': ('core.incremental_scanner', 'IncrementalScanner'),
    }
    
    if name in _LAZY_ATTRS:
        mod_path, attr_name = _LAZY_ATTRS[name]
        mod = _importlib.import_module(mod_path)
        val = getattr(mod, attr_name)
        # 缓存到本模块命名空间，下次直接访问
        globals()[name] = val
        return val
    
    raise AttributeError(f"module 'core' has no attribute {name!r}")


# 服务层便捷导入（懒加载，避免循环导入）
def _get_services():
    """获取服务层模块（延迟导入）"""
    try:
        import importlib
        return importlib.import_module("..services", __name__)
    except (ImportError, ValueError):
        try:
            import os
            import sys
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            import services
            return services
        except ImportError:
            return None


def get_fp_service(mode: str = "quick", config: dict = None):
    """获取误报过滤服务实例"""
    svc = _get_services()
    if svc and hasattr(svc, 'get_fp_service'):
        return svc.get_fp_service(mode, config)
    return None


def get_diagnosis_service(mode: str = "quick", config: dict = None, sdk=None):
    """获取深度诊断服务实例"""
    svc = _get_services()
    if svc and hasattr(svc, 'get_diagnosis_service'):
        return svc.get_diagnosis_service(mode, config, sdk)
    return None


def get_scoring_service(mode: str = "quick", config: dict = None):
    """获取评分服务实例"""
    svc = _get_services()
    if svc and hasattr(svc, 'get_scoring_service'):
        return svc.get_scoring_service(mode, config)
    return None


# ===== 章鱼架构v2.0: 便捷入口 =====

def get_architecture(project_id: str = "default", **kwargs):
    """
    获取章鱼架构统一入口（延迟导入）。
    
    Args:
        project_id: 项目标识
        **kwargs: 传递给 OctopusArchitecture 的参数
        
    Returns:
        已初始化的 OctopusArchitecture 实例，或 None（模块不可用时）
    """
    try:
        from .registry import get_architecture as _get_arch
        return _get_arch(project_id=project_id, **kwargs)
    except (ImportError, Exception):
        return None


__all__ = [
    'QAContext',
    'ProjectProfile', 
    'RuleLoader',
    'Rule',
    'RuleCheckResult',
    'RuleRunner',
    'ResultReporter',
    'OldModuleRuleAdapter',
    'get_check_category',
    'CATEGORY_NAMES',
    'CATEGORY_ICONS',
    # v4.2 新增
    'RulePruner',
    'IncrementalScanner',
    # 服务层便捷函数
    'get_fp_service',
    'get_diagnosis_service',
    'get_scoring_service',
    # 章鱼架构v2.0
    'get_architecture',
]
