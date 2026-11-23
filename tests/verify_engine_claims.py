#!/usr/bin/env python3
"""引擎数量对外口径守卫（2026-11-08，QA 6k）。

问题：页面绝大多数写「7 大规则引擎 E1-E7」，控制台 overview 却写「8 大」，
谁对谁错靠人记；以后引擎一扩容，又是一轮到处改文案、必然再次漂移。

治本不是手抄一张「正确数字表」，而是**从运行时代码把数字算出来**：
  BRAIN_MODULES 里模块路径 `engine.e<N>_xxx` 的 eN 前缀去重个数 = 引擎数。
  e7_ai_health 与 e7_deployment_readiness 同属 E7，所以 8 号模块不是第 8 个引擎。
事实源 `scripts/engine_facts.json` 只是把这份推导结果写给人和页面看，
守卫每次都拿它跟运行时代码、跟官网 BRAINS、跟全站文案逐条对账。
「把事实源和所有文案一起改成 8」也骗不过去——运行时代码对不上，照样判红。

判据只针对「引擎总数声明」这一语义：
  * `N 大规则引擎` / `N 个规则引擎` / `七大规则引擎`（「个」与「大」都算总数声明）
  * `E1~EN` / `E1-EN` 且与「全 / 并行」同现（全引擎范围声明）
  `E1-E5 规则引擎` 这类「某个档位启用哪几台」不是总数声明，不在判据内。

用法：
  python3 verify_engine_claims.py                # QA 巡检（只读）
  python3 verify_engine_claims.py --self-test    # 造坏自检
"""
import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

DEFAULT_ROOT = Path("/opt/xinpect-website")
DEFAULT_RUNTIME = Path("/opt/xinpect-scanner-green/engine/parallel_runner.py")
FACTS_REL = "scripts/engine_facts.json"
CONSTANTS_REL = "modules/constants.py"

