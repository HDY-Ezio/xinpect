#!/usr/bin/env python3
"""
煋鉴(Xinpect) 规则统计脚本
统一计数口径：JSON的rules数组条目 + Python的RULES列表条目，按规则ID全局去重

用法：
    python3 count_rules.py              # 完整报告
    python3 count_rules.py --brief      # 简洁摘要
    python3 count_rules.py --json       # JSON格式输出
    python3 count_rules.py --coverage   # 覆盖率分析（含覆盖领域统计）
"""

import json
import os
import re
import sys
import ast
from collections import defaultdict
from pathlib import Path

# ===== 配置 =====
RULES_DIR = Path(__file__).parent

# 目录 → 大脑映射
DIR_TO_BRAIN = {
    "common":              "B1_规则引擎",
    "javascript":          "B1_规则引擎",
    "miniprogram":         "B1_规则引擎",
    "web":                 "B1_规则引擎",
    "agent":               "B1_规则引擎",
    "ai_code_check":       "B1_规则引擎",
    "python":              "B1_规则引擎",
    "skill":               "B1_规则引擎",
    "electron":            "B1_规则引擎",
    "brain2_security":     "B2_安全扫描",
    "brain3_semantic":     "B3_AI语义分析",
    "brain4_performance":  "B4_性能分析",
    "brain5_deps":         "B5_依赖审计",
    "brain6_code_quality": "B6_代码质量",
    "brain7_architecture": "B7_架构合规",
}

# 排除的文件模式
EXCLUDE_FILES = {
    "__init__.py", "merge.py", "whitelist_config.json",
}
EXCLUDE_PREFIXES_PY = ("gen_", "_gen_")
EXCLUDE_PREFIXES_JSON = ("_part",)

# 大脑显示名称
BRAIN_DISPLAY = {
    "B1_规则引擎":     "Brain 1 · 规则引擎(含UI/UX)",
    "B2_安全扫描":     "Brain 2 · 安全扫描",
    "B3_AI语义分析":   "Brain 3 · AI语义分析(LLM)",
    "B4_性能分析":     "Brain 4 · 性能分析",
    "B5_依赖审计":     "Brain 5 · 依赖审计",
    "B6_代码质量":     "Brain 6 · 代码质量",
    "B7_架构合规":     "Brain 7 · 架构合规",
}


def should_skip(filename):
    """判断是否应跳过该文件"""
    if filename in EXCLUDE_FILES:
        return True
    if filename.endswith(".py"):
        return any(filename.startswith(p) for p in EXCLUDE_PREFIXES_PY)
    if filename.endswith(".json"):
        return any(filename.startswith(p) for p in EXCLUDE_PREFIXES_JSON)
    return False


def extract_ids_from_json(filepath):
    """从JSON文件的rules数组中提取规则ID"""
    ids = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        rules = data.get("rules", [])
        for rule in rules:
            rid = rule.get("id")
            if rid:
                ids.append(str(rid))
    except Exception as e:  # noqa: intentional catch-all
        print(f"  ⚠️  JSON解析失败: {filepath}: {e}", file=sys.stderr)
    return ids


def extract_ids_from_python(filepath):
    """从Python文件的RULES列表中提取规则ID"""
    ids = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "RULES":
                        if isinstance(node.value, ast.List):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Dict):
                                    for k, v in zip(elt.keys, elt.values):
                                        if isinstance(k, ast.Constant) and k.value == "id":
                                            if isinstance(v, ast.Constant):
                                                ids.append(str(v.value))
    except Exception as e:  # noqa: intentional catch-all
        print(f"  ⚠️  Python解析失败: {filepath}: {e}", file=sys.stderr)
    return ids


def extract_categories_from_json(filepath):
    """从JSON文件中提取规则的category分布"""
    cats = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        rules = data.get("rules", [])
        for rule in rules:
            cat = rule.get("category", "未分类")
            rid = rule.get("id")
            if rid:
                cats.append((str(rid), cat))
    except:  # noqa: intentional empty handler
        pass
    return cats


