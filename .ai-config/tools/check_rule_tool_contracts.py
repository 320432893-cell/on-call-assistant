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
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
REGISTRY = ROOT / ".ai-config" / "config" / "tooling.registry.toml"


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


def load_pre_commit_config(path: pathlib.Path) -> dict[str, Any]:
    try:
        import yaml
    except Exception as exc:  # pragma: no cover - PyYAML is provided by pre-commit.
        raise RuntimeError("PyYAML is required to validate pre-commit hook wiring") from exc
    data = yaml.safe_load(read_text(path))
    return data if isinstance(data, dict) else {}


def find_pre_commit_hook(config: dict[str, Any], hook_id: str) -> dict[str, Any] | None:
    for repo in config.get("repos", []):
        for hook in repo.get("hooks", []):
            if hook.get("id") == hook_id:
                return hook
    return None


def parse_entrypoint_profile_items(entrypoint: str, profile: str) -> set[str]:
    pattern = rf'"{re.escape(profile)}":\s*\[(.*?)\]'
    match = re.search(pattern, entrypoint, flags=re.DOTALL)
    if not match:
        return set()
    return set(re.findall(r'"([A-Za-z0-9_.-]+)"', match.group(1)))


def manifest_hook_files(path: pathlib.Path) -> dict[str, str]:
    data = json.loads(read_text(path))
    hooks = data.get("hooks", {})
    files: dict[str, str] = {}
    for event, names in hooks.items():
        for name in names:
            files[f".ai-hooks/{name}"] = event
    return files


def manifest_permissions(path: pathlib.Path) -> list[str]:
    data = json.loads(read_text(path))
    allow = data.get("permissions", {}).get("allow", [])
    return [item for item in allow if isinstance(item, str)]


def check_path_exists(root: pathlib.Path, path_str: str, issues: list[Issue], field: str) -> None:
    path = root / path_str
    if not path.exists():
        issues.append(Issue("ERROR", f"{field} points to missing path: {path_str}"))


def check_relative_path_literal(path_str: str, issues: list[Issue], field: str) -> None:
    path = pathlib.PurePosixPath(path_str)
    if path.is_absolute() or ".." in path.parts or not path_str.strip():
        issues.append(Issue("ERROR", f"{field} must be a non-empty repository-relative path: {path_str}"))


def check_tools(root: pathlib.Path, registry: dict, issues: list[Issue]) -> None:
    pyproject = load_toml(root / "pyproject.toml")
    dev_packages = parse_dev_packages(pyproject)
    pre_commit_hooks = parse_pre_commit_hooks(root / ".pre-commit-config.yaml")
    ci = read_text(root / ".github" / "workflows" / "ci.yml")
    entrypoint = read_text(root / registry.get("metadata", {}).get("unified_entrypoint", "tools/check.py"))

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

        for command in tool.get("ci_commands", []):
            if command not in ci and command not in entrypoint:
                issues.append(Issue("ERROR", f"tool {tool_id}: CI/entrypoint command missing: {command}"))
        for command in tool.get("entrypoint_commands", []):
            if command not in entrypoint:
                issues.append(Issue("ERROR", f"tool {tool_id}: entrypoint command missing: {command}"))
        for command in tool.get("manual_commands", []):
            if command not in entrypoint:
                issues.append(
                    Issue("ERROR", f"tool {tool_id}: manual command is not available through entrypoint: {command}")
                )


def check_rule_tool_contracts_trigger(root: pathlib.Path, issues: list[Issue]) -> None:
    config = load_pre_commit_config(root / ".pre-commit-config.yaml")
    hook = find_pre_commit_hook(config, "rule-tool-contracts")
    if not hook:
        issues.append(Issue("ERROR", "pre-commit rule-tool-contracts hook is missing"))
        return
    pattern = hook.get("files")
    if not isinstance(pattern, str) or not pattern:
        issues.append(Issue("ERROR", "pre-commit rule-tool-contracts hook must define a files regex"))
        return

    samples = [
        ".ai-config/tools/check_rule_tool_contracts.py",
        ".ai-config/config/tooling.registry.toml",
        ".ai-config/rules/engineering/index.md",
        ".ai-hooks/rag_hygiene.sh",
        ".semgrep/rag-hygiene.yml",
        ".github/workflows/ci.yml",
        ".pre-commit-config.yaml",
        ".ruff.toml",
        ".importlinter",
        "AGENTS.md",
        "tools/check.py",
        "pyproject.toml",
        "uv.lock",
    ]
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        issues.append(Issue("ERROR", f"pre-commit rule-tool-contracts files regex is invalid: {exc}"))
        return

    for sample in samples:
        if not compiled.search(sample):
            issues.append(
                Issue("ERROR", f"pre-commit rule-tool-contracts files regex does not match required path: {sample}")
            )


