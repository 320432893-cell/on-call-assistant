#!/usr/bin/env python3
"""Unified static-check entrypoint for local hooks, manual runs, and CI."""

from __future__ import annotations

import argparse
import fnmatch
import os
import pathlib
import shlex
import subprocess
import sys
import tomllib
from collections.abc import Sequence

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / ".ai-config" / "tooling.registry.toml"
LOCAL_UV_CACHE = ROOT / ".uv-cache"
LOCAL_HOME = ROOT / ".cache" / "home"
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
    "rule-tool-contracts": "uv run python .ai-config/check_rule_tool_contracts.py",
    "semgrep": "uv run semgrep --disable-version-check --metrics=off --config .semgrep --no-git-ignore app scripts market-impact-study tests tools .ai-config .ai-hooks",
    "dependency-change-approval": "python3 tools/check.py dependency-change-approval",
    "pip-audit": "uv run pip-audit --strict",
    "rag-drift": "uv run python scripts/check_rag_drift.py",
    "market-impact-validation": "uv run python market-impact-study/validate_market_outputs.py",
    "detect-secrets-scan": "uv run detect-secrets scan --baseline .secrets.baseline --exclude-files '^(uv\\.lock|\\.secrets\\.baseline|\\.ai-config/settings\\.json\\.template)$'",
    "detect-secrets-audit": "uv run detect-secrets audit .secrets.baseline --report",
    "pytest": "uv run pytest tests",
    "ruff-staged": "uv run ruff check --no-fix --force-exclude",
    "ruff-check": "uv run ruff check .",
    "ruff-format-check": "uv run ruff format --check .",
    "basedpyright": "uv run basedpyright",
    "market-impact-basedpyright": "uv run basedpyright market-impact-study/build_management_signal_tables.py --baselinefile market-impact-study/.basedpyright-baseline.json",
    "dirty-diff-review": "python3 .ai-config/dirty_diff_review.py",
    "radon-cc": "uv run radon cc app scripts market-impact-study -s -n C",
    "radon-mi": "uv run radon mi app scripts market-impact-study -s",
    "vulture": "uv run vulture app scripts market-impact-study --min-confidence 80",
    "deptry": "uv run deptry .",
}

HOOK_TESTS = [
    "bash .ai-hooks/tests/test_bash_safety_hooks.sh",
    "bash .ai-hooks/tests/test_dirty_static_review.sh",
    "bash .ai-hooks/tests/test_reference_drift_hooks.sh",
    "bash .ai-hooks/tests/test_rag_hygiene.sh",
]

PROFILES: dict[str, list[str]] = {
    "quick": ["coverage-audit", "python-compile", "import-linter", "rule-tool-contracts", "ruff-staged", "semgrep"],
    "manual": ["ruff-check", "ruff-format-check", "basedpyright", "pip-audit"],
    "deep": ["radon-cc", "radon-mi", "vulture", "deptry"],
    "ci": [
        "python-compile",
        "import-linter",
        "rule-tool-contracts",
        "ai-hook-tests",
        "semgrep",
        "pip-audit",
        "rag-drift",
        "detect-secrets",
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


def run_command(label: str, command: Sequence[str] | str) -> int:
    print(f"[check] {label}", flush=True)
    env = os.environ.copy()
    env["HOME"] = str(LOCAL_HOME)
    env["UV_CACHE_DIR"] = str(LOCAL_UV_CACHE)
    if label == "pytest" or label.startswith("changed:pytest"):
        env["DEBUG"] = "false"
    if isinstance(command, str):
        return subprocess.run(shlex.split(command), cwd=ROOT, env=env, check=False).returncode
    return subprocess.run(command, cwd=ROOT, env=env, check=False).returncode


def run_item(item: str) -> int:
    if item == "ai-hook-tests":
        return run_many((f"hook-test:{index}", command) for index, command in enumerate(HOOK_TESTS, start=1))
    if item == "changed":
        return run_changed()
    if item == "coverage-audit":
        return run_coverage_audit()
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
        choices=[*PROFILES, *COMMANDS, "ai-hook-tests", "detect-secrets", "list"],
    )
    args = parser.parse_args()

    os.chdir(ROOT)
    if args.target == "list":
        print_list()
        return 0
    if args.target in PROFILES:
        return run_profile(args.target)
    return run_item(args.target)


if __name__ == "__main__":
    sys.exit(main())
