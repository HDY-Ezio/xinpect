#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仓库泄漏守卫：拦住「已经提交」的密钥/备份，而不只是「还没被跟踪」的文件。

为什么要有它（2026-11-23）：`backups/database/*.db.gz` 从 10-20 起躺在公开仓库里，
里面有 14 个用户邮箱、753 条扫描、2 个明文 `xk_` API Key。当时的 `.gitignore` 只写
`*.db`，而这些文件叫 `*.db.gz`；事后补的 `tests/test_no_db_dumps_tracked.py` 只查
「git 已跟踪的文件」，**历史里的提交照样能被 git clone 拉下来**。

所以这里补三件彼此独立的事，缺一件就守不住：
  1. 按内容查：`xk_` + 32 位十六进制、私钥头。只查文件名挡不住「key 被贴进配置/文档」。
  2. 查全部历史：每个提交的每个 blob，而不只是 HEAD。这次泄漏正是历史里的。
  3. 给一个 pre-push 钩子：推送前强制跑一遍，钩子不在就由 QA 判红。

二进制 blob（如 `.db.gz`）没法按内容查，靠文件名规则兜；两条轨道都要有。

用法：
    python3 scripts/verify_repo_secrets.py --scope index     # 查索引（将要提交的东西）
    python3 scripts/verify_repo_secrets.py --scope history   # 查全部提交（推送前）
    python3 scripts/verify_repo_secrets.py --self-test       # 造坏自检
    python3 scripts/verify_repo_secrets.py --install-hook    # 装/更新 pre-push

退出码：0 干净；1 有命中；2 环境或白名单问题（例如历史已清理、名单条目过期）。
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.environ.get("XINPECT_WEB_ROOT", os.path.dirname(HERE))
ALLOWLIST_REL = "scripts/repo_secrets_allowlist.json"
HOOK_REL = ".git/hooks/pre-push"
MARKER = "verify_repo_secrets"          # 钩子内容必须含它，QA 据此判断钩子是不是我们装的

# ---------------------------------------------------------------- 判据（单一事实来源）
# 文件名判据：数据库转储与备份校验文件。只写「禁止什么」，不写「必须包含什么」。
FILE_RULES = [
    (re.compile(r"(^|/)backups/"), "备份目录整个不许进仓库"),
    (re.compile(r"\.db$", re.I), "SQLite 库文件"),
    (re.compile(r"\.db\.gz$", re.I), "gzip 过的 SQLite 库文件"),
    (re.compile(r"\.sqlite3?$", re.I), "SQLite 库文件"),
    (re.compile(r"\.dump$", re.I), "数据库转储"),
    (re.compile(r"\.md5$", re.I), "备份校验文件"),
]
# 这些路径带 .sql 之类但是源码/文档，不许误伤
FILE_ALLOW = re.compile(r"(schema|migration|\.sql$)", re.I)

# 内容判据：只认能直接用的凭据，不认「长得像」的字段名。
# 私钥头必须拆开拼：把完整字面量写进源码，守卫会把自己扫成命中（2026-11-23 端到端
# 试验抓到：装好钩子后连「添加守卫」这个提交都推不上去）。
_BEGIN = "-" * 5 + "BEGIN "
_END = "PRIVATE KEY" + "-" * 5
# 邮箱授权码：判「变量名 = 字符串字面量」这个形态，不判字段名。
# 2026-11-23：三个监控脚本把 163 授权码写死在源码里并进了公开仓库，此前无人守。
# 变量名与引号都拆开拼，否则这行本身就成了被禁的东西。
_MAIL_VARS = "|".join(["smtp_" + "pass", "smtp_" + "password", "mail_" + "pass",
                       "email_" + "password", "mail_" + "auth_code"])
_Q = chr(34) + chr(39)
_MAIL_LITERAL = r"\b(?:%s)\b\s*[=:]\s*[%s][^%s\s]{8,}[%s]" % (_MAIL_VARS, _Q, _Q, _Q)

