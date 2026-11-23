# -*- coding: utf-8 -*-
"""守卫：问题分类（category）必须来自权威声明，不许再从编号猜。

事故背景（2026-11-04）：
  报告显示「安全 100 / 质量 70 / 架构 100」，同一页挂着 1 条越权高危。
  根因是 free_try._dim_of() 拿 check_id 匹配 9 个关键词，E2-BIZ-PY-002
  （检测器注册时写的就是 category="security"）一个都不中，被算成质量问题。

这一组测试钉三件事：
  1. 检测器注册表里的 category 优先，能一路传到对外输出
  2. E2 安全引擎产出的东西，100% 归 security（结构性事实，不靠白名单）
  3. 展示层不许再出现"按 id 关键词猜维度"的写法
"""
import importlib.util
import os
import re
import sys
from pathlib import Path

import pytest
from contextlib import contextmanager

ENGINE = Path('/opt/xinpect-scanner-green')
WEBSITE = Path('/opt/xinpect-website')
NORMALIZE = ENGINE / '_output_normalize.py'
FREE_TRY = WEBSITE / 'modules' / 'free_try.py'


def _readable(p: Path) -> bool:
    """能不能读到这个文件。

    直接 p.exists() 在父目录没 x 权限时会抛 PermissionError
    （/opt/xinpect-scanner-green 只给 xinpect-scan），测试收集阶段就崩，
    而不是优雅跳过。
    """
    try:
        return p.is_file() and os.access(str(p), os.R_OK)
    except (PermissionError, OSError):
        return False


# 引擎侧断言要读 /opt/xinpect-scanner-green（属主 xinpect-scan），
# 官网 pytest 以 xinpect-web 跑时读不到 —— 这类测试单独 skip，
# 真正的引擎侧守卫在 /opt/xinpect-scanner-green/verify_category_output.py，
# 由 run_qa_suite.sh 用 sudo -u xinpect-scan 调。
needs_engine = pytest.mark.skipif(
    not _readable(NORMALIZE),
    reason='读不到引擎文件，引擎侧守卫见 verify_category_output.py',
)
needs_site = pytest.mark.skipif(
    not _readable(FREE_TRY), reason='官网代码不在本机',
)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@contextmanager
def _engine_path():
    """临时把引擎根目录放进 sys.path，用完立刻移除。

    绝不能长期 insert：那个目录里也有个 app.py，一旦留在 sys.path 最前面，
    后续任何 `import app` 都会拿到扫描引擎的 Flask 应用。实测后果是
    test_funnel_analytics 四个用例全红，报 `'compensation_banner' is undefined`
    —— 页面其实是被 scanner-green 的 404 handler 渲染的，跟埋点毫无关系。
    测试之间的 sys.path 污染比测试失败更难查：症状出现在别的文件里。
    """
    sys.path.insert(0, str(ENGINE))
    try:
        yield
    finally:
        try:
            sys.path.remove(str(ENGINE))
        except ValueError:
            pass


def _normalize_one(check_id, category=None):
    issue = {'check_id': check_id, 'name': 'x', 'severity': 'high'}
    if category is not None:
        issue['category'] = category
    res = {'results': {'2': {'issues': [issue]}}}
    with _engine_path():
        norm = _load(NORMALIZE, f'norm_{abs(hash(check_id))}')
        norm.normalize_result(res)
    return res['results']['2']['issues'][0]


@needs_engine
def test_registry_declaration_wins():
    """注册时声明 security 的检测器，补出来的必须也是 security。

    E2-BIZ-PY-002 = Python Flask IDOR-路由参数直接查询，就是截图里那条。
    """
    out = _normalize_one('E2-BIZ-PY-002')
    assert out['category'] == 'security', out


@needs_engine
def test_security_engine_rule_without_registration():
    """不走 @register_check 的 E2 检测器（引擎段兜底）。

    E2-BS-IDOR-002 在 e2_security/check_idor.py 里直接 append，注册表查不到，
    但它百分百是安全问题——按编号首段的引擎归属兜底。
    """
    out = _normalize_one('E2-BS-IDOR-002')
    assert out['category'] == 'security', out


