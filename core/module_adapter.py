"""
======================================================================
[DEPRECATED / 已归档] 旧模块适配器 (module_adapter.py)
======================================================================
本文件是旧版 qa_framework.py 的配套适配器，用于将 BaseModule
子类包装为新的规则引擎可执行的规则集。

随着 qa_framework.py 归档，本适配器的使用场景已大幅收窄。
仅在 HybridQARunner._run_legacy_mode() 中仍有调用。

⚠️ 当旧引擎完全下线后，本文件可一并移除。
   - 新规则开发请直接使用 rules/ 目录下的规则格式
   - 参考: core/rule_loader.py
======================================================================

模块适配器 - 旧模块兼容层
将旧的BaseModule子类适配为新的规则引擎可执行的规则集
用于渐进式迁移，保证向后兼容
"""

import os
import sys
from typing import Dict, List, Any, Optional

# 导入旧框架的模块
try:
    import importlib.util
    _OLD_FRAMEWORK_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "qa_framework.py"
    )
    _HAS_OLD_FRAMEWORK = os.path.isfile(_OLD_FRAMEWORK_PATH)
except Exception as e:  # noqa: broad exception handling
    _HAS_OLD_FRAMEWORK = False

# 旧框架模块缓存（避免重复 exec_module 导致重复日志和性能问题）
_old_framework_cache = None


def get_old_modules():
    """获取旧框架中的所有模块类
    
    返回: {module_id: module_class}
    """
    if not _HAS_OLD_FRAMEWORK:
        return {}
    
    try:
        # 使用缓存的旧框架模块（避免重复 exec_module）
        global _old_framework_cache
        if _old_framework_cache is not None:
            old_module = _old_framework_cache
        elif "qa_old" in sys.modules:
            # hybrid_runner 可能已经加载过，复用
            old_module = sys.modules["qa_old"]
            _old_framework_cache = old_module
        else:
            # 动态加载旧框架
            spec = importlib.util.spec_from_file_location(
                "qa_old", _OLD_FRAMEWORK_PATH
            )
            old_module = importlib.util.module_from_spec(spec)
            sys.modules["qa_old"] = old_module
            spec.loader.exec_module(old_module)
            _old_framework_cache = old_module
        
        # 查找所有模块类
        modules = {}
        for name in dir(old_module):
            obj = getattr(old_module, name)
            if isinstance(obj, type) and hasattr(obj, 'module_id') and hasattr(obj, 'run'):
                if obj.__name__ == 'BaseModule':
                    continue
                if getattr(obj, 'module_id', ''):
                    modules[obj.module_id] = obj
        
        # 注入全局helper：旧模块类从qa_framework.py拆分到legacy/modules/后，
        # 原来共享的全局函数/常量找不到了。将qa_framework中的常用helper
        # 注入到每个模块类的__globals__，保持向后兼容。
        _inject_helper_symbols(old_module, modules)
        
        return modules
    except Exception as e:  # noqa: intentional catch-all
        import logging; logging.getLogger(__name__).warning("加载旧框架模块失败: %s", e)
        return {}


# 需要注入到旧模块类的全局符号列表（从qa_framework模块中获取）
# 这些函数/常量原本定义在qa_framework.py中，模块类拆分到legacy/modules/后
# 仍然需要访问它们。通过注入到类的__globals__实现向后兼容。
_LEGACY_HELPER_SYMBOLS = [
    # 工具函数
    '_get_backend_content',
    '_get_all_backend_content',
    '_get_all_backend_py_files',
    '_detect_backend_architecture',
    '_parse_backend_routes',
    '_parse_frontend_api_calls',
    '_has_audit_comment',
    '_line_num',
    '_get_match_context',
    '_skip_checks',
    '_get_main_backend_file',
    '_find_handler_def',
    '_collect_audited_handlers',
    '_parse_backend_routes_enhanced',
    '_parse_backend_routes_legacy',
    # 数据类
    'CheckResult',
    'BaseModule',
    # 常量/配置
    'CHECK_SKIP',
    'ARCH_LAYER_KEYWORDS',
    'safe_read',
    'find_files',
    'severity_icon',
]


