# -*- coding: utf-8 -*-
"""
程序化 SEO 蓝图 —— 为高频「漏洞类型」关键词生成标准化落地页。

参考 Snyk Advisor 的程序化 SEO 打法：用一个「漏洞知识库」数据表驱动
一个模板，批量生成几十上百个高质量落地页，每个页面都覆盖独立的搜索
关键词（如「Java SQL 注入」「Python 命令注入」「XSS 检测」），页尾统一
CTA 引流回主产品。

URL 规则：/detect/<slug>，slug 稳定、语义化、含语言+漏洞类型。
"""

from flask import Blueprint, render_template, abort, redirect, url_for

seo_bp = Blueprint('seo', __name__)

# ─────────────────────────────────────────────────────────────
# 漏洞知识库（单一事实来源）
# 每个条目：slug / 漏洞类型 / 语言 / 标题 / 描述 / 危害 / 代码示例 / 修复 / 检测点
# ─────────────────────────────────────────────────────────────

VULN_KB = {
    # ── SQL 注入 ──
    "sql-injection": {
        "title": "SQL 注入检测（SQL Injection）—— 原理、示例与自动化检测",
        "vuln_name": "SQL 注入",
        "vuln_name_en": "SQL Injection",
        "cwe": "CWE-89",
        "owasp": "OWASP Top 10 A03:2021",
        "severity": "高危",
        "summary": "当攻击者能够把恶意的 SQL 语句拼接进查询，进而读取、篡改、删除数据库内容时，就发生了 SQL 注入。它是历史上最常见、危害最大的 Web 漏洞之一。",
        "harm": [
            "直接读取数据库中的敏感数据（用户密码、订单、身份证号）",
            "篡改或删除数据，导致业务瘫痪",
            "在部分场景下可进一步拿到数据库服务器权限",
        ],
        "code_sample_lang": "Java",
        "code_sample": '''// 危险写法：字符串拼接用户输入
String userId = request.getParameter("id");
String sql = "SELECT * FROM users WHERE id = " + userId;
Statement stmt = conn.createStatement();
ResultSet rs = stmt.executeQuery(sql);  // 攻击者输入 "1 OR 1=1" 即全表泄露''',
        "fix_sample": '''// 安全写法：参数化查询（PreparedStatement）
String userId = request.getParameter("id");
String sql = "SELECT * FROM users WHERE id = ?";
PreparedStatement ps = conn.prepareStatement(sql);
ps.setString(1, userId);  // 参数与 SQL 结构分离，无法注入
ResultSet rs = ps.executeQuery();''',
        "detect_points": [
            "追踪不可信输入（request.getParameter / @RequestParam / getenv）经拼接、函数调用流入 JDBC executeQuery/executeUpdate/prepareStatement 的完整数据流",
            "跨文件方法透传：接口 → 实现类 → 方法调用链的污点传播",
            "识别 PreparedStatement 参数化是否真正隔离了用户输入",
        ],
        "related": ["命令注入", "XSS 跨站脚本", "路径遍历"],
    },

    "command-injection": {
        "title": "命令注入检测（Command Injection）—— 原理、示例与自动化检测",
        "vuln_name": "命令注入",
        "vuln_name_en": "Command Injection",
        "cwe": "CWE-78",
        "owasp": "OWASP Top 10 A03:2021",
        "severity": "高危",
        "summary": "当应用把用户输入拼进系统命令并执行时，攻击者可以注入额外的命令，从而在服务器上执行任意指令，通常能直接拿到服务器控制权。",
        "harm": [
            "在服务器上执行任意系统命令",
            "直接获取服务器 shell，控制整个主机",
            "作为内网渗透的跳板，横向攻击其他系统",
        ],
        "code_sample_lang": "Python",
        "code_sample": '''# 危险写法：用户输入拼进系统命令
import os
cmd = request.args.get("cmd")
os.system("ping " + cmd)  # 输入 "; rm -rf /" 即执行任意命令''',
        "fix_sample": '''# 安全写法：白名单校验 + 参数数组（不经过 shell）
import subprocess
allowed = {"baidu.com", "google.com"}
host = request.args.get("host")
if host not in allowed:
    raise ValueError("非法主机")
subprocess.run(["ping", "-c", "1", host])  # 参数数组，不经 shell 解释''',
        "detect_points": [
            "追踪 request 输入流入 os.system / subprocess / Runtime.exec / ProcessBuilder 等命令执行 sink",
            "识别 shell 拼接（字符串 + 变量）而非参数数组调用",
            "跨语言覆盖 Python/Java/PHP/Ruby/Go 等命令执行模式",
        ],
        "related": ["SQL 注入", "SSRF 服务端请求伪造", "代码执行"],
    },

    "xss": {
        "title": "XSS 跨站脚本检测（Cross-Site Scripting）—— 原理、示例与自动化检测",
        "vuln_name": "XSS 跨站脚本",
        "vuln_name_en": "Cross-Site Scripting",
        "cwe": "CWE-79",
        "owasp": "OWASP Top 10 A03:2021",
        "severity": "中高危",
        "summary": "当应用把用户输入未经转义地输出到页面时，攻击者可以注入恶意脚本，在受害者浏览器中执行，窃取登录态、Cookie 或进行钓鱼。",
        "harm": [
            "窃取用户 Cookie 与登录凭证（会话劫持）",
            "在受害者浏览器中执行任意脚本",
            "钓鱼、篡改页面内容、传播蠕虫",
        ],
        "code_sample_lang": "JavaScript",
        "code_sample": '''// 危险写法：用户输入直接写入页面
const name = req.query.name;
res.send("<div>欢迎 " + name + "</div>");  // name 含 <script> 即被注入''',
        "fix_sample": '''// 安全写法：转义输出
const escapeHtml = (s) => s.replace(/[&<>"']/g, c => ({
  "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
}[c]));
res.send("<div>欢迎 " + escapeHtml(name) + "</div>");''',
        "detect_points": [
            "追踪用户输入流入 innerHTML / document.write / res.send 等危险输出点",
            "识别未转义的字符串拼接输出",
            "识别 split/charAt 等「转换不净化」操作后仍继承污点的场景",
        ],
        "related": ["SQL 注入", "命令注入", "不安全反序列化"],
    },

    "path-traversal": {
        "title": "路径遍历检测（Path Traversal）—— 原理、示例与自动化检测",
        "vuln_name": "路径遍历",
        "vuln_name_en": "Path Traversal",
        "cwe": "CWE-22",
        "owasp": "OWASP Top 10 A01:2021",
        "severity": "高危",
        "summary": "当应用用用户输入拼接文件路径且未做规范化校验时，攻击者可用 ../ 跳出预期目录，读取或写入任意文件，如 /etc/passwd、源码、配置文件。",
        "harm": [
            "读取任意文件（密码文件、源码、配置、密钥）",
            "覆盖或写入任意文件，可能写入 webshell",
            "泄露敏感配置导致进一步渗透",
        ],
        "code_sample_lang": "Java",
        "code_sample": '''// 危险写法：用户输入直接拼文件路径
String filename = request.getParameter("file");
File f = new File("/var/www/uploads/" + filename);  // 输入 "../../etc/passwd" 越权读取''',
        "fix_sample": '''// 安全写法：规范化路径 + 白名单校验
String filename = request.getParameter("file");
File base = new File("/var/www/uploads/").getCanonicalFile();
File f = new File(base, filename).getCanonicalFile();
if (!f.getPath().startsWith(base.getPath())) {
    throw new SecurityException("非法路径");
}''',
        "detect_points": [
            "追踪用户输入流入 File / Files / FileInputStream 等文件操作 sink",
            "识别未做 getCanonicalPath 规范化的路径拼接",
            "识别缺失「前缀目录校验」的文件读写",
        ],
        "related": ["命令注入", "任意文件写入", "SSRF"],
    },

    "ssrf": {
        "title": "SSRF 服务端请求伪造检测（Server-Side Request Forgery）—— 原理与自动化检测",
        "vuln_name": "SSRF 服务端请求伪造",
        "vuln_name_en": "Server-Side Request Forgery",
        "cwe": "CWE-918",
        "owasp": "OWASP Top 10 A10:2021",
        "severity": "中高危",
        "summary": "当应用根据用户输入向任意 URL 发起服务端请求时，攻击者可诱导服务器访问内网地址（如 169.254.169.254 云元数据）或内部服务，绕过网络边界。",
        "harm": [
            "访问云主机元数据接口，窃取临时密钥",
            "探测并攻击内网服务，绕过防火墙",
            "作为代理访问受保护的内部资源",
        ],
        "code_sample_lang": "Java",
        "code_sample": '''// 危险写法：用户输入的 URL 直接发起请求
String url = request.getParameter("url");
URL target = new URL(url);
HttpURLConnection conn = (HttpURLConnection) target.openConnection();
// 输入 "http://169.254.169.254/latest/meta-data/" 可窃取云密钥''',
        "fix_sample": '''// 安全写法：URL 白名单 + 禁止内网地址
String url = request.getParameter("url");
if (!url.startsWith("https://api.example.com/")) {
    throw new SecurityException("仅允许访问白名单域名");
}
// 进一步：解析后校验 IP 非内网段（10./172.16./192.168./169.254.）''',
        "detect_points": [
            "追踪用户输入流入 URL.openConnection / HttpClient / requests.get 等网络请求 sink",
            "识别缺失域名/IP 白名单校验的请求",
            "识别可被指向内网地址的服务端请求",
        ],
        "related": ["命令注入", "路径遍历", "XXE"],
    },

    "insecure-deserialization": {
        "title": "不安全反序列化检测（Insecure Deserialization）—— 原理与自动化检测",
        "vuln_name": "不安全反序列化",
        "vuln_name_en": "Insecure Deserialization",
        "cwe": "CWE-502",
        "owasp": "OWASP Top 10 A08:2021",
        "severity": "高危",
        "summary": "当应用反序列化不可信数据时，攻击者可构造恶意序列化对象，在反序列化过程中触发任意代码执行，这是 Java/Python/PHP 等语言的高危漏洞。",
        "harm": [
            "反序列化时触发任意代码执行（RCE）",
            "绕过认证、篡改对象状态",
            "利用 gadget chain 实现完整控制",
        ],
        "code_sample_lang": "Java",
        "code_sample": '''// 危险写法：反序列化不可信数据
byte[] data = request.getParameter("data").getBytes();
ObjectInputStream ois = new ObjectInputStream(new ByteArrayInputStream(data));
Object obj = ois.readObject();  // 恶意 payload 可触发 RCE''',
        "fix_sample": '''// 安全写法：校验类型 + 白名单 + 避免反序列化不可信输入
// 首选：不要反序列化不可信数据；改用 JSON + schema 校验
// 必须反序列化时，用 ObjectInputFilter 限制允许的类
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
    "com.example.*;java.lang.*;!*");
ois.setObjectInputFilter(filter);''',
        "detect_points": [
            "追踪用户输入流入 ObjectInputStream.readObject / pickle.loads / unserialize 等反序列化 sink",
            "识别缺失类型白名单过滤的反序列化",
            "跨语言覆盖 Java/Python/PHP/Ruby 的反序列化模式",
        ],
        "related": ["代码执行", "命令注入", "SSRF"],
    },

    # ── 静态类（字面量/配置检测）──
    "hardcoded-secret": {
        "title": "硬编码密钥检测（Hardcoded Secret）—— 原理与自动化检测",
        "vuln_name": "硬编码密钥",
        "vuln_name_en": "Hardcoded Secret",
        "cwe": "CWE-798",
        "owasp": "OWASP Top 10 A07:2021",
        "severity": "高危",
        "summary": "当密码、API 密钥、数据库口令等敏感凭证被直接写死在源码中时，一旦代码泄露（开源、Git 历史、误传）凭证即暴露，且难以轮换。",
        "harm": [
            "凭证随代码泄露（Git 历史、开源仓库、代码分享）",
            "硬编码凭证难以轮换，泄露后长期有效",
            "数据库、云服务、第三方 API 被直接接管",
        ],
        "code_sample_lang": "Python",
        "code_sample": '''# 危险写法：密钥写死在源码
API_KEY = "sk-xxxxxxxxxxxxxxxxxxxxxxxx"
DB_PASSWORD = "P@ssw0rd123"
conn = psycopg2.connect(password=DB_PASSWORD)''',
        "fix_sample": '''# 安全写法：从环境变量/密钥管理服务读取
import os
API_KEY = os.environ["API_KEY"]
DB_PASSWORD = os.environ["DB_PASSWORD"]
# 密钥注入运行时环境，绝不进入源码或 Git''',
        "detect_points": [
            "识别源码中写死的密码、API Key、Token、数据库口令",
            "区分真实密钥与占位符/示例值",
            "覆盖常见密钥命名模式（key/secret/password/token）",
        ],
        "related": ["弱加密算法", "不安全随机数", "不安全的 Cookie"],
    },

    "weak-crypto": {
        "title": "弱加密算法检测（Weak Cryptography）—— 原理与自动化检测",
        "vuln_name": "弱加密算法",
        "vuln_name_en": "Weak Cryptography",
        "cwe": "CWE-327",
        "owasp": "OWASP Top 10 A02:2021",
        "severity": "中高危",
        "summary": "使用 MD5、SHA1、DES、ECB 模式等已被证明不安全的加密算法或模式，攻击者可利用碰撞、暴力破解等手段破解密文，导致机密泄露。",
        "harm": [
            "MD5/SHA1 存在碰撞攻击，无法保证完整性",
            "DES 密钥空间过小，可暴力破解",
            "ECB 模式暴露数据块模式，可被结构化攻击",
        ],
        "code_sample_lang": "Java",
        "code_sample": '''// 危险写法：弱哈希 + 弱加密
String hash = md5(password);  // MD5 已被碰撞攻击
Cipher c = Cipher.getInstance("DES");  // DES 可暴力破解
Cipher ecb = Cipher.getInstance("AES/ECB/PKCS5Padding");  // ECB 不安全''',
        "fix_sample": '''// 安全写法：强哈希 + 现代加密
// 密码哈希用 bcrypt/argon2（带盐）
// 对称加密用 AES-256-GCM（带认证加密）
Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
// 哈希用 SHA-256 或更优的 bcrypt''',
        "detect_points": [
            "识别 MD5/SHA1/DES/3DES/ECB 等弱算法调用",
            "区分「弱算法用于安全场景」与「非安全用途」",
            "覆盖 Java/Python/Go/JS 等语言的弱算法模式",
        ],
        "related": ["硬编码密钥", "不安全随机数", "弱哈希"],
    },

    "weak-random": {
        "title": "不安全随机数检测（Insecure Randomness）—— 原理与自动化检测",
        "vuln_name": "不安全随机数",
        "vuln_name_en": "Insecure Randomness",
        "cwe": "CWE-330",
        "owasp": "OWASP Top 10 A02:2021",
        "severity": "中危",
        "summary": "使用可预测的伪随机数生成器（如 java.util.Random、Python random 模块）来生成安全相关的 token、密码、会话 ID，攻击者可预测其值。",
        "harm": [
            "会话 ID、重置 token 可被预测",
            "密钥、盐值可被复现",
            "导致认证绕过或数据泄露",
        ],
        "code_sample_lang": "Java",
        "code_sample": '''// 危险写法：用可预测的 Random 生成安全 token
Random r = new Random();  // 种子可预测
String token = Long.toString(r.nextLong());  // 可被预测''',
        "fix_sample": '''// 安全写法：密码学安全的随机源
SecureRandom sr = new SecureRandom();
byte[] bytes = new byte[32];
sr.nextBytes(bytes);  // 真随机源，无法预测''',
        "detect_points": [
            "识别 java.util.Random / Python random 等可预测随机源用于安全场景",
            "区分「随机数用于安全」与「用于游戏/模拟」",
            "识别应使用 SecureRandom / secrets 却用了弱随机源的场景",
        ],
        "related": ["弱加密算法", "硬编码密钥", "弱哈希"],
    },

    "weak-hash": {
        "title": "弱哈希算法检测（Weak Hash）—— 原理与自动化检测",
        "vuln_name": "弱哈希算法",
        "vuln_name_en": "Weak Hash",
        "cwe": "CWE-328",
        "owasp": "OWASP Top 10 A02:2021",
        "severity": "中高危",
        "summary": "使用 MD5、SHA1 等已破解的哈希算法做密码存储或完整性校验，攻击者可通过彩虹表、碰撞攻击破解。密码存储应使用带盐的慢哈希。",
        "harm": [
            "密码可被彩虹表/碰撞攻击破解",
            "完整性校验可被绕过",
            "哈希值泄露后明文可恢复",
        ],
        "code_sample_lang": "Python",
        "code_sample": '''# 危险写法：弱哈希存储密码
import hashlib
stored = hashlib.md5(password.encode()).hexdigest()  # MD5 可碰撞、可彩虹表破解''',
        "fix_sample": '''# 安全写法：bcrypt 慢哈希（带盐）
import bcrypt
stored = bcrypt.hashpw(password.encode(), bcrypt.gensalt())  # 慢哈希 + 随机盐''',
        "detect_points": [
            "识别 MD5/SHA1 用于密码存储或完整性校验",
            "区分「弱哈希」与「非安全用途的快速哈希」",
            "识别应使用 bcrypt/argon2/scrypt 的场景",
        ],
        "related": ["弱加密算法", "硬编码密钥", "不安全随机数"],
    },

    "insecure-cookie": {
        "title": "不安全的 Cookie 配置检测（Insecure Cookie）—— 原理与自动化检测",
        "vuln_name": "不安全的 Cookie",
        "vuln_name_en": "Insecure Cookie",
        "cwe": "CWE-614",
        "owasp": "OWASP Top 10 A07:2021",
        "severity": "中危",
        "summary": "Cookie 未设置 Secure、HttpOnly、SameSite 等安全属性时，会话凭证可能被中间人窃取、被 XSS 读取、或被 CSRF 利用。",
        "harm": [
            "HttpOnly 缺失 → 会话 Cookie 可被 XSS 窃取",
            "Secure 缺失 → 明文传输，可被中间人截获",
            "SameSite 缺失 → 可被 CSRF 攻击利用",
        ],
        "code_sample_lang": "Java",
        "code_sample": '''// 危险写法：Cookie 缺安全属性
Cookie c = new Cookie("session", sessionId);
response.addCookie(c);  // 未设 HttpOnly/Secure/SameSite''',
        "fix_sample": '''// 安全写法：设置安全属性
Cookie c = new Cookie("session", sessionId);
c.setHttpOnly(true);   // 禁止 JS 读取
c.setSecure(true);     // 仅 HTTPS 传输
c.setAttribute("SameSite", "Lax");  // 防 CSRF
response.addCookie(c);''',
        "detect_points": [
            "识别创建 Cookie 但未设置 HttpOnly/Secure/SameSite",
            "区分「会话 Cookie」与「非敏感 Cookie」",
            "覆盖 Java/Python/Node 等 Cookie 设置模式",
        ],
        "related": ["XSS", "硬编码密钥", "会话固定"],
    },

    "ldap-injection": {
        "title": "LDAP 注入检测（LDAP Injection）—— 原理、示例与自动化检测",
        "vuln_name": "LDAP 注入",
        "vuln_name_en": "LDAP Injection",
        "cwe": "CWE-90",
        "owasp": "OWASP Top 10 A03:2021",
        "severity": "高危",
        "summary": "当应用把用户输入未经过滤地拼进 LDAP 查询过滤器时，攻击者可注入 LDAP 元字符（*、()、&、| 等）篡改查询逻辑，绕过认证或读取未授权目录数据。",
        "harm": [
            "绕过登录认证（构造恒真的 LDAP 过滤器）",
            "读取、篡改目录服务器中的敏感信息",
            "横向扩展权限，访问未授权的目录节点",
        ],
        "code_sample_lang": "Java",
        "code_sample": '''// 危险写法：用户输入直接拼进 LDAP 过滤器
String user = request.getParameter("username");
String filter = "(&(uid=" + user + ")(objectClass=person))";
DirContext ctx = new InitialDirContext(env);
ctx.search("ou=users,dc=example,dc=com", filter, null);
// 输入 "*)(uid=*))(|(uid=*" 可绕过认证''',
        "fix_sample": '''// 安全写法：转义 LDAP 特殊字符后再拼过滤器
String user = request.getParameter("username");
user = user.replace("\\\\", "\\\\5c").replace("*", "\\\\2a")
           .replace("(", "\\\\28").replace(")", "\\\\29");
String filter = "(&(uid=" + user + ")(objectClass=person))";''',
        "detect_points": [
            "追踪 request 输入流入 DirContext.search / LDAP query 的过滤器参数",
            "识别字符串拼接的过滤器（非参数化/转义）",
            "识别 LDAP 元字符（* ( ) & | !）未转义即拼入过滤器",
        ],
        "related": ["SQL 注入", "XPath 注入", "命令注入"],
    },

    "xpath-injection": {
        "title": "XPath 注入检测（XPath Injection）—— 原理、示例与自动化检测",
        "vuln_name": "XPath 注入",
        "vuln_name_en": "XPath Injection",
        "cwe": "CWE-643",
        "owasp": "OWASP Top 10 A03:2021",
        "severity": "高危",
        "summary": "当应用把用户输入拼进 XPath 查询表达式时，攻击者可注入 XPath 逻辑（or、and、位置谓词等）篡改查询，读取 XML 文档中的任意数据或绕过权限控制。",
        "harm": [
            "读取 XML 文档中的全部数据（XPath 无参数化机制，危害比 SQL 注入更大）",
            "绕过基于 XML 的认证与授权",
            "枚举 XML 结构，窃取敏感配置",
        ],
        "code_sample_lang": "Java",
        "code_sample": '''// 危险写法：用户输入拼进 XPath 表达式
String user = request.getParameter("username");
String expr = "//users/user[username/text()='" + user + "']";
XPath xpath = XPathFactory.newInstance().newXPath();
xpath.evaluate(expr, doc);
// 输入 "x' or '1'='1" 可绕过查询条件''',
        "fix_sample": '''// 安全写法：白名单校验输入 + 参数化（XPath 无原生参数化，用变量绑定）
String user = request.getParameter("username");
if (!user.matches("[a-zA-Z0-9_]{1,32}")) {
    throw new IllegalArgumentException("非法用户名");
}
String expr = "//users/user[username/text()='" + user + "']";''',
        "detect_points": [
            "追踪 request 输入流入 XPath.evaluate / XPathExpression 的表达式参数",
            "识别字符串拼接的 XPath（未白名单/转义）",
            "识别 or/and/位置谓词注入特征",
        ],
        "related": ["SQL 注入", "LDAP 注入", "XXE"],
    },

    "trust-boundary": {
        "title": "信任边界违背检测（Trust Boundary Violation）—— 原理与自动化检测",
        "vuln_name": "信任边界违背",
        "vuln_name_en": "Trust Boundary Violation",
        "cwe": "CWE-501",
        "owasp": "OWASP Top 10（扩展类）",
        "severity": "中高危",
        "summary": "当不可信数据（用户输入）未经校验直接写入可信存储（会话、Cookie、全局变量）时，就发生了信任边界违背——攻击者可以污染后续依赖该数据的业务逻辑。",
        "harm": [
            "污染会话/全局状态，后续逻辑误信攻击者数据",
            "绕过基于会话/全局变量的访问控制",
            "造成二次注入或越权操作",
        ],
        "code_sample_lang": "Java",
        "code_sample": '''// 危险写法：用户输入直接写入会话（信任域）
String userId = request.getParameter("userId");
request.getSession().setAttribute("userId", userId);
// 后续代码信任 session 里的 userId 做鉴权，即被污染''',
        "fix_sample": '''// 安全写法：写入前校验 + 规范化
String userId = request.getParameter("userId");
if (userId == null || !userId.matches("[0-9]{1,16}")) {
    throw new IllegalArgumentException("非法 userId");
}
request.getSession().setAttribute("userId", userId);''',
        "detect_points": [
            "追踪不可信输入流入 HttpSession.setAttribute / putValue 等可信域写入点",
            "识别「键名注入」（写入的 key 本身不可信）与「值注入」两形态",
            "跨文件方法透传下的污点追踪（接口→实现→调用链）",
        ],
        "related": ["SQL 注入", "不安全反序列化", "越权访问"],
    },
    # ── 2026-11-09 扩容（14 → 30），覆盖更贴近业务的类型 ──
    "idor": {
        "title": "越权访问检测（IDOR）—— 原理、示例与自动化检测",
        "vuln_name": "越权访问",
        "vuln_name_en": "Insecure Direct Object Reference (IDOR)",
        "cwe": "CWE-639",
        "owasp": "OWASP Top 10 A01:2021 失效的访问控制",
        "severity": "高危",
        "summary": "接口拿到了资源 ID 就直接查库返回，却没验证这个资源是不是属于当前登录用户。攻击者把 URL 里的 id 从自己的改成别人的，就能读到、改到别人的数据——这类问题在 AI 生成的代码里尤其常见。",
        "harm": [
            "读走他人的订单、地址、账单、身份证等敏感数据",
            "以他人身份修改或删除数据，形成业务事故",
            "批量遍历 ID 即可拖库，无需任何漏洞利用工具",
        ],
        "code_sample_lang": "Python",
        "code_sample": '''# 危险写法：只按 id 查，不问「这条数据是谁的」
@app.get("/api/orders/{order_id}")
def get_order(order_id: int, user=Depends(current_user)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404)
    return order          # 换个 order_id 就是别人的订单''',
        "fix_sample": '''# 安全写法：把当前身份拼进查询条件
@app.get("/api/orders/{order_id}")
def get_order(order_id: int, user=Depends(current_user)):
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.user_id == user.id,      # 身份与资源必须对上
    ).first()
    if not order:
        raise HTTPException(404)       # 不区分「不存在」和「不是你的」
    return order''',
        "detect_points": [
            "接口参数里有资源 ID，但查询条件里没有出现当前登录身份",
            "查询条件用的是 request 里传进来的 user_id / tenant_id，而不是会话里的身份",
            "列表接口只做了分页，没做归属过滤，遍历即可拿到全量数据",
        ],
        "related": [
            "SQL 注入",
            "信任边界违背",
            "批量赋值",
        ],
    },
    "csrf": {
        "title": "CSRF 跨站请求伪造检测 —— 原理、示例与自动化检测",
        "vuln_name": "CSRF 跨站请求伪造",
        "vuln_name_en": "Cross-Site Request Forgery",
        "cwe": "CWE-352",
        "owasp": "OWASP Top 10 A01:2021 失效的访问控制",
        "severity": "中高危",
        "summary": "浏览器会自动带上 Cookie，于是攻击者只要在别的站点放一个隐藏表单或一张图片，就能以受害者的身份向我们发起写操作。关键在于服务端的写接口有没有校验「这个请求是不是我们自己的页面发出来的」。",
        "harm": [
            "以受害者身份转账、改密码、删数据",
            "篡改账号绑定的手机号或邮箱，为下一步接管账号铺路",
            "用户无需点击任何可疑链接，只要打开攻击者页面就可能中招",
        ],
        "code_sample_lang": "Java",
        "code_sample": '''// 危险写法：写接口只认 Cookie，不校验请求来源
@PostMapping("/api/password/change")
public Result changePassword(@RequestParam String newPwd,
                             HttpSession session) {
    Long uid = (Long) session.getAttribute("uid");   // 只靠 Cookie 里的会话
    userService.updatePassword(uid, newPwd);
    return Result.ok();      // 任意站点构造表单即可替用户改密码
}''',
        "fix_sample": '''// 安全写法一：校验 CSRF Token
@PostMapping("/api/password/change")
public Result changePassword(@RequestParam String newPwd,
                             @RequestParam String csrfToken,
                             HttpSession session) {
    if (!csrfToken.equals(session.getAttribute("csrfToken"))) {
        throw new ForbiddenException("非法请求");
    }
    Long uid = (Long) session.getAttribute("uid");
    userService.updatePassword(uid, newPwd);
    return Result.ok();
}
// 安全写法二：会话 Cookie 设 SameSite=Lax/Strict（需配合校验来源）''',
        "detect_points": [
            "写操作的 POST/PUT/DELETE 接口里，没有任何 CSRF Token 或来源校验",
            "双重提交 Cookie、SameSite 属性是否真的配了（不是只在注释里写）",
            "把 GET 当成写操作（GET 改数据天然无法防 CSRF）",
        ],
        "related": [
            "越权访问",
            "不安全 Cookie 配置",
            "信任边界违背",
        ],
    },
    "xxe": {
        "title": "XXE 外部实体注入检测 —— 原理、示例与自动化检测",
        "vuln_name": "XXE 外部实体注入",
        "vuln_name_en": "XML External Entity",
        "cwe": "CWE-611",
        "owasp": "OWASP Top 10 A05:2021 安全配置错误",
        "severity": "高危",
        "summary": "XML 解析器默认允许引用外部实体。攻击者在 XML 里声明一个指向本地文件或内网地址的实体，解析器就会替他读取服务器上的文件，或者向内部服务发起请求。",
        "harm": [
            "读取服务器任意文件（/etc/passwd、配置文件、密钥）",
            "以内网身份发起请求，穿透防火墙探测内网服务",
            "配合 expect 等协议可进一步执行命令（部分环境）",
        ],
        "code_sample_lang": "Java",
        "code_sample": '''// 危险写法：默认配置的解析器允许外部实体
DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
DocumentBuilder db = dbf.newDocumentBuilder();
Document doc = db.parse(request.getInputStream());
// 攻击者提交 <!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]>
// 并在字段里写 &e; 即可读到文件内容''',
        "fix_sample": '''// 安全写法：关掉 DTD 与外部实体
DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
dbf.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
dbf.setFeature("http://xml.org/sax/features/external-general-entities", false);
dbf.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
dbf.setXIncludeAware(false);
dbf.setExpandEntityReferences(false);
DocumentBuilder db = dbf.newDocumentBuilder();''',
        "detect_points": [
            "XML 解析器创建后没有关闭 DOCTYPE / 外部实体特性",
            "Python 用 lxml 时 resolve_entities 保持默认 True",
            "自定义 SAXReader / SAXParserFactory 未设置安全特性",
        ],
        "related": [
            "SSRF 服务端请求伪造",
            "路径遍历",
            "不安全反序列化",
        ],
    },
    "ssti": {
        "title": "模板注入（SSTI）检测 —— 原理、示例与自动化检测",
        "vuln_name": "模板注入",
        "vuln_name_en": "Server-Side Template Injection",
        "cwe": "CWE-1336",
        "owasp": "OWASP Top 10 A03:2021 注入",
        "severity": "高危",
        "summary": "把用户输入当成模板内容去渲染，而不仅仅是当成变量值。模板引擎大多支持在表达式里调对象、调方法，于是「渲染一段字符串」就变成了「执行一段代码」。",
        "harm": [
            "在服务器上执行任意代码，直接拿到主机权限",
            "读取环境变量里的密钥、数据库口令",
            "横向访问内网、植入后门",
        ],
        "code_sample_lang": "Python",
        "code_sample": '''# 危险写法：用户输入拼进模板再渲染
@app.route("/hello")
def hello():
    name = request.args.get("name", "")
    return render_template_string("你好，" + name)
    # 传 {{7*7}} 回显 49；传 {{config}} 直接吐出配置''',
        "fix_sample": '''# 安全写法：模板是常量，用户输入只作为变量
@app.route("/hello")
def hello():
    name = request.args.get("name", "")
    return render_template_string("你好，{{ name }}", name=name)
    # 模板内容永远来自代码，不来自请求''',
        "detect_points": [
            "render_template_string / Template().render / eval 类渲染函数收到非字面量参数",
            "模板文件路径由用户输入拼接（模板路径穿越）",
            "前端组件里把用户输入当模板编译（Vue compile / Angular $compile）",
        ],
        "related": [
            "XSS 跨站脚本",
            "命令注入",
            "SQL 注入",
        ],
    },
    "nosql-injection": {
        "title": "NoSQL 注入检测 —— 原理、示例与自动化检测",
        "vuln_name": "NoSQL 注入",
        "vuln_name_en": "NoSQL Injection",
        "cwe": "CWE-943",
        "owasp": "OWASP Top 10 A03:2021 注入",
        "severity": "高危",
        "summary": "MongoDB 这类数据库的查询是文档而不是字符串，所以传统 SQL 注入的防护手段不适用。只要把请求里的 JSON 对象原样丢进查询条件，攻击者就能用 $ne、$gt、$regex 这类操作符绕过登录校验。",
        "harm": [
            "用 $ne 运算符绕过账号密码校验，直接登录任意账户",
            "用 $regex 逐位爆破口令与 token",
            "拖走整张集合的数据",
        ],
        "code_sample_lang": "JavaScript",
        "code_sample": '''// 危险写法：整个请求体丢进查询条件
app.post('/login', async (req, res) => {
  const user = await db.collection('users').findOne({
    username: req.body.username,
    password: req.body.password,
  });
  // 提交 {"username":"admin","password":{"$ne":null}} 即可登录成功
});''',
        "fix_sample": '''// 安全写法：白名单取值 + 强制类型
app.post('/login', async (req, res) => {
  const username = String(req.body.username || '');
  const password = String(req.body.password || '');
  if (!username || !password) return res.status(400).end();
  const user = await db.collection('users').findOne({ username });
  const ok = user && await bcrypt.compare(password, user.pwdHash);
  if (!ok) return res.status(401).end();
});''',
        "detect_points": [
            "req.body / req.query 整体作为查询文档传入 find / findOne / update",
            "没有把参数强制转成字符串，对象型参数可以带操作符",
            "MongoDB 查询里拼 $where 字符串（等价于服务端执行 JS）",
        ],
        "related": [
            "SQL 注入",
            "认证绕过",
            "批量赋值",
        ],
    },
    "jwt-misuse": {
        "title": "JWT 使用不当检测 —— 原理、示例与自动化检测",
        "vuln_name": "JWT 使用不当",
        "vuln_name_en": "JWT Misuse",
        "cwe": "CWE-347",
        "owasp": "OWASP Top 10 A02:2021 加密机制失效",
        "severity": "高危",
        "summary": "JWT 的安全性全在签名校验上。常见错误有三种：不验签只解码、接受 alg=none、把密钥写死在代码里。任一种都等于让人自己签发身份。",
        "harm": [
            "伪造任意用户身份的 token，直接接管账号",
            "把普通用户改成管理员，越权到后台",
            "密钥泄露后，已发出的所有 token 全部失效需重签",
        ],
        "code_sample_lang": "JavaScript",
        "code_sample": '''// 危险写法：只解码不验签
const payload = jwt.decode(token);      // 没传密钥，等于没校验
if (payload.role === 'admin') { ... }
// 攻击者自己造一个 {"role":"admin"} 的 token 即可

// 危险写法二：不限制算法
jwt.verify(token, secret, { algorithms: ['none', 'HS256'] });''',
        "fix_sample": '''// 安全写法：固定算法 + 必须验签 + 校验关键字段
const payload = jwt.verify(token, process.env.JWT_SECRET, {
  algorithms: ['HS256'],       // 白名单，禁止 none
  issuer: 'xinpect',
  maxAge: '2h',
});
if (payload.role !== 'admin') throw new Error('forbidden');''',
        "detect_points": [
            "调用 jwt.decode 后直接用 payload 做鉴权判断",
            "verify 未指定 algorithms，或白名单里含 none",
            "签名密钥硬编码在源码里，或从不可信 header 取",
        ],
        "related": [
            "硬编码密钥",
            "认证绕过",
            "弱加密算法",
        ],
    },
    "cors-misconfiguration": {
        "title": "CORS 配置错误检测 —— 原理、示例与自动化检测",
        "vuln_name": "CORS 配置错误",
        "vuln_name_en": "CORS Misconfiguration",
        "cwe": "CWE-942",
        "owasp": "OWASP Top 10 A05:2021 安全配置错误",
        "severity": "中高危",
        "summary": "为了让前端能跨域调接口，服务端要回 Access-Control-Allow-Origin。一旦这个值直接回显请求的 Origin，再配上 Allow-Credentials: true，任何网站都能带着用户的 Cookie 读我们的接口，跨域隔离就失效了。",
        "harm": [
            "任意站点读取登录用户的私有数据",
            "配合 CSRF 形成完整攻击链：读 + 写",
            "把内网管理接口暴露给外部页面调用",
        ],
        "code_sample_lang": "Python",
        "code_sample": '''# 危险写法：Origin 原样回显 + 允许携带凭据
@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = request.headers.get("Origin")
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    return resp''',
        "fix_sample": '''# 安全写法：白名单比对，不命中就不回 CORS 头
ALLOWED = {"https://xinpect.xingwangzhineng.com"}

@app.after_request
def add_cors(resp):
    origin = request.headers.get("Origin")
    if origin in ALLOWED:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        resp.headers["Vary"] = "Origin"
    return resp''',
        "detect_points": [
            "Allow-Origin 取值来自请求头，或写死为 * 且同时允许凭据",
            "用 startswith / endswith 匹配域名（evil-xinpect.com 也能过）",
            "预检响应里放开了 Allow-Headers 与 Allow-Methods 但没做来源校验",
        ],
        "related": [
            "CSRF 跨站请求伪造",
            "不安全 Cookie 配置",
            "越权访问",
        ],
    },
    "open-redirect": {
        "title": "开放重定向检测 —— 原理、示例与自动化检测",
        "vuln_name": "开放重定向",
        "vuln_name_en": "Open Redirect",
        "cwe": "CWE-601",
        "owasp": "OWASP Top 10（扩展类）",
        "severity": "中危",
        "summary": "登录成功、支付完成这类场景常带一个 next / redirect 参数。如果跳转地址直接取自参数且不做域名校验，攻击者就能构造一条指向自己站点的「官方链接」，用来钓鱼或窃取 token。",
        "harm": [
            "钓鱼：链接域名是我们，落地页是攻击者的仿冒登录页",
            "绕过邮件与风控的白名单校验，把用户导向恶意站点",
            "配合 OAuth 流程可窃取授权码",
        ],
        "code_sample_lang": "Go",
        "code_sample": '''// 危险写法：跳转地址直接取参数
func afterLogin(w http.ResponseWriter, r *http.Request) {
    next := r.URL.Query().Get("next")
    http.Redirect(w, r, next, http.StatusFound)
    // ?next=https://evil.example/login 即被带走
}''',
        "fix_sample": '''// 安全写法：只允许站内相对路径
func afterLogin(w http.ResponseWriter, r *http.Request) {
    next := r.URL.Query().Get("next")
    if !strings.HasPrefix(next, "/") || strings.HasPrefix(next, "//") {
        next = "/dashboard"
    }
    http.Redirect(w, r, next, http.StatusFound)
}''',
        "detect_points": [
            "重定向目标来自请求参数，且没有域名白名单或站内路径校验",
            "用 Contains / HasPrefix(\"http\") 判断，可被 //evil.com、@ 绕过",
            "OAuth 回调 redirect_uri 未做精确匹配",
        ],
        "related": [
            "JWT 使用不当",
            "认证绕过",
            "XSS 跨站脚本",
        ],
    },
    "insecure-file-upload": {
        "title": "不安全文件上传检测 —— 原理、示例与自动化检测",
        "vuln_name": "不安全文件上传",
        "vuln_name_en": "Unrestricted File Upload",
        "cwe": "CWE-434",
        "owasp": "OWASP Top 10（扩展类）",
        "severity": "高危",
        "summary": "上传接口只看扩展名、或者干脆什么都不看，把文件原样落到 Web 可访问目录，就等于给了攻击者一个写文件并执行的机会。",
        "harm": [
            "上传 webshell，直接在服务器上执行任意代码",
            "上传超大文件撑爆磁盘，或上传恶意文件做水坑攻击",
            "覆盖已有配置文件，篡改站点行为",
        ],
        "code_sample_lang": "PHP",
        "code_sample": '''<?php
// 危险写法：只信客户端给的文件名和类型
$name = $_FILES['f']['name'];
move_uploaded_file($_FILES['f']['tmp_name'], "uploads/" . $name);
// 上传 shell.php，或 shell.php.jpg 配合解析漏洞即可执行''',
        "fix_sample": '''<?php
// 安全写法：白名单后缀 + 服务端重命名 + 落盘到非可执行目录
$allow = ['jpg' => 'image/jpeg', 'png' => 'image/png', 'pdf' => 'application/pdf'];
$ext = strtolower(pathinfo($_FILES['f']['name'], PATHINFO_EXTENSION));
if (!isset($allow[$ext])) { exit('不支持的格式'); }
if (mime_content_type($_FILES['f']['tmp_name']) !== $allow[$ext]) { exit('类型不符'); }
$dest = '/data/uploads/' . bin2hex(random_bytes(16)) . '.' . $ext;
move_uploaded_file($_FILES['f']['tmp_name'], $dest);''',
        "detect_points": [
            "上传后缀取自文件名且无白名单",
            "落盘路径可由用户控制（含 ../ 拼接）",
            "上传目录位于 Web 根目录且可执行脚本",
        ],
        "related": [
            "路径遍历",
            "命令注入",
            "XSS 跨站脚本",
        ],
    },
    "mass-assignment": {
        "title": "批量赋值检测 —— 原理、示例与自动化检测",
        "vuln_name": "批量赋值",
        "vuln_name_en": "Mass Assignment",
        "cwe": "CWE-915",
        "owasp": "OWASP Top 10（扩展类）",
        "severity": "中高危",
        "summary": "把请求体整体绑定到数据库实体上，框架会把请求里出现的每一个字段都写进去——包括 role、is_admin、balance 这些本该由服务端控制的字段。",
        "harm": [
            "注册时把自己写成管理员",
            "直接改余额、改价格、改审核状态",
            "越权修改他人资源的归属字段",
        ],
        "code_sample_lang": "Java",
        "code_sample": '''// 危险写法：请求体直接绑定实体
@PostMapping("/api/user/update")
public Result update(@RequestBody User user) {
    userRepository.save(user);   // 请求里带 "role":"ADMIN" 就改成了管理员
    return Result.ok();
}''',
        "fix_sample": '''// 安全写法：用 DTO 只接收允许修改的字段
public class UserUpdateDTO {
    public String nickname;
    public String avatar;
}

@PostMapping("/api/user/update")
public Result update(@RequestBody UserUpdateDTO dto, HttpSession session) {
    Long uid = (Long) session.getAttribute("uid");
    User u = userRepository.findById(uid).orElseThrow();
    u.setNickname(dto.nickname);   // 只覆盖白名单字段
    u.setAvatar(dto.avatar);
    userRepository.save(u);
    return Result.ok();
}''',
        "detect_points": [
            "Controller 直接接收实体或 Map 作为请求体并保存",
            "框架层关闭了字段过滤（如 Django exclude 缺失、Rails permit! ）",
            "敏感字段（role、status、balance、owner_id）在可写字段清单里",
        ],
        "related": [
            "越权访问",
            "NoSQL 注入",
            "认证绕过",
        ],
    },
    "prototype-pollution": {
        "title": "原型链污染检测 —— 原理、示例与自动化检测",
        "vuln_name": "原型链污染",
        "vuln_name_en": "Prototype Pollution",
        "cwe": "CWE-1321",
        "owasp": "OWASP Top 10（扩展类）",
        "severity": "中高危",
        "summary": "JavaScript 的对象都继承自原型。如果合并、赋值类函数允许 key 是 __proto__、constructor、prototype，攻击者就能改写全局原型的属性，影响所有对象——包括鉴权判断里用到的字段。",
        "harm": [
            "改写全局对象属性，绕过权限判断",
            "触发依赖库里的危险分支，最终演变成 RCE",
            "造成服务崩溃（拒绝服务）",
        ],
        "code_sample_lang": "JavaScript",
        "code_sample": '''// 危险写法：递归合并不过滤原型键
function merge(target, src) {
  for (const k in src) {
    if (typeof src[k] === 'object') {
      target[k] = target[k] || {};
      merge(target[k], src[k]);
    } else {
      target[k] = src[k];
    }
  }
  return target;
}
merge({}, JSON.parse('{"__proto__":{"isAdmin":true}}'));
// 之后任意对象的 isAdmin 都是 true''',
        "fix_sample": '''// 安全写法：跳过原型相关键 + 用无原型对象
function merge(target, src) {
  for (const k of Object.keys(src)) {
    if (k === '__proto__' || k === 'constructor' || k === 'prototype') continue;
    if (src[k] && typeof src[k] === 'object' && !Array.isArray(src[k])) {
      target[k] = target[k] || Object.create(null);
      merge(target[k], src[k]);
    } else if (!Array.isArray(src[k])) {
      target[k] = src[k];
    }
  }
  return target;
}''',
        "detect_points": [
            "自定义 merge / clone / extend 递归赋值未过滤 __proto__ 与 constructor",
            "用 req.body 直接做 Object.assign 的目标或来源",
            "JSON 反序列化后直接参与对象合并",
        ],
        "related": [
            "NoSQL 注入",
            "认证绕过",
            "XSS 跨站脚本",
        ],
    },
    "regex-dos": {
        "title": "正则拒绝服务（ReDoS）检测 —— 原理、示例与自动化检测",
        "vuln_name": "正则拒绝服务",
        "vuln_name_en": "Regular Expression Denial of Service",
        "cwe": "CWE-1333",
        "owasp": "OWASP Top 10（扩展类）",
        "severity": "中危",
        "summary": "嵌套量词这类正则的回溯次数随输入长度指数增长。一条几十字节的恶意输入就能让一次匹配跑几分钟，把线程池占满，接口整体不可用。",
        "harm": [
            "单次请求即可打挂一个工作线程，几十个请求打挂整个服务",
            "CPU 打满，同机其他服务被拖死",
            "输入只在校验阶段用了一次，排查时极难定位",
        ],
        "code_sample_lang": "Java",
        "code_sample": '''// 危险写法：嵌套量词 + 无长度上限
private static final Pattern EMAIL =
    Pattern.compile("^([a-zA-Z0-9]+)*@[a-zA-Z0-9]+\\.[a-zA-Z]{2,}$");

public boolean check(String input) {
    return EMAIL.matcher(input).matches();
}''',
        "fix_sample": '''// 安全写法：先限长，再用无嵌套回溯的表达式
private static final Pattern EMAIL =
    Pattern.compile("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$");

public boolean check(String input) {
    if (input == null || input.length() > 254) return false;
    return EMAIL.matcher(input).matches();
}''',
        "detect_points": [
            "正则里出现 (a+)*、(.*)* 、(a|a)* 这类嵌套或重叠量词",
            "校验函数未先做长度上限",
            "正则编译在请求处理路径上且模式来自配置/用户",
        ],
        "related": [
            "日志注入",
            "命令注入",
            "路径遍历",
        ],
    },
    "log-injection": {
        "title": "日志注入检测 —— 原理、示例与自动化检测",
        "vuln_name": "日志注入",
        "vuln_name_en": "Log Injection / Log Forging",
        "cwe": "CWE-117",
        "owasp": "OWASP Top 10（扩展类）",
        "severity": "中危",
        "summary": "把用户输入原样写进日志，而日志里又有换行。攻击者插入换行就能伪造出一条看起来完全正常的日志记录，误导排障、污染审计证据。",
        "harm": [
            "伪造日志，掩盖自己的攻击痕迹",
            "往日志里塞假告警，消耗运维注意力",
            "日志被下游解析器读取时可能触发二次注入",
        ],
        "code_sample_lang": "Python",
        "code_sample": '''# 危险写法：用户输入直接进日志
username = request.form.get("username")
logger.info("login failed: %s" % username)
# 传入 "admin\n2026-11-09 INFO login success: admin"
# 就凭空多出一条成功登录记录''',
        "fix_sample": '''# 安全写法：剥离换行与控制字符后再记录
import re
username = request.form.get("username", "")
safe = re.sub(r"[\r\n\t\x00-\x1f]", "_", username)[:128]
logger.info("login failed: %s", safe)''',
        "detect_points": [
            "日志拼接里出现未经处理的请求参数（含 logger.info(\"...\" + x)）",
            "使用 % 或 f-string 拼接而不是参数化占位符",
            "日志字段长度没有上限",
        ],
        "related": [
            "敏感信息写入日志",
            "正则拒绝服务",
            "XSS 跨站脚本",
        ],
    },
    "log-sensitive-data": {
        "title": "敏感信息写入日志检测 —— 原理、示例与自动化检测",
        "vuln_name": "敏感信息写入日志",
        "vuln_name_en": "Sensitive Data Exposure in Logs",
        "cwe": "CWE-532",
        "owasp": "OWASP Top 10 A09:2021 日志与监控失效",
        "severity": "中高危",
        "summary": "调试时顺手把整个请求体、整个响应体打进日志，里面可能带着口令、身份证、token、支付信息。日志的访问权限通常比数据库松得多，等于把敏感数据挪到了更不安全的地方。",
        "harm": [
            "口令与 token 明文落盘，内鬼或日志系统被拖即泄露",
            "个人信息违规留存，触碰个人信息保护法",
            "日志被第三方采集/外发时数据出境失控",
        ],
        "code_sample_lang": "Python",
        "code_sample": '''# 危险写法：整个请求体与响应体入日志
logger.info("req body: %s", await request.body())
logger.info("resp: %s", json.dumps(resp_payload))
# body 里有 password / idCard / access_token 时全部明文留存''',
        "fix_sample": '''# 安全写法：白名单字段 + 脱敏
SENSITIVE = ("password", "pwd", "token", "secret", "idCard", "phone", "bank")

def scrub(d):
    if isinstance(d, dict):
        return {k: ("***" if k.lower() in SENSITIVE else scrub(v))
                for k, v in d.items()}
    if isinstance(d, list):
        return [scrub(i) for i in d]
    return d

logger.info("req body: %s", scrub(payload))''',
        "detect_points": [
            "日志语句里出现 password / token / idCard / 完整请求体等字段",
            "异常处理把整个请求对象 repr 进日志",
            "日志级别在线上仍是 DEBUG 且打印出入参",
        ],
        "related": [
            "硬编码密钥",
            "日志注入",
            "不安全 Cookie 配置",
        ],
    },
    "insecure-tls": {
        "title": "TLS 配置不当检测 —— 原理、示例与自动化检测",
        "vuln_name": "TLS 配置不当",
        "vuln_name_en": "Improper Certificate Validation / Insecure TLS",
        "cwe": "CWE-295",
        "owasp": "OWASP Top 10 A02:2021 加密机制失效",
        "severity": "中高危",
        "summary": "为了「让请求先跑通」，把证书校验关掉、信任所有证书，或者用 http 明文传数据。看起来只是开发期妥协，上线后就是中间人攻击的入口。",
        "harm": [
            "中间人可解密、篡改全部通信内容",
            "内网横向时被劫持，扩大失陷范围",
            "关闭校验的代码往往带着测试用的默认口令一起上线",
        ],
        "code_sample_lang": "Python",
        "code_sample": '''# 危险写法：关掉证书校验 / 信任一切证书
requests.get(url, verify=False)
# 或
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE''',
        "fix_sample": '''# 安全写法：默认校验 + 指定 CA / 双向认证
sess = requests.Session()
sess.verify = "/etc/ssl/certs/xinspect-ca.pem"   # 自签时指定 CA
resp = sess.get(url, timeout=10)''',
        "detect_points": [
            "verify=False / InsecureSkipVerify: true / CERT_NONE 出现在业务代码",
            "自定义 TrustManager 全部信任（X509TrustManager 空实现）",
            "配置里写死 http:// 的内部调用地址",
        ],
        "related": [
            "硬编码密钥",
            "弱加密算法",
            "JWT 使用不当",
        ],
    },
    "race-condition": {
        "title": "竞态条件检测（TOCTOU）—— 原理、示例与自动化检测",
        "vuln_name": "竞态条件",
        "vuln_name_en": "Race Condition / TOCTOU",
        "cwe": "CWE-367",
        "owasp": "OWASP Top 10（扩展类）",
        "severity": "中高危",
        "summary": "先查后写：查余额够不够、查库存还有没有、查这个优惠券用没用过——检查与写入之间有时间窗口，并发请求压进去就能同时通过检查，把「只能用一次」变成「能用很多次」。",
        "harm": [
            "优惠券、积分、余额被重复使用，直接资金损失",
            "库存被超卖，出现负库存",
            "并发下重复绑定、重复注册，污染唯一性约束",
        ],
        "code_sample_lang": "Python",
        "code_sample": '''# 危险写法：先查后改，两步之间有窗口
coupon = db.query(Coupon).filter_by(code=code).first()
if coupon.used:                    # 检查
    raise HTTPException(400, "已使用")
do_business(coupon)                # 业务
coupon.used = True                 # 写入
db.commit()
# 并发两个请求同时通过 used=False 的判断''',
        "fix_sample": '''# 安全写法：把判定压进一条原子语句
updated = db.query(Coupon).filter(
    Coupon.code == code,
    Coupon.used.is_(False),
).update({"used": True}, synchronize_session=False)
db.commit()
if updated == 0:                   # 影响行数为 0 说明没抢到
    raise HTTPException(400, "已使用")''',
        "detect_points": [
            "同一资源先 select 判断状态、再 update 的业务路径",
            "余额/库存扣减没有用原子语句或行锁（SELECT ... FOR UPDATE）",
            "文件操作 check + open 两步走（TOCTOU 文件版）",
        ],
        "related": [
            "越权访问",
            "批量赋值",
            "信任边界违背",
        ],
    },

}

