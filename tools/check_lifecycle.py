# 职责：扫生命周期声明——报 临时件/兼容别名缺机器可读 expires、已过期未清理、旧自由文本待迁移、expires-when 待人工核验、
#       非正式区(scripts/devtools/tmp/probes)文件缺 # lifecycle: 身份标注(存量挂 baseline 棘轮·新增阻塞)、devtool 标注但不在 devtools/。
# 不做什么：不删文件、不归档、不评估 expires-when 文本本身是否仍成立（交人工 sweep）；不判断 devtool 的业务归属。
# 允许依赖层：标准库、本仓库 git 工作区状态、被扫描的源码注释、lifecycle baseline 文件。
# 谁不应该 import：正式业务代码、测试夹具、应用入口不应 import 本检查脚本。
"""Lifecycle debt forcing function: temp/T0/alias files carry a machine-readable expiry;
informal-zone files carry a `# lifecycle:` identity tag (untagged stock pinned by an only-shrink baseline)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEAD_LINES = 15

TEMP = re.compile(r"#\s*lifecycle:\s*(t0|temp)\b", re.IGNORECASE)
DEVTOOL = re.compile(r"#\s*lifecycle:\s*devtool\b", re.IGNORECASE)
ALIAS = re.compile(r"#\s*兼容别名")
EXPIRES = re.compile(r"#\s*expires:\s*(\d{4})-(\d{2})-(\d{2})")
EXPIRES_WHEN = re.compile(r"#\s*expires-when:\s*(.+)")
LEGACY = re.compile(r"删除条件|一次性脚本|临时探针")

# 非正式区：住这些目录的 .py MUST 带 # lifecycle: 身份标注(temp/t0 带 expires，或 devtool 住 devtools/)。
INFORMAL_ZONE_DIRS = {"scripts", "devtools", "tmp", "probes"}
DEVTOOLS_DIR = "devtools"

# 存量未标注清单(只减不增的条目型 baseline)：新增不在册的未标注文件 → 阻塞；在册的 → 挂账提醒。
# 同 .secrets.baseline / .basedpyright-baseline.json 惯例：提交进仓库，作为棘轮记录。
BASELINE_PATH = ROOT / ".ai-config" / "config" / "lifecycle_untagged.baseline.json"

# 定义这些标记串的目录会被命中（误报源），与项目其它工具同口径排除。
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


def in_informal_zone(path: Path) -> bool:
    return bool(set(path.relative_to(ROOT).parts) & INFORMAL_ZONE_DIRS)


def scan(path: Path) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    head = "\n".join(text.splitlines()[:HEAD_LINES])
    is_temp = bool(TEMP.search(head)) or bool(ALIAS.search(text))
    is_devtool = bool(DEVTOOL.search(head))
    has_tag = is_temp or is_devtool
    has_expiry = bool(EXPIRES.search(text)) or bool(EXPIRES_WHEN.search(text))
    findings: list[tuple[str, str]] = []
    if is_temp and not has_expiry:
        findings.append(("MISSING-EXPIRY", "临时件/兼容别名缺机器可读 # expires: 或 # expires-when:"))
    if is_devtool and DEVTOOLS_DIR not in path.relative_to(ROOT).parts:
        findings.append(("DEVTOOL-MISPLACED", "标 # lifecycle: devtool 必须住 devtools/，否则上提或改标 temp"))
    if in_informal_zone(path) and not has_tag and not path.name.startswith("__"):
        findings.append(
            ("UNTAGGED", "非正式区文件缺 # lifecycle: 身份标注(temp/t0 带 expires，或 devtool 住 devtools/)")
        )
    if LEGACY.search(head) and not is_temp and not is_devtool and not has_expiry:
        findings.append(("BACKLOG", "旧自由文本生命周期声明，迁到 # expires: 或 # expires-when:"))
    if (match := EXPIRES.search(text)) and date(int(match[1]), int(match[2]), int(match[3])) < datetime.now(UTC).date():
        findings.append(("EXPIRED", f"已过期 {match[1]}-{match[2]}-{match[3]}，应清理或续期"))
    if when := EXPIRES_WHEN.search(text):
        findings.append(("MANUAL", f"expires-when 待人工核验：{when[1].strip()}"))
    return findings


def load_baseline() -> set[str]:
    if not BASELINE_PATH.exists():
        return set()
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    return set(data.get("entries", []))


def write_baseline(entries: set[str]) -> None:
    payload = {
        "reason": "存量非正式区(scripts/ 等)文件在身份规则上线前未标 # lifecycle:",
        "clear_by": "各文件随其切片闭包或项目收尾补标 temp/devtool 或删除，目标降到 0 条",
        "registered": "2026-06-15",
        "ratchet": "只减不增：新增未标注文件不得入册(CI 阻塞)；修好的条目应从此清单移除",
        "entries": sorted(entries),
    }
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    if "--update-baseline" in argv:
        untagged = {rel(p) for p in all_py_files() for kind, _ in scan(p) if kind == "UNTAGGED"}
        write_baseline(untagged)
        sys.stdout.write(f"[lifecycle] baseline 已写入 {rel(BASELINE_PATH)}：{len(untagged)} 条存量未标注\n")
        return 0

    changed_mode = "--changed" in argv
    targets = changed_py_files() if changed_mode else all_py_files()
    baseline = load_baseline()
    findings = [(path, kind, msg) for path in targets for kind, msg in scan(path)]

    # 阻塞项：① changed 模式新增临时件缺 expiry ② devtool 错位 ③ 非正式区未标注且不在 baseline(棘轮：只减不增)。
    blocking = 0
    seen_untagged: set[str] = set()
    for path, kind, msg in findings:
        relp = rel(path)
        if kind == "UNTAGGED":
            seen_untagged.add(relp)
        baselined = kind == "UNTAGGED" and relp in baseline
        is_block = (
            (kind == "MISSING-EXPIRY" and changed_mode)
            or kind == "DEVTOOL-MISPLACED"
            or (kind == "UNTAGGED" and not baselined)
        )
        if is_block:
            blocking += 1
        suffix = "（baseline 挂账·只减不增）" if baselined else ""
        stream = sys.stderr if is_block else sys.stdout
        stream.write(f"{'X' if is_block else '!'} [{kind}] {relp}: {msg}{suffix}\n")

    # 棘轮收紧提醒(仅全量)：在册却已修好/已删的条目应从 baseline 移除。
    stale = sorted(b for b in baseline if b not in seen_untagged) if not changed_mode else []
    for entry in stale:
        sys.stdout.write(
            f"! [BASELINE-STALE] {entry}: 已不再未标注，可从 lifecycle baseline 移除（运行 --update-baseline）\n"
        )

    if blocking:
        sys.stderr.write(
            "\n[lifecycle] 阻塞项必须修复：\n"
            "  临时件        → # lifecycle: temp + # expires: 2026-07-01（或 # expires-when: <条件>）\n"
            "  长寿开发工具  → 移入 devtools/ + # lifecycle: devtool（免过期）\n"
            "  非正式区新文件 → 补上述身份标注（勿塞进 baseline；存量挂账只减不增）\n"
        )
        return 1
    if not findings and not stale:
        sys.stdout.write(
            "[lifecycle] 无生命周期债务" + ("（changed 范围）" if changed_mode else "（全量 sweep）") + "\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