@needs_engine
def test_e2_prefix_never_lands_outside_security():
    """E2 系列全量必须 100% 归 security，一条都不许漏到别处。

    这条是这次事故的根因守卫：E2 是安全引擎，它产出的一切都是安全问题。
    """
    with _engine_path():
        norm = _load(NORMALIZE, 'norm_bulk')
    import subprocess
    out = subprocess.run(
        ['grep', '-rhoE', r'"check_id":\s*"[A-Za-z0-9_-]+"', str(ENGINE / 'engine')],
        capture_output=True, text=True).stdout
    ids = sorted(set(re.findall(r'"check_id":\s*"([A-Za-z0-9_-]+)"', out)))
    e2 = [i for i in ids if i.upper().startswith('E2-')]
    assert len(e2) > 100, f'E2 规则只找到 {len(e2)} 条，样本不对'

    res = {'results': {'2': {'issues': [
        {'check_id': i, 'name': 'x', 'severity': 'high'} for i in e2]}}}
    with _engine_path():
        norm.normalize_result(res)
    bad = [(x['check_id'], x['category']) for x in res['results']['2']['issues']
           if x['category'] != 'security']
    assert not bad, f'{len(bad)} 条 E2 规则没归安全：{bad[:8]}'


@needs_engine
def test_explicit_category_is_kept():
    """引擎自报的合法 category 不许被覆盖（幂等、尊重引擎判断）。"""
    out = _normalize_one('E1-NOT-EXIST-999', category='correctness')
    assert out['category'] == 'correctness', out


@needs_engine
def test_non_category_fields_untouched():
    """补分类只许动 category，name/severity/check_id 一个字都不许变。"""
    out = _normalize_one('E2-BIZ-PY-002')
    assert out['check_id'] == 'E2-BIZ-PY-002'
    assert out['severity'] == 'high'
    assert out['name'], 'name 被清空了'


def _free_try():
    """导入官网模块。modules/__init__ 会校验 XINPECT_SECRET（长度≥32），
    测试里给个占位值——这里只调 _health_score 纯函数，不碰数据库和网络。"""
    os.environ.setdefault('XINPECT_SECRET', 'pytest-placeholder-secret-0123456789abcdef')
    if str(WEBSITE) not in sys.path:
        sys.path.insert(0, str(WEBSITE))
    from modules import free_try
    return free_try


@needs_site
def test_dim_of_does_not_guess_from_id():
    """展示层不许再拿 check_id 猜维度。

    关键词表一旦回来，这条测试就红——那是这次事故的原始写法。
    """
    src = FREE_TRY.read_text(encoding='utf-8')
    m = re.search(r'def _dim_of\(.*?\n(.*?)\n\s{4}unclassified', src, re.S)
    assert m, '找不到 _dim_of 函数体'
    body = m.group(1)
    forbidden = ['-SEC-', '-TAINT-', 'INJECT', 'SQLI', 'CMDI', 'PATHTRAVER']
    hit = [k for k in forbidden if k in body]
    assert not hit, f'_dim_of 又在按编号关键词猜维度：{hit}'


@needs_site
def test_unclassified_high_blocks_perfect_security():
    """判不出维度的高危问题存在时，安全维度不许显示满分。

    "不知道"不能变成"100 分"——满分比不报更危险。
    """
    ft = _free_try()
    result = {'issues': [
        {'check_id': 'X-UNKNOWN-1', 'severity': 'high', 'category': ''},
    ], 'engines': {b: {'executed': True, 'issues': 0, 'error': ''} for b in ('1', '2', '4', '5', '6')}}
    health = ft._health_score(result)
    assert health['dims']['security'] == '待确认', health['dims']
    assert health['unclassified_high'] >= 1, health


@needs_site
def test_real_security_issue_deducts_security_dim():
    """归好类的安全问题，扣分必须落在安全维度上，而不是质量。"""
    ft = _free_try()
    result = {'issues': [
        {'check_id': 'E2-BIZ-PY-002', 'severity': 'high', 'category': 'security'},
    ], 'engines': {b: {'executed': True, 'issues': 0, 'error': ''} for b in ('1', '2', '4', '5', '6')}}
    health = ft._health_score(result)
    assert health['dims']['security'] < 100, health['dims']
    assert health['dims']['quality'] == 100, health['dims']
