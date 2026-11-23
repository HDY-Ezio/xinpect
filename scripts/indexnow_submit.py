#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把站点 URL 推给 IndexNow（Bing / Yandex / Seznam / Naver 共用协议）。

用法：
    python3 indexnow_submit.py                # 提交 sitemap 里全部 URL
    python3 indexnow_submit.py /try /detect   # 只提交指定路径
    python3 indexnow_submit.py --dry-run      # 只打印不发送

为什么要有这个脚本：改完文案只改站内是没用的，索引里还是旧摘要
（今天踩过：官网全站挂着 1.7% 旧误报率，稿子写 0，读者一搜就撞车）。
提交后 Bing 一侧通常几小时到一天内刷新，百度不吃这套，要走它自己的 API。

key 文件由 nginx 的精确匹配 location 提供：https://<host>/<KEY>.txt
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request

HOST = 'xinpect.xingwangzhineng.com'
SITE = f'https://{HOST}'
KEY_FILE = '/home/ubuntu/.indexnow_key'
ENDPOINTS = ['https://api.indexnow.org/indexnow', 'https://www.bing.com/indexnow']


def sitemap_urls() -> list:
    with urllib.request.urlopen(f'{SITE}/sitemap.xml', timeout=20) as r:
        xml = r.read().decode('utf-8', 'ignore')
    return re.findall(r'<loc>(.*?)</loc>', xml)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='*', help='只提交这些路径，留空=全站')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    try:
        key = open(KEY_FILE).read().strip()
    except OSError as e:
        print(f'读不到 key 文件 {KEY_FILE}: {e}')
        return 1
    if not re.fullmatch(r'[0-9a-f]{32}', key):
        print(f'key 格式不对：{key!r}')
        return 1

    urls = sitemap_urls()
    if a.paths:
        want = {p.rstrip('/') or '/' for p in a.paths}
        urls = [u for u in urls if (u[len(SITE):].rstrip('/') or '/') in want]
        if not urls:
            print('指定路径不在 sitemap 里，什么也没提交')
            return 1

    print(f'待提交 {len(urls)} 条：')
    for u in urls:
        print('  ', u)
    if a.dry_run:
        return 0

    body = json.dumps({
        'host': HOST,
        'key': key,
        'keyLocation': f'{SITE}/{key}.txt',
        'urlList': urls,
    }).encode()
    bad = 0
    for ep in ENDPOINTS:
        req = urllib.request.Request(
            ep, data=body, headers={'Content-Type': 'application/json; charset=utf-8'})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                print(f'{ep} -> HTTP {r.status}')
                # 200/202 才是收下；其它都是被拒（key 不匹配、host 不符等）
                if r.status not in (200, 202):
                    bad += 1
        except urllib.error.HTTPError as e:
            print(f'{ep} -> HTTP {e.code} {e.read()[:200].decode(errors="ignore")}')
            bad += 1
        except Exception as e:
            print(f'{ep} -> FAIL {type(e).__name__}: {e}')
            bad += 1
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
