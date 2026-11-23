"""访客行为埋点（Visitor Analytics）—— 全站访问记录的唯一出口。

## 为什么必须自建

整站此前没有任何访客记录：
- 数据库里只有 `users`（注册后才有）、`scans`、`api_calls`，**匿名访客零记录**；
- nginx access.log 也不能当数据源：443 端口前面是 sslh 协议复用器
  （`--listen 0.0.0.0:443 --tls 127.0.0.1:8443`），所有 HTTPS 访客
  在 nginx 眼里都是 127.0.0.1，真实 IP 在转发时丢失；且日志只留 21 天。

结论：**访客身份不能依赖客户端 IP**。改用匿名 cookie（vid）识别，
IP 只作为辅助字段（能拿到就记，拿不到记 127.0.0.1，不参与身份判定）。

## 铁律

1. **埋点失败绝不影响业务**：全部包 try/except，异常只落 logger，不抛。
2. **只记页面访问**：排除 /static/、/api/、favicon 等，避免音量爆炸。
3. **vid 是随机 UUID**，不关联邮箱/姓名等任何个人信息。
4. **爬虫不进访客口径**：UA 命中爬虫特征时 `is_bot=1`，统计时排除。
5. **我们自己的工具不进访客口径**：UA 以 `xinpect-` / `xp-` 开头时
   `is_internal=1`，统计时排除。判据定义在 `visitor_scope.py`，
   统计口径也只有一个出处（`VISITOR_FILTER`），不许在别处另写一份——
   2026-11-18 实测：自己的监控脚本一天灌了 1600 多次「访客」，
   报表显示"有人来过"，真相是一个人没来。
6. **没把内容送到就不算访问**：状态码 ≥ 400 的请求（404 探测为主）
   不落页面记录。2026-11-18 实测：7 天 1894 次 `/.env`、`/.git/config`
   这类探测，占了「独立访客」的 1353/1567，真人一个没多。

## 表结构

    visitor_events(id, vid, user_id, kind, path, method, status, referer, ua, ip,
                   is_bot, is_internal, detail, created_at)

`vid` 在用户注册/登录前就存在，因此可以把「匿名访客」和「注册用户」
用同一个 vid 串起来，算出真实的注册转化漏斗。

## 页面访问 vs 行为事件

`kind` 区分两类记录，**同一张表、同一个出口**——不开第二张表，
因为漏斗要按 vid 把「看了什么页」和「做了什么动作」串起来算，
分两处存迟早会漂移：

- `kind='page'`：页面访问（默认，由 after_request 自动记）
- `kind='event'`：行为事件（由 `track_event()` 显式记），`path` 存事件名，
  `detail` 存 JSON 属性

事件名统一用 `域.动作` 格式（`try.ok` / `try.cta_click`），
所有统计查询必须带 `kind` 过滤，否则会把事件当成页面访问。
"""

import json
import re
import sqlite3
import uuid

from flask import g, jsonify, request, session

from .constants import DB_PATH, app, logger
from .visitor_scope import is_internal_ua

COOKIE_NAME = 'xp_vid'
COOKIE_MAX_AGE = 365 * 24 * 3600

# 不记录的前缀：静态资源、接口、健康检查、SEO 文件
_SKIP_PREFIXES = (
    '/static/',
    '/api/',
    '/favicon',
    '/robots.txt',
    '/sitemap',
    '/health',
    '/metrics',
    '/.well-known/',
)

