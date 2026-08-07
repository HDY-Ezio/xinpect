#!/usr/bin/env python3
"""维度覆盖映射分析"""

import json, os, ast
from collections import defaultdict

RULES_DIR = os.path.dirname(os.path.abspath(__file__))

def extract_all_rules():
    """提取所有规则的详细信息"""
    all_rules = []
    
    for root, dirs, files in os.walk(RULES_DIR):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        rel_dir = os.path.relpath(root, RULES_DIR)
        if rel_dir == ".":
            continue
            
        for fname in files:
            fpath = os.path.join(root, fname)
            if fname.endswith('.json') and not fname.startswith('_part') and fname != 'whitelist_config.json':
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    for r in data.get('rules', []):
                        all_rules.append({
                            'id': r.get('id',''),
                            'name': r.get('name',''),
                            'category': r.get('category',''),
                            'dir': rel_dir,
                            'file': fname,
                        })
                except:  # noqa: intentional empty handler
                    pass
            elif fname.endswith('.py') and not fname.startswith('gen_') and fname not in ('__init__.py', 'merge.py', 'count_rules.py', 'coverage_analysis.py'):
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        source = f.read()
                    tree = ast.parse(source)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Assign):
                            for target in node.targets:
                                if isinstance(target, ast.Name) and target.id == 'RULES':
                                    if isinstance(node.value, ast.List):
                                        for elt in node.value.elts:
                                            if isinstance(elt, ast.Dict):
                                                r = {}
                                                for k, v in zip(elt.keys, elt.values):
                                                    if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                                                        r[k.value] = v.value
                                                if 'id' in r:
                                                    r['dir'] = rel_dir
                                                    r['file'] = fname
                                                    all_rules.append(r)
                except:  # noqa: intentional empty handler
                    pass
    return all_rules