# slug 别名（兼容常见搜索词的 URL 变体）
SLUG_ALIASES = {
    "insecure-direct-object-reference": "idor",
    "broken-access-control": "idor",
    "idor-java": "idor",
    "cross-site-request-forgery": "csrf",
    "csrf-token": "csrf",
    "xml-external-entity": "xxe",
    "xxe-injection": "xxe",
    "server-side-template-injection": "ssti",
    "template-injection": "ssti",
    "mongodb-injection": "nosql-injection",
    "jwt": "jwt-misuse",
    "jwt-none-algorithm": "jwt-misuse",
    "cors": "cors-misconfiguration",
    "cors-misconfig": "cors-misconfiguration",
    "unvalidated-redirect": "open-redirect",
    "arbitrary-file-upload": "insecure-file-upload",
    "unrestricted-file-upload": "insecure-file-upload",
    "prototype-pollution-js": "prototype-pollution",
    "redos": "regex-dos",
    "regular-expression-dos": "regex-dos",
    "log-forging": "log-injection",
    "sensitive-data-in-logs": "log-sensitive-data",
    "improper-certificate-validation": "insecure-tls",
    "tls-misconfiguration": "insecure-tls",
    "toctou": "race-condition",
    "time-of-check-time-of-use": "race-condition",
    "sqli": "sql-injection",
    "sql-injection-java": "sql-injection",
    "command-injection-python": "command-injection",
    "cmdi": "command-injection",
    "cross-site-scripting": "xss",
    "path-traversal-java": "path-traversal",
    "server-side-request-forgery": "ssrf",
    "deserialization": "insecure-deserialization",
    "hardcoded-credentials": "hardcoded-secret",
    "weak-cryptography": "weak-crypto",
    "insecure-random": "weak-random",
    "weak-hash-algorithm": "weak-hash",
    "insecure-cookie-configuration": "insecure-cookie",
    "ldap-injection-java": "ldap-injection",
    "xpath-injection-java": "xpath-injection",
    "trust-boundary-violation": "trust-boundary",
}


