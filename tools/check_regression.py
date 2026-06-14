# 职责：校验 docs/INCIDENTS.md 中 status=fixed 的生产事故，必须有引用其 ID 的回归测试，否则不算修好。
# 不做什么：不运行测试、不验证回归测试是否真能复现该 bug（轻量版只验登记关系，不验证有效性）。
# 允许依赖层：标准库、docs/INCIDENTS.md、tests/ 目录下测试源码。
# 谁不应该 import：正式业务代码、测试夹具、应用入口不应 import 本检查脚本。
"""Forcing function: every fixed incident must be referenced by a regression test."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCIDENTS = ROOT / "docs" / "INCIDENTS.md"
TESTS = ROOT / "tests"

# 表格行：| INC-001 | <根因> | fixed | <修复> |
ROW = re.compile(r"\|\s*INC-(\d+)\s*\|[^|]*\|\s*(open|fixed)\s*\|", re.IGNORECASE)
# 测试里引用：# regression: INC-007 / 测试名含 inc_007 / INC-007
REF = re.compile(r"INC[-_](\d+)", re.IGNORECASE)


def referenced_incident_ids() -> set[str]:
    ids: set[str] = set()
    for path in TESTS.rglob("*.py"):
        ids.update(REF.findall(path.read_text(encoding="utf-8", errors="replace")))
    return ids


def main() -> int:
    if not INCIDENTS.exists():
        # 无事故台账 = 无 fixed 事故待验证；不阻塞，提示建台账。
        try:
            shown = INCIDENTS.relative_to(ROOT).as_posix()
        except ValueError:
            shown = str(INCIDENTS)
        sys.stdout.write(f"[regression] 无 {shown}，跳过（无事故台账可验）\n")
        return 0

    rows = ROW.findall(INCIDENTS.read_text(encoding="utf-8", errors="replace"))
    fixed = {num for num, status in rows if status.lower() == "fixed"}
    missing = sorted(fixed - referenced_incident_ids(), key=int)

    for num in missing:
        sys.stderr.write(f"X INC-{num} 标记 fixed 却无引用其 ID 的回归测试 => 不算修好\n")
    if missing:
        sys.stderr.write(
            "\n[regression] 每个 fixed 事故须有回归测试引用其 ID：\n"
            "  在测试文件写注释 # regression: INC-NNN，或测试函数名含 inc_NNN。\n"
        )
        return 1
    sys.stdout.write(f"[regression] 全部 {len(fixed)} 个 fixed 事故均有回归测试覆盖\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
