#!/usr/bin/env python3
"""检查 Python 文件是否有职责声明注释块。

新文件/本次改动文件要求使用当前 AGENTS.md 四项格式：
  # 职责：...
  # 不做什么：...
  # 允许依赖层：...
  # 谁不应该 import：...

全量扫描仍兼容旧字段名，避免存量文件因纯规则迁移被迫 churn。
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
GIT = "/usr/bin/git"
SCAN_DIRS = ["app", "scripts", "market-impact-study", "tools"]
EXCLUDE_NAMES = {"__init__.py", "conftest.py"}
EXCLUDE_PREFIXES = ("test_",)
EXCLUDE_SUFFIXES = ("_test.py",)

CURRENT_MARKERS = ("# 职责：", "# 不做什么：", "# 允许依赖层：", "# 谁不应该 import：")
FULL_SCAN_MARKER_GROUPS = (
    ("# 职责：",),
    ("# 不做什么：", "# 不负责："),
    ("# 允许依赖层：", "# 依赖层："),
    ("# 谁不应该 import：",),
)
LINE_THRESHOLD = 400


def rel(path: pathlib.Path) -> str:
    return path.relative_to(ROOT).as_posix()


def should_scan(path: pathlib.Path) -> bool:
    name = path.name
    if path.suffix != ".py" or not path.is_file():
        return False
    if name in EXCLUDE_NAMES:
        return False
    if any(name.startswith(p) for p in EXCLUDE_PREFIXES):
        return False
    return not any(name.endswith(s) for s in EXCLUDE_SUFFIXES)


def read_file(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def missing_current_markers(path: pathlib.Path) -> list[str]:
    text = read_file(path)
    if not text:
        return []
    return [marker for marker in CURRENT_MARKERS if marker not in text]


def missing_full_scan_markers(path: pathlib.Path) -> list[str]:
    text = read_file(path)
    if not text:
        return []
    return [" 或 ".join(group) for group in FULL_SCAN_MARKER_GROUPS if not any(marker in text for marker in group)]


def line_count(path: pathlib.Path) -> int:
    try:
        return sum(1 for _ in path.open("r", encoding="utf-8", errors="ignore"))
    except OSError:
        return 0


def git_changed_names() -> tuple[int, list[str], str]:
    names: list[str] = []
    for args in (
        ["diff", "--name-only", "--diff-filter=ACMR"],
        ["diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        ["ls-files", "--others", "--exclude-standard"],
    ):
        proc = subprocess.run([GIT, *args], cwd=ROOT, text=True, capture_output=True, check=False)  # noqa: S603
        if proc.returncode != 0:
            return proc.returncode, [], proc.stderr.strip()
        names.extend(line.strip() for line in proc.stdout.splitlines() if line.strip())
    return 0, sorted(set(names)), ""


def iter_full_scan_files() -> list[pathlib.Path]:
    paths: list[pathlib.Path] = []
    for scan_dir in SCAN_DIRS:
        base = ROOT / scan_dir
        if not base.exists():
            continue
        paths.extend(path for path in sorted(base.rglob("*.py")) if should_scan(path))
    return paths


def iter_changed_scan_files() -> tuple[int, list[pathlib.Path]]:
    rc, names, err = git_changed_names()
    if rc != 0:
        sys.stderr.write(f"[module-boundary] git changed files failed: {err}\n")
        return rc, []
    paths = []
    for name in names:
        path = ROOT / name
        if path.exists() and should_scan(path):
            paths.append(path)
    return 0, paths


def report_oversized(paths: list[pathlib.Path]) -> None:
    oversized = [(path, line_count(path)) for path in paths if line_count(path) >= LINE_THRESHOLD]
    if not oversized:
        return
    sys.stderr.write(
        f"[module-boundary] WARNING：{len(oversized)} 个文件 ≥ {LINE_THRESHOLD} 行（拆分候选，闭包记 defer）：\n"
    )
    for path, lines in oversized:
        sys.stderr.write(f"  {rel(path)}  {lines} 行\n")


def run_changed() -> int:
    rc, paths = iter_changed_scan_files()
    if rc != 0:
        return rc
    if not paths:
        sys.stdout.write("[module-boundary] changed: no changed Python module files\n")
        return 0

    failures = [(path, missing_current_markers(path)) for path in paths]
    failures = [(path, missing) for path, missing in failures if missing]
    report_oversized(paths)
    if not failures:
        sys.stdout.write("[module-boundary] changed: 本次改动文件均有四项职责声明注释块\n")
        return 0

    sys.stderr.write(f"[module-boundary] changed: {len(failures)} 个本次改动文件缺少当前四项职责声明：\n")
    for path, missing in failures:
        sys.stderr.write(f"  {rel(path)}  缺失: {', '.join(missing)}\n")
    sys.stderr.write(
        "\n在文件顶部添加：\n"
        "  # 职责：[做什么]\n"
        "  # 不做什么：[不做什么，至少一项]\n"
        "  # 允许依赖层：[允许 import 的层/模块]\n"
        "  # 谁不应该 import：[不应 import 本文件的层/模块]\n",
    )
    return 1


def run_full() -> int:
    failures: list[tuple[pathlib.Path, list[str]]] = []
    paths = iter_full_scan_files()
    for path in paths:
        missing = missing_full_scan_markers(path)
        if missing:
            failures.append((path, missing))

    report_oversized(paths)

    if not failures:
        sys.stdout.write("[module-boundary] 全部文件均有职责声明注释块\n")
        return 0

    sys.stderr.write(f"[module-boundary] {len(failures)} 个文件缺少职责声明注释块：\n")
    for path, missing in failures:
        sys.stderr.write(f"  {rel(path)}  缺失: {', '.join(missing)}\n")
    sys.stderr.write(
        "\n推荐使用当前格式：\n"
        "  # 职责：[做什么]\n"
        "  # 不做什么：[不做什么，至少一项]\n"
        "  # 允许依赖层：[允许 import 的层/模块]\n"
        "  # 谁不应该 import：[不应 import 本文件的层/模块]",
    )
    sys.stderr.write("\n")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--changed", action="store_true", help="Only check changed, staged, and untracked Python files."
    )
    args = parser.parse_args()
    if args.changed:
        return run_changed()
    return run_full()


if __name__ == "__main__":
    sys.exit(main())