def _canonical_slug(slug: str) -> str:
    """把别名 slug 归一化到知识库主键。"""
    if slug in VULN_KB:
        return slug
    return SLUG_ALIASES.get(slug, "")


@seo_bp.route("/detect")
def detect_index():
    """漏洞检测落地页索引：列出全部漏洞类型。"""
    items = []
    for slug, data in VULN_KB.items():
        item = dict(data)
        item["slug"] = slug
        items.append(item)
    return render_template("seo_index.html", items=items)


@seo_bp.route("/detect/<slug>")
def detect_page(slug: str):
    """单个漏洞检测落地页。"""
    canonical = _canonical_slug(slug.lower())
    if not canonical:
        abort(404)
    # 别名统一 301 到规范 URL，避免重复页面稀释权重
    if canonical != slug.lower():
        return redirect(url_for("seo.detect_page", slug=canonical), code=301)
    data = VULN_KB[canonical]
    return render_template("seo_detect.html", slug=canonical, **data)


@seo_bp.route("/sitemap-vulns.xml")
def sitemap_vulns():
    """漏洞检测页的 sitemap，供搜索引擎抓取。"""
    from flask import Response
    base = "https://xinpect.xingwangzhineng.com"
    urls = ["{}/detect/{}".format(base, slug) for slug in VULN_KB]
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in urls:
        xml += "  <url><loc>{}</loc><changefreq>monthly</changefreq><priority>0.7</priority></url>\n".format(u)
    xml += "</urlset>"
    return Response(xml, mimetype="application/xml")
