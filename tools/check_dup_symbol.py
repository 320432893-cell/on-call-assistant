# 职责：近似重复符号检测——正式代码里顶层 def/class 若与别处同名(或去版本后缀后同词根)，报"取代还是重复?"，
#       强制把"已有同类"摆到台面,逼出取代分叉交人拍板。不靠语义,靠名字(写前上下文 + 名字=最便宜的信号)。
# 不做什么：不删、不判取代/重复(交人);不查类内方法名(同名合法);不管 tests/scratch/archive。
# 允许依赖层：标准库(ast/re/subprocess)、git 工作区状态、被扫描的正式代码。
# 谁不应该 import：正式业务代码、测试夹具、应用入口不应 import 本检查脚本。
"""Near-duplicate top-level symbol detector: a new/changed production def/class whose name
(or version-suffix-stripped stem) matches one elsewhere → surface "supersede or duplicate?"
for the human to rule on. Lexical (name) signal, not semantic. WARN, never blocks."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROD_DIRS = ["app", "market-impact-study"]
SKIP_PARTS = {"__pycache__", "archive", "tests", "scratch", ".venv", ".venv-causal", "site-packages"}
SUFFIX = re.compile(r"_(v?\d+|new|old|legacy|copy|bak|tmp|fix\d*)$", re.IGNORECASE)
# 通用入口/钩子名:多文件同名是常态、非重复嫌疑,排除以压误报。
GENERIC = {"main", "run", "cli", "setup", "build", "parse_args", "lifespan", "health", "index"}


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def prod_files() -> list[Path]:
    out: list[Path] = []
    for name in PROD_DIRS:
        base = ROOT / name
        if base.exists():
            out += [
                p
                for p in base.rglob("*.py")
                if not (set(p.parts) & SKIP_PARTS) and not p.name.startswith("test_")
            ]
    return out


def top_symbols(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    return [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]


def stem(name: str) -> str:
    return SUFFIX.sub("", name)


def changed_files() -> set[Path]:
    names: set[str] = set()
    for args in (
        ["diff", "--name-only", "--diff-filter=ACMR", "--", "*.py"],
        ["diff", "--cached", "--name-only", "--diff-filter=ACMR", "--", "*.py"],
        ["ls-files", "--others", "--exclude-standard", "--", "*.py"],
    ):
        proc = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)
        names.update(line.strip() for line in proc.stdout.splitlines() if line.strip())
    return {ROOT / n for n in names}


def main(argv: list[str]) -> int:
    changed_mode = "--changed" in argv
    index: dict[str, list[tuple[str, Path]]] = {}
    for path in prod_files():
        for sym in top_symbols(path):
            if sym.startswith("__") or sym in GENERIC or len(stem(sym)) < 4:
                continue
            index.setdefault(stem(sym), []).append((sym, path))

    changed = changed_files() if changed_mode else None
    hits: list[tuple[str, list[str], str]] = []
    for stem_name, occ in index.items():
        files = {p for _, p in occ}
        if len(files) < 2:
            continue
        if changed is not None and not (files & changed):
            continue
        names = sorted({s for s, _ in occ})
        hits.append((stem_name, names, ", ".join(sorted(rel(p) for p in files))))

    for stem_name, names, locs in sorted(hits):
        sys.stderr.write(
            f"! [dup-symbol] 词根 '{stem_name}'(符号 {names})出现在多处: {locs} —— 取代还是重复?摆分叉交人拍板。\n"
        )
    if hits:
        sys.stderr.write(
            f"[dup-symbol] {len(hits)} 处近似重复顶层符号(WARN·非阻塞)：同一能力两处=SSOT 双源嫌疑，"
            "MUST 摆分叉交人(取代旧 / 还是新增+理由)，禁静默另写。见 AGENTS.md §5。\n"
        )
    else:
        sys.stdout.write("[dup-symbol] 无近似重复顶层符号" + ("（changed 范围）" if changed_mode else "") + "\n")
    return 0  # WARN：强制触发+surface，删/留判断交人，不阻塞


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