CONTENT_RULES = [
    (re.compile(r"\bxk_[0-9a-f]{32}\b"), "明文 API Key"),
    # 头之后必须跟 base64 正文：检测规则里的样本常量
    # （'-----BEGIN RSA PRIVATE KEY-----' 单独一行）没有正文，不算真私钥。
    (re.compile(re.escape(_BEGIN) + r"(?:RSA |OPENSSH |EC |DSA )?" + re.escape(_END)
                + r"\s*\r?\n[A-Za-z0-9+/=]{20,}"), "私钥"),
    # 第三位 True = 落在字符串字面量里时不算，见 _in_string_literal
    (re.compile(_MAIL_LITERAL, re.I), "写死的邮箱授权码", True),
]

# 二进制判定：前 8000 字节里有 NUL 就跳过内容扫描（内容规则对压缩字节无意义）
SNIFF = 8000


# ---------------------------------------------------------------- 纯函数
def scan_paths(paths):
    """按文件名规则扫路径，返回 [(路径, 原因)]。测试与造坏自检共用同一个判据。"""
    hits = []
    for p in paths:
        if FILE_ALLOW.search(p) and not re.search(r"(^|/)backups/", p):
            continue
        for rx, why in FILE_RULES:
            if rx.search(p):
                hits.append((p, why))
                break
    return hits


def _in_string_literal(text, pos):
    """pos 是否落在同一行的字符串字面量内部：数该行 pos 之前的未转义引号。

    用途：基准题库里 'code_snippet':'SMTP_PASSWORD = "MyEmailP@ss2024!"' 这类
    合成样本，整段本身是一个字符串值。它不是赋值语句，不该判成泄露。
    多行三引号有盲区（按行计数），那种写法里几乎不会出现完整的
    「变量名 = 带引号的值」形态，宁可漏报，不误伤题库。
    """
    line_start = text.rfind("\n", 0, pos) + 1
    prefix = text[line_start:pos]
    for esc in ('\\"', "\\'"):
        prefix = prefix.replace(esc, "")
    return (prefix.count(chr(39)) % 2 == 1) or (prefix.count(chr(34)) % 2 == 1)


def scan_text(text):
    """按内容规则扫文本，返回 [(原因, 脱敏片段)]。"""
    hits = []
    for rule in CONTENT_RULES:
        rx, why = rule[0], rule[1]
        strict = len(rule) > 2 and rule[2]
        for m in rx.finditer(text):
            if strict and _in_string_literal(text, m.start()):
                continue
            s = m.group(0)
            # 片段脱敏：只露前 8 个字符，日志里不留可直接使用的凭据
            hits.append((why, s[:8] + "…" if len(s) > 8 else s))
            break
    return hits


def is_binary(blob):
    return b"\x00" in blob[:SNIFF]


# ---------------------------------------------------------------- git 访问
def git(root, *args, binary=False, timeout=180):
    cmd = ["git", "-C", root, "-c", "safe.directory=*"] + list(args)
    out = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError("git %s 失败: %s" % (" ".join(args), out.stderr.decode("utf-8", "replace")[:300]))
    return out.stdout if binary else out.stdout.decode("utf-8", "replace")


def read_blobs(root, shas):
    """批量取 blob 内容，返回 {sha: bytes}。"""
    shas = [s for s in dict.fromkeys(shas) if s]
    if not shas:
        return {}
    cmd = ["git", "-C", root, "-c", "safe.directory=*", "cat-file", "--batch"]
    p = subprocess.run(cmd, input=("\n".join(shas) + "\n").encode(), capture_output=True, timeout=600)
    if p.returncode != 0:
        raise RuntimeError("cat-file --batch 失败")
    data = p.stdout
    out, i = {}, 0
    while i < len(data):
        nl = data.find(b"\n", i)
        if nl < 0:
            break
        header = data[i:nl].decode("utf-8", "replace").split()
        i = nl + 1
        if len(header) >= 3 and header[1] == "blob":
            size = int(header[2])
            out[header[0]] = data[i:i + size]
            i += size + 1
    return out