CN_NUM = {"六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
CLAIM_RE = re.compile(r"(\d+|[六七八九十])\s*(?:大|个)\s*(?:规则)?引擎")
SCOPE_RE = re.compile(r"E1\s*[~\-]\s*E(\d+)[^\n]{0,16}?(?:全|并行)")
BRAIN_BLOCK = re.compile(r"BRAIN_MODULES\s*=\s*\{([\s\S]*?)\n\}")
MODULE_RE = re.compile(r"['\"]engine\.e(\d+)_[A-Za-z0-9_]+['\"]")
BRAINS_BLOCK = re.compile(r"^BRAINS\s*=\s*\[([\s\S]*?)^\]", re.M)
BRAIN_CODE_RE = re.compile(r"['\"]code['\"]\s*:\s*['\"]E\d+['\"]")

TEXT_SUFFIXES = (".html", ".txt", ".md", ".py", ".json", ".sh")
SKIP_PARTS = ("__pycache__", ".pytest_cache", "_archive", "vendor",
              "reports", "logs", "versions", "node_modules")
MIN_CLAIM_FILES = 5  # 最小核心集：声明被删光也算红

# 紧邻上文出现这些词，说明这句话是在否定/对比「N 个引擎」，不是在声明总数。
NEG_MARKERS = ("第", "不代表", "不等于", "不是", "而非", "不算")


def derive_engine_count(runtime_text):
    """从运行时 BRAIN_MODULES 推导引擎数（唯一权威）。"""
    m = BRAIN_BLOCK.search(runtime_text or "")
    if not m:
        return None, "运行时找不到 BRAIN_MODULES，守卫拒绝判绿"
    groups = {int(x) for x in MODULE_RE.findall(m.group(1))}
    if not groups:
        return None, "BRAIN_MODULES 里没有 engine.eN_ 模块，守卫无法推导引擎数"
    if groups != set(range(1, max(groups) + 1)):
        return None, "运行时引擎编号不连续：%s" % sorted(groups)
    return len(groups), None


def count_website_brains(constants_text):
    m = BRAINS_BLOCK.search(constants_text or "")
    if not m:
        return None
    return len(BRAIN_CODE_RE.findall(m.group(1)))


def claim_files(root: Path):
    """按目录类别圈对外文案，不写死文件名。"""
    out = []
    for top in ("templates", "static", "content", "modules", "scripts"):
        base = root / top
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file() or p.suffix not in TEXT_SUFFIXES:
                continue
            rel = p.relative_to(root).as_posix()
            if any(s in rel.split("/") for s in SKIP_PARTS):
                continue
            if ".bak" in p.name or p.name.startswith("_backup"):
                continue
            out.append(p)
    return out


def scan_claims(root: Path):
    found = []
    for p in claim_files(root):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = p.relative_to(root).as_posix()
        for m in CLAIM_RE.finditer(text):
            raw = m.group(1)
            n = CN_NUM.get(raw, None) if not raw.isdigit() else int(raw)
            if n is None:
                continue
            # 「8 号模块不是第 8 个引擎」这类是在消歧，不是总数声明。
            # 不加这层，把正则从「N 大」放宽到「N 个」之后，
            # engine_facts.json 里那句解释自己就会把守卫判红。
            head = text[max(0, m.start() - 8):m.start()]
            if any(k in head for k in NEG_MARKERS):
                continue
            found.append((rel, n, "claim"))
        for m in SCOPE_RE.finditer(text):
            found.append((rel, int(m.group(1)), "scope"))
    return found


def check(root: Path, runtime: Path):
    errors = []
    facts_path = root / FACTS_REL
    if not facts_path.is_file():
        return ["事实源缺失：%s（守卫拒绝判绿）" % FACTS_REL]
    try:
        facts = json.loads(facts_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return ["事实源不是合法 JSON：%s" % exc]
    if not runtime.is_file():
        return ["运行时代码找不到：%s（守卫拒绝判绿）" % runtime]
    try:
        runtime_text = runtime.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return ["运行时代码读不到：%s" % exc]

    derived, err = derive_engine_count(runtime_text)
    if err:
        return [err]
    declared = facts.get("rule_engine_count")
    if declared != derived:
        errors.append("S1 事实源写 %s 个引擎，运行时推导是 %s 个（不许手填）"
                      % (declared, derived))
    codes = facts.get("rule_engine_codes") or []
    if len(codes) != derived:
        errors.append("S1 事实源引擎编号表 %d 项，与运行时 %d 个对不上" % (len(codes), derived))

    constants = root / CONSTANTS_REL
    if not constants.is_file():
        errors.append("S2 官网 BRAINS 定义找不到：%s" % CONSTANTS_REL)
    else:
        n_brains = count_website_brains(constants.read_text(encoding="utf-8", errors="replace"))
        if n_brains != derived:
            errors.append("S2 官网 BRAINS 有 %s 个规则引擎，运行时是 %s 个" % (n_brains, derived))

    claims = scan_claims(root)
    bad = [(rel, n, kind) for rel, n, kind in claims if n != derived]
    for rel, n, kind in bad[:12]:
        errors.append("S3 %s 声明 %s 个引擎（%s），应为 %s" % (rel, n, kind, derived))
    if len(bad) > 12:
        errors.append("S3 另有 %d 处同类错误" % (len(bad) - 12))
    distinct = {rel for rel, _, _ in claims}
    if len(distinct) < MIN_CLAIM_FILES:
        errors.append("S4 只有 %d 个文件有引擎总数声明，少于最小核心集 %d（文案被删光也算红）"
                      % (len(distinct), MIN_CLAIM_FILES))
    if str(derived) not in (facts.get("claim_wording") or ""):
        errors.append("S5 事实源的对外标准写法没写引擎数")
    return errors


# ---------------------------------------------------------------- self-test
SEED_RUNTIME = '''BRAIN_MODULES = {
    "1": "engine.e1_syntax",
    "2": "engine.e2_security",
    "3": "engine.e3_performance",
    "4": "engine.e4_quality",
    "5": "engine.e5_architecture",
    "6": "engine.e6_component",
    "7": "engine.e7_ai_health",
    "8": "engine.e7_deployment_readiness",
    "ai": "engine.ai_semantic",
    "poc": "engine.poc_verification",
}
'''
SEED_CONSTANTS = '''BRAINS = [
    {'id': '1', 'code': 'E1', 'name': '语法与AST分析'},
    {'id': '2', 'code': 'E2', 'name': '安全检测'},
    {'id': '3', 'code': 'E3', 'name': '性能与可靠性'},
    {'id': '4', 'code': 'E4', 'name': '代码质量与可观测性'},
    {'id': '5', 'code': 'E5', 'name': '架构与部署'},
    {'id': '6', 'code': 'E6', 'name': '组件合规'},
    {'id': '7', 'code': 'E7', 'name': 'AI应用健康检测'},
    {'id': 'ai', 'code': 'AI', 'name': 'AI语义分析'},
    {'id': 'poc', 'code': 'PoC', 'name': 'PoC自动验证'},
]
'''
SEED_CLAIMS = {
    "templates/index.html": "<p>7 大规则引擎 + AI 语义 + PoC 验证</p>",
    "templates/base.html": "<meta content='7大规则引擎并行扫描'>",
    "templates/dashboard/overview.html": "<p>享受全部 7 大规则引擎检测</p>",
    "templates/help.html": "<p>煋鉴采用 7 大规则引擎（E1~E7）并行扫描</p><p>一键全选七大规则引擎</p>",
    "static/pages/product.html": "<h3>7 大规则引擎</h3>",
    "static/llms.txt": "- 扫描引擎：7 大规则引擎 + AI 语义分析 + PoC 验证",
    "templates/dashboard/ci_setup.html": "<div>E1-E7 全引擎</div><div>E1-E5 规则引擎</div>",
}
SEED_FACTS = {
    "schema": 1, "rule_engine_count": 7,
    "rule_engine_codes": ["E1", "E2", "E3", "E4", "E5", "E6", "E7"],
    "claim_wording": "7 大规则引擎 + AI 语义 + PoC 验证",
}


def seed(root: Path):
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "modules").mkdir(parents=True, exist_ok=True)
    (root / "engine").mkdir(parents=True, exist_ok=True)
    (root / CONSTANTS_REL).write_text(SEED_CONSTANTS, encoding="utf-8")
    (root / FACTS_REL).write_text(
        json.dumps(SEED_FACTS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for rel, text in SEED_CLAIMS.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text + "\n", encoding="utf-8")
    runtime = root / "engine" / "parallel_runner.py"
    runtime.write_text(SEED_RUNTIME, encoding="utf-8")
    return runtime


def self_test():
    cases = [
        ("干净样本必须判绿", lambda r, rt: None, False),
        ("一处文案改成 9 大会判红",
         lambda r, rt: (r / "templates/index.html").write_text(
             "<p>9 大规则引擎</p>\n", encoding="utf-8"), True),
        ("文案写成「8 个规则引擎」会判红（旧正则只认「大」，漏过一整天）",
         lambda r, rt: (r / "static/pages/product.html").write_text(
             "<h3>8 个规则引擎</h3>\n", encoding="utf-8"), True),
        ("「7 个规则引擎」这种写法必须判绿（判据要认「个」）",
         lambda r, rt: (r / "templates/index.html").write_text(
             "<p>7 个规则引擎 + AI 语义 + PoC 验证</p>\n", encoding="utf-8"), False),
        ("只改事实源数字会判红",
         lambda r, rt: (r / FACTS_REL).write_text(
             json.dumps(dict(SEED_FACTS, rule_engine_count=8), ensure_ascii=False) + "\n",
             encoding="utf-8"), True),
        ("事实源和全部文案一起改成 8 想蒙混，仍然判红",
         lambda r, rt: _rewrite_all(r, 8), True),
        ("运行时新增 e9 模块、事实源没跟上会判红",
         lambda r, rt: rt.write_text(
             SEED_RUNTIME.replace('"poc": "engine.poc_verification",',
                                  '"poc": "engine.poc_verification",\n'
                                  '    "9": "engine.e9_new_engine",'), encoding="utf-8"), True),
        ("官网 BRAINS 删一项会判红",
         lambda r, rt: (r / CONSTANTS_REL).write_text(
             SEED_CONSTANTS.replace("    {'id': '7', 'code': 'E7', 'name': 'AI应用健康检测'},\n", ""),
             encoding="utf-8"), True),
        ("全引擎编号范围写成 E1-E9 会判红",
         lambda r, rt: (r / "templates/dashboard/ci_setup.html").write_text(
             "<div>E1-E9 全引擎</div>\n", encoding="utf-8"), True),
        ("删掉事实源会判红", lambda r, rt: (r / FACTS_REL).unlink(), True),
        ("删掉运行时代码会判红", lambda r, rt: rt.unlink(), True),
        ("把所有对外声明删光会判红", lambda r, rt: _drop_claims(r), True),
        ("档位描述 E1-E5 不该被当成总数声明", lambda r, rt: None, False),
        ("只改时间戳不改内容必须判绿",
         lambda r, rt: __import__("os").utime(r / "templates/index.html", (1, 1)), False),
    ]
    ok = failed = 0
    for name, mutate, want_red in cases:
        with tempfile.TemporaryDirectory(prefix="xp_engine_") as td:
            root = Path(td)
            runtime = seed(root)
            mutate(root, runtime)
            errs = check(root, runtime)
            red = bool(errs)
            if red == want_red:
                ok += 1
                print("  OK  %s%s" % (name, "" if not red else "（判红 %d 项）" % len(errs)))
            else:
                failed += 1
                print("FAIL  %s：期望%s，实际%s；%s" % (
                    name, "判红" if want_red else "判绿",
                    "判红" if red else "判绿", "; ".join(errs[:2])))
    print("引擎口径守卫自测: %d 项, 通过 %d, 失败 %d" % (len(cases), ok, failed))
    return 1 if failed else 0


def _rewrite_all(root: Path, n: int):
    for rel in SEED_CLAIMS:
        (root / rel).write_text("<p>%d 大规则引擎 + AI 语义 + PoC 验证</p>\n" % n,
                                encoding="utf-8")
    (root / FACTS_REL).write_text(
        json.dumps(dict(SEED_FACTS, rule_engine_count=n,
                        claim_wording="%d 大规则引擎 + AI 语义 + PoC 验证" % n),
                   ensure_ascii=False) + "\n", encoding="utf-8")


def _drop_claims(root: Path):
    for rel in SEED_CLAIMS:
        (root / rel).write_text("<p>煋鉴代码质检</p>\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--runtime", default=str(DEFAULT_RUNTIME))
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    root = Path(args.root)
    errors = check(root, Path(args.runtime))
    if errors:
        for e in errors:
            print("FAIL " + e)
        print("引擎口径守卫: %d 项不通过" % len(errors))
        return 1
    facts = json.loads((root / FACTS_REL).read_text(encoding="utf-8"))
    derived, _ = derive_engine_count(Path(args.runtime).read_text(encoding="utf-8", errors="replace"))
    claims = scan_claims(root)
    print("引擎口径守卫: 运行时推导 %s 个引擎，事实源 %s，%d 个文件 %d 处声明全一致"
          % (derived, facts["rule_engine_count"],
             len({r for r, _, _ in claims}), len(claims)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
