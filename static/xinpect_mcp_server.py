# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "mcp>=1.0.0",
#     "httpx>=0.27.0",
# ]
# ///
"""
Xinpect (煋鉴) MCP Server
=========================
AI Code Quality Analysis MCP Server for Claude Code / Cursor / Windsurf / Codex.

Exposes Xinpect's 7-engine code scanning capability as MCP tools,
allowing AI agents to perform professional code quality analysis
directly from their editor or terminal.

Transport: stdio (standard for Claude Code / Cursor integration)
"""

from __future__ import annotations

import json
import os
import traceback
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────
XINPECT_API_BASE = "https://xinpect.xingwangzhineng.com"
XINPECT_VERSION = "1.0.0"
DEFAULT_TIMEOUT = 60.0  # seconds – scanning can take a while for large projects

SUPPORTED_LANGUAGES = [
    "python", "javascript", "typescript", "java", "c", "cpp",
    "go", "rust", "ruby", "php", "swift", "kotlin",
    "csharp", "scala", "wxml", "auto",
]

SEVERITY_EMOJI = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🔵",
    "info": "⚪",
}

# ──────────────────────────────────────────────────────────────
# MCP Server Instance
# ──────────────────────────────────────────────────────────────
mcp = FastMCP(
    "xinpect",
    instructions="Xinpect (煋鉴) AI Code Quality Analysis Server. "
                 "Provides 7-engine code scanning with 9 analysis dimensions "
                 "covering syntax, security, performance, architecture, and more.",
)


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _get_api_key() -> str:
    """Read API key from environment, raise with friendly message if missing."""
    key = os.environ.get("XINPECT_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "XINPECT_API_KEY environment variable is not set.\n"
            "Please set it: export XINPECT_API_KEY='xk_your_key_here'\n"
            "Get your key at: https://xinpect.xingwangzhineng.com/dashboard"
        )
    if not key.startswith("xk_"):
        raise ValueError(
            f"Invalid API key format (got '{key[:6]}...'). "
            "Xinpect API keys start with 'xk_'. "
            "Get your key at: https://xinpect.xingwangzhineng.com/dashboard"
        )
    return key


def _headers(api_key: str) -> dict:
    return {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
        "User-Agent": f"xinpect-mcp-server/{XINPECT_VERSION}",
    }


def _format_severity(sev: str) -> str:
    emoji = SEVERITY_EMOJI.get(sev, "⚪")
    return f"{emoji} {sev.upper()}"


def _format_issues_compact(issues: list[dict], limit: int = 30) -> str:
    """Format issues into a compact, Agent-friendly list."""
    if not issues:
        return "  No issues found ✨"
    lines = []
    for i, issue in enumerate(issues[:limit], 1):
        sev = _format_severity(issue.get("severity", "medium"))
        title = issue.get("title", issue.get("message", "Unknown issue"))
        file_path = issue.get("file", "")
        line = issue.get("line", 0)
        brain = issue.get("brain_name", issue.get("brain_id", ""))
        location = f"{file_path}:{line}" if file_path else "N/A"
        lines.append(f"  {i}. [{sev}] {title}")
        lines.append(f"     📍 {location}  🔍 {brain}")
        suggestion = issue.get("suggestion", "")
        if suggestion:
            # Truncate long suggestions for readability
            if len(suggestion) > 200:
                suggestion = suggestion[:200] + "..."
            lines.append(f"     💡 {suggestion}")
        lines.append("")
    if len(issues) > limit:
        lines.append(f"  ... and {len(issues) - limit} more issues (truncated)")
    return "\n".join(lines)


def _format_bb_scores(bb_scores: dict) -> str:
    """Format building block scores into a readable summary."""
    if not bb_scores:
        return "  N/A"
    labels = {
        "code_quality": "Code Quality",
        "security": "Security",
        "performance": "Performance",
        "architecture": "Architecture",
        "maintainability": "Maintainability",
    }
    lines = []
    for key, label in labels.items():
        val = bb_scores.get(key)
        if val is not None:
            lines.append(f"  {label}: {val}/100")
    # Include any extra keys not in our predefined labels
    for key, val in bb_scores.items():
        if key not in labels and isinstance(val, (int, float)):
            lines.append(f"  {key}: {val}/100")
    return "\n".join(lines) if lines else "  N/A"


