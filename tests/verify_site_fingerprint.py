#!/usr/bin/env python3
"""整站交付文件指纹守卫（2026-11-08，QA 6j）。

背景：之前对外说明（static/llms.txt）、博客正文、两个模板被写回旧内容，
靠人眼偶然发现，回头查「哪个进程写的」查不到；QA 守卫本身都只写临时目录，
可生产文件还是会被一次性脚本、手工操作、或以后的自动任务改掉。

治本：把「什么算交付文件」和「每份交付文件长什么样」变成单一事实来源 + 反馈闭环：
  * 范围按目录类别圈定（页面/样式/脚本/博客/对外说明/后端/测试），
    排除的是运行产物（日志、报告、缓存、数据库、状态文件、备份），不是某个文件名；
  * 每次 QA 按同一口径重算 md5，新增 / 删除 / 内容变化一律判红，只改时间戳不判红；
  * 正规上线必须 `--update --manifest 上线清单`，未申报的改动不许签进基线；
    每次重签往一条带链条校验的追加日志里留痕，私自改基线会断链。
  * 守卫自己持有最小核心集：某类交付文件整天被排除掉也判红。

用法：
  python3 verify_site_fingerprint.py                    # QA 巡检（只读）
  python3 verify_site_fingerprint.py --self-test       # 造坏自检
  python3 verify_site_fingerprint.py --update --manifest 清单.json --task 说明
"""
import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

DEFAULT_ROOT = "/opt/xinpect-website"
BASELINE_REL = "scripts/site_files_baseline.json"
DEFAULT_LEDGER = "/var/log/xinpect/site_baseline.log"

# 交付物范围：唯一事实来源在守卫里，基线不许自带一份可悄悄改小的范围。
INCLUDE = (
    "app.py", "design.md",
    "templates", "static", "content", "scripts", "modules", "tests",
    "config", "queue_system", "ops", "codeact", "docker-deploy", "monitoring",
)
EXCLUDE_DIR_NAMES = frozenset({
    "__pycache__", ".pytest_cache", ".git", "reports", "logs", "backups",
    "_archive", "vendor", "versions", "data", "status", "node_modules",
    "output", "alerts", "slo", "adversarial",
})
EXCLUDE_SUFFIXES = (".pyc", ".log", ".db", ".db-shm", ".db-wal", ".sqlite",
                    ".tgz", ".tar.gz", ".zip", ".swp", ".tmp", ".pid")
EXCLUDE_NAME_RES = tuple(re.compile(p) for p in (
    r"\.bak", r"^_backup", r"^\.",
    r"^TODOS\.md$", r"^status\.json$", r"^heal_state\.json$",
    r"^slow_state\.json$", r"^xinpect_status\.json$",
    r"^critical_path_state\.json$", r"^journal_cursor\.json$",
    r"^scan_channel_health\.json$", r"^notify_state\.json$",
    r"^urgent_alert\.json$", r"^monitor_user15_state\.json$",
))
EXCLUDE_PATH_RES = tuple(re.compile(p) for p in (r"^monitoring/[^/]+\.json$",))
# 守卫自己持有的最小核心集：按语义类别，不写死某个文件名。
MUST_GLOBS = (
    "templates/**/*.html", "static/**/*.css", "static/**/*.js", "static/*.txt",
    "content/blog/*.md", "modules/*.py", "scripts/*.py", "scripts/*.sh",
    "tests/verify_*.py",
)


def md5(path):
    h = hashlib.md5()                                   # noqa: S324（完整性对照，非安全用途）
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def excluded(rel):
    if rel == BASELINE_REL:                              # 基线自己不能进自己的清单
        return True
    name = rel.rsplit("/", 1)[-1]
    if rel.endswith(EXCLUDE_SUFFIXES):
        return True
    if any(r.search(name) for r in EXCLUDE_NAME_RES):
        return True
    if any(r.search(rel) for r in EXCLUDE_PATH_RES):
        return True
    return False