# 132个维度定义
dimensions = {
    'B1': {
        'B1-01': '命名规范',
        'B1-02': '代码格式化',
        'B1-03': '注释与文档',
        'B1-04': '导入规范',
        'B1-05': '代码规模限制',
        'B1-06': '语法正确性',
        'B1-07': '变量声明与使用',
        'B1-08': '代码风格一致性',
        'B1-09': '注解规范',
        'B1-10': '空值基础检查',
        'B1-11': '资源泄漏基础模式',
        'B1-12': '前端可访问性(WCAG)',
        'B1-13': '前端语义化HTML',
        'B1-14': '响应式设计检查',
        'B1-15': '颜色对比度',
        'B1-16': '图标与排版规范',
        'B1-17': '国际化(i18n)',
        'B1-18': '前端性能基础',
        'B1-19': '错误提示与反馈',
        'B1-20': '移动端可用性',
        'B1-21': '编码约定(语言特定)',
        'B1-22': '文件与目录结构',
    },
    'B2': {
        'B2-01': 'SQL注入',
        'B2-02': '跨站脚本(XSS)',
        'B2-03': '命令注入',
        'B2-04': '路径遍历',
        'B2-05': '服务端请求伪造(SSRF)',
        'B2-06': '不安全反序列化',
        'B2-07': '身份认证缺陷',
        'B2-08': '访问控制缺失',
        'B2-09': '密码学失败',
        'B2-10': '安全配置错误',
        'B2-11': '敏感信息泄露',
        'B2-12': 'XML外部实体(XXE)',
        'B2-13': 'CSRF攻击',
        'B2-14': '不安全直接对象引用',
        'B2-15': '文件上传漏洞',
        'B2-16': '日志与监控不足',
        'B2-17': '软件与数据完整性失败',
        'B2-18': '不安全设计',
        'B2-19': '拒绝服务(DoS)',
        'B2-20': 'LDAP注入',
        'B2-21': '模板注入',
        'B2-22': 'Cookie安全',
        'B2-23': '开放重定向',
        'B2-24': '不安全API使用',
        'B2-25': '批量赋值(Mass Assignment)',
        'B2-26': '业务逻辑安全',
    },
    'B3': {
        'B3-01': '逻辑错误检测',
        'B3-02': '空指针深度分析',
        'B3-03': '并发与竞态条件',
        'B3-04': '异常处理正确性',
        'B3-05': '类型安全与类型错误',
        'B3-06': 'API契约违反',
        'B3-07': '资源生命周期管理',
        'B3-08': '算法正确性',
        'B3-09': '状态机完整性',
        'B3-10': '数据流一致性',
        'B3-11': '业务逻辑验证',
        'B3-12': '代码意图匹配',
        'B3-13': '表达式逻辑错误',
        'B3-14': '时间与日期处理',
        'B3-15': '文件I/O正确性',
        'B3-16': '正则表达式正确性',
        'B3-17': '死代码与无用计算',
        'B3-18': '测试语义审查',
        'B3-19': '安全语义增强',
        'B3-20': '重构建议生成',
        'B3-21': '代码可理解性',
    },
    'B4': {
        'B4-01': '循环性能优化',
        'B4-02': '字符串操作性能',
        'B4-03': '集合与数据结构选择',
        'B4-04': '内存泄漏模式',
        'B4-05': '不必要的对象创建',
        'B4-06': 'I/O效率问题',
        'B4-07': '数据库访问性能',
        'B4-08': '并发性能问题',
        'B4-09': '算法复杂度',
        'B4-10': '无用计算与重复计算',
        'B4-11': '正则表达式性能',
        'B4-12': '前端渲染性能',
        'B4-13': '启动/初始化性能',
        'B4-14': '网络请求优化',
        'B4-15': '图片与资源性能',
        'B4-16': '序列化/反序列化性能',
    },
    'B5': {
        'B5-01': '已知漏洞检测(CVE)',
        'B5-02': '依赖组件识别',
        'B5-03': '许可证合规检测',
        'B5-04': '过时组件检测',
        'B5-05': '恶意包检测',
        'B5-06': 'SBOM生成与管理',
        'B5-07': '漏洞可利用性评估',
        'B5-08': '依赖版本锁定',
        'B5-09': '传递依赖风险',
        'B5-10': '组件维护状态',
        'B5-11': '漏洞修复建议',
        'B5-12': '许可证义务追踪',
        'B5-13': '依赖瘦身优化',
    },
    'B6': {
        'B6-01': '认知复杂度',
        'B6-02': '圈复杂度',
        'B6-03': '代码重复率',
        'B6-04': '函数/方法质量',
        'B6-05': '类设计质量',
        'B6-06': '模块耦合度',
        'B6-07': '内聚性度量',
        'B6-08': '死代码与未使用代码',
        'B6-09': '魔法数字与魔法字符串',
        'B6-10': '错误的抽象层次',
        'B6-11': '过长参数列表',
        'B6-12': '过大类/上帝类',
        'B6-13': 'shotgun surgery',
        'B6-14': '数据泥团(Data Clumps)',
        'B6-15': '技术债务估算',
        'B6-16': '可维护性评分',
        'B6-17': '测试覆盖率',
        'B6-18': '注释质量与占比',
        'B6-19': '坏味道检测',
        'B6-20': '一致性与约定遵守',
        'B6-21': '重构建议',
        'B6-22': '代码质量趋势',
    },
    'B7': {
        'B7-01': '分层架构违规',
        'B7-02': '循环依赖检测',
        'B7-03': '模块边界合规',
        'B7-04': '单向依赖原则',
        'B7-05': '耦合度与扇出控制',
        'B7-06': 'ADR(架构决策记录)合规',
        'B7-07': 'API契约一致性',
        'B7-08': '微服务边界完整性',
        'B7-09': '依赖注入合规',
        'B7-10': '架构腐化趋势',
        'B7-11': '领域模型纯度',
        'B7-12': '包/命名空间结构合规',
    },
}

