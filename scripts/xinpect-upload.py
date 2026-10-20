# ============================================================
# 煋鉴 CLI 上传工具
# 将本地扫描结果上传到煋鉴云端看板
#
# 用法:
#   python xinpect-upload.py <result.json> --server https://xinpect.xingwangzhineng.com --key xk_xxxx
#   python xinpect-upload.py ./scan-results/ --server https://xinpect.xingwangzhineng.com --key xk_xxxx
#
# 环境变量（可替代命令行参数）:
#   XINPECT_SERVER=https://xinpect.xingwangzhineng.com
#   XINPECT_API_KEY=xk_xxxxxxxx
# ============================================================

import argparse
import json
import os
import sys
import glob
import hashlib
from datetime import datetime

try:
    import requests
except ImportError:
    print("错误: 需要安装 requests 库")
    print("运行: pip install requests")
    sys.exit(1)


DEFAULT_SERVER = "https://xinpect.xingwangzhineng.com"
API_ENDPOINT = "/api/v1/results/upload"


def upload_result(filepath, server, api_key, project_tag=""):
    """上传单个结果文件到云端"""
    if not os.path.exists(filepath):
        print(f"  ❌ 文件不存在: {filepath}")
        return False

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"  ❌ JSON 解析失败: {e}")
        return False
    except Exception as e:
        print(f"  ❌ 读取文件失败: {e}")
        return False

    # 构建上传数据
    payload = {
        "results": data,
        "source": "cli",
        "uploaded_at": datetime.now().isoformat(),
    }
    if project_tag:
        payload["project_tag"] = project_tag

    # 从文件名推断语言
    basename = os.path.basename(filepath).lower()
    if '.py' in basename or data.get('language') == 'python':
        payload.setdefault("language", "python")
    elif '.js' in basename or '.ts' in basename:
        payload.setdefault("language", "javascript")

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
    }

    try:
        url = f"{server.rstrip('/')}{API_ENDPOINT}"
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        result = resp.json()

        if resp.status_code == 200 and result.get("status") == "ok":
            scan_id = result.get("scan_id", "")[:12]
            score = result.get("score", "?")
            grade = result.get("grade", "?")
            issues = result.get("issue_count", 0)
            print(f"  ✅ 上传成功 | 评分: {score} ({grade}) | 问题: {issues} | ID: {scan_id}...")
            return True
        else:
            error = result.get("error", f"HTTP {resp.status_code}")
            print(f"  ❌ 上传失败: {error}")
            return False

    except requests.exceptions.ConnectionError:
        print(f"  ❌ 无法连接到服务器: {server}")
        return False
    except requests.exceptions.Timeout:
        print(f"  ❌ 请求超时")
        return False
    except Exception as e:
        print(f"  ❌ 上传异常: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="煋鉴 CLI 上传工具 - 将本地扫描结果上传到云端看板",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 上传单个文件
  python xinpect-upload.py result.json --key xk_xxxxx

  # 上传整个目录
  python xinpect-upload.py ./scan-results/ --key xk_xxxxx

  # 使用环境变量
  export XINPECT_API_KEY=xk_xxxxx
  python xinpect-upload.py result.json --project my-project
        """,
    )
    parser.add_argument("path", help="扫描结果文件或目录路径")
    parser.add_argument("--server", default=os.environ.get("XINPECT_SERVER", DEFAULT_SERVER),
                        help=f"服务器地址 (默认: {DEFAULT_SERVER})")
    parser.add_argument("--key", default=os.environ.get("XINPECT_API_KEY", ""),
                        help="API Key (或设置 XINPECT_API_KEY 环境变量)")
    parser.add_argument("--project", default="",
                        help="项目标签（用于在看板中筛选）")
    parser.add_argument("--pattern", default="*.json",
                        help="目录模式匹配 (默认: *.json)")

    args = parser.parse_args()

    if not args.key:
        print("错误: 请提供 API Key")
        print("  --key xk_xxxxx  或  export XINPECT_API_KEY=xk_xxxxx")
        sys.exit(1)

    print(f"🔍 煋鉴上传工具")
    print(f"   服务器: {args.server}")
    print(f"   目标:   {args.path}")
    print()

    # 收集要上传的文件
    files_to_upload = []
    if os.path.isdir(args.path):
        pattern = os.path.join(args.path, args.pattern)
        files_to_upload = sorted(glob.glob(pattern))
        print(f"📁 找到 {len(files_to_upload)} 个结果文件")
    elif os.path.isfile(args.path):
        files_to_upload = [args.path]
    else:
        print(f"❌ 路径不存在: {args.path}")
        sys.exit(1)

    if not files_to_upload:
        print("没有找到要上传的文件")
        sys.exit(0)

    # 逐个上传
    success_count = 0
    for i, filepath in enumerate(files_to_upload, 1):
        print(f"\n[{i}/{len(files_to_upload)}] {os.path.basename(filepath)}")
        if upload_result(filepath, args.server, args.key, args.project):
            success_count += 1

    # 汇总
    print(f"\n{'='*40}")
    print(f"上传完成: {success_count}/{len(files_to_upload)} 成功")
    if success_count > 0:
        print(f"📊 前往 {args.server}/dashboard 查看结果")

    sys.exit(0 if success_count == len(files_to_upload) else 1)


if __name__ == "__main__":
    main()
