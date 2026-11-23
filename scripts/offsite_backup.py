#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把数据库备份往云上存一份（腾讯云 COS）。

为什么做：2026-11-14 巡检发现，数据库备份和主库在同一块盘上（都是 /dev/vda2）。
盘坏、误删库、被锁，备份跟着一起没 —— 那就不叫备份，叫复印件。

判据（不满足就不算成功）：
1. 传完必须 HEAD 回查，云上大小和本地**一模一样**才算通过。
   只打印「上传成功」不算数：收了钱没交货的事发生过一次就够了。
2. 位置、时间、大小写进 tests/reports/last_cos_backup.json，给守卫和监控读。
3. 云上只留 7 天，跟本地一致；清理按对象名里的日期算，不靠 mtime（云上没有 mtime）。

配置在 /etc/xinpect/cos.env（600，root）。缺任何一项直接报错退出 ——
猜一个桶名等于往别人家备份。
"""
import argparse
import glob
import hashlib
import hmac
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

CONF = '/etc/xinpect/cos.env'
LOCAL_DIR = '/opt/xinpect-website/backups/database'
RECORD = '/opt/xinpect-website/tests/reports/last_cos_backup.json'
KEEP_DAYS = 7
PREFIX = 'db/'


def load_conf(path=CONF):
    """读配置。缺项直接报错，不给默认值。"""
    conf = {}
    if not os.path.exists(path):
        raise SystemExit('缺少配置文件 %s（要有 COS_SECRET_ID/COS_SECRET_KEY/COS_BUCKET/COS_REGION）' % path)
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            conf[k.strip()] = v.strip().strip('"').strip("'")
    need = ['COS_SECRET_ID', 'COS_SECRET_KEY', 'COS_BUCKET', 'COS_REGION']
    missing = [k for k in need if not conf.get(k)]
    if missing:
        raise SystemExit('配置缺项：%s' % ', '.join(missing))
    return conf


class Cos(object):
    """够用就行的 COS 客户端：PUT / HEAD / DELETE / LIST。"""

    def __init__(self, conf):
        self.ak = conf['COS_SECRET_ID']
        self.sk = conf['COS_SECRET_KEY']
        self.bucket = conf['COS_BUCKET']
        self.region = conf['COS_REGION']
        self.host = '%s.cos.%s.myqcloud.com' % (self.bucket, self.region)

    @staticmethod
    def _normalize(params):
        """把 URL 参数按字典序排好并重新编码。

        COS 签名要求参数必须是**字典序**，URL 里的顺序无所谓。直接拿传进来的
        字符串拼签名，只要顺序不是字典序就 403 —— 2026-11-14 在这上面栽过一次
        （PUT 成功、HEAD 成功，只有带 prefix 的列举 403，看着像权限问题）。
        """
        if not params:
            return '', ''
        pairs = sorted(urllib.parse.parse_qsl(params, keep_blank_values=True))
        enc = '&'.join('%s=%s' % (k, urllib.parse.quote(str(v), safe='')) for k, v in pairs)
        return enc, ';'.join(k for k, _v in pairs)

    def _authorization(self, method, path, params='', param_list='', headers=None):
        now = int(time.time())
        keytime = '%d;%d' % (now - 300, now + 3600)
        signkey = hmac.new(self.sk.encode(), keytime.encode(), hashlib.sha1).hexdigest()

        hdrs = {'host': self.host}
        for k, v in (headers or {}).items():
            hdrs[k.lower()] = str(v)
        hl = ';'.join(sorted(hdrs))
        header_str = '&'.join('%s=%s' % (k, hdrs[k]) for k in sorted(hdrs))
        http_str = '%s\n%s\n%s\n%s\n' % (method.lower(), path, params, header_str)
        tosign = 'sha1\n%s\n%s\n' % (keytime, hashlib.sha1(http_str.encode()).hexdigest())
        sig = hmac.new(signkey.encode(), tosign.encode(), hashlib.sha1).hexdigest()

        return ('q-sign-algorithm=sha1&q-ak=%s&q-sign-time=%s&q-key-time=%s'
                '&q-header-list=%s&q-url-param-list=%s&q-signature=%s'
                % (self.ak, keytime, keytime, hl, param_list, sig))

    def _request(self, method, key='', params='', body=None, headers=None, timeout=120):
        path = '/' + key
        enc, pl = self._normalize(params)
        hdrs = {'Host': self.host}
        for k, v in (headers or {}).items():
            hdrs[k] = str(v)
        hdrs['Authorization'] = self._authorization(method, path, enc, pl, headers)
        url = 'https://%s%s' % (self.host, path) + (('?' + enc) if enc else '')
        req = urllib.request.Request(url, data=body, method=method, headers=hdrs)
        return urllib.request.urlopen(req, timeout=timeout)

    def put_file(self, local, key):
        with open(local, 'rb') as f:
            data = f.read()
        md5 = hashlib.md5(data).hexdigest()
        # 不签 Content-Type：urllib 发出去的值和签名里的不完全一致，COS 直接 403。
        # 只签 host 最稳（建桶就是这么过的）。类型对二进制无所谓。
        try:
            resp = self._request('PUT', key, body=data)
        except urllib.error.HTTPError as e:
            raise RuntimeError('上传失败 HTTP %s：%s' % (e.code, e.read().decode('utf-8', 'replace')[:300]))
        etag = (resp.headers.get('ETag') or '').strip('"')
        return etag, len(data), md5

    def head(self, key):
        try:
            resp = self._request('HEAD', key, timeout=30)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise
        return {'size': int(resp.headers.get('Content-Length') or 0),
                'etag': (resp.headers.get('ETag') or '').strip('"')}

    def delete(self, key):
        try:
            self._request('DELETE', key, timeout=30)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise

    def list_objects(self, prefix=PREFIX, marker='', limit=1000):
        """列出对象名和大小。返回 ([(key, size)], 是否还有下一页)。"""
        params = 'marker=%s&max-keys=%d&prefix=%s' % (
            urllib.parse.quote(marker), limit, urllib.parse.quote(prefix))
        with self._request('GET', '', params=params, timeout=40) as r:
            body = r.read().decode('utf-8', 'replace')
        keys = re.findall(r'<Key>([^<]+)</Key>', body)
        sizes = re.findall(r'<Size>(\d+)</Size>', body)
        return list(zip(keys, [int(s) for s in sizes])), '<IsTruncated>true</IsTruncated>' in body


def latest_local():
    files = sorted(glob.glob(os.path.join(LOCAL_DIR, 'xinpect_backup_*.db.gz')))
    if not files:
        raise SystemExit('本地没有备份文件：%s' % LOCAL_DIR)
    return files[-1]


def key_of(local):
    return PREFIX + os.path.basename(local)


def upload_and_verify(cos, local, key):
    """上传，然后回头问云上一句「东西真的在了吗、大小对不对」。

    单独抽出来是为了能被测：只写在 main 里，只能靠「源码里有这行字」来验，
    而字符串检查挡不住把判据改成 `if False:`（2026-11-14 就这么漏过一次）。
    返回 (etag, size)；任何一步对不上都抛 RuntimeError。
    """
    size = os.path.getsize(local)
    etag, sent, md5 = cos.put_file(local, key)
    if sent != size:
        raise RuntimeError('只发出 %d 字节，本地是 %d' % (sent, size))

    head = cos.head(key)
    if not head:
        raise RuntimeError('传完 HEAD 查不到对象（云上没落地）：%s' % key)
    if head['size'] != size:
        raise RuntimeError('云上大小 %d 与本地 %d 不一致：%s' % (head['size'], size, key))
    return etag, size, md5


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='只打印要做什么，不真的传')
    ap.add_argument('--file', help='指定本地备份文件（默认取最新）')
    args = ap.parse_args(argv)

    cos = Cos(load_conf())
    local = args.file or latest_local()
    key = key_of(local)
    size = os.path.getsize(local)

    if args.dry_run:
        print('[dry-run] 要上传 %s (%d 字节) -> cos://%s/%s'
              % (local, size, cos.bucket, key))
        return 0

    print('上传 %s (%d 字节) -> cos://%s/%s' % (local, size, cos.bucket, key))
    try:
        etag, sent, md5 = upload_and_verify(cos, local, key)
    except RuntimeError as e:
        raise SystemExit('❌ %s' % e)
    if etag and etag.lower() != md5:
        print('⚠️ 云上 ETag 与本地 md5 不同（分段上传会这样），以大小为准')
    print('云上回查通过：size=%d' % sent)

    # 清理：云上超过 KEEP_DAYS 天的（按对象名里的日期，不靠 mtime）
    cutoff = time.strftime('%Y%m%d', time.localtime(time.time() - KEEP_DAYS * 86400))
    removed = []
    keys, truncated = cos.list_objects()
    if truncated:
        print('⚠️ 对象超过一页（1000），本轮只清理了第一页')
    for k, _sz in keys:
        m = re.search(r'(\d{8})_\d{6}\.db\.gz$', os.path.basename(k))
        if m and m.group(1) < cutoff:
            cos.delete(k)
            removed.append(os.path.basename(k))
    if removed:
        print('云上清理 %d 个过期对象：%s' % (len(removed), ', '.join(removed[:3])))

    head = cos.head(key)
    if not head or head['size'] != size:
        raise SystemExit('❌ 收尾核对失败：云上那份不见了或大小不对')

    rec = {'epoch': int(time.time()),
           'when': time.strftime('%Y-%m-%d %H:%M:%S'),
           'bucket': cos.bucket, 'key': key, 'local_file': local,
           'size': size, 'etag': head['etag'], 'removed': len(removed)}
    os.makedirs(os.path.dirname(RECORD), exist_ok=True)
    tmp = RECORD + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(rec, f, ensure_ascii=False)
    os.replace(tmp, RECORD)
    print('✅ 云上备份完成，记录已写')
    return 0


if __name__ == '__main__':
    sys.exit(main())
