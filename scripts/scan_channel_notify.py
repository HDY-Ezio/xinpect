#!/usr/bin/env python3
"""
煋鉴自愈结果即时通知（飞书版）
- 有修不了的问题 → 立即通过飞书给主人发消息
- 全部修复成功 → 静默（由日报汇报）
"""

import json
import os
import subprocess
from datetime import datetime

HEAL_LOG = '/opt/xinpect-website/data/auto_heal_history.json'
STATE_FILE = '/opt/xinpect-website/data/notify_state.json'
ALERT_FILE = '/opt/xinpect-website/data/urgent_alert.json'

# 飞书配置
FEISHU_USER_ID = 'ou_9d2fbdfef3ddf0379c6b0286e6d5c4c9'

def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return None if not os.path.exists(path) else {}

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def send_feishu(text):
    """通过飞书CLI发送消息给主人"""
    try:
        result = subprocess.run(
            ['lark-cli', 'im', '+messages-send',
             '--user-id', FEISHU_USER_ID,
             '--as', 'bot',
             '--text', text],
            capture_output=True, text=True, timeout=15
        )
        resp = json.loads(result.stdout) if result.stdout.strip() else {}
        if resp.get('ok'):
            print("FEISHU_SENT")
            return True
        else:
            print(f"FEISHU_FAILED: {resp.get('error', {}).get('message', 'unknown')}")
            return False
    except Exception as e:
        print(f"FEISHU_ERROR: {e}")
        return False

def main():
    heal_history = load_json(HEAL_LOG) or []
    state = load_json(STATE_FILE)
    last_notified_id = state.get('last_notified_id', -1)

    # 找出还没通知过的修复记录
    new_records = heal_history[last_notified_id + 1:]
    if not new_records:
        print("NO_NEW_RECORDS")
        return

    # 筛选：有修复失败的记录
    need_notify = []
    success_count = 0
    for rec in new_records:
        fixes = rec.get('fixes_applied', [])
        failed = rec.get('failed_count', 0)
        status_after = rec.get('status_after', 'unknown')
        if failed > 0 or (fixes and status_after != 'ok'):
            need_notify.append(rec)
        elif fixes and failed == 0:
            success_count += 1

    # 更新状态
    state['last_notified_id'] = len(heal_history) - 1
    save_json(STATE_FILE, state)

    if not need_notify:
        # 全部修复成功，静默
        if success_count > 0:
            print(f"ALL_FIXED: {success_count} issues auto-healed")
        else:
            print("NO_FIX_NEEDED")
        return

    # 有修不了的 → 立即飞书通知
    latest = need_notify[-1]
    fixes = latest.get('fixes_applied', [])
    heal_time = latest.get('timestamp', '')
    status_after = latest.get('status_after', '')

    # 构建飞书消息
    lines = []
    lines.append('🚨 煋鉴异常自动修复失败，需人工介入')
    lines.append('')
    lines.append(f'检测时间：{heal_time}')
    lines.append(f'当前状态：{status_after}')
    lines.append('')
    for f in fixes:
        if '失败' in f or '需人工' in f:
            lines.append(f'❌ {f}')
        else:
            lines.append(f'✅ {f}')

    message = '\n'.join(lines)
    ok = send_feishu(message)

    # 写入告警文件（供日报读取）
    save_json(ALERT_FILE, {
        'timestamp': heal_time,
        'fixes_applied': fixes,
        'status_after': status_after,
        'feishu_sent': ok,
        'status': 'notified' if ok else 'pending'
    })

if __name__ == '__main__':
    main()
