# 职责：扫生命周期身份标注——报 非正式区(scripts/devtools/tmp/probes)文件缺 # lifecycle: 身份标注
#       (存量挂 baseline 棘轮·新增阻塞)、标 devtool 却不在 devtools/。
# 不做什么：不删文件、不归档；不再管 expires 日期/superseded 标记那套（理想情况设计·0 使用，已删——
#           旧码清理交「取代纪律」的状态推导：死码 vulture + 重复块 + 晋升门，不靠自愿写日期/贴标）。
# 允许依赖层：标准库、本仓库 git 工作区状态、被扫描的源码注释、lifecycle baseline 文件。
# 谁不应该 import：正式业务代码、测试夹具、应用入口不应 import 本检查脚本。
"""Lifecycle identity-tag check: informal-zone files must carry a `# lifecycle:` tag;
untagged stock is pinned by an only-shrink baseline. The expires-date machinery was
removed — it was an ideal-case design (needs a voluntary, unrewarded `# expires:`) with
zero real usage; stale-code cleanup is handled by supersession discipline (state-derived)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEAD_LINES = 15

# 仅保留"身份标注"识别：temp/t0、devtool、兼容别名——用于判断文件是否已声明身份(has_tag)。
TEMP = re.compile(r"#\s*lifecycle:\s*(t0|temp)\b", re.IGNORECASE)
DEVTOOL = re.compile(r"#\s*lifecycle:\s*devtool\b", re.IGNORECASE)
ALIAS = re.compile(r"#\s*兼容别名")

# 非正式区：住这些目录的 .py MUST 带 # lifecycle: 身份标注。
INFORMAL_ZONE_DIRS = {"scripts", "devtools", "tmp", "probes"}
DEVTOOLS_DIR = "devtools"

# 存量未标注清单(只减不增的条目型 baseline)：新增不在册的未标注文件 → 阻塞；在册的 → 挂账提醒。
BASELINE_PATH = ROOT / ".ai-config" / "config" / "lifecycle_untagged.baseline.json"

# 与项目其它工具同口径排除；scratch/ 是零检查草稿区，一并跳过。
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
    "scratch",
    ".venv-causal",
    "site-packages",
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
    findings: list[tuple[str, str]] = []
    if is_devtool and DEVTOOLS_DIR not in path.relative_to(ROOT).parts:
        findings.append(("DEVTOOL-MISPLACED", "标 # lifecycle: devtool 必须住 devtools/，否则上提或改标 temp"))
    if in_informal_zone(path) and not has_tag and not path.name.startswith("__"):
        findings.append(
            ("UNTAGGED", "非正式区文件缺 # lifecycle: 身份标注(temp/t0 临时件，或 devtool 住 devtools/)")
        )
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

    # 阻塞项：① devtool 错位 ② 非正式区未标注且不在 baseline(棘轮：只减不增)。
    blocking = 0
    seen_untagged: set[str] = set()
    for path, kind, msg in findings:
        relp = rel(path)
        if kind == "UNTAGGED":
            seen_untagged.add(relp)
        baselined = kind == "UNTAGGED" and relp in baseline
        is_block = kind == "DEVTOOL-MISPLACED" or (kind == "UNTAGGED" and not baselined)
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
            "  长寿开发工具  → 移入 devtools/ + # lifecycle: devtool\n"
            "  非正式区新文件 → 补 # lifecycle: 身份标注（勿塞进 baseline；存量挂账只减不增）\n"
        )
        return 1
    if not findings and not stale:
        sys.stdout.write(
            "[lifecycle] 无身份标注债务" + ("（changed 范围）" if changed_mode else "（全量 sweep）") + "\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
