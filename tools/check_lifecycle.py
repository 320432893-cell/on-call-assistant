# 职责：扫生命周期声明，报 临时件/兼容别名缺机器可读 expires、已过期未清理、旧自由文本待迁移、expires-when 待人工核验。
# 不做什么：不删文件、不归档、不评估 expires-when 文本本身是否仍成立（这交人工 sweep）。
# 允许依赖层：标准库、本仓库 git 工作区状态、被扫描的源码注释。
# 谁不应该 import：正式业务代码、测试夹具、应用入口不应 import 本检查脚本。
"""Lifecycle debt forcing function: temp/T0/alias files must carry a machine-readable expiry."""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEAD_LINES = 15

TEMP = re.compile(r"#\s*lifecycle:\s*(t0|temp)\b", re.IGNORECASE)
ALIAS = re.compile(r"#\s*兼容别名")
EXPIRES = re.compile(r"#\s*expires:\s*(\d{4})-(\d{2})-(\d{2})")
EXPIRES_WHEN = re.compile(r"#\s*expires-when:\s*(.+)")
LEGACY = re.compile(r"删除条件|一次性脚本|临时探针")

# 定义这些标记串的目录会被 grep 命中（误报源），与项目其它工具同口径排除。
# tests/ 排除：测试夹具常含这些标记串字面量，且测试生命周期由 test-meta 管，不归 lifecycle。
SKIP_DIRS = {
    ".venv",
    ".cache",
    ".uv-cache",
    "node_modules",
    ".git",
    "__pycache__",
    "tools",
    ".ai-config",
    ".ai-hooks",
    "tests",
}


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def changed_py_files() -> list[Path]:
    names: set[str] = set()
    for args in (
        ["diff", "--name-only", "--diff-filter=ACMR", "--", "*.py"],
        ["diff", "--cached", "--name-only", "--diff-filter=ACMR", "--", "*.py"],
        ["ls-files", "--others", "--exclude-standard", "--", "*.py"],
    ):
        proc = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)
        names.update(line.strip() for line in proc.stdout.splitlines() if line.strip())
    paths = [ROOT / name for name in sorted(names) if (ROOT / name).exists()]
    # 与 full 模式同口径排除：定义这些标记串的目录（tools/.ai-config 等）不参与扫描，避免误报。
    return [path for path in paths if not (set(path.parts) & SKIP_DIRS)]


def all_py_files() -> list[Path]:
    return [path for path in ROOT.rglob("*.py") if not (set(path.parts) & SKIP_DIRS)]


def scan(path: Path) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    head = "\n".join(text.splitlines()[:HEAD_LINES])
    is_temp = bool(TEMP.search(head)) or bool(ALIAS.search(text))
    has_expiry = bool(EXPIRES.search(text)) or bool(EXPIRES_WHEN.search(text))
    findings: list[tuple[str, str]] = []
    if is_temp and not has_expiry:
        findings.append(("MISSING-EXPIRY", "临时件/兼容别名缺机器可读 # expires: 或 # expires-when:"))
    if LEGACY.search(head) and not is_temp and not has_expiry:
        findings.append(("BACKLOG", "旧自由文本生命周期声明，迁到 # expires: 或 # expires-when:"))
    if (match := EXPIRES.search(text)) and date(int(match[1]), int(match[2]), int(match[3])) < datetime.now(UTC).date():
        findings.append(("EXPIRED", f"已过期 {match[1]}-{match[2]}-{match[3]}，应清理或续期"))
    if when := EXPIRES_WHEN.search(text):
        findings.append(("MANUAL", f"expires-when 待人工核验：{when[1].strip()}"))
    return findings


def main(argv: list[str]) -> int:
    changed_mode = "--changed" in argv
    targets = changed_py_files() if changed_mode else all_py_files()
    findings = [(path, kind, msg) for path in targets for kind, msg in scan(path)]

    # changed 模式只阻塞「新增临时件缺 expiry」；其余形态及 full sweep 全为 WARNING，避免惊吓式中断 CI。
    blocking = [f for f in findings if f[1] == "MISSING-EXPIRY" and changed_mode]
    for path, kind, msg in findings:
        is_block = kind == "MISSING-EXPIRY" and changed_mode
        stream = sys.stderr if is_block else sys.stdout
        stream.write(f"{'X' if is_block else '!'} [{kind}] {rel(path)}: {msg}\n")

    if blocking:
        sys.stderr.write(
            "\n[lifecycle] 新增临时件/兼容别名必须带机器可读过期标注：\n"
            "  # lifecycle: temp        （或 t0）\n"
            "  # expires: 2026-07-01     （优先用日期，机器自动判过期）\n"
            "  # expires-when: <非日期条件>  （每次 sweep 人工核验）\n"
        )
        return 1
    if not findings:
        sys.stdout.write(
            "[lifecycle] 无生命周期债务" + ("（changed 范围）" if changed_mode else "（全量 sweep）") + "\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