# 手动映射：规则关键字 → 维度
# 基于对规则name和category的分析
keyword_to_dim = {
    # B1 mapping
    '命名': 'B1-01', 'naming': 'B1-01', 'NAME-': 'B1-01',
    '格式化': 'B1-02', '缩进': 'B1-02', '空格': 'B1-02', '换行': 'B1-02',
    '注释': 'B1-03', '文档': 'B1-03', 'TODO': 'B1-03', 'FIXME': 'B1-03', 'Javadoc': 'B1-03', 'TSDoc': 'B1-03', 'DOC-': 'B1-03',
    '导入': 'B1-04', 'import': 'B1-04', '未使用导入': 'B1-04',
    '代码规模': 'B1-05', '方法长度': 'B1-05', '类长度': 'B1-05', '文件行数': 'B1-05', '参数数量': 'B1-05', '嵌套深度': 'B1-05',
    '语法': 'B1-06', '闭合': 'B1-06', 'JS语法': 'B1-06',
    '变量': 'B1-07', '未使用变量': 'B1-07', '重复声明': 'B1-07', '作用域': 'B1-07',
    '魔法数字': 'B1-08', '字面量': 'B1-08', 'MAGIC-': 'B1-08', '代码风格': 'B1-08',
    '注解': 'B1-09', 'Deprecated': 'B1-09', 'Override': 'B1-09',
    '空指针': 'B1-10', 'null': 'B1-10', '空值': 'B1-10',
    '资源泄漏': 'B1-11', '未关闭': 'B1-11', '流': 'B1-11',
    '可访问性': 'B1-12', 'WCAG': 'B1-12', 'alt': 'B1-12', 'ARIA': 'B1-12', '无障碍': 'B1-12',
    '语义化': 'B1-13', 'HTML': 'B1-13', 'wxml': 'B1-13', 'WXML': 'B1-13',
    '响应式': 'B1-14', '断点': 'B1-14', '移动适配': 'B1-14',
    '对比度': 'B1-15', '颜色': 'B1-15',
    '图标': 'B1-16', '排版': 'B1-16', '字体': 'B1-16',
    '国际化': 'B1-17', 'i18n': 'B1-17', '硬编码字符串': 'B1-17',
    '前端性能': 'B1-18', '未使用CSS': 'B1-18', '大图': 'B1-18', '懒加载': 'B1-18',
    '错误提示': 'B1-19', '表单验证': 'B1-19', '加载状态': 'B1-19', 'loading': 'B1-19',
    '触摸': 'B1-20', '手势': 'B1-20', '横屏': 'B1-20', '移动端': 'B1-20',
    '编码约定': 'B1-21', 'PEP8': 'B1-21', 'TypeScript': 'B1-21', 'TS-': 'B1-21', '语言特定': 'B1-21',
    '文件与目录': 'B1-22', '目录结构': 'B1-22', '文件命名': 'B1-22',
    
    # B2 mapping
    'SQL注入': 'B2-01', 'sql-injection': 'B2-01', 'SQL': 'B2-01',
    'XSS': 'B2-02', 'xss': 'B2-02', '跨站脚本': 'B2-02',
    '命令注入': 'B2-03', 'command-injection': 'B2-03', '系统命令': 'B2-03',
    '路径遍历': 'B2-04', 'path-traversal': 'B2-04',
    'SSRF': 'B2-05', 'ssrf': 'B2-05', '服务端请求伪造': 'B2-05',
    '反序列化': 'B2-06', 'deserialization': 'B2-06',
    '认证': 'B2-07', 'authentication': 'B2-07', '密码强度': 'B2-07', '会话': 'B2-07', 'MFA': 'B2-07',
    '访问控制': 'B2-08', 'authorization': 'B2-08', '越权': 'B2-08', 'IDOR': 'B2-08', '权限': 'B2-08',
    '加密': 'B2-09', 'cryptography': 'B2-09', '弱哈希': 'B2-09', '随机数': 'B2-09',
    '安全配置': 'B2-10', 'misconfiguration': 'B2-10', '默认密码': 'B2-10', '调试模式': 'B2-10', 'CORS': 'B2-10', '安全头部': 'B2-10', 'config_headers': 'B2-10',
    '信息泄露': 'B2-11', 'info-leakage': 'B2-11', '硬编码密码': 'B2-11', '敏感信息': 'B2-11',
    'XXE': 'B2-12', 'xml-injection': 'B2-12', 'XML外部实体': 'B2-12',
    'CSRF': 'B2-13', 'csrf': 'B2-13',
    'IDOR': 'B2-14', '不安全直接对象引用': 'B2-14',
    '文件上传': 'B2-15', 'file-upload': 'B2-15',
    '日志': 'B2-16', '监控': 'B2-16', '审计': 'B2-16',
    '完整性': 'B2-17', 'integrity': 'B2-17', 'supply-chain': 'B2-17', '签名': 'B2-17',
    '不安全设计': 'B2-18', '业务逻辑': 'B2-18', '威胁建模': 'B2-18',
    'DoS': 'B2-19', 'ReDoS': 'B2-19', '拒绝服务': 'B2-19', 'dos': 'B2-19',
    'LDAP': 'B2-20', 'ldap': 'B2-20',
    '模板注入': 'B2-21', 'SSTI': 'B2-21', 'Jinja': 'B2-21',
    'Cookie': 'B2-22', 'cookie': 'B2-22', 'HttpOnly': 'B2-22', 'SameSite': 'B2-22',
    '重定向': 'B2-23', 'open-redirect': 'B2-23',
    '不安全API': 'B2-24', '危险函数': 'B2-24', '废弃API': 'B2-24',
    '批量赋值': 'B2-25', 'Mass Assignment': 'B2-25',
    '业务逻辑安全': 'B2-26', '支付绕过': 'B2-26',
    
    # B3 mapping
    '逻辑错误': 'B3-01', 'logic-pattern': 'B3-01', '条件判断': 'B3-01', '矛盾': 'B3-01',
    '空指针深度': 'B3-02', 'null-safety': 'B3-02',
    '并发': 'B3-03', '竞态': 'B3-03', '死锁': 'B3-03',
    '异常处理': 'B3-04', 'exception-handling': 'B3-04', '异常吞': 'B3-04',
    '类型安全': 'B3-05', '类型错误': 'B3-05', '类型转换': 'B3-05',
    'API契约': 'B3-06',
    '资源生命周期': 'B3-07', '双重释放': 'B3-07',
    '算法正确性': 'B3-08',
    '状态机': 'B3-09',
    '数据流': 'B3-10', 'data_consistency': 'B3-10',
    '业务逻辑验证': 'B3-11', 'business_flow': 'B3-11',
    '代码意图': 'B3-12',
    '表达式': 'B3-13', '运算符': 'B3-13',
    '时间': 'B3-14', '日期': 'B3-14', '时区': 'B3-14',
    '文件I/O': 'B3-15',
    '正则表达式': 'B3-16',
    '死代码': 'B3-17', 'dead-code': 'B3-17', '无用计算': 'B3-17',
    '测试语义': 'B3-18',
    '安全语义': 'B3-19', 'security_extension': 'B3-19', 'llm_security': 'B3-19',
    '重构建议': 'B3-20',
    '可理解性': 'B3-21',
    
    # B4 mapping
    '循环': 'B4-01',
    '字符串操作': 'B4-02', '字符串拼接': 'B4-02',
    '集合': 'B4-03', '数据结构': 'B4-03',
    '内存泄漏': 'B4-04', 'memory': 'B4-04',
    '对象创建': 'B4-05',
    'I/O效率': 'B4-06', 'io': 'B4-06',
    '数据库': 'B4-07', 'database': 'B4-07', 'N+1': 'B4-07',
    '并发性能': 'B4-08',
    '算法复杂度': 'B4-09', 'algorithm': 'B4-09',
    '无用计算': 'B4-10', '重复计算': 'B4-10',
    '正则': 'B4-11',
    '渲染性能': 'B4-12', '重排': 'B4-12', '重绘': 'B4-12', 'DOM': 'B4-12',
    '启动': 'B4-13', '初始化': 'B4-13',
    '网络请求': 'B4-14', 'network': 'B4-14',
    '图片': 'B4-15',
    '序列化': 'B4-16',
    
    # B5 mapping
    'CVE': 'B5-01', 'dependency_security': 'B5-01', '已知': 'B5-01',
    '组件识别': 'B5-02', '传递依赖': 'B5-02',
    '许可证': 'B5-03', 'dependency_license': 'B5-03',
    '过时': 'B5-04',
    '恶意包': 'B5-05',
    'SBOM': 'B5-06',
    '可利用性': 'B5-07',
    '版本锁定': 'B5-08', 'Lock': 'B5-08', 'lock': 'B5-08',
    '传递依赖风险': 'B5-09',
    '维护状态': 'B5-10', 'dependency_quality': 'B5-10',
    '修复建议': 'B5-11',
    '许可证义务': 'B5-12',
    '依赖瘦身': 'B5-13',
    
    # B6 mapping  
    '认知复杂度': 'B6-01',
    '圈复杂度': 'B6-02', 'complexity': 'B6-02',
    '重复率': 'B6-03', 'duplication': 'B6-03', 'duplicate': 'B6-03',
    '函数': 'B6-04', '方法质量': 'B6-04',
    '类设计': 'B6-05', 'maintainability': 'B6-05',
    '耦合度': 'B6-06',
    '内聚性': 'B6-07',
    '死代码': 'B6-08',
    '魔法数字': 'B6-09', 'magic_literal': 'B6-09',
    '抽象层次': 'B6-10',
    '参数列表': 'B6-11',
    '过大类': 'B6-12', '上帝类': 'B6-12',
    'shotgun': 'B6-13',
    '数据泥团': 'B6-14',
    '技术债务': 'B6-15',
    '可维护性': 'B6-16',
    '测试覆盖': 'B6-17', 'testing': 'B6-17',
    '注释质量': 'B6-18',
    '坏味道': 'B6-19', 'code_smell': 'B6-19',
    '一致性': 'B6-20', '约定遵守': 'B6-20',
    '重构建议': 'B6-21',
    '质量趋势': 'B6-22',
    
    # B7 mapping
    '分层': 'B7-01', 'layer_violation': 'B7-01', 'code_layering': 'B7-01',
    '循环依赖': 'B7-02', 'circular_dependency': 'B7-02',
    '模块边界': 'B7-03', 'module_boundary': 'B7-03',
    '单向依赖': 'B7-04', 'dependency_structure': 'B7-04',
    '扇出': 'B7-05',
    'ADR': 'B7-06',
    'API契约': 'B7-07', 'restful': 'B7-07', 'versioning': 'B7-07',
    '微服务': 'B7-08', 'service_boundary': 'B7-08',
    '依赖注入': 'B7-09',
    '架构腐化': 'B7-10',
    '领域模型': 'B7-11',
    '包/命名空间': 'B7-12', 'directory_structure': 'B7-12', 'file_naming': 'B7-12',
}