def collect(root: Path):
    """按唯一口径枚举交付文件；返回 {相对路径: md5}。"""
    out = {}
    for top in INCLUDE:
        base = root / top
        if base.is_file():
            rel = top
            if not excluded(rel):
                out[rel] = md5(base)
            continue
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIR_NAMES)
            for fn in sorted(filenames):
                p = Path(dirpath) / fn
                if not p.is_file():
                    continue
                rel = p.relative_to(root).as_posix()
                if excluded(rel):
                    continue
                out[rel] = md5(p)
    return out


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def payload_of(root: Path, files, task, owner):
    return {
        "schema": 1,
        "root": str(root),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "include": list(INCLUDE),
        "task": task,
        "owner": owner,
        "count": len(files),
        "files": files,
    }


def integrity_of(payload):
    return hashlib.sha256(canonical(payload)).hexdigest()


def write_baseline(path: Path, payload):
    """重签只换内容，不换属主。

    root 跑 --update 时，新建的 .tmp 是 root:root，os.replace 之后基线就跟着
    变成 root:root；服务身份 xinpect-web 从此读不了也改不了。写盘前把临时文件
    归位成原基线（没有旧基线就用所在目录）的属主，从根上消除这次漂移。
    """
    doc = dict(payload)
    doc["integrity"] = integrity_of(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    owner = None
    for probe in (path, path.parent):
        try:
            st = probe.stat()
            owner = (st.st_uid, st.st_gid)
            break
        except OSError:
            continue
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    # 非 root 身份下 .tmp 本来就是自己的，不需要也不能改属主。
    if owner is not None and hasattr(os, "geteuid") and os.geteuid() == 0:
        os.chown(str(tmp), owner[0], owner[1])
    os.replace(str(tmp), str(path))
    return doc["integrity"]


def read_baseline(path: Path):
    if not path.is_file():
        return None, None, ["基线文件不存在：%s（上线后必须走 --update）" % path]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:                            # noqa: BLE001
        return None, None, ["基线不是合法 JSON：%s" % exc]
    integrity = doc.pop("integrity", None)
    if not integrity:
        return None, None, ["基线缺 integrity 指纹"]
    if integrity != integrity_of(doc):
        return None, None, ["基线被手改过（integrity 对不上），不许判绿"]
    return doc, integrity, []


def chain_of(prev, row):
    raw = "%s|%s|%s|%s" % (prev, row["integrity"], row["ts"], row["i"])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def read_ledger(ledger: Path):
    if not ledger.is_file():
        return [], ["重签日志不存在：%s" % ledger]
    rows, errors = [], []
    prev = "genesis"
    for n, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception as exc:                        # noqa: BLE001
            errors.append("重签日志第 %d 行不是合法 JSON：%s" % (n, exc))
            return rows, errors
        if row.get("i") != n or row.get("prev") != prev:
            errors.append("重签日志第 %d 行序号/前驱断裂" % n)
            return rows, errors
        if chain_of(prev, row) != row.get("chain"):
            errors.append("重签日志第 %d 行链条校验失败" % n)
            return rows, errors
        prev = row["chain"]
        rows.append(row)
    if not rows:
        errors.append("重签日志是空的")
    return rows, errors


def append_ledger(ledger: Path, integrity, count, changed, task, owner):
    ledger.parent.mkdir(parents=True, exist_ok=True)
    rows, errs = ([], []) if not ledger.is_file() else read_ledger(ledger)
    if errs and ledger.is_file():
        raise RuntimeError("重签日志已损坏，拒绝追加：%s" % "; ".join(errs))
    prev = rows[-1]["chain"] if rows else "genesis"
    row = {
        "i": len(rows) + 1,
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "integrity": integrity,
        "count": count,
        "changed": sorted(changed),
        "task": task,
        "owner": owner,
        "prev": prev,
    }
    row["chain"] = chain_of(prev, row)
    with open(ledger, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def coverage_errors(root: Path, files):
    errors = []
    for pat in MUST_GLOBS:
        hits = [p.relative_to(root).as_posix() for p in sorted(root.glob(pat)) if p.is_file()]
        if not hits:
            errors.append("覆盖缺口：%s 一个交付文件都没有" % pat)
            continue
        missed = [h for h in hits if h not in files]
        if missed:
            errors.append("覆盖缺口：%s 有 %d 个文件被排除规则吞掉（例：%s）"
                          % (pat, len(missed), missed[0]))
    return errors


def diff_files(old, new):
    changed = sorted(k for k in old.keys() & new.keys() if old[k] != new[k])
    added = sorted(new.keys() - old.keys())
    removed = sorted(old.keys() - new.keys())
    return {"changed": changed, "added": added, "removed": removed}


def check(root: Path, baseline: Path, ledger: Path):
    errors = []
    doc, integrity, errs = read_baseline(baseline)
    rows, lerrs = read_ledger(ledger)
    errors += errs + lerrs
    current = collect(root)
    if doc is not None:
        if doc.get("include") != list(INCLUDE):
            errors.append("基线里的交付范围与守卫口径不一致（不许悄悄缩小范围）")
        if doc.get("root") != str(root):
            errors.append("基线记录的路径与本次巡检路径不一致")
        if doc.get("count") != len(doc.get("files", {})):
            errors.append("基线文件数自相矛盾")
        d = diff_files(doc.get("files", {}), current)
        for key, label in (("changed", "内容被改"), ("added", "冒出未申报的新文件"),
                           ("removed", "交付文件不见了")):
            for rel in d[key][:8]:
                errors.append("F %s：%s" % (label, rel))
            if len(d[key]) > 8:
                errors.append("F %s：还有 %d 个" % (label, len(d[key]) - 8))
    errors += coverage_errors(root, current)
    if integrity and rows and rows[-1]["integrity"] != integrity:
        errors.append("L 基线与重签日志最后一条对不上（有人绕开 --update 动了基线）")
    if rows and doc is not None and rows[-1]["count"] != doc.get("count"):
        errors.append("L 重签日志记的文件数与基线不符")
    return errors


def do_update(root: Path, baseline: Path, ledger: Path, manifest, task, owner):
    """只有「上线清单里申报过的改动」才允许签进基线。"""
    current = collect(root)
    declared = set()
    if manifest:
        p = Path(manifest)
        if not p.is_file():
            return ["--update 拒跑：上线清单不存在 %s" % p]
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            declared = set(doc.get("files", []))
        except Exception as exc:                        # noqa: BLE001
            return ["--update 拒跑：上线清单不是合法 JSON：%s" % exc]
        if not declared:
            return ["--update 拒跑：上线清单里没有申报任何文件"]
    old, _, errs = read_baseline(baseline)
    if errs and old is None and baseline.is_file():
        return errs                                     # 基线被手改，不许覆盖掉证据
    if old is not None:
        d = diff_files(old.get("files", {}), current)
        undeclared = sorted(set(d["changed"] + d["added"] + d["removed"]) - declared)
        if undeclared:
            return ["--update 拒跑：有 %d 个改动没在上线清单里申报（例：%s）"
                    % (len(undeclared), undeclared[0])] + [
                        "  · %s" % x for x in undeclared[:10]]
        changed = sorted(set(d["changed"] + d["added"] + d["removed"]))
    else:
        if manifest is None:
            return ["--update 拒跑：首次建基线也要有上线清单"]
        changed = sorted(current)
    errors = coverage_errors(root, current)
    if errors:
        return errors
    payload = payload_of(root, current, task, owner)
    integrity = write_baseline(baseline, payload)
    append_ledger(ledger, integrity, len(current), changed, task, owner)
    print("基线已重签：%d 个交付文件，本次申报改动 %d 个，指纹 %s"
          % (len(current), len(changed), integrity[:16]))
    return []


def seed_tree(root: Path):
    files = {
        "app.py": "from flask import Flask\n",
        "design.md": "# 设计规矩\n",
        "templates/base.html": "<html></html>\n",
        "templates/index.html": "<html>首页</html>\n",
        "static/css/tokens.css": ":root{--x:#123456;}\n",
        "static/js/main.js": "console.log(1);\n",
        "static/llms.txt": "对外口径\n",
        "content/blog/a.md": "文章A\n",
        "content/blog/b.md": "文章B\n",
        "scripts/run_qa_suite.sh": "#!/bin/bash\n",
        "scripts/generate_status.py": "def main():\n    pass\n",
        "scripts/site_nav.json": "{}\n",
        "modules/blog.py": "def f():\n    return 1\n",
        "tests/verify_demo.py": "def test_x():\n    pass\n",
        "monitoring/xinpect_monitor.py": "def main():\n    pass\n",
        # 运行产物：按类别排除，改它们不该判红
        "tests/reports/out.log": "运行日志\n",
        "monitoring/status.json": "{}\n",
        "monitoring/monitor.log": "日志\n",
        "data/state.json": "{}\n",
        "scripts/reports/x.json": "{}\n",
        ".pytest_cache/v/cache/nodeids": "[]\n",
        "static/llms.txt.bak_2026": "旧备份\n",
    }
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return files


def self_test(_root, _baseline, _ledger):
    """每个用例都在自己全新的临时树上做，不读任何固定临时文件、不依赖生产状态。"""
    def build(td):
        r = Path(td) / "site"
        b = r / BASELINE_REL
        l = Path(td) / "site_baseline.log"
        seed_tree(r)
        mf = Path(td) / "manifest.json"
        mf.write_text(json.dumps({"files": sorted(collect(r))}), encoding="utf-8")
        errs = do_update(r, b, l, str(mf), "自检建基线", "self-test")
        return r, b, l, mf, errs

    # 每个造坏动作作用于「本用例自己的树」，只按语义类别挑文件，不写死某个文件名
    def pick(r, prefix, suffix=None):
        hits = sorted(k for k in collect(r)
                      if k.startswith(prefix) and (suffix is None or k.endswith(suffix)))
        assert hits, "样本里找不到 %s 这类文件" % prefix
        return hits[0]

    def bad_none(r, b, l):
        pass

    def bad_edit(r, b, l):
        (r / pick(r, "content/blog/", ".md")).write_text("被人偷偷改了\n", encoding="utf-8")

    def bad_add(r, b, l):
        p = r / "templates" / "new_page.html"
        p.write_text("<p>新</p>\n", encoding="utf-8")

    def bad_delete(r, b, l):
        (r / pick(r, "templates/", ".html")).unlink()

    def bad_mtime(r, b, l):
        os.utime(r / pick(r, "content/blog/", ".md"), (1234567890, 1234567890))

    def bad_runtime(r, b, l):
        (r / "tests/reports/out.log").write_text("新日志\n", encoding="utf-8")

    def bad_runtime_new(r, b, l):
        (r / "monitoring/new.log").write_text("新日志\n", encoding="utf-8")

    def bad_baseline(r, b, l):
        doc = json.loads(b.read_text(encoding="utf-8"))
        key = pick(r, "content/blog/", ".md")
        doc["files"][key] = "deadbeef"
        b.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                     encoding="utf-8")

    def bad_baseline_rehashed(r, b, l):
        """连文件带基线一起改、integrity 也重算，想绕开 --update —— 应被重签日志抓住。"""
        key = pick(r, "content/blog/", ".md")
        (r / key).write_text("偷偷改的\n", encoding="utf-8")
        doc = json.loads(b.read_text(encoding="utf-8"))
        doc["files"][key] = md5(r / key)
        doc.pop("integrity", None)
        doc["integrity"] = integrity_of(doc)
        b.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                     encoding="utf-8")

    def bad_no_baseline(r, b, l):
        b.unlink(missing_ok=True)

    def bad_ledger(r, b, l):
        lines = l.read_text(encoding="utf-8").splitlines()
        row = json.loads(lines[-1])
        row["chain"] = "broken"
        lines[-1] = json.dumps(row, ensure_ascii=False, sort_keys=True)
        l.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def bad_shrink_scope(r, b, l):
        doc = json.loads(b.read_text(encoding="utf-8"))
        doc["include"] = ["app.py"]
        doc.pop("integrity", None)
        doc["integrity"] = integrity_of(doc)
        b.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                     encoding="utf-8")

    cases = [
        ("干净样本必须判绿", bad_none, False),
        ("改一份交付文件会判红", bad_edit, True),
        ("冒出一份新交付文件会判红", bad_add, True),
        ("删掉一份交付文件会判红", bad_delete, True),
        ("只改时间戳不改内容必须判绿", bad_mtime, False),
        ("改运行产物必须判绿", bad_runtime, False),
        ("新增运行产物必须判绿", bad_runtime_new, False),
        ("手改基线内容会判红", bad_baseline, True),
        ("连指纹一起重算也躲不过重签日志", bad_baseline_rehashed, True),
        ("删掉基线会判红", bad_no_baseline, True),
        ("篡改重签日志会判红", bad_ledger, True),
        ("悄悄缩小交付范围会判红", bad_shrink_scope, True),
    ]

    ok = failed = 0
    for name, bad, want_red in cases:
        with tempfile.TemporaryDirectory(prefix="xp_fp_") as td:
            r, b, l, _mf, prep = build(td)
            if prep:
                print("FAIL  %s：样本没建起来 %s" % (name, prep))
                failed += 1
                continue
            bad(r, b, l)
            errs = check(r, b, l)
            red = bool(errs)
            if red == want_red:
                ok += 1
                print("  OK  %s%s" % (name, "" if not red else "（判红 %d 项）" % len(errs)))
            else:
                failed += 1
                print("FAIL  %s：期望%s，实际%s；%s" % (
                    name, "判红" if want_red else "判绿",
                    "判红" if red else "判绿", "; ".join(errs[:2])))

    # 反馈闭环：没申报的改动不许签进基线；申报了才允许
    with tempfile.TemporaryDirectory(prefix="xp_fp_up_") as td:
        r, b, l, _mf, _prep = build(td)
        changed = pick(r, "content/blog/", ".md")
        (r / changed).write_text("偷偷改的\n", encoding="utf-8")
        short = Path(td) / "short.json"
        short.write_text(json.dumps({"files": ["app.py"]}), encoding="utf-8")
        refused = do_update(r, b, l, str(short), "想蒙混过关", "self-test")
        still_red = check(r, b, l)
        if refused and still_red:
            ok += 1
            print("  OK  未申报的改动被 --update 拒绝，且基线仍判红")
        else:
            failed += 1
            print("FAIL  未申报改动竟然能签进基线")
        full = Path(td) / "full.json"
        full.write_text(json.dumps({"files": [changed]}), encoding="utf-8")
        accepted = do_update(r, b, l, str(full), "正规上线", "self-test")
        if not accepted and not check(r, b, l):
            ok += 1
            print("  OK  申报过的改动走正规重签后判绿")
        else:
            failed += 1
            print("FAIL  正规重签没能恢复绿：%s" % "; ".join(accepted))
        cases.append(("闭环", bad_none, True))

    total = ok + failed
    print("整站文件指纹守卫自测: %d 项, 通过 %d, 失败 %d" % (total, ok, failed))
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--baseline")
    ap.add_argument("--ledger")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--manifest")
    ap.add_argument("--task", default="未注明")
    ap.add_argument("--owner", default="workbuddy-xinpect")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    baseline = Path(args.baseline) if args.baseline else root / BASELINE_REL
    ledger = Path(args.ledger) if args.ledger else (
        Path(DEFAULT_LEDGER) if str(root) == DEFAULT_ROOT else root / "site_baseline.log")

    if args.self_test:
        with tempfile.TemporaryDirectory(prefix="xp_fp_self_") as td:
            r = Path(td) / "site"
            return self_test(r, r / BASELINE_REL, Path(td) / "site_baseline.log")
    if args.update:
        errs = do_update(root, baseline, ledger, args.manifest, args.task, args.owner)
        for e in errs:
            print("FAIL " + e)
        return 1 if errs else 0
    errs = check(root, baseline, ledger)
    if errs:
        for e in errs:
            print("FAIL " + e)
        print("整站文件指纹守卫: %d 项不合格" % len(errs))
        return 1
    print("整站文件指纹守卫: %d 个交付文件与基线一致，覆盖类别 %d 组，重签日志链条完好"
          % (len(collect(root)), len(MUST_GLOBS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
