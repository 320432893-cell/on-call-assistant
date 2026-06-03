#!/usr/bin/env python3
"""Validate AI delivery evidence packs against the current git diff.

This checker is intentionally mechanical: it verifies structure, freshness, and
diff coverage. It does not judge whether a business decision is correct.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import pathlib
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE_DIR = ROOT / ".ai-evidence" / "current"
IGNORED_DIFF_PREFIXES = (".ai-evidence/",)
REQUIRED_CONTRACT_SLOT_IDS = {str(index) for index in range(1, 10)}
REQUIRED_RISK_MODES = {"半成", "重跑", "乱序", "中间态"}
HIGH_SIGNAL_TRIGGER_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tool-contracts", (".ai-config/**", ".ai-hooks/**", ".github/workflows/**", ".pre-commit-config.yaml", "tools/check.py")),
    ("dependency", ("pyproject.toml", "uv.lock", "package.json", "package-lock.json", "pnpm-lock.yaml")),
    ("contract", ("**/models/**", "**/schemas/**", "**/api/**", "**/routers/**", "**/*schema*", "**/*state*")),
    ("risk", ("**/migrations/**", "**/deploy/**", "**/*publish*", "**/*delete*", "**/*write*")),
    ("review", (".ai-config/**", ".ai-hooks/**", ".github/workflows/**", "tools/check.py", "**/models/**", "**/schemas/**", "**/api/**", "**/routers/**", "**/*schema*", "**/*state*")),
)
VAGUE_TERMS = re.compile(r"(已处理|没问题|应该|可能|基本|大概|看起来|无风险|通过)", re.IGNORECASE)


@dataclass(frozen=True)
class Issue:
    severity: str
    message: str


def rel(path: pathlib.Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def read_toml(path: pathlib.Path, issues: list[Issue]) -> dict[str, Any]:
    if not path.exists():
        issues.append(Issue("ERROR", f"missing evidence file: {rel(path)}"))
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        issues.append(Issue("ERROR", f"invalid TOML in {rel(path)}: {exc}"))
        return {}


def run_git(args: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr.strip()


def collect_changed_files() -> tuple[list[str], list[Issue]]:
    issues: list[Issue] = []
    names: set[str] = set()
    for args in (
        ["diff", "--name-only", "--diff-filter=ACMRD"],
        ["diff", "--cached", "--name-only", "--diff-filter=ACMRD"],
        ["ls-files", "--others", "--exclude-standard"],
    ):
        rc, stdout, stderr = run_git(args)
        if rc != 0:
            issues.append(Issue("ERROR", f"git {' '.join(args)} failed: {stderr}"))
            continue
        names.update(line.strip() for line in stdout.splitlines() if line.strip())
    return sorted(name for name in names if not name.startswith(IGNORED_DIFF_PREFIXES)), issues


def current_diff_hash(changed_files: list[str]) -> tuple[str, list[Issue]]:
    issues: list[Issue] = []
    chunks: list[bytes] = []
    rc, stdout, stderr = run_git(["diff", "--binary", "--no-ext-diff", "--", *changed_files])
    if rc not in (0, 1):
        issues.append(Issue("ERROR", f"git diff hash source failed: {stderr}"))
    chunks.append(stdout.encode("utf-8", errors="surrogateescape"))

    for name in changed_files:
        path = ROOT / name
        if not path.exists() or path.is_dir():
            continue
        rc, stdout, _ = run_git(["ls-files", "--error-unmatch", "--", name])
        if rc == 0 or stdout.strip():
            continue
        chunks.append(f"\n--- untracked:{name}\n".encode())
        chunks.append(path.read_bytes())

    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk)
    return digest.hexdigest(), issues


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def nonempty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return value is not None


def expected_triggers(changed_files: list[str]) -> set[str]:
    triggers: set[str] = set()
    for trigger, patterns in HIGH_SIGNAL_TRIGGER_PATTERNS:
        if any(fnmatch.fnmatch(name, pattern) for name in changed_files for pattern in patterns):
            triggers.add(trigger)
    return triggers


def require_fields(data: dict[str, Any], fields: list[str], where: str, issues: list[Issue]) -> None:
    for field in fields:
        current: Any = data
        for part in field.split("."):
            current = current.get(part) if isinstance(current, dict) else None
        if not nonempty(current):
            issues.append(Issue("ERROR", f"{where}: missing required field `{field}`"))


def check_manifest(evidence_dir: pathlib.Path, changed_files: list[str], diff_hash: str, issues: list[Issue]) -> set[str]:
    manifest = read_toml(evidence_dir / "manifest.toml", issues)
    if not manifest:
        return set()

    require_fields(
        manifest,
        [
            "task.type",
            "task.delivery_shape",
            "task.acceptance_action",
            "git.base",
            "git.head",
            "git.diff_hash",
            "git.changed_files",
            "rules.triggered",
        ],
        "manifest.toml",
        issues,
    )

    reported_files = sorted(str(item) for item in as_list(manifest.get("git", {}).get("changed_files")))
    if reported_files != sorted(changed_files):
        issues.append(
            Issue(
                "ERROR",
                "manifest.toml: changed_files does not match current git diff "
                f"(reported={reported_files}, actual={changed_files})",
            )
        )

    reported_hash = text(manifest.get("git", {}).get("diff_hash"))
    if reported_hash and reported_hash != diff_hash:
        issues.append(Issue("ERROR", "manifest.toml: diff_hash is stale for current git diff"))

    triggers = {str(item) for item in as_list(manifest.get("rules", {}).get("triggered"))}
    missing_triggers = expected_triggers(changed_files) - triggers
    for trigger in sorted(missing_triggers):
        issues.append(Issue("ERROR", f"manifest.toml: missing triggered rule `{trigger}` for current diff"))
    return triggers


def check_contract(evidence_dir: pathlib.Path, issues: list[Issue]) -> None:
    data = read_toml(evidence_dir / "contract.toml", issues)
    slots = as_list(data.get("slots"))
    seen = {text(slot.get("id")) for slot in slots if isinstance(slot, dict)}
    missing = REQUIRED_CONTRACT_SLOT_IDS - seen
    for slot_id in sorted(missing, key=int):
        issues.append(Issue("ERROR", f"contract.toml: missing contract slot {slot_id}"))
    for slot in slots:
        if not isinstance(slot, dict):
            issues.append(Issue("ERROR", "contract.toml: slot must be a table"))
            continue
        status = text(slot.get("status"))
        if status not in {"answered", "na", "unverified"}:
            issues.append(Issue("ERROR", f"contract.toml: slot {slot.get('id')} has invalid status `{status}`"))
        if not text(slot.get("answer")):
            issues.append(Issue("ERROR", f"contract.toml: slot {slot.get('id')} missing answer"))
        if status == "na" and not text(slot.get("na_reason")):
            issues.append(Issue("ERROR", f"contract.toml: slot {slot.get('id')} uses N/A without na_reason"))


def check_risk(evidence_dir: pathlib.Path, issues: list[Issue]) -> None:
    data = read_toml(evidence_dir / "risk.toml", issues)
    risks = as_list(data.get("risks"))
    modes = {text(item.get("mode")) for item in risks if isinstance(item, dict)}
    for mode in sorted(REQUIRED_RISK_MODES):
        if mode not in modes:
            issues.append(Issue("ERROR", f"risk.toml: missing risk mode `{mode}`"))
    for index, item in enumerate(risks, start=1):
        if not isinstance(item, dict):
            issues.append(Issue("ERROR", f"risk.toml: risks[{index}] must be a table"))
            continue
        require_fields(
            item,
            ["step", "mode", "assumption", "blast_radius", "detectability", "guarantor", "uncovered_risk"],
            f"risk.toml risks[{index}]",
            issues,
        )


def check_verification(evidence_dir: pathlib.Path, issues: list[Issue]) -> None:
    data = read_toml(evidence_dir / "verification.toml", issues)
    checks = as_list(data.get("checks"))
    if not checks:
        issues.append(Issue("ERROR", "verification.toml: missing [[checks]]"))
    for index, item in enumerate(checks, start=1):
        if not isinstance(item, dict):
            issues.append(Issue("ERROR", f"verification.toml: checks[{index}] must be a table"))
            continue
        require_fields(item, ["tool", "command", "scope", "result", "evidence"], f"verification.toml checks[{index}]", issues)
        result = text(item.get("result"))
        if result not in {"pass", "fail", "skipped", "unverified"}:
            issues.append(Issue("ERROR", f"verification.toml checks[{index}]: invalid result `{result}`"))
        if result == "pass" and item.get("exit_code") != 0:
            issues.append(Issue("ERROR", f"verification.toml checks[{index}]: pass requires exit_code = 0"))


def check_oracle(evidence_dir: pathlib.Path, issues: list[Issue]) -> None:
    data = read_toml(evidence_dir / "oracle.toml", issues)
    oracle = data.get("oracle", {})
    if not isinstance(oracle, dict):
        issues.append(Issue("ERROR", "oracle.toml: [oracle] must be a table"))
        return
    require_fields(oracle, ["status", "method", "impact"], "oracle.toml", issues)
    status = text(oracle.get("status"))
    if status not in {"independent", "unverified"}:
        issues.append(Issue("ERROR", f"oracle.toml: invalid status `{status}`"))
    if status == "independent" and not nonempty(oracle.get("evidence")):
        issues.append(Issue("ERROR", "oracle.toml: independent oracle requires evidence"))
    if status == "unverified" and "已验证" in text(oracle.get("method")):
        issues.append(Issue("ERROR", "oracle.toml: unverified oracle must not claim verified method"))


def check_review(evidence_dir: pathlib.Path, changed_files: list[str], issues: list[Issue]) -> None:
    data = read_toml(evidence_dir / "review.toml", issues)
    files = as_list(data.get("files"))
    covered = {text(item.get("path")) for item in files if isinstance(item, dict)}
    missing = sorted(set(changed_files) - covered)
    for path in missing:
        issues.append(Issue("ERROR", f"review.toml: missing review coverage for changed file `{path}`"))
    for index, item in enumerate(files, start=1):
        if not isinstance(item, dict):
            issues.append(Issue("ERROR", f"review.toml: files[{index}] must be a table"))
            continue
        require_fields(item, ["path", "conclusion", "uncovered_risk", "evidence"], f"review.toml files[{index}]", issues)
        if text(item.get("conclusion")) not in {"通过", "有限通过", "必须重构"}:
            issues.append(Issue("ERROR", f"review.toml files[{index}]: invalid conclusion `{item.get('conclusion')}`"))


def check_vague_claims(evidence_dir: pathlib.Path, issues: list[Issue]) -> None:
    for path in sorted(evidence_dir.glob("*.toml")):
        data = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(data.splitlines(), start=1):
            if not VAGUE_TERMS.search(line):
                continue
            if "evidence" in line or "unverified" in line or "未验证" in line:
                continue
            issues.append(Issue("WARN", f"{rel(path)}:{line_no}: vague claim should point to evidence or be marked unverified"))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default=str(DEFAULT_EVIDENCE_DIR), help="Evidence pack directory.")
    parser.add_argument(
        "--optional",
        action="store_true",
        help="Return success when the evidence directory is absent; still validate strictly when it exists.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    evidence_dir = pathlib.Path(args.path)
    if not evidence_dir.is_absolute():
        evidence_dir = ROOT / evidence_dir

    issues: list[Issue] = []
    if not evidence_dir.exists():
        print(f"[delivery-evidence] evidence directory missing: {rel(evidence_dir)}", file=sys.stderr)
        print("[delivery-evidence] create manifest.toml, verification.toml, oracle.toml, and triggered evidence files.", file=sys.stderr)
        return 0 if args.optional else 1

    changed_files, git_issues = collect_changed_files()
    issues.extend(git_issues)
    diff_hash, hash_issues = current_diff_hash(changed_files)
    issues.extend(hash_issues)

    triggers = check_manifest(evidence_dir, changed_files, diff_hash, issues)
    check_verification(evidence_dir, issues)
    check_oracle(evidence_dir, issues)
    if "contract" in triggers:
        check_contract(evidence_dir, issues)
    if "risk" in triggers:
        check_risk(evidence_dir, issues)
    if "review" in triggers:
        check_review(evidence_dir, changed_files, issues)
    check_vague_claims(evidence_dir, issues)

    if issues:
        print("[delivery-evidence] evidence check findings:", file=sys.stderr)
        for item in issues:
            print(f"  - {item.severity}: {item.message}", file=sys.stderr)
        return 1 if any(item.severity == "ERROR" for item in issues) else 0

    print("[delivery-evidence] evidence pack matches current diff and required structure")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
