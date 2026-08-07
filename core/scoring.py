"""
评分引擎模块
分类体系定义 + 严重性判定 + 评分计算

从 runner.py 拆出，职责：
  - 定义 CHECK_CATEGORIES / CATEGORY_NAMES / CATEGORY_ICONS 等分类常量
  - 提供 normalize_level / get_check_category / classify_severity 工具函数
  - ScoringEngine: 基于检查结果计算各维度得分（本地降级实现）
"""

import logging
from collections import defaultdict
from typing import Dict, Any

logger = logging.getLogger(__name__)

# ====================================================================
# 分类常量
# ====================================================================
CHECK_CATEGORIES: Dict[str, str] = {
    '1.0':'code_smell','1.1':'bug','1.2':'bug','1.3':'bug','1.4':'code_smell','1.5':'bug','1.6':'bug','1.7':'code_smell',
    '2.0':'code_smell','2.1':'bug','2.2':'bug','2.3':'code_smell','2.4':'bug','2.5':'code_smell',
    '3.0':'bug','3.1':'bug','3.2':'bug','3.3':'bug','3.4':'bug','3.5':'bug',
    '3.6':'bug','3.7':'bug','3.8':'bug','3.9':'bug','3.10':'bug','3.11':'bug','3.12':'bug',
    '4.1':'bug',
    '5.1':'code_smell','5.2':'code_smell','5.3':'code_smell','5.4':'code_smell','5.5':'code_smell',
    '5.6':'code_smell','5.7':'code_smell','5.8':'code_smell','5.9':'code_smell','5.10':'code_smell',
    '5.11':'code_smell','5.12':'bug','5.13':'bug','5.14':'code_smell','5.15':'code_smell',
    '5.16':'code_smell','5.17':'code_smell','5.18':'code_smell','5.19':'code_smell','5.20':'code_smell',
    '5.21':'bug','5.22':'code_smell','5.23':'code_smell','5.24':'code_smell','5.25':'code_smell','5.26':'code_smell','5.27':'code_smell','5.28':'code_smell',
    '6.1':'code_smell','6.2':'code_smell','6.3':'code_smell','6.4':'code_smell','6.5':'code_smell','6.6':'code_smell','6.7':'code_smell',
    '7.1':'bug','7.2':'bug','7.3':'code_smell','7.4':'engineering_maturity','7.5':'engineering_maturity',
    '8.1':'bug','8.2':'bug','8.3':'bug',
    '9.1':'code_smell','9.2':'code_smell','9.3':'code_smell','9.4':'code_smell','9.5':'code_smell',
    '10.1':'engineering_maturity','10.2':'engineering_maturity','10.3':'engineering_maturity',
    '10.4':'engineering_maturity','10.5':'engineering_maturity','10.6':'engineering_maturity','10.7':'engineering_maturity',
    '11.1':'code_smell','11.2':'code_smell','11.3':'code_smell','11.4':'bug',
    '12.1':'bug','12.2':'code_smell','12.3':'code_smell','12.4':'code_smell','12.5':'bug',
    '12.6':'code_smell','12.7':'bug','12.8':'bug','12.9':'code_smell','12.10':'code_smell','12.11':'code_smell','12.12':'bug',
    '13.1':'code_smell','13.2':'bug','13.3':'bug','13.4':'bug','13.5':'bug',
    '13.6':'bug','13.7':'code_smell','13.8':'code_smell','13.9':'code_smell',
    '14.1':'engineering_maturity','14.2':'engineering_maturity','14.3':'engineering_maturity',
    '14.4':'engineering_maturity','14.5':'engineering_maturity','14.6':'engineering_maturity',
    '15.0':'code_smell','15.1':'code_smell','15.2':'code_smell','15.3':'bug','15.4':'code_smell','15.5':'code_smell','15.6':'code_smell',
    '16.0':'code_smell','16.1':'code_smell','16.2':'code_smell','16.3':'code_smell','16.4':'code_smell',
    '17.1':'code_smell','17.2':'code_smell',
    '18.0':'code_smell','18.1':'code_smell','18.2':'bug','18.3':'bug','18.4':'code_smell','18.5':'code_smell',
    '19.1':'bug','19.2':'code_smell','19.3':'code_smell','19.4':'code_smell','19.5':'code_smell',
    '19.6':'code_smell','19.7':'bug','19.8':'code_smell','19.9':'code_smell','19.10':'bug','19.11':'code_smell',
}
CATEGORY_NAMES = {'bug':'Bug（可靠性问题）','code_smell':'Code Smell（可维护性问题）','engineering_maturity':'工程成熟度（过程质量）'}
CATEGORY_ICONS = {'bug':'🐛','code_smell':'💩','engineering_maturity':'🏗️'}

# ====================================================================
# Level 标准化
# ====================================================================
_LEVEL_MAP = {'blocking':'error','problem':'warning','suggestion':'info','error':'error','warning':'warning','info':'info'}
def normalize_level(level: str) -> str:
    return _LEVEL_MAP.get(level, 'warning')

# 建议类级别（不扣分，仅展示提醒）
_SUGGESTION_LEVELS = ('suggestion', 'info')
def _is_suggestion_level(level: str) -> bool:
    """判断是否为建议类级别，建议类不扣分、不计入问题总数"""
    return level in _SUGGESTION_LEVELS

# ====================================================================
# 检查项分类
# ====================================================================
_PREFIX_MAP = {"MP-":"bug","AI-SPEC-":"bug","SEC-":"bug","PERF-":"bug","ARCH-":"code_smell","QUAL-":"code_smell"}
def get_check_category(check_id: str) -> str:
    if check_id in CHECK_CATEGORIES: return CHECK_CATEGORIES[check_id]
    for p, c in _PREFIX_MAP.items():
        if check_id.startswith(p): return c
    return "code_smell"

