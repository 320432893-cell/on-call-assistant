#!/usr/bin/env python3
"""Review dirty git diff additions for high-ROI code smells.

This is intentionally heuristic and non-blocking. It exists to tell the AI and
user what engineering approach to discuss before expanding a change.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

MAX_FINDINGS_TO_PRINT = 20


@dataclass(frozen=True)
class Finding:
    path: str
    line: int | None
    label: str
    detail: str


RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("debug-print", re.compile(r"\bprint\s*\("), "新增 print，确认是临时调试还是要换成日志/稳定错误响应。"),
    (
        "broad-except",
        re.compile(r"\bexcept\s+Exception\b"),
        "新增宽泛异常，确认是边界兜底、兼容修补，还是应该捕获具体异常。",
    ),
    ("raw-sleep", re.compile(r"\btime\.sleep\s*\("), "新增固定 sleep，确认是外部节流，还是应改成条件等待/重试。"),
    (
        "http-without-timeout",
        re.compile(r"\b(requests\.(get|post|put|patch|delete)|httpx\.(get|post|put|patch|delete))\s*\("),
        "新增 HTTP 调用，确认是否显式 timeout，以及失败策略。",
    ),
    (
        "inner-html",
        re.compile(r"\.innerHTML\s*=|insertAdjacentHTML\s*\("),
        "新增 HTML 注入入口，确认转义/DOM 构造策略。",
    ),
    (
        "shell-subprocess",
        re.compile(r"\bsubprocess\.(run|Popen|call|check_call|check_output)\s*\("),
        "新增子进程调用，确认输入来源、shell、超时和错误处理。",
    ),
    (
        "global-state",
        re.compile(r"^\s*(global\s+\w+|_[a-zA-Z0-9_]+\s*=\s*None\s*(#.*)?$)"),
        "新增/触碰全局状态，确认是兼容单例、缓存，还是应注入依赖。",
    ),
    (
        "hardcoded-secret-shape",
        re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*=\s*['\"][^'\"]{8,}['\"]"),
        "新增疑似密钥形态，确认是否应改环境变量或 secret store。",
    ),
    (
        "new-api-route-auth-marker",
        re.compile(r"^\s*@\w+\.(get|post|put|patch|delete)\s*\("),
        "新增 API 路由，确认已标明公开/登录/管理员/内部调用或接入项目鉴权。",
    ),
)


def run_git_diff(root: Path, path: str | None) -> str:
    git = shutil.which("git")
    if git is None:
        return ""
    command = [git, "diff", "--unified=0", "--no-ext-diff", "--"]
    if path:
        command.append(path)
    proc = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)  # noqa: S603
    if proc.returncode not in (0, 1):
        return ""
    return proc.stdout


def iter_added_lines(diff_text: str) -> list[tuple[str, int | None, str]]:
    current_path = ""
    new_line: int | None = None
    out: list[tuple[str, int | None, str]] = []

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_path = line[6:]
            continue
        if line.startswith("@@"):
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            new_line = int(match.group(1)) if match else None
            continue
        if line.startswith("+") and not line.startswith("+++"):
            text = line[1:]
            out.append((current_path, new_line, text))
            if new_line is not None:
                new_line += 1
            continue
        if line.startswith("-") and not line.startswith("---"):
            continue
        if new_line is not None:
            new_line += 1
    return out


def review(diff_text: str) -> list[Finding]:
    findings: list[Finding] = []
    for path, line_no, text in iter_added_lines(diff_text):
        stripped = text.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for label, pattern, detail in RULES:
            if pattern.search(text):
                findings.append(Finding(path=path, line=line_no, label=label, detail=detail))
    return findings


def print_findings(findings: list[Finding]) -> None:
    if not findings:
        return
    sys.stderr.write("[dirty_diff] 本次 diff 新增高 ROI 脏点:\n")
    for item in findings[:MAX_FINDINGS_TO_PRINT]:
        loc = item.path if item.line is None else f"{item.path}:{item.line}"
        sys.stderr.write(f"  - {loc} [{item.label}] {item.detail}\n")
    if len(findings) > MAX_FINDINGS_TO_PRINT:
        sys.stderr.write(f"  ... 还有 {len(findings) - MAX_FINDINGS_TO_PRINT} 条\n")
    sys.stderr.write("[dirty_diff] 建议先和用户确认处理范式:局部修补 / 分层重构 / 兼容优先 / 测试先行 / 安全优先。\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="Limit review to one dirty file.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    git = shutil.which("git")
    if git is None:
        return 0
    root_proc = subprocess.run(  # noqa: S603
        [git, "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
        check=False,
    )
    if root_proc.returncode != 0:
        return 0
    root = Path(root_proc.stdout.strip())
    path = None
    if args.file:
        file_path = Path(args.file)
        try:
            path = str(file_path.resolve().relative_to(root))
        except ValueError:
            path = args.file
    findings = review(run_git_diff(root, path))
    print_findings(findings)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
