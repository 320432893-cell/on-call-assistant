#!/usr/bin/env python3
"""Check rule/tool/hook contracts without a full manual scan."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / ".ai-config" / "tooling.registry.toml"


@dataclass
class Issue:
    severity: str
    message: str


def read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def rel(path: pathlib.Path) -> str:
    return str(path.relative_to(ROOT))


def load_toml(path: pathlib.Path) -> dict:
    return tomllib.loads(read_text(path))


def parse_dev_packages(pyproject: dict) -> set[str]:
    packages: set[str] = set()
    for item in pyproject.get("dependency-groups", {}).get("dev", []):
        if isinstance(item, str):
            packages.add(re.split(r"[<>=!~\[]", item, maxsplit=1)[0].lower())
    return packages


def parse_pre_commit_hooks(path: pathlib.Path) -> set[str]:
    text = read_text(path)
    return set(re.findall(r"^\s*-\s+id:\s*([A-Za-z0-9_.-]+)\s*$", text, flags=re.MULTILINE))


def manifest_hook_files(path: pathlib.Path) -> dict[str, str]:
    data = json.loads(read_text(path))
    hooks = data.get("hooks", {})
    files: dict[str, str] = {}
    for event, names in hooks.items():
        for name in names:
            files[f".ai-hooks/{name}"] = event
    return files


def check_path_exists(root: pathlib.Path, path_str: str, issues: list[Issue], field: str) -> None:
    path = root / path_str
    if not path.exists():
        issues.append(Issue("ERROR", f"{field} points to missing path: {path_str}"))


def check_tools(root: pathlib.Path, registry: dict, issues: list[Issue]) -> None:
    pyproject = load_toml(root / "pyproject.toml")
    dev_packages = parse_dev_packages(pyproject)
    pre_commit_hooks = parse_pre_commit_hooks(root / ".pre-commit-config.yaml")
    ci = read_text(root / ".github" / "workflows" / "ci.yml")

    for tool in registry.get("tools", []):
        tool_id = tool["id"]
        package = tool.get("package")
        if package and package.lower() not in dev_packages:
            issues.append(Issue("ERROR", f"tool {tool_id}: dev dependency missing: {package}"))

        for path_str in tool.get("configured_in", []):
            check_path_exists(root, path_str, issues, f"tool {tool_id}.configured_in")

        rule = tool.get("rule")
        if rule:
            check_path_exists(root, rule, issues, f"tool {tool_id}.rule")

        pre_commit_hook = tool.get("pre_commit_hook")
        if pre_commit_hook and pre_commit_hook not in pre_commit_hooks:
            issues.append(Issue("ERROR", f"tool {tool_id}: pre-commit hook missing: {pre_commit_hook}"))
        issues.extend(
            Issue("ERROR", f"tool {tool_id}: pre-commit hook missing: {hook_id}")
            for hook_id in tool.get("pre_commit_hooks", [])
            if hook_id not in pre_commit_hooks
        )

        issues.extend(
            Issue("ERROR", f"tool {tool_id}: CI command missing: {command}")
            for command in tool.get("ci_commands", [])
            if command not in ci
        )


def check_ci_semantics(root: pathlib.Path, issues: list[Issue]) -> None:
    ci = read_text(root / ".github" / "workflows" / "ci.yml")
    if "detect-secrets scan --list-all-plugins" in ci:
        issues.append(Issue("ERROR", "CI detect-secrets uses --list-all-plugins instead of scanning files"))
    if "uv run pytest tests/" in ci:
        issues.append(Issue("ERROR", "CI pytest only runs tests/ instead of project pytest configuration"))
    if re.search(r"if:\s*hashFiles\('tests/'\)", ci):
        issues.append(Issue("ERROR", "CI pytest can be skipped when tests/ is absent"))


def check_semgrep_rulesets(root: pathlib.Path, registry: dict, issues: list[Issue]) -> None:
    semgrep_dir = root / ".semgrep"
    registered = {item["path"] for item in registry.get("semgrep_rulesets", [])}
    actual = {rel(path) for path in semgrep_dir.glob("*.yml")}

    issues.extend(
        Issue("ERROR", f"semgrep ruleset exists but is not registered: {missing}")
        for missing in sorted(actual - registered)
    )
    issues.extend(
        Issue("ERROR", f"semgrep ruleset registered but missing: {stale}") for stale in sorted(registered - actual)
    )

    for ruleset in registry.get("semgrep_rulesets", []):
        owner = ruleset.get("owner_rule")
        if owner:
            check_path_exists(root, owner, issues, f"semgrep {ruleset['path']}.owner_rule")


def check_hooks(root: pathlib.Path, registry: dict, issues: list[Issue]) -> None:
    manifest_files = manifest_hook_files(root / ".ai-hooks" / "manifest.json")
    registered = {hook["file"] for hook in registry.get("hooks", [])}
    actual = {rel(path) for path in (root / ".ai-hooks").glob("*.sh")}

    issues.extend(
        Issue("ERROR", f"hook file exists but is not registered in tooling registry: {missing}")
        for missing in sorted(actual - registered)
    )
    issues.extend(
        Issue("ERROR", f"hook registered in tooling registry but file missing: {stale}")
        for stale in sorted(registered - actual)
    )

    for hook in registry.get("hooks", []):
        file = hook["file"]
        event = hook.get("event")
        hook_path = root / file
        if manifest_files.get(file) != event:
            issues.append(
                Issue(
                    "ERROR",
                    f"hook {file}: manifest event mismatch, registry={event!r}, manifest={manifest_files.get(file)!r}",
                )
            )
        if hook_path.exists() and not os.access(hook_path, os.X_OK):
            issues.append(Issue("ERROR", f"hook {file}: file is not executable"))
        route = hook.get("rule_route")
        if route:
            check_path_exists(root, route, issues, f"hook {file}.rule_route")

    for file, event in sorted(manifest_files.items()):
        if file not in registered:
            issues.append(Issue("ERROR", f"hook manifest registers {file} for {event}, but registry is missing it"))


def check_hook_tests(root: pathlib.Path, registry: dict, issues: list[Issue]) -> None:
    ci = read_text(root / ".github" / "workflows" / "ci.yml")
    registered = {item["file"] for item in registry.get("hook_tests", [])}
    actual = {rel(path) for path in (root / ".ai-hooks" / "tests").glob("*.sh")}

    issues.extend(
        Issue("ERROR", f"hook test exists but is not registered in tooling registry: {missing}")
        for missing in sorted(actual - registered)
    )
    issues.extend(
        Issue("ERROR", f"hook test registered in tooling registry but file missing: {stale}")
        for stale in sorted(registered - actual)
    )

    for test in registry.get("hook_tests", []):
        file = test["file"]
        path = root / file
        if path.exists() and not os.access(path, os.X_OK):
            issues.append(Issue("ERROR", f"hook test {file}: file is not executable"))
        command = test.get("ci_command")
        if command and command not in ci:
            issues.append(Issue("ERROR", f"hook test {file}: CI command missing: {command}"))


def build_hook_entry(hook_name: str) -> dict[str, str]:
    return {"type": "command", "command": f"bash .ai-hooks/{hook_name}"}


def expected_template_from_manifest(manifest: dict) -> dict:
    hooks = manifest["hooks"]
    env = {"OPENAI_API_KEY": "REPLACE_ME_WITH_YOUR_TOKEN"}  # pragma: allowlist secret
    if manifest.get("base_url"):
        env["OPENAI_BASE_URL"] = manifest["base_url"]
    return {
        "env": env,
        "model": manifest["model"],
        "permissions": manifest.get("permissions", {"allow": []}),
        "hooks": {
            "UserPromptSubmit": [
                {
                    "matcher": "",
                    "hooks": [build_hook_entry(name) for name in hooks.get("UserPromptSubmit", [])],
                }
            ],
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [build_hook_entry(name) for name in hooks.get("PreToolUse_Bash", [])],
                },
                {
                    "matcher": "Edit|Write|MultiEdit",
                    "hooks": [build_hook_entry(name) for name in hooks.get("PreToolUse_EditWriteMultiEdit", [])],
                },
            ],
            "PostToolUse": [
                {
                    "matcher": "Edit|Write|MultiEdit",
                    "hooks": [build_hook_entry(name) for name in hooks.get("PostToolUse_EditWriteMultiEdit", [])],
                }
            ],
        },
        "enabledPlugins": manifest.get("enabledPlugins", {}),
    }


def check_settings_template(root: pathlib.Path, issues: list[Issue]) -> None:
    manifest = json.loads(read_text(root / ".ai-hooks" / "manifest.json"))
    supported_events = {
        "UserPromptSubmit",
        "PreToolUse_Bash",
        "PreToolUse_EditWriteMultiEdit",
        "PostToolUse_EditWriteMultiEdit",
    }
    unknown = sorted(set(manifest.get("hooks", {})) - supported_events)
    if unknown:
        issues.append(Issue("ERROR", f"manifest contains unsupported hook events: {', '.join(unknown)}"))

    template_path = root / ".ai-config" / "settings.json.template"
    if template_path.exists():
        actual = json.loads(read_text(template_path))
        expected = expected_template_from_manifest(manifest)
        if actual != expected:
            issues.append(Issue("ERROR", ".ai-config/settings.json.template is not equivalent to manifest output"))

    proc = subprocess.run(
        [sys.executable, "scripts/regen_settings.py", "--help"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        issues.append(Issue("ERROR", "scripts/regen_settings.py --help failed"))


def check_metadata(root: pathlib.Path, registry: dict, issues: list[Issue]) -> None:
    metadata = registry.get("metadata", {})
    for key in ("owner_rule", "human_doc", "checker"):
        value = metadata.get(key)
        if value:
            check_path_exists(root, value, issues, f"metadata.{key}")


def check_rule_references(root: pathlib.Path, issues: list[Issue]) -> None:
    targets = [
        root / ".ai-config" / "AGENTS.md",
        *list((root / ".ai-config" / "rules").rglob("*.md")),
    ]
    stale_patterns = {
        "../../AGENTS.md": "old AGENTS.md relative rule entry",
        "rules/workflow.md": "old flat rules path",
        "rules/governance.md": "old flat rules path",
    }
    for path in targets:
        text = read_text(path)
        for pattern, label in stale_patterns.items():
            if pattern in text:
                issues.append(Issue("ERROR", f"{rel(path)} contains {label}: {pattern}"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=pathlib.Path, default=REGISTRY)
    args = parser.parse_args()

    registry_path = args.registry if args.registry.is_absolute() else ROOT / args.registry
    registry = load_toml(registry_path)
    issues: list[Issue] = []

    check_metadata(ROOT, registry, issues)
    check_tools(ROOT, registry, issues)
    check_ci_semantics(ROOT, issues)
    check_semgrep_rulesets(ROOT, registry, issues)
    check_hooks(ROOT, registry, issues)
    check_hook_tests(ROOT, registry, issues)
    check_settings_template(ROOT, issues)
    check_rule_references(ROOT, issues)

    if issues:
        sys.stderr.write("Rule/tool contract check failed:\n")
        for issue in issues:
            sys.stderr.write(f"[{issue.severity}] {issue.message}\n")
        return 1

    sys.stdout.write("Rule/tool contract check passed.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