def scan_all():
    """扫描所有规则文件，返回结构化数据"""
    # 结果结构
    all_rules = {}  # id -> {source, brain, dir, category, severity}
    brain_counts = defaultdict(set)  # brain -> set of ids
    dir_counts = defaultdict(set)  # dir -> set of ids
    category_counts = defaultdict(set)  # category -> set of ids
    file_stats = []  # 每个文件的统计

    for root, dirs, files in os.walk(RULES_DIR):
        # 跳过__pycache__
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        
        rel_dir = os.path.relpath(root, RULES_DIR)
        if rel_dir == ".":
            continue
        
        brain = DIR_TO_BRAIN.get(rel_dir, f"未知({rel_dir})")
        
        for fname in sorted(files):
            if should_skip(fname):
                continue
            
            fpath = os.path.join(root, fname)
            ids = []
            file_type = None
            
            if fname.endswith(".json"):
                ids = extract_ids_from_json(fpath)
                file_type = "JSON"
            elif fname.endswith(".py"):
                ids = extract_ids_from_python(fpath)
                file_type = "Python"
            
            if not ids:
                continue
            
            new_ids = 0
            for rid in ids:
                if rid not in all_rules:
                    all_rules[rid] = {
                        "source": fname,
                        "brain": brain,
                        "dir": rel_dir,
                        "type": file_type,
                    }
                    brain_counts[brain].add(rid)
                    dir_counts[rel_dir].add(rid)
                    new_ids += 1
            
            file_stats.append({
                "file": f"{rel_dir}/{fname}",
                "type": file_type,
                "total": len(ids),
                "new": new_ids,
                "dup": len(ids) - new_ids,
            })
    
    return all_rules, brain_counts, dir_counts, category_counts, file_stats


def scan_categories():
    """单独扫描category分布（仅JSON文件，因为Python的category在RULES里也有）"""
    cat_map = defaultdict(set)  # category -> set of ids
    
    for root, dirs, files in os.walk(RULES_DIR):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        rel_dir = os.path.relpath(root, RULES_DIR)
        if rel_dir == ".":
            continue
        
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            if fname.endswith(".json") and not should_skip(fname):
                pairs = extract_categories_from_json(fpath)
                for rid, cat in pairs:
                    cat_map[cat].add(rid)
            elif fname.endswith(".py") and not should_skip(fname):
                # 也从Python的RULES中提取category
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        source = f.read()
                    tree = ast.parse(source)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Assign):
                            for target in node.targets:
                                if isinstance(target, ast.Name) and target.id == "RULES":
                                    if isinstance(node.value, ast.List):
                                        for elt in node.value.elts:
                                            if isinstance(elt, ast.Dict):
                                                rid = None
                                                cat = "未分类"
                                                for k, v in zip(elt.keys, elt.values):
                                                    if isinstance(k, ast.Constant):
                                                        if k.value == "id" and isinstance(v, ast.Constant):
                                                            rid = str(v.value)
                                                        if k.value == "category" and isinstance(v, ast.Constant):
                                                            cat = str(v.value)
                                                if rid:
                                                    cat_map[cat].add(rid)
                except:  # noqa: intentional empty handler
                    pass
    
    return cat_map