all_rules = extract_all_rules()
print(f"总共提取了 {len(all_rules)} 条规则")

# 现在按大脑分析覆盖情况
# 手动映射每个维度到已知覆盖的规则（基于上面的分析）
coverage = {}
for brain, dims in dimensions.items():
    coverage[brain] = {}
    for dim_id, dim_name in dims.items():
        coverage[brain][dim_id] = {'name': dim_name, 'covered': False, 'rules': [], 'count': 0}

# 对每条规则尝试匹配维度
# 这里用更精确的文件级映射
b1_rule_files = ['common', 'javascript', 'miniprogram', 'web', 'agent', 'ai_code_check', 'python', 'skill', 'electron']

file_to_dim_mapping = {
    # B1
    'common/naming_convention_rules.py': ['B1-01'],
    'common/doc_rules.py': ['B1-03'],
    'common/reflection.py': ['B1-03'],  # TODO/FIXME tracking
    'common/dead_code_rules.py': ['B1-04', 'B1-07'],
    'common/code_review_common.json': ['B1-05', 'B1-08'],
    'common/complexity_rules.py': ['B1-05'],
    'common/magic_literal_rules.py': ['B1-08'],
    'common/typescript_rules.py': ['B1-21'],
    'common/error_handling.py': ['B1-06'],
    'common/error_handling_rules.json': ['B1-06'],
    'common/security.py': ['B2-01', 'B2-02', 'B2-03'],  # general security in B1
    'common/security_common.json': ['B2-01', 'B2-02', 'B2-03', 'B2-11'],
    'common/performance.py': ['B1-18', 'B4-15'],
    'common/css_convention_rules.py': ['B1-02'],
    'common/supplementary_rules.py': ['B1-05', 'B1-08'],
    'common/supplementary_rules_2.py': ['B2-24'],
    'common/logging_rules.json': ['B2-16'],
    'common/config_management.json': ['B2-10', 'B2-11'],
    'common/git_convention_rules.py': ['B1-22'],
    'common/deploy.py': ['B1-22'],
    'common/miniapp_ux.json': ['B1-12', 'B1-13', 'B1-19'],
    'common/miniapp_performance.json': ['B1-18'],
    'common/wx_api_security.json': ['B2-02', 'B2-10'],
    'common/smoke_test.py': ['B1-06'],
    'common/business_flow.py': ['B1-19', 'B3-11'],
    'common/architecture.py': ['B6-01', 'B6-02', 'B6-03'],
    'common/code_quality.py': ['B6-04', 'B6-08', 'B6-09'],
    'common/component_design_rules.py': ['B6-05'],
    'common/duplicate_advanced_rules.py': ['B6-03'],
    'common/dep_release_rules.py': ['B5-04'],
    'common/env_build_rules.py': ['B1-22'],
    'common/test_ci.py': ['B6-17'],
    'common/change_impact.py': ['B3-06'],
    'common/doc_consistency_rules.py': ['B6-18'],
    'javascript/js_ts_rules.json': ['B1-01', 'B1-02', 'B1-06', 'B1-07', 'B1-08', 'B1-21'],
    'miniprogram/miniprogram_community_rules.json': ['B1-06', 'B1-08', 'B1-18'],
    'miniprogram/config.py': ['B1-06', 'B1-22'],
    'miniprogram/js_syntax.py': ['B1-06'],
    'miniprogram/wxml_rules.py': ['B1-13'],
    'miniprogram/wxss_rules.py': ['B1-02', 'B1-14'],
    'miniprogram/navigation.py': ['B1-20'],
    'miniprogram/component_check.py': ['B1-20'],
    'miniprogram/lifecycle.py': ['B1-07'],
    'miniprogram/security_rules.py': ['B2-10'],
    'web/frontend_rules.py': ['B1-12', 'B1-13', 'B1-14', 'B1-16', 'B1-17', 'B1-18', 'B1-19'],
    'web/security_p0.py': ['B2-01', 'B2-02', 'B2-03'],
    'agent/llm_security.py': ['B3-19'],
    'ai_code_check/ai_specific_rules.py': ['B1-06', 'B3-01'],
    'ai_code_check/quality_rules.py': ['B3-12', 'B3-21'],
    'ai_code_check/security_rules.py': ['B3-19'],
    'python/api_linkage.py': ['B1-21'],
    'python/backend_rules.py': ['B1-21'],
    'python/data_consistency.py': ['B3-10'],
    'skill/skill_rules.py': ['B1-21'],
    'electron/electron_rules.py': ['B1-21'],
    
    # B2
    'brain2_security/sql_injection.json': ['B2-01'],
    'brain2_security/xss.json': ['B2-02'],
    'brain2_security/path_traversal_command.json': ['B2-03', 'B2-04'],
    'brain2_security/ssrf_file_upload.json': ['B2-05', 'B2-15'],
    'brain2_security/deserialization.json': ['B2-06'],
    'brain2_security/auth_authentication.json': ['B2-07', 'B2-08'],
    'brain2_security/cryptography.json': ['B2-09'],
    'brain2_security/config_headers.json': ['B2-10'],
    'brain2_security/info_leakage.json': ['B2-11'],
    'brain2_security/csrf.json': ['B2-13'],
    'brain2_security/misc_security.json': ['B2-12', 'B2-16', 'B2-17', 'B2-19', 'B2-20', 'B2-21', 'B2-22', 'B2-23', 'B2-24'],
    
    # B3
    'brain3_semantic/logic_pattern_rules.json': ['B3-01', 'B3-13'],
    'brain3_semantic/null_safety_rules.json': ['B3-02'],
    'brain3_semantic/exception_handling_rules.json': ['B3-04'],
    'brain3_semantic/callback_nesting_rules.json': ['B3-03'],
    'brain3_semantic/dead_code_rules.json': ['B3-17'],
    'brain3_semantic/unused_code_rules.json': ['B3-17'],
    'brain3_semantic/hardcoded_secrets_rules.json': ['B2-11'],  # overlaps with B2
    'brain3_semantic/inconsistent_return_rules.json': ['B3-01'],
    
    # B4
    'brain4_performance/perf_algorithm_rules.json': ['B4-09', 'B4-01'],
    'brain4_performance/perf_build_rules.json': ['B4-13'],
    'brain4_performance/perf_caching_rules.json': ['B4-07'],
    'brain4_performance/perf_concurrency_rules.json': ['B4-08'],
    'brain4_performance/perf_database_rules.json': ['B4-07'],
    'brain4_performance/perf_frontend_rules.json': ['B4-12'],
    'brain4_performance/perf_io_rules.json': ['B4-06'],
    'brain4_performance/perf_memory_rules.json': ['B4-04'],
    'brain4_performance/perf_network_rules.json': ['B4-14'],
    
    # B5
    'brain5_deps/dependency_security.json': ['B5-01'],
    'brain5_deps/dependency_config.json': ['B5-02', 'B5-08'],
    'brain5_deps/dependency_license.json': ['B5-03'],
    'brain5_deps/dependency_quality.json': ['B5-04', 'B5-10'],
    
    # B6
    'brain6_code_quality/complexity_rules.json': ['B6-01', 'B6-02'],
    'brain6_code_quality/documentation_rules.json': ['B6-18'],
    'brain6_code_quality/duplication_rules.json': ['B6-03'],
    'brain6_code_quality/error_handling_quality.json': ['B3-04'],  # quality aspect
    'brain6_code_quality/maintainability_rules.json': ['B6-05', 'B6-06', 'B6-15'],
    'brain6_code_quality/naming_convention_rules.json': ['B6-20'],  # naming as quality
    'brain6_code_quality/testing_quality_rules.json': ['B6-17'],
    
    # B7
    'brain7_architecture/dependency_structure.json': ['B7-01', 'B7-02', 'B7-03', 'B7-04'],
    'brain7_architecture/api_design.json': ['B7-07'],
    'brain7_architecture/code_organization.json': ['B7-12', 'B6-05'],
    'brain7_architecture/design_patterns.json': ['B6-19', 'B7-05'],
    'brain7_architecture/microservice_rules.json': ['B7-08'],
    'brain7_architecture/testing_architecture.json': ['B6-17'],

    # === 新增42个规则文件 ===
    # B1 新增
    'common/annotation_rules.json': ['B1-09'],
    'common/null_check_rules.json': ['B1-10'],
    'common/resource_leak_rules.json': ['B1-11'],
    'web/accessibility_rules.json': ['B1-15'],

    # B2 新增
    'brain2_security/idor.json': ['B2-14'],
    'brain2_security/insecure_design.json': ['B2-18'],
    'brain2_security/mass_assignment.json': ['B2-25'],
    'brain2_security/business_logic_security.json': ['B2-26'],

    # B3 新增
    'brain3_semantic/type_safety_rules.json': ['B3-05'],
    'brain3_semantic/resource_lifecycle_rules.json': ['B3-07'],
    'brain3_semantic/algorithm_correctness_rules.json': ['B3-08'],
    'brain3_semantic/state_machine_rules.json': ['B3-09'],
    'brain3_semantic/datetime_rules.json': ['B3-14'],
    'brain3_semantic/file_io_rules.json': ['B3-15'],
    'brain3_semantic/regex_correctness_rules.json': ['B3-16'],
    'brain3_semantic/test_semantic_rules.json': ['B3-18'],
    'brain3_semantic/refactor_suggestion_rules.json': ['B3-20'],

    # B4 新增
    'brain4_performance/perf_string_rules.json': ['B4-02'],
    'brain4_performance/perf_collection_rules.json': ['B4-03'],
    'brain4_performance/perf_object_creation_rules.json': ['B4-05'],
    'brain4_performance/perf_redundant_computation_rules.json': ['B4-10'],
    'brain4_performance/perf_regex_rules.json': ['B4-11'],
    'brain4_performance/perf_serialization_rules.json': ['B4-16'],

    # B5 新增
    'brain5_deps/dependency_malware.json': ['B5-05'],
    'brain5_deps/dependency_sbom.json': ['B5-06'],
    'brain5_deps/dependency_exploitability.json': ['B5-07'],
    'brain5_deps/dependency_transitive.json': ['B5-09'],
    'brain5_deps/dependency_remediation.json': ['B5-11'],
    'brain5_deps/dependency_license_obligation.json': ['B5-12'],
    'brain5_deps/dependency_optimization.json': ['B5-13'],

    # B6 新增
    'brain6_code_quality/cohesion_rules.json': ['B6-07'],
    'brain6_code_quality/abstraction_rules.json': ['B6-10'],
    'brain6_code_quality/parameter_rules.json': ['B6-11'],
    'brain6_code_quality/god_class_rules.json': ['B6-12'],
    'brain6_code_quality/bad_smell_extra_rules.json': ['B6-13', 'B6-14'],
    'brain6_code_quality/maintainability_score_rules.json': ['B6-16'],
    'brain6_code_quality/refactor_rules.json': ['B6-21'],
    'brain6_code_quality/quality_trend_rules.json': ['B6-22'],

    # B7 新增
    'brain7_architecture/adr_rules.json': ['B7-06'],
    'brain7_architecture/di_rules.json': ['B7-09'],
    'brain7_architecture/architecture_decay_rules.json': ['B7-10'],
    'brain7_architecture/domain_purity_rules.json': ['B7-11'],
}