def _format_scan_result(data: dict, *, include_raw: bool = False) -> str:
    """Build a human/Agent-readable string from scan API response."""
    score = data.get("score", "N/A")
    grade = data.get("grade", "N/A")
    total_issues = data.get("total_issues", 0)
    file_count = data.get("file_count", 0)
    total_lines = data.get("total_lines", 0)
    language = data.get("language", "auto")
    scan_time = data.get("scan_time", 0)
    version = data.get("version", "")
    scan_mode = data.get("scan_mode", "full")
    warning = data.get("warning")

    severity = data.get("severity_counts", {})
    credits_used = data.get("credits_used", 0)
    credits_remaining = data.get("credits_remaining", "N/A")
    credits_warning = data.get("credits_warning")

    grade_emoji = {"S": "🏆", "A": "✅", "B": "⚠️", "C": "🔶", "D": "❌"}.get(grade, "")

    sections = [
        f"📊 Score: {score}/100 {grade_emoji}{grade}",
        f"📁 Files: {file_count} | Lines: {total_lines} | Language: {language} | Mode: {scan_mode}",
        f"⏱️ Scan time: {scan_time:.1f}s" + (f" | Engine: {version}" if version else ""),
        "",
        f"🔢 Issues: {total_issues}",
    ]

    if any(severity.values()):
        sev_parts = []
        for sev in ["critical", "high", "medium", "low", "info"]:
            count = severity.get(sev, 0)
            if count:
                sev_parts.append(f"{SEVERITY_EMOJI.get(sev, '')} {sev}: {count}")
        sections.append(f"  Severity breakdown: {' | '.join(sev_parts)}")

    bb_scores = data.get("building_block_scores", {})
    if bb_scores:
        sections.append("")
        sections.append("📐 Building Block Scores:")
        sections.append(_format_bb_scores(bb_scores))

    issues = data.get("issues", [])
    if issues:
        sections.append("")
        sections.append(f"📋 Issues Detail ({len(issues)} total):")
        sections.append(_format_issues_compact(issues))
    else:
        sections.append("")
        sections.append("✨ No issues detected – code quality is excellent!")

    sections.append("")
    sections.append(f"💳 Credits: used {credits_used} | remaining {credits_remaining}")
    if credits_warning:
        sections.append(f"⚠️ Credits Warning: {credits_warning}")
    if warning:
        sections.append(f"⚠️ Note: {warning}")

    return "\n".join(sections)


def _format_cost_result(data: dict) -> str:
    """Build a readable cost estimate string."""
    file_count = data.get("file_count", 0)
    total_lines = data.get("total_lines", 0)
    cost = data.get("credits_cost", data.get("cost", 0))
    balance = data.get("credit_balance", "N/A")
    sufficient = data.get("is_sufficient", True)

    sections = [
        f"📁 Files: {file_count} | Estimated lines: {total_lines}",
        f"💰 Estimated cost: {cost} credits",
        f"💳 Current balance: {balance} credits",
        f"✅ Sufficient: {'Yes' if sufficient else 'No – please recharge'}",
    ]
    detail = data.get("credits_detail", {})
    if detail:
        sections.append("")
        sections.append("📊 Balance Breakdown:")
        sections.append(f"  Subscription: {detail.get('subscription_balance', 'N/A')}"
                        + (f" (refreshes: {detail['subscription_refresh_at']})"
                           if detail.get("subscription_refresh_at") else ""))
        sections.append(f"  Pack: {detail.get('pack_balance', 'N/A')}"
                        + (f" (expires: {detail['pack_expire_at']})"
                           if detail.get("pack_expire_at") else ""))
    return "\n".join(sections)


