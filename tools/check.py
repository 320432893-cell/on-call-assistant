#!/usr/bin/env python3
"""Unified static-check entrypoint for local hooks, manual runs, and CI."""

from __future__ import annotations

import argparse
import os
import pathlib
import shlex
import subprocess
import sys
from collections.abc import Sequence

ROOT = pathlib.Path(__file__).resolve().parents[1]


COMMANDS: dict[str, str] = {
    "python-compile": "uv run python -m compileall -q app scripts",
    "import-linter": "uv run lint-imports --config .importlinter --no-cache",
    "rule-tool-contracts": "uv run python .ai-config/check_rule_tool_contracts.py",
    "semgrep": "uv run semgrep --config .semgrep app scripts .ai-config .ai-hooks",
    "pip-audit": "uv run pip-audit --strict",
    "rag-drift": "uv run python scripts/check_rag_drift.py",
    "detect-secrets-pre-commit": "uv run pre-commit run detect-secrets --all-files",
    "detect-secrets-audit": "uv run detect-secrets audit .secrets.baseline --report",
    "pytest-coverage": "uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=35",
    "ruff-check": "uv run ruff check .",
    "ruff-format-check": "uv run ruff format --check .",
    "basedpyright": "uv run basedpyright",
    "dirty-diff-review": "python3 .ai-config/dirty_diff_review.py",
    "radon-cc": "uv run radon cc app scripts -s -n C",
    "radon-mi": "uv run radon mi app scripts -s",
    "vulture": "uv run vulture app scripts --min-confidence 80",
    "deptry": "uv run deptry .",
}

HOOK_TESTS = [
    "bash .ai-hooks/tests/test_bash_safety_hooks.sh",
    "bash .ai-hooks/tests/test_dirty_static_review.sh",
    "bash .ai-hooks/tests/test_reference_drift_hooks.sh",
    "bash .ai-hooks/tests/test_rag_hygiene.sh",
]

PROFILES: dict[str, list[str]] = {
    "quick": ["python-compile", "import-linter", "rule-tool-contracts", "semgrep"],
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
        "pytest-coverage",
    ],
}


def run_command(label: str, command: Sequence[str] | str) -> int:
    print(f"[check] {label}", flush=True)
    if isinstance(command, str):
        return subprocess.run(shlex.split(command), cwd=ROOT, check=False).returncode
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def run_item(item: str) -> int:
    if item == "ai-hook-tests":
        return run_many((f"hook-test:{index}", command) for index, command in enumerate(HOOK_TESTS, start=1))
    if item == "detect-secrets":
        return run_many(
            [
                ("detect-secrets-pre-commit", COMMANDS["detect-secrets-pre-commit"]),
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
