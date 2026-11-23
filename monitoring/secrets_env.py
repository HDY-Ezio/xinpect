#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""监控脚本的凭据加载：单一出口，源码里不留明文。

2026-11-23：授权码原先写死在三个监控脚本里，并随代码进入公开仓库历史，
之后全部迁到仓库外的 /etc/xinpect/monitor.env（640 root:ubuntu）。

优先级：进程环境变量 > 配置文件。两者都没有时返回空串，
由调用方决定「跳过并记日志」——绝不回退到源码内置的默认密钥。
"""
import os

ENV_PATH = '/etc/xinpect/monitor.env'
KEYS = ('SMTP_HOST', 'SMTP_PORT', 'SMTP_USER', 'SMTP_PASSWORD', 'ALERT_TO')


def _read_file(path):
    cfg = {}
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return cfg


def load():
    cfg = _read_file(ENV_PATH)
    for k in KEYS:
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg


def missing(cfg, keys):
    return [k for k in keys if not cfg.get(k)]