def check_ci_semantics(root: pathlib.Path, issues: list[Issue]) -> None:
    ci = read_text(root / ".github" / "workflows" / "ci.yml")
    if "detect-secrets scan --list-all-plugins" in ci:
        issues.append(Issue("ERROR", "CI detect-secrets uses --list-all-plugins instead of scanning files"))
    if "uv run pytest tests/" in ci:
        issues.append(Issue("ERROR", "CI pytest only runs tests/ instead of project pytest configuration"))
    if re.search(r"if:\s*hashFiles\('tests/'\)", ci):
        issues.append(Issue("ERROR", "CI pytest can be skipped when tests/ is absent"))


def check_enforcement_wiring(root: pathlib.Path, registry: dict, issues: list[Issue]) -> None:
    pre_commit = read_text(root / ".pre-commit-config.yaml")
    normalized_pre_commit = pre_commit.replace("\\", "")
    ci = read_text(root / ".github" / "workflows" / "ci.yml")
    entrypoint = registry.get("metadata", {}).get("unified_entrypoint", "tools/check.py")

    required_pre_commit_patterns = [
        r"id:\s*rule-tool-contracts",
        r"entry:\s*python3 tools/check\.py rule-tool-contracts",
        re.escape(entrypoint),
        r"\.ai-hooks/",
        r"\.semgrep/",
        r"id:\s*ruff-staged",
        r"id:\s*dependency-change-approval",
    ]
    for pattern in required_pre_commit_patterns:
        if not re.search(pattern, pre_commit):
            issues.append(Issue("ERROR", f"pre-commit enforcement wiring missing pattern: {pattern}"))
    for path in (".github/workflows/ci.yml", ".pre-commit-config.yaml"):
        if path not in normalized_pre_commit:
            issues.append(Issue("ERROR", f"pre-commit enforcement wiring missing path: {path}"))
    if "AGENTS.md" not in normalized_pre_commit:
        issues.append(Issue("ERROR", "pre-commit rule-tool-contracts trigger missing path: AGENTS.md"))
    for path in (".ruff.toml", ".importlinter"):
        if path not in normalized_pre_commit:
            issues.append(Issue("ERROR", f"pre-commit rule-tool-contracts trigger missing path: {path}"))

    if f"uv run python {entrypoint} ci" not in ci:
        issues.append(Issue("ERROR", f"CI must call unified entrypoint: uv run python {entrypoint} ci"))

    entrypoint_text = read_text(root / entrypoint)
    if "ONCALL_ALLOW_DEPENDENCY_CHANGE" not in entrypoint_text:
        issues.append(Issue("ERROR", "dependency-change approval env gate missing from unified entrypoint"))
    if "ruff-staged" not in entrypoint_text:
        issues.append(Issue("ERROR", "ruff-staged changed-file check missing from unified entrypoint"))
    if '".importlinter"' not in entrypoint_text:
        issues.append(Issue("ERROR", ".importlinter missing from unified entrypoint contract triggers"))

    ci_items = parse_entrypoint_profile_items(entrypoint_text, "ci")
    tools_by_id = {tool["id"]: tool for tool in registry.get("tools", [])}
    for tool_id, tool in tools_by_id.items():
        if tool.get("ci_commands") and tool_id not in ci_items:
            issues.append(
                Issue("ERROR", f"tool {tool_id}: registry declares CI commands but tool is not in ci profile")
            )


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
    manifest_path = root / ".ai-hooks" / "manifest.json"
    manifest_files = manifest_hook_files(manifest_path)
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

    high_impact_allow_patterns = (
        "Bash(git push",
        "Bash(git add .",
        "Bash(git add -A",
        "Bash(git add --all",
        "Bash(git reset",
        "Bash(git checkout",
        "Bash(git switch",
        "Bash(rm -rf",
        "Bash(pip install",
        "Bash(uv add",
        "Bash(uv sync",
        "Bash(npm install",
        "Bash(pnpm install",
        "Bash(yarn install",
        "Bash(npx",
        "Bash(docker run",
    )
    for permission in manifest_permissions(manifest_path):
        if any(permission.startswith(pattern) for pattern in high_impact_allow_patterns):
            issues.append(Issue("ERROR", f"manifest allow bypasses high-impact hook policy: {permission}"))


