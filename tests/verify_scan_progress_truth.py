#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：进度条必须只说真话（防「假进度」复发）。

接入 QA 第 6 段。--self-test 会在临时副本里故意注回旧假进度，
验证对应检查项会判红 —— 守卫自己不能是「永远绿」的摆设。
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
import tempfile

WEB = "/opt/xinpect-website"
SCANNER = "/opt/xinpect-scanner-green"
DB_PATH = "/opt/xinpect-website/xinpect.db"


def txt(root, rel):
    p = os.path.join(root, rel)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def checks(web=WEB, scanner=SCANNER, db_path=DB_PATH):
    js = txt(web, "static/js/scan-fx.js")
    css = txt(web, "static/css/scan-fx.css")
    base = txt(web, "templates/base.html")
    up = txt(web, "templates/upload.html")
    try_ = txt(web, "templates/try.html")
    api = txt(web, "modules/api.py")
    scan = txt(web, "modules/scan.py")
    bridge = txt(web, "modules/scan_progress_bridge.py")
    wscanner = txt(web, "modules/scanner.py")
    freetry = txt(web, "modules/free_try.py")

    sp = txt(scanner, "scan_progress.py")
    pr = txt(scanner, "engine/parallel_runner.py")
    hh = txt(scanner, "http_handlers.py")
    ss = txt(scanner, "scanner_service.py")
    sh = txt(scanner, "_scan_handler.py")

    c = {}
    c["共享 JS 存在"] = js is not None
    c["共享 CSS 存在"] = css is not None
    c["JS 没有定时器循环"] = js is not None and "setInterval" not in js
    c["JS 没有随机数"] = js is not None and "Math.random" not in js
    c["JS 没有自己推进百分比"] = js is not None and "pct +=" not in js and "prog +=" not in js
    c["JS 没有预计剩余时间"] = js is not None and "预计还需" not in js
    c["JS 只从参数取 pct"] = js is not None and "typeof d.pct === 'number'" in js
    c["CSS 尊重减弱动效"] = css is not None and "prefers-reduced-motion" in css
    c["base 全站引入同一份"] = base is not None and "css/scan-fx.css" in base and "js/scan-fx.js" in base

    c["上传页无随机进度"] = up is not None and "Math.random()" not in up
    c["上传页无假进度定时器"] = up is not None and "setInterval" not in up
    c["上传页无编造阶段"] = up is not None and "排查安全漏洞" not in up and "分析性能瓶颈" not in up
    c["上传页挂载真实组件"] = up is not None and "XpScanFX.mount" in up and "XpScanFX.render(data)" in up
    c["上传页轮询间隔够快"] = up is not None and "setTimeout(doPoll, 800)" in up

    c["试扫页删掉旧等待文案"] = try_ is not None and "正在检测中，通常" not in try_
    c["试扫页接真实进度"] = try_ is not None and "xp-scanfx-try" in try_ and "progress_job_id" in try_
    c["试扫有进度转发接口"] = freetry is not None and "/api/try-scan/progress/" in freetry

    c["API 心跳不再编百分比"] = api is not None and "预计还需约 %d 秒" not in api
    c["API 心跳只写心跳字段"] = api is not None and "UPDATE scans SET last_heartbeat_at=?" in api
    c["异步任务删掉编造阶段"] = scan is not None and 'progress_callback(15, "正在连接扫描引擎")' not in scan
    c["异步任务启动真实桥接"] = scan is not None and "_progress_start(scan_id)" in scan
    c["状态接口返回真实事件"] = scan is not None and 'resp["events"]' in scan and 'progress_source": "engine"' in scan
    c["桥接模块存在且不估算"] = bridge is not None and "预计" not in bridge and "_estimate" not in bridge
    c["官网 payload 带任务号"] = wscanner is not None and "options.get('progress_job_id')" in wscanner

    c["扫描器进度模块存在"] = sp is not None
    c["进度模块无 sleep/随机/估算"] = sp is not None and "time.sleep" not in sp and "random" not in sp and "预计" not in sp
    c["引擎完成有真实打点"] = pr is not None and "_mark_engine_done" in pr
    c["扫描入口 begin/finish 齐全"] = hh is not None and "_sp.begin(" in hh and "_sp2.finish(" in hh
    c["进度查询路由存在"] = ss is not None and 'path.startswith("/scan/progress/")' in ss
    c["文件清单逐条登记"] = sh is not None and "_sp.file_seen(" in sh
    c["引擎调用传任务号"] = sh is not None and "progress_job_id=_pjid" in sh

    # job_id 绝不能写进 config：config 参与扫描缓存键，会让缓存全失效
    dirty = []
    for name, body in (("parallel_runner", pr), ("_scan_handler", sh), ("http_handlers", hh)):
        if body and ('config["_progress_job_id"]' in body or "config['_progress_job_id']" in body
                     or 'config["progress_job_id"]' in body or "config['progress_job_id']" in body):
            dirty.append(name)
    c["任务号未污染缓存键 config"] = not dirty

    # 数据库列必须真的存在（不是只改了代码）
    try:
        conn = sqlite3.connect(db_path)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(scans)")]
        conn.close()
        c["事件流水列已落库"] = "scan_progress_events" in cols
    except Exception:
        c["事件流水列已落库"] = False
    return c