# 爬虫/工具特征。命中则 is_bot=1，不计入访客数。
_BOT_RE = re.compile(
    r'(?:bot\b|spider|crawl|slurp|scrapy|curl/|wget|python-requests'
    r'|python-urllib|headlesschrome|phantomjs|lighthouse|palo alto'
    r'|semrush|ahrefs|mj12|bytespider|petalsearch|yandex|googlebot'
    r'|bingbot|facebookexternalhit|go-http-client|okhttp|scanner'
    r'|nmap|nikto|masscan'
    # Werkzeug 是 Flask 自带测试客户端的 UA。我们自己跑验证脚本、出预览快照
    # 都会走 test_client，如果不排除，测试流量会被算成真实访客（已实测踩过）。
    r'|werkzeug)',
    re.I,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS visitor_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vid TEXT NOT NULL,
    user_id INTEGER,
    kind TEXT NOT NULL DEFAULT 'page',
    path TEXT NOT NULL,
    method TEXT,
    status INTEGER,
    referer TEXT,
    ua TEXT,
    ip TEXT,
    is_bot INTEGER NOT NULL DEFAULT 0,
    is_internal INTEGER NOT NULL DEFAULT 0,
    detail TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_visitor_created ON visitor_events(created_at);
CREATE INDEX IF NOT EXISTS idx_visitor_vid ON visitor_events(vid);
CREATE INDEX IF NOT EXISTS idx_visitor_path ON visitor_events(path);
"""

# 老库补列：CREATE TABLE IF NOT EXISTS 不会给已存在的表加列，
# 所以升级必须显式迁移。加列是幂等的（先查 PRAGMA），重复执行无害。
_MIGRATIONS = (
    ('kind', "ALTER TABLE visitor_events ADD COLUMN kind TEXT NOT NULL DEFAULT 'page'"),
    ('detail', 'ALTER TABLE visitor_events ADD COLUMN detail TEXT'),
    # 2026-11-18：自检流量单独成档。老记录一律默认 0，随后由
    # `scripts/backfill_internal_flag.py` 按 UA 回填（历史数据也是错的，
    # 只加列不回填，账面还是把自检算成人）。
    ('is_internal',
     'ALTER TABLE visitor_events ADD COLUMN is_internal INTEGER NOT NULL DEFAULT 0'),
)

# 前端能上报的事件白名单。
# 只收「决定漏斗走不走得下去」的那几个动作，其余一概拒绝——
# 开放写入等于让任何脚本都能往统计表里灌垃圾，数据脏了比没数据更糟。
CLIENT_EVENTS = frozenset({
    'try.submit',     # 点了「开始免费检测」
    'try.cta_click',  # 结果页点了注册引导
})

_schema_ready = False


def _ensure_schema(conn):
    """建表 + 补列（进程内只做一次）。"""
    global _schema_ready
    if _schema_ready:
        return
    conn.executescript(_SCHEMA)
    existing = {row[1] for row in conn.execute('PRAGMA table_info(visitor_events)')}
    for column, ddl in _MIGRATIONS:
        if column not in existing:
            conn.execute(ddl)
    conn.commit()
    _schema_ready = True


def _is_trackable(path, method):
    if method != 'GET':
        return False
    if not path or path == '/':
        return True
    # 接口不是页面。按「路径里有没有 api 段」判，而不是只认 /api 开头——
    # 实测有 /xinpect/api/scan/health 这类带前缀的内部健康检查，
    # 用 startswith('/api/') 漏掉了，白白记成一次「页面访问」。
    if '/api/' in path or path.startswith('/api'):
        return False
    for prefix in _SKIP_PREFIXES:
        if path.startswith(prefix):
            return False
    return True


def get_vid():
    """取当前访客的匿名 id（不写入 cookie，只读）。"""
    vid = request.cookies.get(COOKIE_NAME, '')
    if vid and len(vid) == 32:
        return vid
    return ''


def _new_vid():
    return uuid.uuid4().hex


def current_vid():
    """本次请求的访客 id：有就读，没有就就地发放一个（同一请求内反复调用返回同一个）。

    「发放」和「下发」是两件事，这里只做前者：
    - 发放 = 决定这次请求算哪个人，存进 `g`，保证**同一个请求里**
      free_try 的限流和 after_request 的落库用的是同一个 vid；
    - 下发 = 写 Set-Cookie，在 after_request 统一做（或需要提前下发的接口
      自己调 `set_vid_cookie`）。

    为什么要这么绕：以前 `track_event()` 只读 cookie，而 POST /api/try-scan
    在第一次访问时请求里根本没有 cookie —— 于是「扫描成功」这件事记不下来，
    既丢了漏斗，又让「按已用次数算额度」无从入手。
    """
    vid = getattr(g, '_cur_vid', '')
    if vid:
        return vid
    vid = get_vid()
    if vid:
        g._cur_vid = vid
        g._vid_new = False
    else:
        vid = _new_vid()
        g._cur_vid = vid
        g._vid_new = True
    return vid


def set_vid_cookie(response, vid):
    """把访客 id 写到浏览器。Secure 跟着实际协议走，别在 http 下写不进去。"""
    response.set_cookie(
        COOKIE_NAME, vid,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite='Lax',
        secure=request.is_secure or request.headers.get('X-Forwarded-Proto') == 'https',
    )
    return response


def _trusted_ip():
    """取「可信」的那一跳 IP，只用于辅助观测，绝不参与身份判定。

    X-Forwarded-For 里 nginx 用 `$proxy_add_x_forwarded_for` 把 `$remote_addr`
    追加在**最右边**；最左边那段是客户端自己写的，随手就能伪造。所以只有
    最后一跳是反向代理亲手写的。

    但这台机 443 前面还挡着 sslh 1.22（纯 TCP 转发，不支持 PROXY protocol），
    nginx 的 `$remote_addr` 恒为 127.0.0.1 —— 实测整张 visitor_events 表里
    所有访客的 ip 都是 127.0.0.1，这个字段在本机拓扑下**没有任何信息量**。

    那为什么还要改：原来取第一节，等于把伪造值写进库，将来一定有人拿它做
    判断（限流/去重/风控）然后踩空。宁可记一个诚实的 127.0.0.1。
    """
    xff = request.headers.get('X-Forwarded-For', '')
    if xff:
        return xff.split(',')[-1].strip()
    return request.remote_addr or ''


def _insert(vid, *, kind, path, method=None, status=None, detail=None):
    """唯一的写入口。页面记录和事件记录都走这里，表结构只在这一个地方被拼。"""
    conn = sqlite3.connect(DB_PATH, timeout=1)
    try:
        _ensure_schema(conn)
        # UA 只读一次：is_bot 和 is_internal 必须看同一个值，
        # 分两次读的话将来有人改了上面那行，两边就会对不上。
        ua = request.headers.get('User-Agent') or ''
        conn.execute(
            'INSERT INTO visitor_events '
            '(vid, user_id, kind, path, method, status, referer, ua, ip, '
            ' is_bot, is_internal, detail) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (
                vid,
                session.get('user_id'),
                kind,
                path[:300],
                method,
                status,
                (request.headers.get('Referer') or '')[:400],
                ua[:400],
                _trusted_ip()[:64],
                1 if _BOT_RE.search(ua) else 0,
                1 if is_internal_ua(ua) else 0,
                detail,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def track_event(name, **props):
    """记一条行为事件（kind='event'）。

    **失败一律吞掉**：埋点是观察工具，不该成为业务链路上的故障点。
    返回 True/False 只用于测试断言，调用方不需要关心。

    没有 vid 就不记——试扫/注册这些动作必然发生在页面访问之后，
    cookie 早就在了；凭空造一个 vid 只会得到一堆串不起来的孤儿记录。
    """
    try:
        if app.config.get('TESTING') and not app.config.get('VISITOR_ANALYTICS_ALLOW_TESTING'):
            return False
        vid = current_vid()
        if not vid:
            return False
        payload = {k: v for k, v in props.items() if v is not None}
        _insert(
            vid,
            kind='event',
            path=name[:100],
            method='EVENT',
            detail=json.dumps(payload, ensure_ascii=False)[:1000] if payload else None,
        )
        return True
    except Exception as exc:  # noqa: BLE001 - 埋点永不影响业务
        try:
            logger.debug('[访客埋点] 事件 %s 写入失败（已忽略）: %s', name, exc)
        except Exception:
            pass
        return False


def _same_origin():
    """只接受本站发来的上报。跨站脚本往统计表灌数据，直接挡在门外。"""
    origin = request.headers.get('Origin') or ''
    ref = request.headers.get('Referer') or ''
    src = origin or ref
    if not src:
        return False
    host = request.host
    return src.split('://', 1)[-1].split('/', 1)[0] == host


@app.route('/api/track', methods=['POST'])
def _track_client_event():
    """前端行为上报。只收白名单事件 + 标量属性，且只认同源。"""
    if not _same_origin():
        return jsonify({'ok': False}), 403
    data = request.get_json(silent=True) or {}
    name = (data.get('event') or '').strip()
    if name not in CLIENT_EVENTS:
        return jsonify({'ok': False}), 400
    props = data.get('props')
    if not isinstance(props, dict):
        props = {}
    # 只保留标量，且限条数/长度：前端塞大对象会把表撑坏
    clean = {}
    for k, v in list(props.items())[:10]:
        if isinstance(v, bool) or isinstance(v, (int, float)):
            clean[str(k)[:32]] = v
        elif isinstance(v, str):
            clean[str(k)[:32]] = v[:80]
    track_event(name, **clean)
    return jsonify({'ok': True})


@app.after_request
def _record_visitor(response):
    """记录页面访问。任何异常都吞掉，绝不影响正常响应。"""
    try:
        # 测试默认不写生产访问表。
        # 根因：Flask test_client 的请求同样会走 after_request，UA 是
        # Werkzeug/x.x。我们的验证脚本（verify_onboarding / snapshot /
        # vipcheck）一跑，就凭空多出一批"访客"——实测今天 24 个访客
        # 全是自己的测试，真人一个都没有。测试数据污染生产口径，
        # 比没有数据更糟：它会让人得出"有人来过"的错误结论。
        #
        # 但埋点测试自身必须真的落一条才能验证口径（同一 cookie 认成同一人）。
        # 所以给一个显式开关，只有专门测埋点的用例才打开它，测完自己清理。
        if app.config.get('TESTING') and not app.config.get('VISITOR_ANALYTICS_ALLOW_TESTING'):
            return response

        # 先决定「这次算哪个访客」，再决定要不要记一条页面访问。
        # 顺序不能反：vid 的下发与否跟「记不记页面」无关。
        vid = current_vid()

        # 只有**真的把内容送到**了，才算一次页面访问。
        #
        # 2026-11-18 实测：7 天里 1894 次 404（`/.env`、`/.git/config`、
        # `/.env.backup`……全是漏洞扫描器的探测），占了「独立访客」的
        # 1353/1567 —— 真人一个都没多。404 页面对访客口径没有意义，
        # 它只能证明「有个脚本在扫我们」。
        #
        # 判据用状态码而不是路径黑名单：探测路径是无穷的（.env.local /
        # .env.prod / .env.docker ……），而「没送到内容」这件事只有一个判据。
        # 想留安全审计，nginx 的 access.log 里有全量记录。
        if (_is_trackable(request.path, request.method)
                and response.status_code < 400):
            _insert(vid, kind='page', path=request.path, method=request.method,
                    status=response.status_code)

        # 新 vid 要下发给浏览器，哪怕这个请求本身不进访问记录
        # （POST /api/try-scan 就是这种：不记页面，但试扫额度要靠这个 vid 记账）。
        #
        # 2026-11-04 修正：这段原来写在 `if not _is_trackable: return response`
        # 之后，而 /api/* 恰好被 _is_trackable 排除 —— 等于永远不执行。
        # 实测后果是匿名每次 POST 都拿到新 vid，3 次额度永远用不完，
        # 限流形同不存在。别再把「记不记页面」和「发不发身份」绑在一起。
        if getattr(g, '_vid_new', False):
            set_vid_cookie(response, vid)
    except Exception as exc:  # noqa: BLE001 - 埋点永不影响业务
        try:
            logger.debug('[访客埋点] 写入失败（已忽略）: %s', exc)
        except Exception:
            pass
    return response