def check_hook_tests(root: pathlib.Path, registry: dict, issues: list[Issue]) -> None:
    ci = read_text(root / ".github" / "workflows" / "ci.yml")
    entrypoint = read_text(root / registry.get("metadata", {}).get("unified_entrypoint", "tools/check.py"))
    registered = {item["file"] for item in registry.get("hook_tests", [])}
    actual = {rel(path) for path in (root / ".ai-hooks" / "tests").glob("*.sh")}
    covered_hooks = {hook_file for item in registry.get("hook_tests", []) for hook_file in item.get("covers", [])}
    hook_files = {hook["file"] for hook in registry.get("hooks", [])}

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
        if command and command not in ci and command not in entrypoint:
            issues.append(Issue("ERROR", f"hook test {file}: CI/entrypoint command missing: {command}"))
        for hook_file in test.get("covers", []):
            check_path_exists(root, hook_file, issues, f"hook test {file}.covers")

    missing_coverage = sorted(hook_files - covered_hooks)
    issues.extend(
        Issue("ERROR", f"hook {hook_file}: no registered hook_tests.covers entry") for hook_file in missing_coverage
    )


def check_path_triggers(root: pathlib.Path, registry: dict, issues: list[Issue]) -> None:
    entrypoint = read_text(root / registry.get("metadata", {}).get("unified_entrypoint", "tools/check.py"))
    tools = {tool["id"] for tool in registry.get("tools", [])}
    registry_text = read_text(REGISTRY)
    for trigger in registry.get("path_triggers", []):
        trigger_id = trigger.get("id", "<missing>")
        tool_id = trigger.get("tool")
        if not trigger.get("paths"):
            issues.append(Issue("ERROR", f"path trigger {trigger_id}: paths missing"))
        if tool_id not in tools:
            issues.append(Issue("ERROR", f"path trigger {trigger_id}: tool is not registered: {tool_id}"))
        if f'id = "{trigger_id}"' not in registry_text:
            issues.append(Issue("ERROR", f"path trigger {trigger_id}: registry id not found"))
        for required_path in trigger.get("required_paths", []):
            check_relative_path_literal(required_path, issues, f"path trigger {trigger_id}.required_paths")
    if registry.get("path_triggers", []) and "path_triggers" not in entrypoint:
        issues.append(Issue("ERROR", "unified entrypoint does not evaluate path_triggers"))


def build_hook_entry(hook_name: str) -> dict[str, str]:
    return {"type": "command", "command": f"bash .ai-hooks/{hook_name}"}


def expected_template_from_manifest(manifest: dict) -> dict:
    hooks = manifest["hooks"]
    env = {"OPENAI_API_KEY": "REPLACE_ME_WITH_YOUR_TOKEN"}  # pragma: allowlist secret
    if manifest.get("base_url"):
        env["OPENAI_BASE_URL"] = manifest["base_url"]
    settings_hooks: dict[str, list[dict]] = {}
    pre_tool_use = []
    if hooks.get("PreToolUse_Bash"):
        pre_tool_use.append(
            {
                "matcher": "Bash",
                "hooks": [build_hook_entry(name) for name in hooks["PreToolUse_Bash"]],
            },
        )
    if pre_tool_use:
        settings_hooks["PreToolUse"] = pre_tool_use
    if hooks.get("PostToolUse_EditWriteMultiEdit"):
        settings_hooks["PostToolUse"] = [
            {
                "matcher": "Edit|Write|MultiEdit",
                "hooks": [build_hook_entry(name) for name in hooks["PostToolUse_EditWriteMultiEdit"]],
            }
        ]
    return {
        "env": env,
        "model": manifest["model"],
        "permissions": manifest.get("permissions", {"allow": []}),
        "hooks": settings_hooks,
        "enabledPlugins": manifest.get("enabledPlugins", {}),
    }


def check_settings_template(root: pathlib.Path, issues: list[Issue]) -> None:
    manifest = json.loads(read_text(root / ".ai-hooks" / "manifest.json"))
    supported_events = {
        "PreToolUse_Bash",
        "PostToolUse_EditWriteMultiEdit",
    }
    unknown = sorted(set(manifest.get("hooks", {})) - supported_events)
    if unknown:
        issues.append(Issue("ERROR", f"manifest contains unsupported hook events: {', '.join(unknown)}"))

    template_path = root / ".ai-config" / "config" / "settings.json.template"
    if template_path.exists():
        actual = json.loads(read_text(template_path))
        expected = expected_template_from_manifest(manifest)
        if actual != expected:
            issues.append(Issue("ERROR", ".ai-config/config/settings.json.template is not equivalent to manifest output"))

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


def check_agents_mirror(root: pathlib.Path, issues: list[Issue]) -> None:
    root_agents = root / "AGENTS.md"
    config_agents = root / ".ai-config" / "AGENTS.md"
    if not root_agents.exists():
        issues.append(Issue("ERROR", "AGENTS.md mirror is missing at repository root"))
        return
    if read_text(root_agents) != read_text(config_agents):
        issues.append(Issue("ERROR", "AGENTS.md must mirror .ai-config/AGENTS.md exactly"))


