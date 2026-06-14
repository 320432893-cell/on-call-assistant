# 职责：校验代码中使用的 API error_code 均登记在 docs/ERROR_CATALOG.md。
# 不做什么：不判断错误码语义是否准确，不扫描非 Python 运行时生成的错误码。
# 允许依赖层：标准库、docs/ERROR_CATALOG.md、app Python 源码。
# 谁不应该 import：正式业务代码、测试夹具、应用入口不应 import 本检查脚本。
"""Validate API error codes against the human-maintained error catalog."""

from __future__ import annotations

import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = ROOT / "docs" / "ERROR_CATALOG.md"
SCAN_DIRS = ("app",)


def rel(path: pathlib.Path) -> str:
    return path.relative_to(ROOT).as_posix()


def catalog_codes() -> set[str]:
    text = CATALOG.read_text(encoding="utf-8")
    return set(re.findall(r"`([a-z][a-z0-9_]*_error|internal_error|http_error)`", text))


def iter_python_files() -> list[pathlib.Path]:
    paths: list[pathlib.Path] = []
    for scan_dir in SCAN_DIRS:
        paths.extend(sorted((ROOT / scan_dir).rglob("*.py")))
    return paths


def called_error_codes(path: pathlib.Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    codes: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "error_payload":
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
            continue
        codes.append((node.lineno, node.args[0].value))
    return codes


def main() -> int:
    if not CATALOG.exists():
        sys.stderr.write(f"[error-catalog] missing catalog: {rel(CATALOG)}\n")
        return 1

    registered = catalog_codes()
    issues: list[str] = []
    used: set[str] = set()
    for path in iter_python_files():
        for line, code in called_error_codes(path):
            used.add(code)
            if code not in registered:
                issues.append(f"{rel(path)}:{line}: error_code `{code}` is not registered in {rel(CATALOG)}")

    stale = sorted(registered - used)
    if issues:
        sys.stderr.write("[error-catalog] unregistered error codes:\n")
        for issue in issues:
            sys.stderr.write(f"  - {issue}\n")
        return 1
    if stale:
        sys.stdout.write("[error-catalog] WARNING：catalog has currently unused error codes:\n")
        for code in stale:
            sys.stdout.write(f"  - {code}\n")
    sys.stdout.write("[error-catalog] all used error codes are registered\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