def print_report(all_rules, brain_counts, dir_counts, file_stats, cat_map):
    """打印完整报告"""
    total = len(all_rules)
    
    print("=" * 60)
    print("  煋鉴(Xinpect) 规则统计报告")
    print(f"  统计口径: JSON rules数组 + Python RULES列表, 按ID全局去重")
    print("=" * 60)
    print()
    
    # 按大脑汇总
    print("📊 按大脑统计")
    print("-" * 50)
    
    brain_order = ["B1_规则引擎", "B2_安全扫描", "B3_AI语义分析", 
                   "B4_性能分析", "B5_依赖审计", "B6_代码质量", "B7_架构合规"]
    
    for brain in brain_order:
        display = BRAIN_DISPLAY.get(brain, brain)
        count = len(brain_counts.get(brain, set()))
        pct = f"{count/total*100:.1f}%" if total > 0 else "0%"
        bar = "█" * int(count / total * 30) if total > 0 else ""
        print(f"  {display:<30s} {count:>5d}条  ({pct}) {bar}")
    
    print(f"  {'─' * 45}")
    print(f"  {'总计':<30s} {total:>5d}条")
    print()
    
    # 按子目录明细
    print("📁 按目录明细")
    print("-" * 50)
    for brain in brain_order:
        dirs_in_brain = sorted([d for d, b in DIR_TO_BRAIN.items() if b == brain])
        if not dirs_in_brain:
            continue
        brain_total = len(brain_counts.get(brain, set()))
        if brain_total == 0 and brain != "B3_AI语义分析":
            continue
        print(f"  {BRAIN_DISPLAY.get(brain, brain)}")
        for d in dirs_in_brain:
            count = len(dir_counts.get(d, set()))
            if count > 0:
                print(f"    └─ {d:<25s} {count:>4d}条")
        if brain == "B3_AI语义分析":
            print(f"    └─ (LLM驱动，无静态规则)")
    print()
    
    # 按覆盖领域统计
    print("🏷️ 按覆盖领域统计")
    print("-" * 50)
    sorted_cats = sorted(cat_map.items(), key=lambda x: -len(x[1]))
    for cat, ids in sorted_cats:
        if len(ids) >= 3:
            print(f"  {cat:<35s} {len(ids):>4d}条")
    print()
    
    # 文件级明细
    print("📄 文件级明细")
    print("-" * 50)
    print(f"  {'文件':<50s} {'类型':>6s} {'规则数':>6s} {'去重':>4s}")
    print(f"  {'─' * 70}")
    for fs in sorted(file_stats, key=lambda x: x["file"]):
        dup_mark = f" (重复{fs['dup']})" if fs['dup'] > 0 else ""
        print(f"  {fs['file']:<50s} {fs['type']:>6s} {fs['total']:>6d}{dup_mark}")
    print()
    
    # 去重信息
    total_raw = sum(fs["total"] for fs in file_stats)
    total_dup = sum(fs["dup"] for fs in file_stats)
    if total_dup > 0:
        print(f"⚠️  原始规则条目: {total_raw}, 去重后: {total}, 重复: {total_dup}")
        print()


def print_brief(all_rules, brain_counts):
    """简洁摘要"""
    total = len(all_rules)
    print(f"煋鉴规则总数: {total}条 (按ID全局去重)")
    print()
    brain_order = ["B1_规则引擎", "B2_安全扫描", "B3_AI语义分析",
                   "B4_性能分析", "B5_依赖审计", "B6_代码质量", "B7_架构合规"]
    for brain in brain_order:
        count = len(brain_counts.get(brain, set()))
        short = brain.split("_")[0]
        print(f"  {short}: {count}条")


def print_json_output(all_rules, brain_counts, cat_map):
    """JSON格式输出"""
    total = len(all_rules)
    result = {
        "total_rules": total,
        "count_method": "JSON rules数组 + Python RULES列表, 按ID全局去重",
        "by_brain": {},
        "by_category": {},
    }
    brain_order = ["B1_规则引擎", "B2_安全扫描", "B3_AI语义分析",
                   "B4_性能分析", "B5_依赖审计", "B6_代码质量", "B7_架构合规"]
    for brain in brain_order:
        result["by_brain"][brain] = len(brain_counts.get(brain, set()))
    
    for cat, ids in sorted(cat_map.items(), key=lambda x: -len(x[1])):
        result["by_category"][cat] = len(ids)
    
    print(json.dumps(result, ensure_ascii=False, indent=2))