def ls_index(root):
    """索引里的 [(路径, blob sha)]，即「下一次提交会带上的内容」。"""
    raw = git(root, "ls-files", "-s", "-z", binary=True).split(b"\x00")
    rows = []
    for rec in raw:
        if not rec:
            continue
        meta, _, path = rec.partition(b"\t")
        parts = meta.split()
        if len(parts) == 3 and parts[2] == b"0":
            rows.append((path.decode("utf-8", "surrogateescape"), parts[1].decode()))
    return rows


def ls_commit(root, commit):
    raw = git(root, "ls-tree", "-r", "-z", commit, binary=True).split(b"\x00")
    rows = []
    for rec in raw:
        if not rec:
            continue
        meta, _, path = rec.partition(b"\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == b"blob":
            rows.append((path.decode("utf-8", "surrogateescape"), parts[2].decode()))
    return rows


# ---------------------------------------------------------------- 白名单（历史旧账）
def load_allowlist(root):
    p = os.path.join(root, ALLOWLIST_REL)
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as fh:
        data = json.load(fh)
    return {e["commit"]: e for e in data.get("entries", []) if e.get("commit")}


def check_allowlist_alive(root, entries):
    """名单里的提交必须还在。历史清理完后再留着条目 = 名单过期，必须删掉。"""
    dead = []
    for sha in entries:
        r = subprocess.run(["git", "-C", root, "-c", "safe.directory=*", "cat-file", "-e", sha + "^{commit}"],
                           capture_output=True)
        if r.returncode != 0:
            dead.append(sha)
    return dead


# ---------------------------------------------------------------- 两种扫描
def scan_index(root):
    """查将要提交的内容。返回 (findings, skipped)。"""
    rows = ls_index(root)
    findings = []
    for p, why in scan_paths([p for p, _ in rows]):
        findings.append({"where": "index", "path": p, "reason": why, "commit": None})
    blobs = read_blobs(root, [s for _, s in rows])
    for p, sha in rows:
        b = blobs.get(sha, b"")
        if is_binary(b):
            continue
        for why, snip in scan_text(b.decode("utf-8", "replace")):
            findings.append({"where": "index", "path": p, "reason": why, "snippet": snip, "commit": None})
    return findings, []


def scan_history(root, allow):
    """查全部提交。白名单里的提交记为「已知旧账」，不计入失败。"""
    commits = git(root, "rev-list", "--all").split()
    findings, legacy = [], []
    blob_cache = {}
    for c in commits:
        rows = ls_commit(root, c)
        need = [s for p, s in rows if s not in blob_cache]
        blob_cache.update(read_blobs(root, need))
        commit_hits = []
        for p, why in scan_paths([p for p, _ in rows]):
            commit_hits.append({"path": p, "reason": why, "commit": c[:10]})
        for p, sha in rows:
            b = blob_cache.get(sha, b"")
            if is_binary(b):
                continue
            for why, snip in scan_text(b.decode("utf-8", "replace")):
                commit_hits.append({"path": p, "reason": why, "snippet": snip, "commit": c[:10]})
        if c in allow:
            legacy.extend(commit_hits)
        else:
            findings.extend(commit_hits)
    return findings, legacy


# ---------------------------------------------------------------- 钩子
HOOK_BODY = """#!/bin/sh
# 由 scripts/%(marker)s.py --install-hook 生成，请勿手改。
# 推送前扫全部提交：历史里出现明文 API Key / 私钥 / 数据库转储就不许推。
ROOT=$(git -c safe.directory='*' rev-parse --show-toplevel 2>/dev/null) || exit 0
exec /usr/bin/python3 "$ROOT/scripts/%(marker)s.py" --scope history --root "$ROOT"
"""


def install_hook(root):
    p = os.path.join(root, HOOK_REL)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(HOOK_BODY % {"marker": MARKER})
    os.chmod(p, 0o755)
    return p


def hook_installed(root):
    p = os.path.join(root, HOOK_REL)
    if not os.path.isfile(p) or not os.access(p, os.X_OK):
        return False, "钩子文件不存在或不可执行：%s" % HOOK_REL
    with open(p, encoding="utf-8", errors="replace") as fh:
        body = fh.read()
    if MARKER not in body or "--scope history" not in body:
        return False, "钩子内容不是本守卫生成的（缺少 %s / --scope history）" % MARKER
    return True, "ok"


# ---------------------------------------------------------------- 造坏自检
def _write(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)


def _mk_repo(commits):
    """建临时仓库并提交；commits 是 [ {path: content} ] 的列表。返回路径。"""
    d = tempfile.mkdtemp(prefix="guard-selftest-")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    subprocess.run(["git", "init", "-q", d], check=True, env=env)
    for files in commits:
        for p, content in files.items():
            _write(os.path.join(d, p), content)
        subprocess.run(["git", "-C", d, "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", d, "commit", "-q", "-m", "c"], check=True, env=env)
    return d


def self_test(verbose=True):
    ok, bad = [], []

    def check(name, fn):
        """每个用例独立兜异常：一处崩了也要把其余结果报出来，否则等于没自检。"""
        try:
            if fn():
                ok.append(name)
            else:
                bad.append(name)
        except Exception as e:  # noqa: BLE001
            bad.append("%s（异常：%s: %s）" % (name, type(e).__name__, e))

    fake_key = "xk_" + "a1b2c3d4" * 4          # 35 字符，形状与真 key 一致
    clean_src = "import secrets\n\ndef gen():\n    return 'xk_' + secrets.token_hex(16)\n"

    def case_index_key():
        r = _mk_repo([{"app.py": "KEY = '%s'\n" % fake_key}])
        f, _ = scan_index(r)
        return any(x["reason"] == "明文 API Key" for x in f)

    def case_index_backup():
        r = _mk_repo([{"backups/database/x.db.gz": "x"}])
        f, _ = scan_index(r)
        return any("备份目录" in x["reason"] for x in f)

    def case_private_key():
        # 样本也拆开拼，否则守卫把自己的自测样本扫成命中
        pem = ("-" * 5 + "BEGIN RSA " + "PRIVATE KEY" + "-" * 5 + "\n"
               + "MIIEowIBAAKCAQEA" * 4 + "\n")
        r = _mk_repo([{"deploy/id_rsa": pem}])
        f, _ = scan_index(r)
        return any(x["reason"] == "私钥" for x in f)

    def case_negative_control():
        r = _mk_repo([{"modules/api.py": clean_src, "docs/schema.sql": "CREATE TABLE t(a int);\n"}])
        f, _ = scan_index(r)
        return not f

    def case_history_only():
        """提交过又删掉的 key：当前索引干净、历史扫描必须抓到。"""
        r = _mk_repo([{"cfg.py": "KEY = '%s'\n" % fake_key}])
        _write(os.path.join(r, "cfg.py"), "# removed\n")
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        subprocess.run(["git", "-C", r, "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", r, "commit", "-q", "-m", "remove"], check=True, env=env)
        f_cur, _ = scan_index(r)
        f_hist, _ = scan_history(r, {})
        return (not f_cur) and bool(f_hist)

    def case_stale_allowlist():
        r = _mk_repo([{"a.py": "x = 1\n"}])
        return bool(check_allowlist_alive(r, {"0" * 40: {}}))

    def case_rule_sample():
        """检测规则里的私钥头常量不算真私钥——它只有头，没有 base64 正文。"""
        head = "-" * 5 + "BEGIN RSA " + "PRIVATE KEY" + "-" * 5
        src = "PATTERNS = [\n    %s%s%s,\n]\n" % (chr(39), head, chr(39))
        r = _mk_repo([{"rules/x.py": src}])
        f, _ = scan_index(r)
        return not f

    def case_mail_literal():
        """写死的邮箱授权码必须判红。变量名和引号都拆开拼，别把自测样本扫成命中。"""
        src = "%s = %s%s%s\n" % ("SMTP_" + "PASS", chr(39), "a1b2c3d4e5f6g7h8", chr(39))
        r = _mk_repo([{"monitor.py": src}])
        f, _ = scan_index(r)
        return any(x["reason"] == "写死的邮箱授权码" for x in f)

    def case_mail_inside_string():
        """题库形态：整段是一个字符串值，里面的假凭据不许判红。

        样本拆开拼，别让守卫把自己的自测样本扫成命中。
        """
        v = "SMTP_" + "PASSWORD"
        snippet = "'code_snippet':'%s = %sabc12345%s'" % (v, chr(39), chr(39))
        r = _mk_repo([{"gen.py": "samples.append({%s})\n" % snippet}])
        f, _ = scan_index(r)
        return not f

    def case_mail_from_env():
        """从环境变量/配置读授权码的写法不许判红——只有字面量才算。"""
        src = ("PASS = os.environ.get(\"SMTP_\" + \"PASSWORD\", \"\")\n"
               "pwd = cfg[\"smtp_\" + \"pass\"]\n")
        r = _mk_repo([{"monitor.py": src}])
        f, _ = scan_index(r)
        return not f

    def case_self_clean():
        """守卫自己的源码不许被判红：否则装上钩子后，连「添加守卫」这个提交都推不上去。"""
        with open(os.path.abspath(__file__), encoding="utf-8") as fh:
            return not scan_text(fh.read())

    check("索引里的明文 Key 必须判红", case_index_key)
    check("索引里的备份目录必须判红", case_index_backup)
    check("索引里的私钥必须判红", case_private_key)
    check("阴性对照：拼 key 的代码与 schema.sql 不许判红", case_negative_control)
    check("历史里删掉的 Key 必须靠历史扫描抓到", case_history_only)
    check("白名单过期条目必须被识别", case_stale_allowlist)
    check("规则文件里的私钥头常量不许判红", case_rule_sample)
    check("写死的邮箱授权码必须判红", case_mail_literal)
    check("题库形态：字符串里的假凭据不许判红", case_mail_inside_string)
    check("阴性对照：从环境变量读授权码不许判红", case_mail_from_env)
    check("守卫自己的源码不许被判红", case_self_clean)

    if verbose:
        for s in ok:
            print("  ✅ %s" % s)
        for s in bad:
            print("  ❌ %s" % s)
        print("  自检 %d/%d" % (len(ok), len(ok) + len(bad)))
    return not bad


# ---------------------------------------------------------------- 主流程
def main(argv):
    root = DEFAULT_ROOT
    scope = "index"
    args = list(argv[1:])
    if "--root" in args:
        root = args[args.index("--root") + 1]
    if "--scope" in args:
        scope = args[args.index("--scope") + 1]

    if "--install-hook" in args:
        p = install_hook(root)
        print("已安装 pre-push 钩子：%s" % p)
        return 0
    if "--self-test" in args:
        return 0 if self_test() else 1

    if not os.path.isdir(os.path.join(root, ".git")):
        print("不是 git 仓库：%s" % root)
        return 2

    if scope == "history":
        allow = load_allowlist(root)
        dead = check_allowlist_alive(root, allow)
        if dead:
            print("❌ 白名单过期：%s" % ALLOWLIST_REL)
            for s in dead:
                print("   条目 %s 指向的提交已不存在（历史可能已清理）→ 请删掉这一条" % s[:10])
            return 2
        findings, legacy = scan_history(root, allow)
        if legacy:
            print("ℹ 已知旧账 %d 条（都在白名单提交里，不计入失败）：" % len(legacy))
            for x in legacy[:5]:
                print("   %s %s %s" % (x["commit"], x["path"], x["reason"]))
            if len(legacy) > 5:
                print("   … 另有 %d 条" % (len(legacy) - 5))
    else:
        findings, _ = scan_index(root)

    if not findings:
        print("✅ 仓库无明文凭据、无数据库转储（scope=%s）" % scope)
        return 0

    seen, lines = set(), []
    for x in findings:
        k = (x["commit"], x["path"], x["reason"])
        if k in seen:
            continue
        seen.add(k)
        lines.append("  %s%s  %s" % ((x["commit"] + " ") if x.get("commit") else "",
                                     x["path"], x["reason"]))
    print("❌ 发现 %d 处：\n%s" % (len(lines), "\n".join(lines)))
    print("   历史里的旧账请在 %s 里按提交登记；能用一次提交清掉的，别登记。" % ALLOWLIST_REL)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
