#!/usr/bin/env python3
import sqlite3
from datetime import datetime

db = sqlite3.connect('/opt/xinpect-website/xinpect.db')
now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

extra = [
    # Python TP - more
    ('app/views/order.py', 'Python', 'order_id = request.args.get("id")\ndb.execute("UPDATE orders SET status=1 WHERE id=" + order_id)', 'SQL注入', 'P0', 'CWE-89', 'true_positive', 'UPDATE语句SQL注入'),
    ('app/utils/log_reader.py', 'Python', 'import os\nlog = request.args.get("log")\nreturn open("/var/log/" + log).read()', '路径遍历', 'P0', 'CWE-22', 'true_positive', '日志文件路径遍历'),
    ('app/services/notify.py', 'Python', 'import requests\ncallback = request.json["url"]\nrequests.post(callback, data=alert)', 'SSRF', 'P0', 'CWE-918', 'true_positive', '回调URL未校验可SSRF'),
    ('app/views/api_proxy.py', 'Python', 'import urllib\ntarget = request.args.get("target")\nreturn urllib.urlopen(target).read()', 'SSRF', 'P0', 'CWE-918', 'true_positive', '代理接口SSRF'),
    ('app/views/upload.py', 'Python', 'filename = request.files["file"].filename\nopen("/uploads/" + filename, "wb").write(data)', '路径遍历', 'P0', 'CWE-22', 'true_positive', '上传文件名未过滤'),
    ('app/views/config_edit.py', 'Python', '@app.route("/config/edit", methods=["POST"])\ndef edit_config():\n    save_config(request.json)\n    return jsonify(ok=True)', '越权访问', 'P1', 'CWE-862', 'true_positive', '配置修改无权限校验'),
    # JavaScript TP - more
    ('server/routes/upload.js', 'JavaScript', 'const file = req.files.file.name;\nfs.writeFileSync("/uploads/" + file, data);', '路径遍历', 'P0', 'CWE-22', 'true_positive', 'Node上传文件名未过滤'),
    ('server/routes/exec.js', 'JavaScript', 'const cmd = req.body.cmd;\nconst { exec } = require("child_process");\nexec(cmd);', '命令注入', 'P0', 'CWE-78', 'true_positive', 'Node.js命令注入'),
    ('server/routes/config.js', 'JavaScript', 'app.put("/api/config", (req, res) => {\n  updateConfig(req.body);\n  res.json({ok:true});\n});', '越权访问', 'P1', 'CWE-862', 'true_positive', '配置API无权限检查'),
    ('src/components/Comment.jsx', 'JavaScript', 'function Comment({text}) {\n  return <span dangerouslySetInnerHTML={{__html: text}} />;\n}', 'XSS', 'P0', 'CWE-79', 'true_positive', 'React dangerouslySetInnerHTML XSS'),
    ('server/routes/import.js', 'JavaScript', 'const data = req.body.data;\nconst obj = JSON.parse(eval("(" + data + ")"));', 'SQL注入', 'P0', 'CWE-89', 'true_positive', 'eval执行不可信数据'),
    # Java TP - more
    ('src/main/java/com/app/UploadController.java', 'Java', 'String name = request.getParameter("file");\nFile f = new File("/uploads/" + name);\nFileOutputStream fos = new FileOutputStream(f);', '路径遍历', 'P0', 'CWE-22', 'true_positive', 'Java上传路径遍历'),
    ('src/main/java/com/app/ImportService.java', 'Java', 'String cmd = "import " + request.getParameter("file");\nRuntime.getRuntime().exec(cmd);', '命令注入', 'P0', 'CWE-78', 'true_positive', 'Java Runtime.exec注入'),
    ('src/main/java/com/app/ProxyServlet.java', 'Java', 'String url = request.getParameter("url");\nHttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();', 'SSRF', 'P0', 'CWE-918', 'true_positive', 'Java SSRF代理'),
    ('src/main/java/com/app/SettingsController.java', 'Java', '@RequestMapping("/settings/save")\npublic void saveSettings(@RequestBody Map data) {\n  settingsService.saveAll(data);\n}', '越权访问', 'P1', 'CWE-862', 'true_positive', '设置保存无权限控制'),
    ('src/main/webapp/search.jsp', 'Java', '<input value="<%= request.getParameter("q") %>">\n<div><%= request.getParameter("content") %></div>', 'XSS', 'P0', 'CWE-79', 'true_positive', 'JSP多输出点XSS'),
    # Go TP - more
    ('internal/handler/upload.go', 'Go', 'name := r.FormValue("filename")\nhttp.ServeFile(w, r, "/data/"+name)', '路径遍历', 'P0', 'CWE-22', 'true_positive', 'Go上传路径遍历'),
    ('internal/service/task.go', 'Go', 'cmd := exec.Command("sh", "-c", "process "+input)\noutput, _ := cmd.CombinedOutput()', '命令注入', 'P0', 'CWE-78', 'true_positive', 'Go任务执行命令注入'),
    ('internal/handler/config.go', 'Go', 'func UpdateConfig(w http.ResponseWriter, r *http.Request) {\n    var cfg Config\n    json.NewDecoder(r.Body).Decode(&cfg)\n    saveConfig(cfg)\n}', '越权访问', 'P1', 'CWE-862', 'true_positive', 'Go配置更新无权限'),
    # PHP TP - more
    ('public/upload.php', 'PHP', '$file = $_FILES["file"]["name"];\nmove_uploaded_file($file, "/uploads/" . $file);', '路径遍历', 'P0', 'CWE-22', 'true_positive', 'PHP上传路径遍历'),
    ('public/exec.php', 'PHP', '$cmd = $_POST["cmd"];\npassthru("ls " . $cmd);', '命令注入', 'P0', 'CWE-78', 'true_positive', 'PHP passthru注入'),
    ('public/proxy.php', 'PHP', '$url = $_GET["url"];\n$ch = curl_init($url);\ncurl_exec($ch);', 'SSRF', 'P0', 'CWE-918', 'true_positive', 'PHP curl SSRF'),
    ('api/admin.php', 'PHP', 'if ($_POST) {\n    $pdo->exec("UPDATE settings SET value=" . $_POST["val"]);\n}', 'SQL注入', 'P0', 'CWE-89', 'true_positive', 'PHP管理设置SQL注入'),
    # More FP samples
    ('tests/test_config.py', 'Python', 'import os\nAPI_KEY = os.environ.get("TEST_API_KEY", "mock_key_for_testing")', '硬编码密钥', 'P3', 'CWE-798', 'false_positive', '从环境变量读取测试密钥'),
    ('tests/integration/test_db.py', 'Python', 'DB_URL = "sqlite:///test.db"\nPASSWORD = "test"', '硬编码密钥', 'P3', 'CWE-798', 'false_positive', '测试数据库使用SQLite无真实密码'),
    ('src/templates/safe.html', 'JavaScript', '<p>{{ user.name | e }}</p>\n<div>{{ content | escape }}</div>', 'XSS', 'P3', 'CWE-79', 'false_positive', '显式使用escape过滤器'),
    ('server/routes/safe.js', 'JavaScript', 'const id = parseInt(req.params.id, 10);\ndb.query("SELECT * FROM users WHERE id = " + id);', 'SQL注入', 'P3', 'CWE-89', 'false_positive', 'parseInt转换后使用'),
    ('src/main/java/com/app/SafeFile.java', 'Java', 'String name = FilenameUtils.getName(request.getParameter("file"));\nFile f = new File("/uploads", name);', '路径遍历', 'P3', 'CWE-22', 'false_positive', 'FilenameUtils.getName过滤路径'),
    ('internal/handler/safe_exec.go', 'Go', 'allowed := []string{"pdf", "doc", "txt"}\nif !contains(allowed, ext) { return }', '命令注入', 'P3', 'CWE-78', 'false_positive', '文件扩展名白名单校验'),
    ('public/safe_download.php', 'PHP', '$allowed = ["report.pdf", "data.csv"];\nif (!in_array($file, $allowed)) die("not allowed");', '路径遍历', 'P3', 'CWE-22', 'false_positive', 'PHP下载白名单校验'),
    ('src/utils/sanitize.js', 'JavaScript', 'function sanitize(input) {\n  return input.replace(/[<>]/g, "");\n}\nconst safe = sanitize(userInput);', 'XSS', 'P3', 'CWE-79', 'false_positive', '有sanitize函数处理用户输入'),
    ('app/views/safe_render.py', 'Python', 'from markupsafe import escape\nname = escape(request.args.get("name"))\nreturn f"<h1>{name}</h1>"', 'XSS', 'P3', 'CWE-79', 'false_positive', '使用markupsafe.escape转义'),
    ('src/main/java/com/app/SafeConfig.java', 'Java', '@Value("${db.password}")\nprivate String dbPassword;', '硬编码密钥', 'P3', 'CWE-798', 'false_positive', 'Spring Value从配置文件注入'),
    ('internal/config/secret.go', 'Go', 'type Config struct {\n    DBPassword string `env:"DB_PASSWORD"`\n}', '硬编码密钥', 'P3', 'CWE-798', 'false_positive', 'Go struct tag从环境变量注入'),
    ('tests/mock/test_auth.py', 'Python', 'MOCK_JWT = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.mock"\ndef test_auth():\n    token = MOCK_JWT', '硬编码密钥', 'P3', 'CWE-798', 'false_positive', '测试mock JWT token'),
    ('config/settings.json', 'JavaScript', '{\n  "apiUrl": "https://api.example.com",\n  "docsUrl": "https://docs.example.com"\n}', '硬编码密钥', 'P3', 'CWE-798', 'false_positive', 'JSON配置文件仅包含公开URL'),
    ('src/main/java/com/app/PublicApi.java', 'Java', '@GetMapping("/api/health")\npublic String health() { return "ok"; }', '越权访问', 'P3', 'CWE-862', 'false_positive', '健康检查接口无需认证'),
    ('app/views/health.py', 'Python', '@app.route("/health")\ndef health():\n    return jsonify(status="ok")', '越权访问', 'P3', 'CWE-862', 'false_positive', '健康检查接口无需认证'),
    ('internal/handler/public.go', 'Go', 'func HealthCheck(w http.ResponseWriter, r *http.Request) {\n    w.Write([]byte("ok"))\n}', '越权访问', 'P3', 'CWE-862', 'false_positive', '健康检查接口无需认证'),
    ('public/health.php', 'PHP', '<?php echo json_encode(["status" => "ok"]); ?>', '越权访问', 'P3', 'CWE-862', 'false_positive', '健康检查接口无需认证'),
    ('app/utils/safe_subprocess.py', 'Python', 'import subprocess\nresult = subprocess.run(["ls", "-la", "/var/log"], capture_output=True, text=True)', '命令注入', 'P3', 'CWE-78', 'false_positive', 'subprocess.run使用列表参数不经过shell'),
    ('src/main/java/com/app/SafeExec.java', 'Java', 'ProcessBuilder pb = new ProcessBuilder("ls", "-la", dir);\nProcess p = pb.start();', '命令注入', 'P3', 'CWE-78', 'false_positive', 'ProcessBuilder使用数组参数'),
    ('server/routes/safe_exec.js', 'JavaScript', 'const { execFile } = require("child_process");\nexecFile("/usr/bin/ls", ["-la", dir], callback);', '命令注入', 'P3', 'CWE-78', 'false_positive', 'execFile不经过shell'),
    ('src/main/java/com/app/SafeCors.java', 'Java', '@CrossOrigin(origins = "https://app.example.com")\n@GetMapping("/api/data")\npublic List<Data> getData() { return dataService.findAll(); }', 'CSRF缺失', 'P3', 'CWE-352', 'false_positive', 'CORS限制到特定域名'),
]

for s in extra:
    db.execute(
        "INSERT INTO benchmark_samples (file_path, language, code_snippet, issue_type, severity, cwe_id, ground_truth, notes, annotated_by, annotated_at, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (s[0], s[1], s[2], s[3], s[4], s[5], s[6], s[7], 'benchmark_gen', now, 'synthetic')
    )

db.commit()
total = db.execute('SELECT COUNT(*) FROM benchmark_samples').fetchone()[0]
tp = db.execute("SELECT COUNT(*) FROM benchmark_samples WHERE ground_truth='true_positive'").fetchone()[0]
fp = db.execute("SELECT COUNT(*) FROM benchmark_samples WHERE ground_truth='false_positive'").fetchone()[0]
print(f'Total: {total}, TP: {tp}, FP: {fp}')

# 按语言统计
for lang in ['Python','JavaScript','Java','Go','PHP']:
    c = db.execute("SELECT COUNT(*) FROM benchmark_samples WHERE language=?", (lang,)).fetchone()[0]
    print(f'  {lang}: {c}')
db.close()
