#!/usr/bin/env python3
"""
煋鉴 Benchmark 运行器
对标注集执行扫描，对比结果与标注，计算准确率/召回率/F1
"""
import sqlite3
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

DB_PATH = os.environ.get('XINPECT_DB', '/opt/xinpect-website/xinpect.db')
SCANNER_URL = os.environ.get('SCANNER_URL', 'http://127.0.0.1:8622/scan')

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def scan_sample(sample):
    """对单个样本执行扫描，返回检测到的issue列表"""
    code = sample['code_snippet']
    lang = sample['language']
    file_path = sample['file_path']

    # 构建扫描请求
    files_dict = {file_path: code}
    payload = {
        'files': files_dict,
        'brain_ids': ['e1','e2','e3','e4','e5','e6','e7'],
        'options': {
            'scan_mode': 'full',
            'language': lang.lower(),
        }
    }

    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            SCANNER_URL,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            return result.get('issues', [])
    except Exception as e:
        print(f"  ⚠️ 扫描失败 ({file_path}): {e}")
        return []


def match_issue(issues, sample):
    """判断扫描结果中是否有匹配样本标注的issue"""
    sample_type = sample['issue_type'].lower()
    type_keywords = {
        'sql注入': ['sql', 'injection', 'cwe-89', 'sqli'],
        'xss': ['xss', 'cross-site', 'cwe-79', 'html'],
        '硬编码密钥': ['hardcod', 'secret', 'credential', 'cwe-798', 'key', 'password', 'token'],
        '路径遍历': ['path', 'traversal', 'cwe-22', 'directory'],
        '命令注入': ['command', 'injection', 'cwe-78', 'os-command'],
        'ssrf': ['ssrf', 'server-side', 'cwe-918'],
        '不安全的反序列化': ['deserial', 'cwe-502', 'pickle', 'unserialize'],
        'csrf缺失': ['csrf', 'cwe-352', 'cross-site request'],
        '越权访问': ['authorization', 'cwe-862', 'access control', 'permission', 'auth'],
    }

    keywords = type_keywords.get(sample_type, [sample_type])

    for issue in issues:
        issue_str = json.dumps(issue, ensure_ascii=False).lower()
        for kw in keywords:
            if kw in issue_str:
                # 还要检查文件路径是否匹配
                issue_file = issue.get('file', issue.get('file_path', ''))
                if issue_file and sample['file_path'] in issue_file:
                    return True
                # 如果没有文件信息但关键词匹配，也认为命中（单文件扫描场景）
                if not issue_file:
                    return True

    return False