def check_rule_references(root: pathlib.Path, issues: list[Issue]) -> None:
    target_roots = [
        root / ".ai-config",
        root / ".ai-hooks",
        root / ".semgrep",
        root / "docs",
        root / "scripts",
        root / "tools",
    ]
    targets = [root / "AGENTS.md", root / "README.md"]
    checker_path = root / ".ai-config" / "tools" / "check_rule_tool_contracts.py"
    for target_root in target_roots:
        if target_root.exists():
            targets.extend(
                path
                for path in target_root.rglob("*")
                if path.is_file()
                and path.suffix.lower() in {".md", ".py", ".sh", ".toml", ".yaml", ".yml", ".json", ".template"}
            )
    stale_patterns = {
        "../../AGENTS.md": "old AGENTS.md relative rule entry",
        "rules/workflow.md": "old flat rules path",
        "rules/governance.md": "old flat rules path",
        "*.details.md": "deleted details rule routing",
        ".details.md": "deleted details rule routing",
        "process/workflow.index.md": "deleted workflow rule",
        "process/flow_legacy_project.index.md": "deleted legacy-project rule",
        "process/loop.index.md": "deleted loop rule",
        "process/dispatch.index.md": "deleted dispatch rule",
        "rules/process/workflow.index.md": "deleted workflow rule",
        "rules/process/flow_legacy_project.index.md": "deleted legacy-project rule",
        "rules/process/loop.index.md": "deleted loop rule",
        "rules/process/dispatch.index.md": "deleted dispatch rule",
        "rules/rule_governance/": "deleted rule_governance rule directory",
        "rule_governance/": "deleted rule_governance rule directory",
        "rules/engineering/backend.index.md": "moved backend rule",
        "rules/engineering/frontend.index.md": "moved frontend rule",
        "rules/engineering/architecture.index.md": "moved architecture rule",
        "rules/engineering/gui.md": "moved GUI rule",
        "engineering/backend.index.md": "moved backend rule",
        "engineering/frontend.index.md": "moved frontend rule",
        "engineering/architecture.index.md": "moved architecture rule",
        "engineering/gui.md": "moved GUI rule",
    }
    for path in targets:
        if not path.exists():
            continue
        if path == checker_path:
            continue
        text = read_text(path)
        for pattern, label in stale_patterns.items():
            if pattern in text:
                issues.append(Issue("ERROR", f"{rel(path)} contains {label}: {pattern}"))


def check_rule_structure(root: pathlib.Path, issues: list[Issue]) -> None:
    rules_dir = root / ".ai-config" / "rules"
    details = {rel(path) for path in rules_dir.rglob("*.details.md")}
    issues.extend(Issue("ERROR", f"details file must be merged into index: {path}") for path in sorted(details))

    for path in [root / ".ai-config" / "AGENTS.md", *rules_dir.rglob("*.md")]:
        text = read_text(path)
        relative_path = rel(path)
        for match in re.finditer(r"[\w./-]+\.details\.md", text):
            target = match.group(0)
            issues.append(Issue("ERROR", f"{relative_path} directly references details file: {target}"))

    for path in rules_dir.rglob("*.index.md"):
        content_lines = [
            line.strip() for line in read_text(path).splitlines() if line.strip() and not line.lstrip().startswith("#")
        ]
        if len(content_lines) < 3:
            issues.append(Issue("ERROR", f"{rel(path)} appears to be an empty or placeholder index"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=pathlib.Path, default=REGISTRY)
    args = parser.parse_args()

    registry_path = args.registry if args.registry.is_absolute() else ROOT / args.registry
    registry = load_toml(registry_path)
    issues: list[Issue] = []

    check_metadata(ROOT, registry, issues)
    check_agents_mirror(ROOT, issues)
    check_tools(ROOT, registry, issues)
    check_ci_semantics(ROOT, issues)
    check_enforcement_wiring(ROOT, registry, issues)
    check_rule_tool_contracts_trigger(ROOT, issues)
    check_semgrep_rulesets(ROOT, registry, issues)
    check_hooks(ROOT, registry, issues)
    check_hook_tests(ROOT, registry, issues)
    check_path_triggers(ROOT, registry, issues)
    check_settings_template(ROOT, issues)
    check_rule_references(ROOT, issues)
    check_rule_structure(ROOT, issues)

    if issues:
        sys.stderr.write("Rule/tool contract check failed:\n")
        for issue in issues:
            sys.stderr.write(f"[{issue.severity}] {issue.message}\n")
        return 1

    sys.stdout.write("Rule/tool contract check passed.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