# 统计每个维度的覆盖情况
dim_rule_count = defaultdict(int)
dim_rule_names = defaultdict(list)

for filepath, dim_list in file_to_dim_mapping.items():
    # count rules in this file
    fpath = os.path.join(RULES_DIR, filepath)
    count = 0
    names = []
    if os.path.exists(fpath):
        if fpath.endswith('.json'):
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for r in data.get('rules', []):
                    if r.get('id'):
                        count += 1
                        names.append(r.get('name', ''))
            except:  # noqa: intentional empty handler
                pass
        elif fpath.endswith('.py'):
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    source = f.read()
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name) and target.id == 'RULES':
                                if isinstance(node.value, ast.List):
                                    for elt in node.value.elts:
                                        if isinstance(elt, ast.Dict):
                                            for k, v in zip(elt.keys, elt.values):
                                                if isinstance(k, ast.Constant) and k.value == 'id' and isinstance(v, ast.Constant):
                                                    count += 1
                                                    # get name
                                                    for k2, v2 in zip(elt.keys, elt.values):
                                                        if isinstance(k2, ast.Constant) and k2.value == 'name' and isinstance(v2, ast.Constant):
                                                            names.append(v2.value)
            except:  # noqa: intentional empty handler
                pass
    
    for dim in dim_list:
        dim_rule_count[dim] += count
        dim_rule_names[dim].extend(names[:5])  # keep first 5 names as sample

