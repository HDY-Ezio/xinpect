#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""监控状态落盘的唯一出口（2026-11-03 交接整改）

为什么要有这一层：
  1. 原子写：先写临时文件再 os.replace，避免进程被中断时留下半截 JSON，
     而读取端 except: pass 会把损坏文件静默当成空状态（等于监控假活着）。
  2. 失败降级：目标是只读/满盘/权限不足时，不抛异常中断监控，改为
     打 WARN 到 stderr 并把内容打到 stdout —— 监控照跑，问题可见。
  3. 属主继承：os.replace 会换 inode，若不显式继承，root 跑出来的文件
     属主会变成 root，读取方（如 xinpect-web 的官网进程）立刻读不到。

用法：
    from monitoring.safe_write import write_json
    write_json(path, payload, perm=0o600, label="状态快照")
"""
import json
import os
import sys
import tempfile


def _inherit(tmp, path, perm):
    """把目标文件既有的属主/权限搬到临时文件上，保证 replace 后不换身份。"""
    if os.path.exists(path):
        st = os.stat(path)
        if perm is None:
            perm = st.st_mode & 0o777
        if os.geteuid() == 0:
            try:
                os.chown(tmp, st.st_uid, st.st_gid)
            except OSError:
                pass
    if perm is not None:
        os.chmod(tmp, perm)


def write_json(path, payload, perm=None, label=""):
    """原子写 JSON；失败返回 False 并降级输出，绝不抛异常。"""
    label = label or os.path.basename(path)
    tmp = None
    try:
        d = os.path.dirname(path) or "."
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        _inherit(tmp, path, perm)
        os.replace(tmp, path)
        tmp = None
        return True
    except OSError as e:
        print("[WARN] %s 落盘失败，存储降级为仅标准输出：%s" % (label, e), file=sys.stderr)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return False
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
