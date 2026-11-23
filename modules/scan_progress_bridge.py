#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""官网侧：把扫描器「真实发生的事」搬进官网数据库（纯旁路）。

不猜、不估、不编：
  · 只转发扫描器 /scan/progress/<job_id> 返回的真实事件，绝不自己按时间推进百分比
  · 查不到进度就什么都不写，页面上保持「检测中」，不假装知道
  · 任何异常都只记 debug 日志，绝不阻塞或改变正在进行的扫描
  · 只在 scan_status='pending' 时更新，绝不覆盖已完成的结论
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
from urllib.parse import urlsplit, urlunsplit

_LOCK = threading.RLock()
_RUNNERS = {}
_POLL_SECONDS = 0.4
_MAX_SECONDS = 900
_JOB_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,128}$")


def _progress_base():
    from modules.constants import SCANNER_URL
    p = urlsplit(SCANNER_URL)
    return urlunsplit((p.scheme, p.netloc, "", "", ""))


def _write(scan_id, snap):
    """把一次真实快照落库；只在任务仍在进行时生效。"""
    try:
        pct = int(snap.get("pct") or 0)
        if snap.get("status") != "finished":
            pct = min(pct, 95)
        payload = {
            "events": snap.get("events") or [],
            "files": snap.get("files") or [],
            "engines_done": snap.get("engines_done", 0),
            "engines_total": snap.get("engines_total", 0),
        }
        events = json.dumps(payload, ensure_ascii=False)
        text = str(snap.get("text") or "")[:300]
        from modules import app, get_db
        with app.app_context():
            db = get_db()
            db.execute(
                "UPDATE scans SET scan_progress=?, scan_progress_text=?, "
                "scan_progress_events=?, last_heartbeat_at=? "
                "WHERE scan_id=? AND scan_status='pending'",
                (pct, text, events,
                 time.strftime("%Y-%m-%d %H:%M:%S"), scan_id))
            db.commit()
    except Exception as e:
        try:
            from modules import logger
            logger.debug("progress bridge 写库旁路失败: %s", e)
        except Exception:
            pass


def start(scan_id, job_id=None):
    """启动真实进度转发线程。返回 stop() 可调用的 Event。"""
    jid = str(job_id or scan_id)
    if not _JOB_RE.match(jid):
        return None
    with _LOCK:
        if scan_id in _RUNNERS:
            return _RUNNERS[scan_id]
        stop = threading.Event()
        _RUNNERS[scan_id] = stop

    def _run():
        t0 = time.time()
        last_sig = None
        try:
            url = _progress_base() + "/scan/progress/" + jid
            from modules.constants import SCANNER_API_KEY
            headers = {"X-API-Key": SCANNER_API_KEY} if SCANNER_API_KEY else {}
            while not stop.is_set() and (time.time() - t0) < _MAX_SECONDS:
                try:
                    req = urllib.request.Request(url, headers=headers, method="GET")
                    with urllib.request.urlopen(req, timeout=3) as r:
                        snap = json.loads(r.read().decode("utf-8"))
                    if snap.get("status") != "unknown":
                        sig = (snap.get("pct"), len(snap.get("events") or []),
                               snap.get("text"), snap.get("status"))
                        if sig != last_sig:
                            last_sig = sig
                            _write(scan_id, snap)
                        if snap.get("status") == "finished":
                            break
                except Exception as e:
                    try:
                        from modules import logger
                        logger.debug("progress bridge 轮询旁路失败: %s", e)
                    except Exception:
                        pass
                stop.wait(_POLL_SECONDS)
        except Exception:
            pass
        finally:
            with _LOCK:
                _RUNNERS.pop(scan_id, None)

    threading.Thread(target=_run, daemon=True,
                     name="scan-progress-%s" % str(scan_id)[:24]).start()
    return stop


def stop(scan_id):
    with _LOCK:
        ev = _RUNNERS.pop(scan_id, None)
    if ev:
        ev.set()


def forward(job_id):
    """免登录试扫用：直接把扫描器的真实快照转发给前端（只读）。"""
    jid = str(job_id or "")
    if not _JOB_RE.match(jid):
        return {"status": "unknown", "pct": 0, "text": "", "events": []}
    try:
        from modules.constants import SCANNER_API_KEY
        url = _progress_base() + "/scan/progress/" + jid
        headers = {"X-API-Key": SCANNER_API_KEY} if SCANNER_API_KEY else {}
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=5) as r:
            snap = json.loads(r.read().decode("utf-8"))
        # 只回展示需要的字段，不把扫描器内部结构暴露给浏览器
        return {
            "status": snap.get("status"),
            "pct": snap.get("pct", 0),
            "text": snap.get("text", ""),
            "events": snap.get("events") or [],
            "files": snap.get("files") or [],
            "engines_done": snap.get("engines_done", 0),
            "engines_total": snap.get("engines_total", 0),
        }
    except Exception:
        return {"status": "unknown", "pct": 0, "text": "", "events": [], "files": []}