def self_test():
    """造坏副本，验证守卫确实会红（谁写谁不能只验自己）。"""
    tmp = tempfile.mkdtemp(prefix="xp_progress_guard_")
    try:
        w = os.path.join(tmp, "web")
        s = os.path.join(tmp, "scanner")
        for root in (w, s):
            os.makedirs(root)
        for rel in ("static/js/scan-fx.js", "static/css/scan-fx.css",
                    "templates/base.html", "templates/upload.html",
                    "templates/try.html", "modules/api.py", "modules/scan.py",
                    "modules/scan_progress_bridge.py", "modules/scanner.py",
                    "modules/free_try.py"):
            dst = os.path.join(w, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            src = os.path.join(WEB, rel)
            if os.path.isfile(src):
                shutil.copyfile(src, dst)
        for rel in ("scan_progress.py", "engine/parallel_runner.py",
                    "http_handlers.py", "scanner_service.py", "_scan_handler.py"):
            dst = os.path.join(s, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            src = os.path.join(SCANNER, rel)
            if os.path.isfile(src):
                shutil.copyfile(src, dst)

        good = checks(w, s, DB_PATH)
        # 故意注回旧假进度
        p = os.path.join(w, "static/js/scan-fx.js")
        with open(p, "a", encoding="utf-8") as f:
            f.write("\nsetInterval(function(){ pct += Math.random() * 5; }, 350);\n")
        p2 = os.path.join(w, "templates/upload.html")
        with open(p2, "a", encoding="utf-8") as f:
            f.write("\n<script>var progInterval = setInterval(function(){ prog += Math.random()*6; },350);</script>\n")
        bad = checks(w, s, DB_PATH)
        red = [k for k in bad if good.get(k) and not bad[k]]
        must_red = ["JS 没有定时器循环", "JS 没有随机数", "JS 没有自己推进百分比",
                    "上传页无随机进度", "上传页无假进度定时器"]
        missing = [k for k in must_red if k not in red]
        if missing:
            raise AssertionError("造坏副本后守卫没有判红: %s" % missing)
        print("SELF-TEST OK：造坏副本后判红的检查项 =", len(red))
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--web", default=WEB)
    ap.add_argument("--scanner", default=SCANNER)
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return 0
    c = checks(args.web, args.scanner)
    bad = [k for k, v in c.items() if not v]
    for k, v in c.items():
        print(("  OK  " if v else " FAIL "), k)
    print("进度真实性守卫: %d 项, 通过 %d, 失败 %d" % (len(c), len(c) - len(bad), len(bad)))
    if bad:
        print("失败项:", "；".join(bad))
        raise AssertionError("进度条真实性守卫未通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
