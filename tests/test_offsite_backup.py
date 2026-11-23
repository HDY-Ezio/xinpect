# -*- coding: utf-8 -*-
"""云上备份的守卫。

钉五件事（不是「脚本存在」，是「云上真有一份、而且真能还原」）：
1. 密钥文件权限没被放松（600；放开了等于把客户数据挂到门上）
2. 昨天的备份记录在、不超过 26 小时、且记录的大小与本地文件一致
3. 云上那个对象真的还在、大小对（真发一次请求，不看本地台账）
4. 每周做过一次恢复演练，且演练是通过的
5. 上传脚本里「传完回头核对大小」那段代码还在（有人删了校验，等于没校验）

第 5 条看着笨，但 2026-11-14 之前 PDF 通道就是「发起成功了、东西没落地」，
日志一路绿灯。校验代码被人顺手删掉，是不会有人发现的。
"""
import json
import os
import stat
import sys
import tempfile
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, 'scripts'))

import offsite_backup as ob  # noqa: E402

H = 3600
BACKUP_MAX_AGE = 26 * H
RESTORE_MAX_AGE = 8 * 24 * H
RECORD = '/opt/xinpect-website/tests/reports/last_cos_backup.json'
RESTORE_RECORD = '/opt/xinpect-website/tests/reports/last_restore_check.json'


def _load(path):
    with open(path) as f:
        return json.load(f)


def test_secret_file_is_private():
    path = '/etc/xinpect/cos.env'
    assert os.path.exists(path), '密钥文件不存在：%s' % path
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600, '密钥文件权限是 %o，应该 600（同组/其他人不能读）' % mode


def test_backup_record_is_fresh_and_matches_local():
    assert os.path.exists(RECORD), '没有云备份记录（从没成功上传过）：%s' % RECORD
    rec = _load(RECORD)
    age = time.time() - float(rec['epoch'])
    assert age <= BACKUP_MAX_AGE, '上次云备份是 %.1f 小时前（上限 26）' % (age / H)

    local = rec['local_file']
    assert os.path.exists(local), '记录里的本地文件不见了：%s' % local
    assert os.path.getsize(local) == rec['size'], \
        '本地文件大小 %d 与记录 %d 不一致（文件被换过？）' % (os.path.getsize(local), rec['size'])


def test_cloud_object_really_exists():
    """真去云上问一句。台账说成功不算数 —— 要云上回答。"""
    rec = _load(RECORD)
    cos = ob.Cos(ob.load_conf())
    head = None
    for attempt in range(2):          # 网络抖动给一次机会
        try:
            head = cos.head(rec['key'])
            break
        except Exception:
            if attempt == 1:
                raise
            time.sleep(1)
    assert head is not None, '云上找不到这个对象：%s（桶被删了？对象过期了？）' % rec['key']
    assert head['size'] == rec['size'], \
        '云上对象大小 %d 与记录 %d 不一致' % (head['size'], rec['size'])


def test_restore_drill_passed_recently():
    assert os.path.exists(RESTORE_RECORD), '从来没做过云上恢复演练：%s' % RESTORE_RECORD
    rec = _load(RESTORE_RECORD)
    age = time.time() - float(rec['epoch'])
    assert age <= RESTORE_MAX_AGE, '上次恢复演练是 %.1f 天前（应每周一次）' % (age / 86400)
    assert rec.get('ok'), '上次恢复演练没通过：%s' % (rec.get('detail') or '')


def test_upload_verifies_cloud_size():
    """钉行为：传完必须回头核对大小，对不上/查不到都要报错。

    上一版是「源码里有没有这行字符串」，造坏成 `if False:` 照样绿 ——
    字符串检查挡不住判据被掏空。所以这里喂假对象，看它会不会真的叫。
    """
    class FakeCos(object):
        def __init__(self, cloud_size, put_size=None):
            self.cloud_size = cloud_size
            self.put_size = put_size

        def put_file(self, local, key):
            n = os.path.getsize(local) if self.put_size is None else self.put_size
            return 'etag', n, 'md5'

        def head(self, key):
            return None if self.cloud_size is None else {'size': self.cloud_size, 'etag': 'etag'}

    fd, local = tempfile.mkstemp()
    os.write(fd, b'x' * 1024)
    os.close(fd)
    try:
        # 云上大小一致 → 通过
        ob.upload_and_verify(FakeCos(1024), local, 'db/x.gz')

        # 云上大小不一致 → 必须抛
        try:
            ob.upload_and_verify(FakeCos(999), local, 'db/x.gz')
        except RuntimeError as e:
            assert '不一致' in str(e), str(e)
        else:
            raise AssertionError('云上大小对不上竟然没报错')

        # 云上查不到对象 → 必须抛
        try:
            ob.upload_and_verify(FakeCos(None), local, 'db/x.gz')
        except RuntimeError as e:
            assert '查不到' in str(e), str(e)
        else:
            raise AssertionError('云上没有对象竟然没报错')

        # 本地读到的和发出去的不一致 → 必须抛
        try:
            ob.upload_and_verify(FakeCos(1024, put_size=512), local, 'db/x.gz')
        except RuntimeError as e:
            assert '只发出' in str(e), str(e)
        else:
            raise AssertionError('发少了一半竟然没报错')
    finally:
        os.unlink(local)


def test_missing_conf_does_not_guess():
    """缺配置必须报错，不能猜一个桶名往里传。"""
    try:
        ob.load_conf('/nonexistent/cos.env')
    except SystemExit as e:
        assert 'cos.env' in str(e), str(e)
    else:
        raise AssertionError('缺配置文件竟然没报错')


def test_monitor_watches_offsite():
    """钉消费方：监控必须把这条挂进告警，否则红了只有自己知道。

    只断言函数名是不够的 —— 函数定义本身也含这个名字，把调用删掉照样绿。
    """
    with open(os.path.join(_ROOT, 'critical_path_monitor.py'), encoding='utf-8') as f:
        src = f.read()
    assert 'alerts.extend(check_offsite_backup())' in src, '监控没调用云备份检查'


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    bad = 0
    for t in tests:
        try:
            t()
            print('  ✅ %s' % t.__name__)
        except AssertionError as e:
            bad += 1
            print('  ❌ %s: %s' % (t.__name__, e))
    print('%s 云上备份守卫: %d 项, 通过 %d, 失败 %d'
          % ('✅' if not bad else '❌', len(tests), len(tests) - bad, bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