# Print coverage report
print("\n" + "="*80)
print("维度覆盖分析报告")
print("="*80)

total_covered = 0
total_uncovered = 0
uncovered_dims = {}

for brain in ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7']:
    dims = dimensions[brain]
    covered_count = 0
    uncovered_list = []
    
    print(f"\n{'─'*60}")
    print(f"  {brain} - 共{len(dims)}个维度")
    print(f"{'─'*60}")
    
    for dim_id, dim_name in dims.items():
        count = dim_rule_count.get(dim_id, 0)
        if count > 0:
            status = "✅ 已覆盖"
            covered_count += 1
        else:
            status = "❌ 未覆盖"
            uncovered_list.append((dim_id, dim_name))
        
        print(f"  {dim_id} {dim_name:<25s} {status} ({count}条规则)")
    
    total_covered += covered_count
    total_uncovered += len(uncovered_list)
    uncovered_dims[brain] = uncovered_list
    print(f"  → 覆盖: {covered_count}/{len(dims)} ({covered_count/len(dims)*100:.0f}%)")

print(f"\n{'='*80}")
print(f"总计: {total_covered}/132 维度已覆盖 ({total_covered/132*100:.1f}%)")
print(f"未覆盖: {total_uncovered} 个维度")

print(f"\n{'='*80}")
print("未覆盖维度汇总:")
for brain, dims in uncovered_dims.items():
    if dims:
        print(f"\n  {brain}:")
        for dim_id, dim_name in dims:
            print(f"    ❌ {dim_id} - {dim_name}")