def print_coverage(all_rules, brain_counts, cat_map):
    """覆盖率分析"""
    total = len(all_rules)
    
    print("=" * 60)
    print("  煋鉴(Xinpect) 覆盖率分析")
    print("=" * 60)
    print()
    
    # 定义各大脑应覆盖的领域
    expected_coverage = {
        "B1_规则引擎": {
            "应覆盖": ["代码质量", "命名规范", "错误处理", "日志规范", "配置管理",
                      "UI/UX", "小程序", "Web前端", "Git规范", "文档", "测试",
                      "部署", "性能", "安全基础", "复杂度", "重复代码", "死代码"],
            "description": "基础规则扫描，覆盖编码全生命周期"
        },
        "B2_安全扫描": {
            "应覆盖": ["SQL注入", "XSS", "CSRF", "认证授权", "加密", "信息泄露",
                      "路径遍历", "SSRF", "反序列化", "安全头配置", " miscellaneous"],
            "description": "安全漏洞扫描，对标OWASP/CWE"
        },
        "B3_AI语义分析": {
            "应覆盖": ["逻辑漏洞", "设计缺陷", "业务逻辑", "意图理解"],
            "description": "LLM驱动，非静态规则，靠prompt模板"
        },
        "B4_性能分析": {
            "应覆盖": ["内存", "算法", "IO", "并发", "前端性能", "数据库",
                      "缓存", "网络", "构建优化"],
            "description": "性能瓶颈检测"
        },
        "B5_依赖审计": {
            "应覆盖": ["安全漏洞(CVE)", "许可证合规", "版本质量", "配置审计"],
            "description": "第三方依赖风险审计"
        },
        "B6_代码质量": {
            "应覆盖": ["复杂度", "重复率", "可维护性", "命名规范", "文档覆盖"],
            "description": "代码质量度量与改进"
        },
        "B7_架构合规": {
            "应覆盖": ["依赖结构", "API设计", "代码组织", "设计模式",
                      "微服务", "测试架构"],
            "description": "架构级合规检查"
        },
    }
    
    # 按大脑输出覆盖分析
    brain_order = ["B1_规则引擎", "B2_安全扫描", "B3_AI语义分析",
                   "B4_性能分析", "B5_依赖审计", "B6_代码质量", "B7_架构合规"]
    
    for brain in brain_order:
        info = expected_coverage.get(brain, {})
        count = len(brain_counts.get(brain, set()))
        print(f"{'─' * 50}")
        print(f"  {BRAIN_DISPLAY.get(brain, brain)}: {count}条规则")
        print(f"  定位: {info.get('description', '')}")
        
        # 找出该大脑下实际的category
        brain_dirs = [d for d, b in DIR_TO_BRAIN.items() if b == brain]
        actual_cats = set()
        for cat, ids in cat_map.items():
            # 检查该category下是否有规则属于这个brain
            for rid in ids:
                if rid in all_rules and all_rules[rid]["brain"] == brain:
                    actual_cats.add(cat)
                    break
        
        if actual_cats:
            print(f"  已覆盖领域({len(actual_cats)}): {', '.join(sorted(actual_cats))}")
        
        expected = info.get("应覆盖", [])
        if expected:
            print(f"  应覆盖领域({len(expected)}): {', '.join(expected)}")
        
        print()
    
    print(f"{'=' * 50}")
    print(f"  总规则数: {total}")
    print(f"  覆盖领域数: {len(cat_map)}")
    print()


def main():
    mode = "full"
    if "--brief" in sys.argv:
        mode = "brief"
    elif "--json" in sys.argv:
        mode = "json"
    elif "--coverage" in sys.argv:
        mode = "coverage"
    
    all_rules, brain_counts, dir_counts, _category_counts, file_stats = scan_all()
    cat_map = scan_categories()
    
    if mode == "brief":
        print_brief(all_rules, brain_counts)
    elif mode == "json":
        print_json_output(all_rules, brain_counts, cat_map)
    elif mode == "coverage":
        print_coverage(all_rules, brain_counts, cat_map)
    else:
        print_report(all_rules, brain_counts, dir_counts, file_stats, cat_map)


if __name__ == "__main__":
    main()