def _build_httpx_error_msg(exc: Exception, action: str = "scan") -> str:
    """Return a friendly error message for HTTP/connection failures."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        try:
            detail = exc.response.json()
        except Exception:
            detail = exc.response.text[:300]
        error_msg = detail.get("error", str(detail)) if isinstance(detail, dict) else str(detail)

        friendly = {
            401: "Authentication failed. Check your XINPECT_API_KEY.",
            402: f"Insufficient credits or membership required. {error_msg}",
            403: f"API key invalid or inactive. {error_msg}",
            429: "Rate limited (max 10 requests/min). Please wait and retry.",
            503: f"Scanning service temporarily unavailable. {error_msg}",
        }
        return f"❌ Xinpect API error ({status}): {friendly.get(status, error_msg)}"

    if isinstance(exc, httpx.TimeoutException):
        return (
            f"⏰ Xinpect API timeout during {action}. "
            "The server might be under heavy load. Try again in a few seconds, "
            "or reduce the number of files / code size."
        )

    return f"❌ Network error during {action}: {exc}. Check your internet connection."


# ──────────────────────────────────────────────────────────────
# MCP Tools
# ──────────────────────────────────────────────────────────────

@mcp.tool()
async def xinpect_scan(
    code_files: dict[str, str],
    language: str = "auto",
) -> str:
    """Scan code for quality issues using Xinpect's 7 analysis engines (9 dimensions).

    Sends code content directly and receives a comprehensive quality report including:
    - Quality score (0-100) and letter grade (S/A/B/C/D)
    - Issues across 7 dimensions: syntax, security, performance, logic, architecture,
      code style, and best practices
    - Severity levels: critical / high / medium / low / info
    - Building block scores (Code Quality, Security, Performance, Architecture, Maintainability)
    - Actionable fix suggestions for each issue

    WHEN TO USE:
    - Review code quality before committing or merging
    - Find security vulnerabilities, performance bottlenecks, or logic errors
    - Get AI-powered fix suggestions for detected issues
    - Analyze Python, JavaScript, TypeScript, Java, Go, Rust, C/C++, and more

    Args:
        code_files: Dict of {filename: code_content}.
            Keys should include file extension, e.g. {"app.py": "import os\\n..."}.
            Max ~20 files per scan. For larger projects, split into multiple scans.
        language: Programming language hint. Default "auto" for auto-detection.
            Options: python, javascript, typescript, java, go, rust, c, cpp, etc.

    Returns:
        Full scan results with score, grade, issues, severity breakdown,
        building block scores, credits used, and fix suggestions.

    Notes:
    - Costs credits based on code line count (membership required)
    - Rate limit: 10 requests per minute per API key
    - Each scan saves to your dashboard history at xinpect.xingwangzhineng.com
    """
    try:
        api_key = _get_api_key()
    except ValueError as e:
        return f"❌ Configuration Error: {e}"

    # ── Validate inputs ──
    if not code_files:
        return (
            "❌ Error: code_files is empty. "
            "Provide at least one file, e.g. {\"main.py\": \"your code here\"}"
        )
    if len(code_files) > 20:
        return (
            f"❌ Error: Too many files ({len(code_files)}). "
            "Maximum is 20 files per scan. Please split into multiple scans."
        )

    total_lines = sum(
        len(content.split("\n"))
        for content in code_files.values()
        if isinstance(content, str)
    )

    # ── Call API ──
    payload = {
        "code_files": code_files,
        "language": language,
    }

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, verify=True) as client:
            resp = await client.post(
                f"{XINPECT_API_BASE}/api/v1/scan",
                headers=_headers(api_key),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as e:
        return _build_httpx_error_msg(e, "scan")
    except Exception as e:
        return f"❌ Unexpected error: {e}\n{traceback.format_exc()}"

    # ── Format & return ──
    return _format_scan_result(data)


@mcp.tool()
async def xinpect_scan_file(
    file_paths: list[str],
    language: str = "auto",
) -> str:
    """Read local files from disk and scan them with Xinpect's code analysis engines.

    This is a convenience wrapper around xinpect_scan that reads files from the
    local filesystem first. Ideal when the AI agent has access to the project
    files and wants to scan them directly without copy-pasting content.

    WHEN TO USE:
    - You have file paths and want to scan without manually reading content
    - Quick quality check on specific project files
    - Batch analysis of related files (e.g., all files in a module)

    Args:
        file_paths: List of absolute or relative file paths to read and scan.
            Must be readable text/code files. Max 20 files.
            Example: ["/project/src/main.py", "/project/src/utils.py"]
        language: Programming language hint. Default "auto" for auto-detection.
            Options: python, javascript, typescript, java, go, rust, etc.

    Returns:
        Full scan results with score, grade, issues, and fix suggestions.
        Same format as xinpect_scan.

    Notes:
    - Files are read from disk, then sent to Xinpect API for analysis
    - Binary files and files that can't be decoded as UTF-8 will be skipped
    - Total cost depends on combined line count of all files
    """
    try:
        api_key = _get_api_key()
    except ValueError as e:
        return f"❌ Configuration Error: {e}"

    if not file_paths:
        return "❌ Error: file_paths is empty. Provide at least one file path."
    if len(file_paths) > 20:
        return (
            f"❌ Error: Too many files ({len(file_paths)}). Maximum is 20 per scan."
        )

    # ── Read files from disk ──
    code_files: dict[str, str] = {}
    errors: list[str] = []

    for fp in file_paths:
        try:
            path = os.path.expanduser(fp)
            path = os.path.realpath(path)
            # 安全加固：限制可访问目录
            ALLOWED_DIRS = [
                os.path.realpath(os.path.dirname(__file__)),
                os.path.realpath('/opt/xinpect-website'),
                os.path.realpath(os.path.expanduser('~')),
            ]
            if not any(path.startswith(d) for d in ALLOWED_DIRS):
                errors.append(f"  Access denied (outside allowed dirs): {fp}")
                continue
            if not os.path.isfile(path):
                errors.append(f"  File not found: {fp}")
                continue
            if not os.access(path, os.R_OK):
                errors.append(f"  Permission denied: {fp}")
                continue
            # Size guard: skip files > 1MB
            size = os.path.getsize(path)
            if size > 1_000_000:
                errors.append(f"  Skipped (too large, {size // 1024}KB): {fp}")
                continue
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                code_files[os.path.basename(fp)] = f.read()
        except Exception as e:
            errors.append(f"  Error reading {fp}: {e}")

    if not code_files:
        err_detail = "\n".join(errors) if errors else "Unknown error"
        return f"❌ No valid files to scan.\n{err_detail}"

    # ── Call scan API ──
    payload = {
        "code_files": code_files,
        "language": language,
    }

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, verify=True) as client:
            resp = await client.post(
                f"{XINPECT_API_BASE}/api/v1/scan",
                headers=_headers(api_key),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as e:
        return _build_httpx_error_msg(e, "scan")
    except Exception as e:
        return f"❌ Unexpected error: {e}\n{traceback.format_exc()}"

    # ── Prepend file-read summary ──
    header_parts = [
        f"📂 Scanned {len(code_files)} file(s) from local disk:",
    ]
    for name in code_files:
        header_parts.append(f"  ✓ {name}")
    if errors:
        header_parts.append(f"  ⚠️ {len(errors)} file(s) skipped:")
        header_parts.extend(errors)
    header_parts.append("")
    header_parts.append("─" * 50)
    header_parts.append("")

    return "\n".join(header_parts) + _format_scan_result(data)


@mcp.tool()
async def xinpect_cost_estimate(
    files_meta: list[dict[str, Any]],
) -> str:
    """Estimate scan credit cost WITHOUT consuming credits or performing a scan.

    Calculates the expected credit cost based on file count and estimated
    line count. Use this before xinpect_scan to understand the cost.

    The scan cost model:
    - Base fee + per-100-lines charge
    - Small files (< 100 lines) cost less
    - Large projects scale linearly

    WHEN TO USE:
    - Before scanning a large project to check if you have enough credits
    - Comparing cost of different scanning strategies (single vs. split scans)
    - Checking your current credit balance

    Args:
        files_meta: List of file metadata dicts, each with:
            - "name" (str): Filename with extension, e.g. "app.py"
            - "size" (int): File size in bytes
            Example: [{"name": "main.py", "size": 5120}, {"name": "utils.js", "size": 2048}]

    Returns:
        Cost estimate with credit breakdown and current balance info.
    """
    try:
        api_key = _get_api_key()
    except ValueError as e:
        return f"❌ Configuration Error: {e}"

    if not files_meta:
        return "❌ Error: files_meta is empty. Provide file metadata, e.g. [{\"name\": \"app.py\", \"size\": 5000}]"

    payload = {"files_meta": files_meta}

    try:
        async with httpx.AsyncClient(timeout=30.0, verify=True) as client:
            resp = await client.post(
                f"{XINPECT_API_BASE}/api/scan/estimate",
                headers=_headers(api_key),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as e:
        return _build_httpx_error_msg(e, "cost estimation")
    except Exception as e:
        return f"❌ Unexpected error: {e}"

    if not data.get("ok"):
        return f"❌ Estimate failed: {data.get('error', 'Unknown error')}"

    return _format_cost_result(data)


@mcp.tool()
async def xinpect_health_check() -> str:
    """Check Xinpect API connectivity and account status.

    Verifies that:
    1. The API key is valid and active
    2. The Xinpect API server is reachable
    3. Your account membership is active
    4. Returns current credit balance info

    WHEN TO USE:
    - First-time setup verification
    - Troubleshooting scan failures
    - Checking credit balance before a batch of scans

    Returns:
        Connection status, account info, and credit balance details.
    """
    try:
        api_key = _get_api_key()
    except ValueError as e:
        return f"❌ Configuration Error: {e}"

    # Use a minimal scan estimate to test connectivity and auth
    # Send a tiny dummy file metadata
    payload = {"files_meta": [{"name": "test.py", "size": 100}]}

    try:
        async with httpx.AsyncClient(timeout=15.0, verify=True) as client:
            resp = await client.post(
                f"{XINPECT_API_BASE}/api/scan/estimate",
                headers=_headers(api_key),
                json=payload,
            )
            data = resp.json()

            if resp.status_code == 401:
                return "❌ Authentication failed (401). API key is missing or invalid."
            if resp.status_code == 403:
                return "❌ Forbidden (403). API key is inactive or expired."
            if resp.status_code == 402:
                return (
                    "⚠️ Membership required (402). "
                    "The API scan feature requires an active membership. "
                    "Upgrade at: https://xinpect.xingwangzhineng.com/dashboard?recharge"
                )

            resp.raise_for_status()

    except httpx.ConnectError:
        return (
            f"❌ Cannot connect to {XINPECT_API_BASE}\n"
            "The Xinpect API server may be down or unreachable.\n"
            "Check: https://xinpect.xingwangzhineng.com"
        )
    except httpx.TimeoutException:
        return f"⏰ Connection timeout. {XINPECT_API_BASE} is not responding."
    except httpx.HTTPStatusError as e:
        return f"❌ API returned HTTP {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        return f"❌ Unexpected error: {e}"

    # Parse successful response
    lines = [
        "✅ Xinpect API is reachable and responsive!",
        "",
        "📊 Account & Cost Info (based on 100-line test):",
    ]

    if data.get("is_vip"):
        balance = data.get("credit_balance", "N/A")
        cost = data.get("credits_cost", data.get("cost", "N/A"))
        lines.append(f"  💳 Credit balance: {balance}")
        lines.append(f"  💰 Cost for ~100 lines: {cost} credits")
        lines.append(f"  👤 Account type: VIP member")
    else:
        lines.append(f"  👤 Account type: Free tier")
        lines.append(f"  📝 Daily free scans: {data.get('daily_remaining', 'N/A')}")

    lines.append("")
    lines.append(f"🌐 API Base: {XINPECT_API_BASE}")
    lines.append(f"🔑 API Key: {api_key[:8]}***")
    lines.append(f"📖 Documentation: https://xinpect.xingwangzhineng.com")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────────────────────

def main():
    """Entry point – starts the MCP server with stdio transport."""
    api_key = os.environ.get("XINPECT_API_KEY", "")
    key_status = f"{api_key[:8]}..." if api_key.startswith("xk_") else "NOT SET ⚠️"

    # Print startup banner to stderr (stdout is reserved for MCP protocol)
    import sys
    print(
        f"╔══════════════════════════════════════════╗\n"
        f"║  🔍 Xinpect (煋鉴) MCP Server v{XINPECT_VERSION}     ║\n"
        f"║  AI Code Quality Analysis via MCP        ║\n"
        f"╠══════════════════════════════════════════╣\n"
        f"║  API:  {XINPECT_API_BASE:<33}║\n"
        f"║  Key:  {key_status:<33}║\n"
        f"╚══════════════════════════════════════════╝",
        file=sys.stderr,
    )

    mcp.run()


if __name__ == "__main__":
    main()