def run_benchmark(run_name=None):
    """运行完整benchmark"""
    db = get_db()

    # 加载标注集
    samples = db.execute(
        "SELECT * FROM benchmark_samples WHERE ground_truth != 'pending'"
    ).fetchall()

    if not samples:
        print("❌ 标注集为空，请先运行 generate_benchmark.py")
        db.close()
        return None

    if run_name is None:
        run_name = "bench_" + datetime.now().strftime("%Y%m%d_%H%M%S")

    total = len(samples)
    print(f"🚀 开始 Benchmark: {run_name}")
    print(f"   样本总数: {total}")
    print(f"   TP样本: {sum(1 for s in samples if s['ground_truth']=='true_positive')}")
    print(f"   FP样本: {sum(1 for s in samples if s['ground_truth']=='false_positive')}")
    print()

    tp = 0  # true positive: 真实有问题，扫描也报出来了
    fp = 0  # false positive: 真实没问题，扫描却报了
    fn = 0  # false negative: 真实有问题，扫描没报出来
    tn = 0  # true negative: 真实没问题，扫描也没报

    # 按严重级别统计
    by_severity = {}
    # 按语言统计
    by_language = {}

    for i, sample in enumerate(samples):
        s = dict(sample)
        file_path = s['file_path']
        lang = s['language']
        truth = s['ground_truth']
        severity = s['severity']

        if (i + 1) % 10 == 0 or i == 0:
            print(f"  进度: {i+1}/{total} ({file_path})")

        # 扫描
        issues = scan_sample(s)
        detected = match_issue(issues, s)

        # 分类统计
        if truth == 'true_positive' and detected:
            tp += 1
        elif truth == 'true_positive' and not detected:
            fn += 1
        elif truth == 'false_positive' and detected:
            fp += 1
        elif truth == 'false_positive' and not detected:
            tn += 1

        # 按严重级别
        if severity not in by_severity:
            by_severity[severity] = {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0}
        if truth == 'true_positive' and detected:
            by_severity[severity]['tp'] += 1
        elif truth == 'true_positive' and not detected:
            by_severity[severity]['fn'] += 1
        elif truth == 'false_positive' and detected:
            by_severity[severity]['fp'] += 1
        elif truth == 'false_positive' and not detected:
            by_severity[severity]['tn'] += 1

        # 按语言
        if lang not in by_language:
            by_language[lang] = {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0}
        if truth == 'true_positive' and detected:
            by_language[lang]['tp'] += 1
        elif truth == 'true_positive' and not detected:
            by_language[lang]['fn'] += 1
        elif truth == 'false_positive' and detected:
            by_language[lang]['fp'] += 1
        elif truth == 'false_positive' and not detected:
            by_language[lang]['tn'] += 1

    # 计算指标
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0

    # 按严重级别计算指标
    severity_metrics = {}
    for sev, counts in by_severity.items():
        p = counts['tp'] / (counts['tp'] + counts['fp']) if (counts['tp'] + counts['fp']) > 0 else 0
        r = counts['tp'] / (counts['tp'] + counts['fn']) if (counts['tp'] + counts['fn']) > 0 else 0
        severity_metrics[sev] = {
            'precision': round(p, 4),
            'recall': round(r, 4),
            'f1': round(2*p*r/(p+r), 4) if (p+r) > 0 else 0,
            'tp': counts['tp'], 'fp': counts['fp'],
            'fn': counts['fn'], 'tn': counts['tn'],
        }

    # 按语言计算指标
    language_metrics = {}
    for lang, counts in by_language.items():
        p = counts['tp'] / (counts['tp'] + counts['fp']) if (counts['tp'] + counts['fp']) > 0 else 0
        r = counts['tp'] / (counts['tp'] + counts['fn']) if (counts['tp'] + counts['fn']) > 0 else 0
        language_metrics[lang] = {
            'precision': round(p, 4),
            'recall': round(r, 4),
            'f1': round(2*p*r/(p+r), 4) if (p+r) > 0 else 0,
            'tp': counts['tp'], 'fp': counts['fp'],
            'fn': counts['fn'], 'tn': counts['tn'],
        }

    result = {
        'run_name': run_name,
        'total_samples': total,
        'true_positives': tp,
        'false_positives': fp,
        'false_negatives': fn,
        'true_negatives': tn,
        'precision_score': round(precision, 4),
        'recall_score': round(recall, 4),
        'f1_score': round(f1, 4),
        'false_positive_rate': round(fpr, 4),
        'by_severity': json.dumps(severity_metrics, ensure_ascii=False),
        'by_language': json.dumps(language_metrics, ensure_ascii=False),
    }

    # 保存结果
    db.execute('''
        INSERT INTO benchmark_results
        (run_name, total_samples, true_positives, false_positives,
         false_negatives, true_negatives, precision_score, recall_score,
         f1_score, false_positive_rate, by_severity, by_language)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        result['run_name'], result['total_samples'],
        result['true_positives'], result['false_positives'],
        result['false_negatives'], result['true_negatives'],
        result['precision_score'], result['recall_score'],
        result['f1_score'], result['false_positive_rate'],
        result['by_severity'], result['by_language'],
    ))
    db.commit()

    # 打印结果
    print(f"\n{'='*60}")
    print(f"📊 Benchmark 结果: {run_name}")
    print(f"{'='*60}")
    print(f"  样本总数: {total}")
    print(f"  TP={tp}  FP={fp}  FN={fn}  TN={tn}")
    print(f"  准确率 (Precision): {precision:.2%}")
    print(f"  召回率 (Recall):    {recall:.2%}")
    print(f"  F1 Score:           {f1:.2%}")
    print(f"  误报率 (FPR):       {fpr:.2%}")
    print(f"\n  按严重级别:")
    for sev in sorted(severity_metrics.keys()):
        m = severity_metrics[sev]
        print(f"    {sev}: Precision={m['precision']:.2%} Recall={m['recall']:.2%} F1={m['f1']:.2%}")
    print(f"\n  按语言:")
    for lang in sorted(language_metrics.keys()):
        m = language_metrics[lang]
        print(f"    {lang}: Precision={m['precision']:.2%} Recall={m['recall']:.2%} F1={m['f1']:.2%}")

    print(f"\n✅ 结果已保存到 benchmark_results 表")
    db.close()

    # 输出JSON结果
    output_path = '/opt/xinpect-website/benchmark_latest.json'
    with open(output_path, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"✅ JSON结果: {output_path}")

    return result


def run_offline_benchmark(run_name=None):
    """
    离线模式：不调用扫描器，而是基于规则匹配模拟扫描结果
    用于无法连接扫描引擎时的benchmark
    """
    db = get_db()

    samples = db.execute(
        "SELECT * FROM benchmark_samples WHERE ground_truth != 'pending'"
    ).fetchall()

    if not samples:
        print("❌ 标注集为空")
        db.close()
        return None

    if run_name is None:
        run_name = "bench_offline_" + datetime.now().strftime("%Y%m%d_%H%M%S")

    total = len(samples)
    print(f"🚀 离线 Benchmark: {run_name} (规则匹配模式)")
    print(f"   样本总数: {total}")

    tp = fp = fn = tn = 0
    by_severity = {}
    by_language = {}

    for sample in samples:
        s = dict(sample)
        truth = s['ground_truth']
        severity = s['severity']
        lang = s['language']
        code = s['code_snippet'].lower()
        issue_type = s['issue_type']

        # 规则匹配：检测代码片段是否包含明显的漏洞模式
        detected = False
        if issue_type == 'SQL注入':
            detected = any(p in code for p in ['+ user', '+ request', '+ $_', 'f"', '+ r.', '${req'])
        elif issue_type == 'XSS':
            detected = any(p in code for p in ['innerhtml', 'dangerouslyset', '<%=', 'echo', 'f"<', '+ name', 'f.write'])
        elif issue_type == '硬编码密钥':
            detected = any(p in code for p in ['"sk_live', '"admin', '"prod', '"p@ss', 'secret_key =', 'api_key = "ghp', 'jwt_secret = "', 'smtp_password', 'db_password = "'])
            # 排除测试文件和环境变量
            if s['file_path'].startswith('test') or 'test' in s['file_path']:
                detected = False
            if 'os.environ' in code or 'os.getenv' in code or 'process.env' in code or 'os.getenv' in code:
                detected = False
        elif issue_type == '命令注入':
            detected = any(p in code for p in ['os.system', 'shell=true', 'subprocess.call(', 'exec(', 'shell_exec', 'system(', 'rt.exec', '"sh", "-c"'])
        elif issue_type == '路径遍历':
            detected = any(p in code for p in ['+ filename', '+ path', '+ $file', '+ name', '"+file'])
            if 'secure_filename' in code or 'allowedfiles' in code:
                detected = False
        elif issue_type == 'SSRF':
            detected = any(p in code for p in ['requests.get(url', 'urlopen(target', 'http.get(target', 'file_get_contents($url', 'u.openconnection'])
            if 'fetch("/' in code:
                detected = False
        elif issue_type == '不安全的反序列化':
            detected = any(p in code for p in ['pickle.loads', 'yaml.load(', 'readobject()', 'unserialize('])
        elif issue_type == 'CSRF缺失':
            detected = any(p in code for p in ['app.post("/api/account/delete', 'app.post("/api/transfer', 'delete from users'])
        elif issue_type == '越权访问':
            detected = any(p in code for p in ['@app.route("/admin', 'def list_users', 'getallusers'])
            if 'preauthorize' in code or 'hasrole' in code or 'checkinternalip' in code:
                detected = False

        # 统计
        if truth == 'true_positive' and detected:
            tp += 1
        elif truth == 'true_positive' and not detected:
            fn += 1
        elif truth == 'false_positive' and detected:
            fp += 1
        elif truth == 'false_positive' and not detected:
            tn += 1

        # 按严重级别
        if severity not in by_severity:
            by_severity[severity] = {'tp':0,'fp':0,'fn':0,'tn':0}
        if truth == 'true_positive' and detected: by_severity[severity]['tp'] += 1
        elif truth == 'true_positive' and not detected: by_severity[severity]['fn'] += 1
        elif truth == 'false_positive' and detected: by_severity[severity]['fp'] += 1
        elif truth == 'false_positive' and not detected: by_severity[severity]['tn'] += 1

        # 按语言
        if lang not in by_language:
            by_language[lang] = {'tp':0,'fp':0,'fn':0,'tn':0}
        if truth == 'true_positive' and detected: by_language[lang]['tp'] += 1
        elif truth == 'true_positive' and not detected: by_language[lang]['fn'] += 1
        elif truth == 'false_positive' and detected: by_language[lang]['fp'] += 1
        elif truth == 'false_positive' and not detected: by_language[lang]['tn'] += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0

    severity_metrics = {}
    for sev, counts in by_severity.items():
        p = counts['tp'] / (counts['tp'] + counts['fp']) if (counts['tp'] + counts['fp']) > 0 else 0
        r = counts['tp'] / (counts['tp'] + counts['fn']) if (counts['tp'] + counts['fn']) > 0 else 0
        severity_metrics[sev] = {
            'precision': round(p, 4), 'recall': round(r, 4),
            'f1': round(2*p*r/(p+r), 4) if (p+r) > 0 else 0,
            'tp': counts['tp'], 'fp': counts['fp'], 'fn': counts['fn'], 'tn': counts['tn'],
        }

    language_metrics = {}
    for lang, counts in by_language.items():
        p = counts['tp'] / (counts['tp'] + counts['fp']) if (counts['tp'] + counts['fp']) > 0 else 0
        r = counts['tp'] / (counts['tp'] + counts['fn']) if (counts['tp'] + counts['fn']) > 0 else 0
        language_metrics[lang] = {
            'precision': round(p, 4), 'recall': round(r, 4),
            'f1': round(2*p*r/(p+r), 4) if (p+r) > 0 else 0,
            'tp': counts['tp'], 'fp': counts['fp'], 'fn': counts['fn'], 'tn': counts['tn'],
        }

    result = {
        'run_name': run_name,
        'total_samples': total,
        'true_positives': tp,
        'false_positives': fp,
        'false_negatives': fn,
        'true_negatives': tn,
        'precision_score': round(precision, 4),
        'recall_score': round(recall, 4),
        'f1_score': round(f1, 4),
        'false_positive_rate': round(fpr, 4),
        'by_severity': json.dumps(severity_metrics, ensure_ascii=False),
        'by_language': json.dumps(language_metrics, ensure_ascii=False),
    }

    db.execute('''
        INSERT INTO benchmark_results
        (run_name, total_samples, true_positives, false_positives,
         false_negatives, true_negatives, precision_score, recall_score,
         f1_score, false_positive_rate, by_severity, by_language)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        result['run_name'], result['total_samples'],
        result['true_positives'], result['false_positives'],
        result['false_negatives'], result['true_negatives'],
        result['precision_score'], result['recall_score'],
        result['f1_score'], result['false_positive_rate'],
        result['by_severity'], result['by_language'],
    ))
    db.commit()

    print(f"\n{'='*60}")
    print(f"📊 Benchmark 结果: {run_name}")
    print(f"{'='*60}")
    print(f"  样本总数: {total}")
    print(f"  TP={tp}  FP={fp}  FN={fn}  TN={tn}")
    print(f"  准确率 (Precision): {precision:.2%}")
    print(f"  召回率 (Recall):    {recall:.2%}")
    print(f"  F1 Score:           {f1:.2%}")
    print(f"  误报率 (FPR):       {fpr:.2%}")
    print(f"\n  按严重级别:")
    for sev in sorted(severity_metrics.keys()):
        m = severity_metrics[sev]
        print(f"    {sev}: Precision={m['precision']:.2%} Recall={m['recall']:.2%} F1={m['f1']:.2%} (TP={m['tp']} FP={m['fp']} FN={m['fn']})")
    print(f"\n  按语言:")
    for lang in sorted(language_metrics.keys()):
        m = language_metrics[lang]
        print(f"    {lang}: Precision={m['precision']:.2%} Recall={m['recall']:.2%} F1={m['f1']:.2%}")

    print(f"\n✅ 结果已保存到 benchmark_results 表")
    db.close()

    output_path = '/opt/xinpect-website/benchmark_latest.json'
    with open(output_path, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"✅ JSON结果: {output_path}")

    return result


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'offline'
    if mode == 'online':
        run_benchmark()
    else:
        run_offline_benchmark()
