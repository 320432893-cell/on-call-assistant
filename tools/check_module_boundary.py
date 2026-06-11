#!/usr/bin/env python3
"""检查 app/ 和 scripts/ 下的 Python 文件是否有职责声明注释块。

职责声明格式（文件顶部，docstring 之前或之后均可）：
  # 职责：...
  # 不负责：...
  # 依赖层：...

三行均需存在才算通过。
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCAN_DIRS = ["app", "scripts"]
EXCLUDE_NAMES = {"__init__.py", "conftest.py"}
EXCLUDE_PREFIXES = ("test_",)
EXCLUDE_SUFFIXES = ("_test.py",)

REQUIRED_MARKERS = ("# 职责：", "# 不负责：", "# 依赖层：")
LINE_THRESHOLD = 400


def should_scan(path: pathlib.Path) -> bool:
    name = path.name
    if name in EXCLUDE_NAMES:
        return False
    if any(name.startswith(p) for p in EXCLUDE_PREFIXES):
        return False
    return not any(name.endswith(s) for s in EXCLUDE_SUFFIXES)


def check_file(path: pathlib.Path) -> list[str]:
    """返回缺失的 marker 列表。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return [m for m in REQUIRED_MARKERS if m not in text]


def line_count(path: pathlib.Path) -> int:
    try:
        return sum(1 for _ in path.open("r", encoding="utf-8", errors="ignore"))
    except OSError:
        return 0


def main() -> int:
    failures: list[tuple[pathlib.Path, list[str]]] = []
    oversized: list[tuple[pathlib.Path, int]] = []
    for scan_dir in SCAN_DIRS:
        for path in sorted((ROOT / scan_dir).rglob("*.py")):
            if should_scan(path):
                missing = check_file(path)
                if missing:
                    failures.append((path, missing))
                lines = line_count(path)
                if lines >= LINE_THRESHOLD:
                    oversized.append((path, lines))

    if oversized:
        # WARNING：超阈文件 = 拆分候选，闭包态记 defer；不改退出码，存量不阻塞。
        sys.stderr.write(f"[module-boundary] WARNING：{len(oversized)} 个文件 ≥ {LINE_THRESHOLD} 行（拆分候选，闭包记 defer）：\n")
        for path, lines in oversized:
            sys.stderr.write(f"  {path.relative_to(ROOT)}  {lines} 行\n")

    if not failures:
        sys.stdout.write("[module-boundary] 全部文件均有职责声明注释块\n")
        return 0

    sys.stderr.write(f"[module-boundary] {len(failures)} 个文件缺少职责声明注释块：\n")
    for path, missing in failures:
        rel = path.relative_to(ROOT)
        sys.stderr.write(f"  {rel}  缺失: {', '.join(missing)}\n")
    sys.stderr.write(
        "\n在文件顶部添加：\n  # 职责：[做什么]\n  # 不负责：[不做什么，至少一项]\n  # 依赖层：[允许 import 的层/模块]",
    )
    sys.stderr.write("\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
