#!/usr/bin/env python3
"""Check obvious code-identity boundary violations.

This tool keeps the static side intentionally small: it blocks production code
from depending on tests/entry/archive/temp code, and warns when temp probes lack
their lifecycle. Ambiguous placement remains an AI/human review matter.
"""

from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCAN_DIRS = ("app", "scripts", "market-impact-study", "tools", "tests")
IGNORED_PARTS = {
    ".cache",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
    "__pycache__",
}
OUTER_MODULES = {"tests", "tools", "archive", "tmp", "probes"}
TEMP_NAME_MARKERS = ("tmp", "probe", "debug")
TEMP_LIFECYCLE_MARKERS = ("删除条件", "归档条件")


def rel(path: pathlib.Path) -> str:
    return path.relative_to(ROOT).as_posix()


def should_scan(path: pathlib.Path) -> bool:
    if path.suffix != ".py" or not path.is_file():
        return False
    parts = set(path.relative_to(ROOT).parts)
    return not parts.intersection(IGNORED_PARTS)


def is_test_path(path: pathlib.Path) -> bool:
    path_rel = path.relative_to(ROOT)
    return path_rel.parts[:1] == ("tests",) or path.name.startswith("test_") or path.name.endswith("_test.py")


def is_outer_path(path: pathlib.Path) -> bool:
    parts = path.relative_to(ROOT).parts
    if not parts:
        return False
    first = parts[0]
    if first in {"tests", "tools", "archive", "tmp", "probes"}:
        return True
    return any(marker in path.name.lower() for marker in TEMP_NAME_MARKERS)


def imported_roots(path: pathlib.Path) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [(exc.lineno or 1, "<syntax-error>")]
    roots: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.extend((alias.lineno, alias.name.split(".", maxsplit=1)[0]) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.append((node.lineno, node.module.split(".", maxsplit=1)[0]))
    return roots


def temp_file_missing_lifecycle(path: pathlib.Path) -> bool:
    name = path.name.lower()
    if not any(marker in name for marker in TEMP_NAME_MARKERS):
        return False
    text = path.read_text(encoding="utf-8", errors="ignore")
    return not any(marker in text for marker in TEMP_LIFECYCLE_MARKERS)


def main() -> int:
    issues: list[str] = []
    warnings: list[str] = []
    for scan_dir in SCAN_DIRS:
        base = ROOT / scan_dir
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            if not should_scan(path):
                continue
            if temp_file_missing_lifecycle(path):
                warnings.append(f"{rel(path)}: 临时/探针文件缺少删除条件或归档条件")
            if is_test_path(path) or is_outer_path(path):
                continue
            for lineno, root in imported_roots(path):
                if root in OUTER_MODULES:
                    issues.append(f"{rel(path)}:{lineno}: 正式代码不得 import 外层模块 `{root}`")
    if warnings:
        sys.stderr.write("[code-identity] WARNING：临时/探针文件缺少生命周期条件：\n")
        for warning in warnings:
            sys.stderr.write(f"  - {warning}\n")
    if not issues:
        sys.stdout.write("[code-identity] 未发现明显代码身份边界违规\n")
        return 0
    sys.stderr.write(f"[code-identity] {len(issues)} 个代码身份边界违规：\n")
    for issue in issues:
        sys.stderr.write(f"  - {issue}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