# ====================================================================
# 严重性分类（v3.5 权重评分模型）
# ====================================================================
_SEVERITY_CLASS_MAP = {
    "SEC-":"security","LLM-SEC-":"security","SKILL-SEC-":"security",
    "3.":"security","19.1":"security","19.2":"security","19.3":"security",
    "MP-001":"logic_bug","MP-004":"logic_bug","AI-SPEC-01":"logic_bug","AI-SPEC-02":"logic_bug",
    "1.":"logic_bug","2.":"logic_bug","4.":"logic_bug","7.":"logic_bug","8.":"logic_bug",
    "10.":"logic_bug","12.":"logic_bug","13.":"logic_bug","18.":"logic_bug","19.4":"logic_bug","19.5":"logic_bug",
    "MP-002":"convention","MP-003":"convention","MP-005":"convention","AI-SPEC-03":"convention","AI-SPEC-04":"convention",
    "5.":"convention","6.":"convention","9.":"convention","11.":"convention",
    "15.":"convention","16.":"convention","17.":"convention",
}
_CAT_TO_SEV = {"security":"security","wxml":"logic_bug","ai_specific":"logic_bug","ai_code_check":"logic_bug",
               "performance":"logic_bug","miniprogram_config":"convention","architecture":"convention",
               "code_quality":"convention","engineering":"convention"}
_PENALTY = {"security":{"error":40,"warning":15,"info":5},"logic_bug":{"error":25,"warning":8,"info":3},
            "convention":{"error":12,"warning":5,"info":2},"engineering_maturity":{"error":20,"warning":8,"info":2}}
_DEF_PEN = {"error":15,"warning":6,"info":2}
_SEV_DIM = {"security":"bug","logic_bug":"bug","convention":"code_smell","engineering_maturity":"engineering_maturity"}

def classify_severity(check_id: str, category_field: str = "") -> str:
    for rid, sc in _SEVERITY_CLASS_MAP.items():
        if check_id == rid: return sc
    if category_field and category_field in _CAT_TO_SEV: return _CAT_TO_SEV[category_field]
    for p, sc in _SEVERITY_CLASS_MAP.items():
        if check_id.startswith(p): return sc
    return "convention"

# ====================================================================
# 服务层延迟导入
# ====================================================================
def _import_services():
    try:
        import importlib; return importlib.import_module("..services", __name__)
    except (ImportError, ValueError):
        try:
            import os, sys; p = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if p not in sys.path: sys.path.insert(0, p)
            import services; return services
        except ImportError: return None

_SERVICES = _import_services()
def _get_scoring_service(mode="quick", config=None):
    if _SERVICES and hasattr(_SERVICES, 'get_scoring_service'): return _SERVICES.get_scoring_service(mode, config)
    return None

# ====================================================================
# ScoringEngine
# ====================================================================
class ScoringEngine:
    """评分引擎，基于检查结果计算各维度得分"""
    def __init__(self, context=None, scoring_mode="quick"):
        self._context = context
        self._mode = scoring_mode
        self._svc = None

    def calculate_scores(self, flat_results: list, config: dict = None) -> dict:
        svc = self._get_svc()
        if svc:
            active = [r for r in flat_results if getattr(r,'status','active')=='active']
            return svc.calculate_scores(
                [(r.rule_id.split('.')[0] if '.' in r.rule_id else r.rule_id, r) for r in active],
                project_type=getattr(self._context,'project_type',''),
                project_profile=getattr(self._context,'project_profile',None))
        return self._local(flat_results)

    def _get_svc(self):
        if self._svc is None:
            cfg = getattr(self._context,'config',None) if self._context else None
            self._svc = _get_scoring_service(mode=self._mode, config=cfg)
        return self._svc

    def _local(self, flat):
        active = [r for r in flat if getattr(r,'status','active')=='active']
        dim_pen = defaultdict(float)
        sev_stats = defaultdict(lambda: {"count":0,"penalty":0.0,"error":0,"warning":0,"info":0})
        suggestion_count = 0
        for r in active:
            cid = getattr(r,'check_id','') or getattr(r,'rule_id','') or ''
            sev = classify_severity(cid, getattr(r,'category','') or '')
            raw_level = getattr(r,'level','warning')
            lvl = normalize_level(raw_level)
            # 建议类 (suggestion/info) 不扣分，只统计数量
            if _is_suggestion_level(raw_level):
                suggestion_count += 1
                sev_stats[sev]["count"] += 1
                sev_stats[sev][lvl] += 1
                continue
            pen = _PENALTY.get(sev, _DEF_PEN).get(lvl, _DEF_PEN.get(lvl, 4))
            # 维度以 CHECK_CATEGORIES 定义为准，engineering_maturity 独立成维
            cat_dim = get_check_category(cid)
            dim_pen[cat_dim] += pen
            sev_stats[sev]["count"] += 1; sev_stats[sev]["penalty"] += pen; sev_stats[sev][lvl] += 1
        s = {}
        for d in ("bug","code_smell","engineering_maturity"): s[d] = max(0, int(100 - dim_pen.get(d, 0)))
        s["total"] = int(s.get("bug",100)*0.6 + s.get("code_smell",100)*0.3 + s.get("engineering_maturity",100)*0.1)
        s["bug_weight"], s["code_smell_weight"], s["engineering_maturity_weight"] = 0.6, 0.3, 0.1
        s["severity_breakdown"] = dict(sev_stats)
        s["scoring_model"] = "weighted_v3.5"
        s["suggestion_count"] = suggestion_count
        s["scoring_note"] = "基于代码问题评分，优化建议不扣分"
        return s