def _inject_helper_symbols(old_module, modules):
    """将qa_framework中的helper函数注入到旧模块相关的模块中
    
    解决模块类和检查函数从qa_framework.py拆分出去后，
    全局helper函数/常量找不到的问题（循环导入无法直接import解决）。
    
    注入目标：
    1. 每个模块类的__globals__（模块类方法访问全局符号）
    2. 每个模块类依赖的legacy.checks模块（检查函数访问全局符号）
    """
    # 从旧框架模块收集需要的符号
    helpers = {}
    for name in _LEGACY_HELPER_SYMBOLS:
        if hasattr(old_module, name):
            helpers[name] = getattr(old_module, name)
    
    # 注入到每个模块类所在模块的全局作用域
    import sys
    for module_id, module_class in modules.items():
        # 通过 __module__ 获取类所在的模块对象
        mod_name = getattr(module_class, '__module__', None)
        class_mod = sys.modules.get(mod_name) if mod_name else None
        
        if class_mod is not None:
            for name, value in helpers.items():
                if not hasattr(class_mod, name):
                    setattr(class_mod, name, value)
    
    # 同时注入到所有已加载的 legacy.checks.* 模块
    # 检查函数从qa_framework拆分出去后，也需要访问这些全局helper
    for mod_name, mod in list(sys.modules.items()):
        if mod_name.startswith('legacy.checks.') and mod is not None:
            for name, value in helpers.items():
                if not hasattr(mod, name):
                    setattr(mod, name, value)


def create_rules_from_old_module(module_class, project_type="all"):
    """将旧模块类转换为规则列表
    
    由于旧模块是整体执行的，这里将整个模块作为一个"元规则"
    后续可以逐步将模块内的检查项拆分为独立规则
    """
    from .rule_loader import Rule
    
    module_id = module_class.module_id
    module_name = module_class.module_name
    
    def make_check_func(mod_cls, mid):
        def check(context):
            """执行旧模块的检查，返回问题列表"""
            # 构建旧模块实例
            mod_instance = mod_cls(
                project_path=context.project_path,
                backend_path=context.backend_path,
                config=context.config,
                project_type=context.project_type,
                project_profile=context.project_profile,
                arch_info=context._arch_info,
            )
            
            # 执行检查
            try:
                results = mod_instance.run()
            except Exception as e:  # noqa: intentional catch-all
                return [{
                    'message': f"模块执行异常: {e}",
                    'level': 'error',
                    'file': '',
                    'line': 0,
                }]
            
            # 转换结果格式
            issues = []
            for r in results:
                issue = {
                    'message': r.message,
                    'detail': getattr(r, 'detail', ''),
                    'fix': getattr(r, 'fix', ''),
                    'level': r.level,
                    'file': r.location.get('file', '') if getattr(r, 'location', None) else '',
                    'line': r.location.get('line', 0) if getattr(r, 'location', None) else 0,
                    'column': r.location.get('column', 0) if getattr(r, 'location', None) else 0,
                    'snippet': r.location.get('snippet', '') if getattr(r, 'location', None) else '',
                    'check_id': r.check_id,
                }
                issues.append(issue)
            
            return issues
        return check
    
    rule = Rule(
        rule_id=f"M{module_id}",
        name=module_name,
        level='problem',
        category='common',
        description=f"{module_name}模块检查（旧框架适配）",
        check_func=make_check_func(module_class, module_id),
        applicable_types=[],  # 空列表表示所有类型适用，实际由模块自身判断
        module_id=module_id,
    )
    
    return [rule]


def load_all_old_modules_as_rules():
    """加载所有旧模块并转换为规则"""
    modules = get_old_modules()
    all_rules = []
    
    for module_id, module_class in modules.items():
        rules = create_rules_from_old_module(module_class)
        all_rules.extend(rules)
    
    return all_rules


class OldModuleRuleAdapter:
    """旧模块规则适配器
    
    将旧的BaseModule子类包装为新的规则集
    用于渐进式迁移过程中，逐步替换为纯规则格式
    """
    
    def __init__(self):
        self._modules = None  # 懒加载，首次使用时才加载491KB旧框架
    
    @property
    def _module_dict(self):
        """懒加载旧模块字典，仅在真正需要执行旧模块时才加载"""
        if self._modules is None:
            self._modules = get_old_modules()
        return self._modules
    
    @property
    def module_count(self):
        return len(self._module_dict)
    
    def get_module(self, module_id: str):
        return self._module_dict.get(module_id)
    
    def get_all_module_ids(self):
        return sorted(self._module_dict.keys())
    
    def run_module(self, module_id: str, context) -> list:
        """运行指定模块"""
        module_class = self._module_dict.get(module_id)
        if not module_class:
            return []
        
        instance = module_class(
            project_path=context.project_path,
            backend_path=context.backend_path,
            config=context.config,
            project_type=context.project_type,
            project_profile=context.project_profile,
            arch_info=context._arch_info,
        )
        
        try:
            return instance.run()
        except Exception as e:  # noqa: intentional catch-all
            from .runner import RuleCheckResult
            return [RuleCheckResult(
                rule_id=f"{module_id}.0",
                rule_name=module_class.module_name,
                level="error",
                message=f"模块执行异常: {e}",
                category="bug",
            )]
