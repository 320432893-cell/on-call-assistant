#!/usr/bin/env python3
# 职责：统一承载本仓库本地 hook、手动检查、CI 复用的静态检查入口。
# 不做什么：不替代业务语义审查，不直接修改源码或自动修复检查结果。
# 允许依赖层：标准库、项目工具脚本、.ai-config 工具契约配置、外部静态检查 CLI。
# 谁不应该 import：正式业务代码、测试夹具、一次性数据处理脚本不应 import 本入口。
"""Unified static-check entrypoint for local hooks, manual runs, and CI."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import pathlib
import shlex
import subprocess
import sys
import time
import tomllib
from collections.abc import Sequence
from datetime import UTC, datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / ".ai-config" / "config" / "tooling.registry.toml"
LOCAL_UV_CACHE = ROOT / ".uv-cache"
LOCAL_HOME = ROOT / ".cache" / "home"
RUN_LOG = ROOT / ".cache" / "check-runs.jsonl"  # 度量日志（.gitignore 内），每次检查记一行供 `check.py debt` 汇总
FIXED_QUALITY_CODE_DIRS = {"app", "scripts", "market-impact-study"}
SUPPORT_CODE_DIRS = {"tests", "tools"}
IGNORED_CODE_DIRS = {
    ".cache",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
    "market-impact-study/data",
    "on_call_assistant.egg-info",
}
CODE_SUFFIXES = {".py", ".html", ".yml", ".yaml", ".toml"}
CONTRACT_TRIGGER_PATTERNS = (
    ".ai-config/**",
    ".ai-hooks/**",
    ".github/workflows/**",
    ".importlinter",
    ".pre-commit-config.yaml",
    ".ruff.toml",
    ".semgrep/**",
    "AGENTS.md",
    "pyproject.toml",
    "tools/check.py",
    "uv.lock",
)


COMMANDS: dict[str, str] = {
    "python-compile": "uv run python -m compileall -q app scripts market-impact-study tests tools",
    "coverage-audit": "python3 tools/check.py coverage-audit",
    "changed": "python3 tools/check.py changed",
    "import-linter": "uv run lint-imports --config .importlinter --no-cache",
    "rule-tool-contracts": "uv run python .ai-config/tools/check_rule_tool_contracts.py",
    "semgrep": "uv run semgrep --disable-version-check --metrics=off --config .semgrep --no-git-ignore app scripts market-impact-study tests tools .ai-config .ai-hooks",
    "dependency-change-approval": "python3 tools/check.py dependency-change-approval",
    "code-identity": "python3 tools/check_code_identity.py",
    "error-catalog": "python3 tools/check_error_catalog.py",
    "pip-audit": "uv run pip-audit --strict",
    "rag-drift": "uv run python scripts/check_rag_drift.py",
    "market-impact-validation": "uv run python market-impact-study/validate_market_outputs.py",
    "test-meta": "python3 tools/check.py test-meta",
    "detect-secrets-scan": "uv run detect-secrets scan --baseline .secrets.baseline --exclude-files '^(uv\\.lock|\\.secrets\\.baseline|\\.ai-config/config/settings\\.json\\.template)$'",
    "detect-secrets-audit": "uv run detect-secrets audit .secrets.baseline --report",
    "pytest": "uv run pytest tests",
    "ruff-staged": "uv run ruff check --no-fix --force-exclude",
    "ruff-check": "uv run ruff check .",
    "ruff-format-check": "uv run ruff format --check .",
    "basedpyright": "uv run basedpyright",
    "market-impact-basedpyright": "uv run basedpyright market-impact-study/build_management_signal_tables.py --baselinefile market-impact-study/.basedpyright-baseline.json",
    "dirty-diff-review": "python3 .ai-config/tools/dirty_diff_review.py",
    "radon-cc": "uv run radon cc app scripts market-impact-study -s -n C",
    "radon-mi": "uv run radon mi app scripts market-impact-study -s",
    "vulture": "uv run vulture app scripts market-impact-study --min-confidence 80",
    "deptry": "uv run deptry .",
    "module-boundary": "python3 tools/check_module_boundary.py",
    "module-boundary-changed": "python3 tools/check_module_boundary.py --changed",
    "lifecycle": "python3 tools/check_lifecycle.py",
    "lifecycle-changed": "python3 tools/check_lifecycle.py --changed",
    "regression": "python3 tools/check_regression.py",
    "debt": "python3 tools/check.py debt",
}

HOOK_TESTS = [
    "bash .ai-hooks/tests/test_bash_safety_hooks.sh",
    "bash .ai-hooks/tests/test_dirty_static_review.sh",
    "bash .ai-hooks/tests/test_reference_drift_hooks.sh",
    "bash .ai-hooks/tests/test_rag_hygiene.sh",
]

PROFILES: dict[str, list[str]] = {
    "quick": ["coverage-audit", "python-compile", "import-linter", "rule-tool-contracts", "ruff-staged", "semgrep"],
    "completion": ["rule-tool-contracts"],
    "manual": ["ruff-check", "ruff-format-check", "basedpyright", "pip-audit"],
    "deep": ["radon-cc", "radon-mi", "vulture", "deptry", "module-boundary", "code-identity"],
    "ci": [
        "python-compile",
        "import-linter",
        "rule-tool-contracts",
        "ai-hook-tests",
        "semgrep",
        "pip-audit",
        "rag-drift",
        "detect-secrets",
        "lifecycle",
        "regression",
        "pytest",
    ],
}


def rel(path: pathlib.Path) -> str:
    return path.relative_to(ROOT).as_posix()


def is_ignored_path(path: pathlib.Path) -> bool:
    path_str = rel(path)
    parts = path_str.split("/")
    return any(path_str == ignored or path_str.startswith(f"{ignored}/") for ignored in IGNORED_CODE_DIRS) or any(
        part == "__pycache__" for part in parts
    )


def is_code_file(path: pathlib.Path) -> bool:
    return path.is_file() and path.suffix in CODE_SUFFIXES and not is_ignored_path(path)


def is_changed_ruff_path(path: pathlib.Path) -> bool:
    path_str = rel(path)
    if path_str.startswith("."):
        return False
    if "/" not in path_str:
        return path.suffix == ".py"
    return path_str.split("/", maxsplit=1)[0] in FIXED_QUALITY_CODE_DIRS | SUPPORT_CODE_DIRS


def git_changed_names(args: Sequence[str]) -> tuple[int, list[str], str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    names = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return proc.returncode, names, proc.stderr.strip()


def load_pytest_file_patterns() -> tuple[list[str], list[str]]:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    options = pyproject.get("tool", {}).get("pytest", {}).get("ini_options", {})
    testpaths = options.get("testpaths", ["tests"])
    python_files = options.get("python_files", ["test_*.py"])
    return list(testpaths), list(python_files)


def is_direct_pytest_file(name: str) -> bool:
    testpaths, python_files = load_pytest_file_patterns()
    if not name.endswith(".py"):
        return False
    return any(
        name.startswith(f"{testpath.rstrip('/')}/")
        and any(fnmatch.fnmatch(pathlib.PurePosixPath(name).name, pattern) for pattern in python_files)
        for testpath in testpaths
    )


def collect_test_file_names() -> set[str]:
    testpaths, python_files = load_pytest_file_patterns()
    names: set[str] = set()
    for testpath in testpaths:
        base = ROOT / testpath.rstrip("/")
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            name = pathlib.PurePosixPath(rel(path)).name
            if any(fnmatch.fnmatch(name, pattern) for pattern in python_files):
                names.add(rel(path))
    return names


def collect_changed_names() -> tuple[int, list[str]]:
    commands = [
        ["diff", "--name-only", "--diff-filter=ACMRD"],
        ["diff", "--cached", "--name-only", "--diff-filter=ACMRD"],
        ["ls-files", "--others", "--exclude-standard"],
    ]
    names: list[str] = []
    for args in commands:
        rc, batch, err = git_changed_names(args)
        if rc != 0:
            print(f"[check] changed: git {' '.join(args)} failed: {err}", file=sys.stderr)
            return rc, []
        names.extend(batch)
    return 0, sorted(set(names))


def load_registry() -> dict:
    return tomllib.loads(REGISTRY.read_text(encoding="utf-8"))


def run_dependency_change_approval() -> int:
    rc, names, err = git_changed_names(
        ["diff", "--cached", "--name-only", "--diff-filter=ACMR", "--", "pyproject.toml", "uv.lock"]
    )
    if rc != 0:
        print(f"[check] dependency-change-approval: git diff failed: {err}", file=sys.stderr)
        return rc
    if not names:
        print("[check] dependency-change-approval: no staged dependency or lock changes")
        return 0
    if os.environ.get("ONCALL_ALLOW_DEPENDENCY_CHANGE") in {"1", "true", "TRUE", "yes", "YES"}:
        print("[check] dependency-change-approval: explicit approval env present")
        return 0

    print("[check] dependency-change-approval blocked staged dependency/tooling files:", file=sys.stderr)
    for name in names:
        print(f"  - {name}", file=sys.stderr)
    print(
        "[check] confirm purpose, install/download scope, lock/CI/pre-commit impact, and fallback first; "
        "then rerun with ONCALL_ALLOW_DEPENDENCY_CHANGE=1.",
        file=sys.stderr,
    )
    return 1


def run_ruff_staged() -> int:
    rc, names, err = git_changed_names(["diff", "--cached", "--name-only", "--diff-filter=ACMR", "--", "*.py"])
    if rc != 0:
        print(f"[check] ruff-staged: git diff failed: {err}", file=sys.stderr)
        return rc
    if not names:
        print("[check] ruff-staged: no staged Python files")
        return 0
    return run_command("ruff-staged", ["uv", "run", "ruff", "check", "--no-fix", "--force-exclude", *names])


def path_matches(path: pathlib.Path, patterns: Sequence[str]) -> bool:
    path_str = rel(path)
    return any(fnmatch.fnmatch(path_str, pattern) for pattern in patterns)


def name_matches(name: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def trigger_data_present(trigger: dict) -> bool:
    return all((ROOT / path).exists() for path in trigger.get("required_paths", []))


def run_path_triggers(changed_paths: Sequence[pathlib.Path]) -> int:
    registry = load_registry()
    status = 0
    for trigger in registry.get("path_triggers", []):
        if not any(path_matches(path, trigger.get("paths", [])) for path in changed_paths):
            continue
        run_mode = trigger.get("run_mode", "manual")
        if run_mode == "manual":
            print(f"[check] path-trigger:{trigger['id']}: manual only")
            continue
        if run_mode == "changed":
            result = run_item(trigger["tool"])
            if result != 0 and status == 0:
                status = result
            continue
        if run_mode == "changed-data-present" and not trigger_data_present(trigger):
            print(f"[check] path-trigger:{trigger['id']}: skipped, required data files are absent")
            continue
        tool_id = trigger.get("tool")
        if not tool_id:
            print(f"[check] path-trigger:{trigger['id']}: missing tool", file=sys.stderr)
            status = status or 2
            continue
        result = run_item(tool_id)
        if result != 0 and status == 0:
            status = result
    return status


def run_changed() -> int:
    rc, changed_names = collect_changed_names()
    if rc != 0:
        return rc
    changed_paths = [ROOT / name for name in changed_names if (ROOT / name).exists()]
    code_paths = [path for path in changed_paths if is_code_file(path)]
    python_paths = [path for path in code_paths if path.suffix == ".py" and is_changed_ruff_path(path)]
    contract_changed = any(name_matches(name, CONTRACT_TRIGGER_PATTERNS) for name in changed_names)
    hook_changed = any(name.startswith(".ai-hooks/") for name in changed_names)
    if not code_paths and not contract_changed and not hook_changed:
        print("[check] changed: no changed code files")
        return 0

    status = 0
    if code_paths:
        status = run_coverage_audit()
    if python_paths:
        status = run_command("changed:python-compile", COMMANDS["python-compile"]) or status
        status = run_item("code-identity") or status
        status = run_item("module-boundary-changed") or status
        status = run_item("lifecycle-changed") or status
        status = run_item("test-meta") or status
        status = run_item("error-catalog") or status
        status = (
            run_command(
                "changed:ruff-check",
                ["uv", "run", "ruff", "check", "--no-fix", "--force-exclude", *[rel(path) for path in python_paths]],
            )
            or status
        )
        status = (
            run_command(
                "changed:ruff-format",
                ["uv", "run", "ruff", "format", "--check", *[rel(path) for path in python_paths]],
            )
            or status
        )
        status = run_command("changed:import-linter", COMMANDS["import-linter"]) or status

    if code_paths:
        status = run_command("changed:semgrep", COMMANDS["semgrep"]) or status

    code_names = {rel(path) for path in code_paths}
    if any(name.startswith("market-impact-study/") for name in code_names):
        status = (
            run_command("changed:market-impact-tests", ["uv", "run", "pytest", "tests/test_market_impact_study.py"])
            or status
        )
        status = run_item("market-impact-basedpyright") or status
    direct_tests = sorted(name for name in code_names if is_direct_pytest_file(name))
    if direct_tests:
        status = run_command("changed:pytest", ["uv", "run", "pytest", *direct_tests]) or status
    if contract_changed:
        status = run_item("rule-tool-contracts") or status
    if hook_changed:
        status = run_item("ai-hook-tests") or status

    return run_path_triggers(code_paths) or status


def discover_code_dirs() -> set[str]:
    dirs: set[str] = set()
    for path in ROOT.rglob("*.py"):
        if is_ignored_path(path):
            continue
        path_str = rel(path)
        if path_str.startswith("."):
            continue
        if "/" not in path_str:
            continue
        dirs.add(path_str.split("/", maxsplit=1)[0])
    return dirs


def run_test_meta() -> int:
    # 新增/改动测试阻塞，存量测试只 WARNING，避免历史 backlog 淹没新增 oracle 质量。
    rc, changed_names = collect_changed_names()
    if rc != 0:
        return rc
    changed = set(changed_names)
    test_files = sorted(collect_test_file_names())
    required_markers = (
        ("生命周期", "缺生命周期说明（T0 删除条件或持久维护）"),
        ("覆盖的业务场景", "缺覆盖的业务场景说明"),
        ("依赖的服务/环境", "缺依赖的服务/环境说明"),
        ("运行方式", "缺运行方式说明"),
    )
    oracle_markers = ("用时", "耗时", "elapsed", "duration", "期望:", "实际:", "[ENV_ERROR]", "[LOGIC_ERROR]")
    blocking: list[str] = []
    warnings: list[str] = []
    for name in test_files:
        path = ROOT / name
        text = path.read_text(encoding="utf-8", errors="ignore")
        missing = [message for marker, message in required_markers if marker not in text]
        if not any(marker in text for marker in oracle_markers):
            missing.append("缺 oracle 输出形状（用时/期望实际/ENV_ERROR/LOGIC_ERROR 至少一类）")
        if not missing:
            continue
        target = blocking if name in changed else warnings
        target.extend(f"{name}: {message}" for message in missing)

    if warnings:
        print("[check] test-meta WARNING（存量测试不阻塞）：", file=sys.stderr)
        for warning in warnings:
            print(f"  - {warning}", file=sys.stderr)
    if blocking:
        print("[check] test-meta failed（本次新增/改动测试必须可复现）：", file=sys.stderr)
        for issue in blocking:
            print(f"  - {issue}", file=sys.stderr)
        print(
            "\n在测试文件顶部添加：\n"
            "  # 生命周期：T0 一次性（删除条件：XXX）/ 持久维护\n"
            "  # 覆盖的业务场景：\n"
            "  # 依赖的服务/环境：\n"
            "  # 运行方式：\n"
            "并让输出或断言信息包含用时、期望/实际或 ENV/LOGIC 错误分类。",
            file=sys.stderr,
        )
        return 1
    if warnings:
        return 0
    print("[check] test-meta: 测试文件均声明复现元信息和 oracle 输出形状")
    return 0


def run_coverage_audit() -> int:
    code_dirs = discover_code_dirs()
    accepted = FIXED_QUALITY_CODE_DIRS | SUPPORT_CODE_DIRS
    missing = sorted(code_dirs - accepted)
    issues: list[str] = []
    if missing:
        issues.append(f"new Python code directories are not mapped to the quality gate: {', '.join(missing)}")
    for path in sorted(FIXED_QUALITY_CODE_DIRS | SUPPORT_CODE_DIRS):
        for command_name in ("python-compile", "semgrep", "radon-cc", "radon-mi", "vulture"):
            if path in SUPPORT_CODE_DIRS and command_name in {"radon-cc", "radon-mi", "vulture"}:
                continue
            if path not in COMMANDS[command_name]:
                issues.append(f"{command_name} does not include required code path: {path}")
    if issues:
        print("[check] coverage-audit failed:", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1
    print("[check] coverage-audit: fixed code directories are covered")
    return 0


def log_run(label: str, returncode: int, seconds: float) -> None:
    # 度量：把每次检查的 过/挂/耗时 记一行 JSONL，供 `check.py debt` 汇总通过率。
    # best-effort：日志失败绝不影响检查本身（检查是门禁，度量是旁路）。
    try:
        RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "label": label,
            "ok": returncode == 0,
            "ms": round(seconds * 1000),
        }
        with RUN_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def run_command(label: str, command: Sequence[str] | str) -> int:
    print(f"[check] {label}", flush=True)
    env = os.environ.copy()
    env["HOME"] = str(LOCAL_HOME)
    env["UV_CACHE_DIR"] = str(LOCAL_UV_CACHE)
    if label == "pytest" or label.startswith("changed:pytest"):
        env["DEBUG"] = "false"
    args = shlex.split(command) if isinstance(command, str) else command
    start = time.monotonic()
    returncode = subprocess.run(args, cwd=ROOT, env=env, check=False).returncode
    log_run(label, returncode, time.monotonic() - start)
    return returncode


def run_item(item: str) -> int:
    if item == "ai-hook-tests":
        return run_many((f"hook-test:{index}", command) for index, command in enumerate(HOOK_TESTS, start=1))
    if item == "changed":
        return run_changed()
    if item == "coverage-audit":
        return run_coverage_audit()
    if item == "test-meta":
        return run_test_meta()
    if item == "debt":
        return run_debt()
    if item == "dependency-change-approval":
        return run_dependency_change_approval()
    if item == "ruff-staged":
        return run_ruff_staged()
    if item == "detect-secrets":
        return run_many(
            [
                ("detect-secrets-scan", COMMANDS["detect-secrets-scan"]),
                ("detect-secrets-audit", COMMANDS["detect-secrets-audit"]),
            ]
        )
    command = COMMANDS.get(item)
    if command is None:
        print(f"[check] unknown item: {item}", file=sys.stderr)
        return 2
    return run_command(item, command)


def run_many(items: Sequence[tuple[str, Sequence[str] | str]] | list[tuple[str, Sequence[str] | str]]) -> int:
    status = 0
    for label, command in items:
        result = run_command(label, command)
        if result != 0 and status == 0:
            status = result
    return status


def print_pass_rates(limit: int = 200) -> None:
    # 从度量日志汇总每个检查的通过率（近 limit 条运行），低通过率=AI 在这类检查上反复返工。
    if not RUN_LOG.exists():
        print("  检查通过率: 暂无日志（跑几次 check.py 后再看）")
        return
    lines = RUN_LOG.read_text(encoding="utf-8").splitlines()[-limit:]
    stats: dict[str, list[bool]] = {}
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        stats.setdefault(str(record.get("label")), []).append(bool(record.get("ok")))
    if not stats:
        print("  检查通过率: 日志为空")
        return
    print(f"  检查通过率（近 {len(lines)} 条运行，低=反复返工的检查）:")
    for label in sorted(stats):
        runs = stats[label]
        rate = round(100 * sum(runs) / len(runs))
        print(f"    {label:26} {rate:3d}%  ({sum(runs)}/{len(runs)})")


def run_debt() -> int:
    # 度量：规则系统健康度只读汇总（非门禁）。聚合已有信号——relaxed 工具、生命周期债、回归债、检查通过率。
    print("[debt] 规则系统健康度（只读汇总，非门禁）", flush=True)
    registry = tomllib.loads(REGISTRY.read_text(encoding="utf-8"))
    relaxed = [tool["id"] for tool in registry.get("tools", []) if tool.get("relaxed")]
    print(f"  relaxed 工具 {len(relaxed)}: {', '.join(relaxed) or '无'}")

    lifecycle = subprocess.run(
        [sys.executable, "tools/check_lifecycle.py"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    for tag in ("EXPIRED", "MISSING-EXPIRY", "BACKLOG", "MANUAL"):
        print(f"  lifecycle {tag:13} {lifecycle.stdout.count('[' + tag + ']')}")

    regression = subprocess.run(
        [sys.executable, "tools/check_regression.py"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    missing = (regression.stdout + regression.stderr).count("X INC-")
    print(f"  regression fixed 缺测试: {missing}")

    print_pass_rates()
    return 0


def _module_scaffold(kind: str, name: str) -> str:
    # 生成：吐出已带四项职责块的骨架，AI 只填业务体，一次过 module-boundary。依赖层按目录身份表预填。
    blocks = {
        "service": (
            f"# 职责：TODO 一句话——{name} 业务模块做什么\n"
            "# 不做什么：TODO 至少一项（不承载 CLI/UI 入口、不做持久化主逻辑）\n"
            "# 允许依赖层：app/core、app/models、app/config\n"
            "# 谁不应该 import：tools/、tests/、scripts/ 不应反向 import 本业务模块\n"
            f'"""TODO: {name} service。"""\n\nfrom __future__ import annotations\n'
        ),
        "core": (
            f"# 职责：TODO {name} 跨业务复用的基础能力\n"
            "# 不做什么：TODO 至少一项（不含具体业务规则、不做一次性流程）\n"
            "# 允许依赖层：标准库、app/config；可被任何正式层 import\n"
            "# 谁不应该 import：入口/测试可调用，但本文件不反向依赖它们\n"
            f'"""TODO: {name} core capability。"""\n\nfrom __future__ import annotations\n'
        ),
        "tool": (
            f"# 职责：TODO {name} 入口——解析参数→调用正式能力→输出→退出码\n"
            "# 不做什么：不含业务规则/核心流程/持久化主逻辑（放 app/）\n"
            "# 允许依赖层：标准库、app/ 正式能力\n"
            "# 谁不应该 import：正式业务代码、测试夹具不应 import 本入口\n"
            f'"""TODO: {name} entrypoint。"""\n\nfrom __future__ import annotations\n'
        ),
    }
    return blocks[kind]


def _test_scaffold(name: str) -> str:
    # 生成：吐出带 test-meta 头 + oracle 标记的回归测试骨架，默认 skip 不污染套件，填完去掉 skip。
    return (
        "# 生命周期：持久维护\n"
        f"# 覆盖的业务场景：TODO {name} 验证什么业务行为\n"
        "# 依赖的服务/环境：TODO 本地 Python / 需要的服务\n"
        f"# 运行方式：uv run pytest tests/test_{name}.py\n"
        "# oracle 输出形状：断言失败给出 期望/实际；pytest 汇总用时。\n"
        f'"""TODO: {name} 的回归测试。"""\n\n'
        "import pytest\n\n\n"
        f'@pytest.mark.skip(reason="TODO: 实现 {name} 业务场景测试")\n'
        f"def test_{name}_placeholder() -> None:\n"
        '    raise AssertionError("期望: TODO | 实际: 尚未实现")\n'
    )


def run_new(rest: list[str]) -> int:
    usage = "用法: python3 tools/check.py new <service|core|tool|test> <name>"
    try:
        kind, name = rest
    except ValueError:
        print(usage, file=sys.stderr)
        return 2
    if kind not in {"service", "core", "tool", "test"} or not name.isidentifier():
        print(usage, file=sys.stderr)
        return 2
    module_dir = {"service": "app/services", "core": "app/core", "tool": "tools"}
    targets: list[tuple[pathlib.Path, str]] = []
    if kind == "test":
        targets.append((ROOT / "tests" / f"test_{name}.py", _test_scaffold(name)))
    else:
        targets.append((ROOT / module_dir[kind] / f"{name}.py", _module_scaffold(kind, name)))
        if kind == "service":  # 业务模块默认配回归测试，回归债从源头不欠
            targets.append((ROOT / "tests" / f"test_{name}.py", _test_scaffold(name)))
    for path, _ in targets:
        if path.exists():
            print(f"[new] 已存在，拒绝覆盖：{path.relative_to(ROOT)}", file=sys.stderr)
            return 1
    for path, content in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"[new] 生成 {path.relative_to(ROOT)}")
    print("[new] 已带好职责块/测试头，填业务体即可，一次过 module-boundary/test-meta。")
    return 0


def run_profile(profile: str) -> int:
    status = 0
    for item in PROFILES[profile]:
        result = run_item(item)
        if result != 0 and status == 0:
            status = result
    return status


def print_list() -> None:
    print("Profiles:")
    for profile, items in PROFILES.items():
        print(f"  {profile}: {', '.join(items)}")
    print("Commands:")
    for name, command in COMMANDS.items():
        print(f"  {name}: {command}")
    print("Hook tests:")
    for command in HOOK_TESTS:
        print(f"  {command}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target",
        nargs="?",
        default="quick",
        choices=[*PROFILES, *COMMANDS, "ai-hook-tests", "detect-secrets", "list", "new"],
    )
    parser.add_argument("rest", nargs="*", help="`new <kind> <name>` 的额外参数")
    args = parser.parse_args()

    os.chdir(ROOT)
    if args.target == "list":
        print_list()
        return 0
    if args.target == "new":
        return run_new(args.rest)
    if args.target in PROFILES:
        return run_profile(args.target)
    return run_item(args.target)


if __name__ == "__main__":
    sys.exit(main())
