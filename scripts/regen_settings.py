#!/usr/bin/env python3
"""SSOT 生成器:从 .ai-hooks/manifest.json 生成 .ai-config/config/settings.json{,.template}。

为什么需要这层:AI/Codex 运行时或兼容层可能会挑剔 settings.json 的增量改动,
有时静默回滚 hook 注册。Python 通过 Bash 写文件是普通 IO 操作,引擎不挑。

用法:
    python3 scripts/regen_settings.py

行为:
    - 读 .ai-hooks/manifest.json(SSOT)
    - 读本地 .ai-config/config/settings.json 的 OPENAI_API_KEY 或 ANTHROPIC_AUTH_TOKEN(若存在)
    - 生成 .ai-config/config/settings.json(含本地 token,不入仓)
    - 生成 .ai-config/config/settings.json.template(token = REPLACE_ME_..., 入仓)
    - 校验:每个 hook 名在 .ai-hooks/ 下都存在对应 .sh 文件,否则报错退出
    - 校验:生成产物是合法 JSON
    - 清理:permissions.allow 只保留 manifest 显式声明的,丢掉 linter 累积的脏命令

退出码:
    0 = 成功
    1 = manifest 或 .sh 文件校验失败
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / ".ai-hooks" / "manifest.json"
HOOKS_DIR = REPO_ROOT / ".ai-hooks"
SETTINGS = REPO_ROOT / ".ai-config" / "config" / "settings.json"
TEMPLATE = REPO_ROOT / ".ai-config" / "config" / "settings.json.template"

TOKEN_PLACEHOLDER = "REPLACE_ME_WITH_YOUR_TOKEN"  # noqa: S105
SUPPORTED_HOOK_EVENTS = {
    "PreToolUse_Bash",
    "PostToolUse_EditWriteMultiEdit",
}


def load_manifest() -> dict[str, Any]:
    if not MANIFEST.exists():
        print(f"[regen_settings] FATAL: {MANIFEST} 不存在", file=sys.stderr)
        sys.exit(1)
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def validate_hooks_exist(manifest: dict[str, Any]) -> None:
    unknown_events = sorted(set(manifest.get("hooks", {})) - SUPPORTED_HOOK_EVENTS)
    if unknown_events:
        print("[regen_settings] FATAL: manifest 包含生成器不支持的 hook event:", file=sys.stderr)
        for event in unknown_events:
            print(f"  {event}", file=sys.stderr)
        sys.exit(1)

    missing: list[str] = [
        f"  {stage_key}: {name}(.ai-hooks/{name} 不存在)"
        for stage_key, hook_names in manifest.get("hooks", {}).items()
        for name in hook_names
        if not (HOOKS_DIR / name).exists()
    ]
    if missing:
        print("[regen_settings] FATAL: manifest 引用的 hook 文件缺失:", file=sys.stderr)
        for m in missing:
            print(m, file=sys.stderr)
        sys.exit(1)


def read_local_token() -> str:
    if not SETTINGS.exists():
        return TOKEN_PLACEHOLDER
    try:
        data = json.loads(SETTINGS.read_text(encoding="utf-8"))
        env = data.get("env", {})
        token = env.get("OPENAI_API_KEY") or env.get("ANTHROPIC_AUTH_TOKEN") or TOKEN_PLACEHOLDER
    except (json.JSONDecodeError, OSError):
        return TOKEN_PLACEHOLDER
    return token if token else TOKEN_PLACEHOLDER


def build_hook_entry(hook_name: str) -> dict[str, str]:
    return {"type": "command", "command": f"bash .ai-hooks/{hook_name}"}


def build_settings(manifest: dict[str, Any], token: str) -> dict[str, Any]:
    h = manifest["hooks"]
    env = {
        "OPENAI_API_KEY": token,
    }
    if manifest.get("base_url"):
        env["OPENAI_BASE_URL"] = manifest["base_url"]
    hooks: dict[str, list[dict[str, Any]]] = {}
    pre_tool_use = []
    if h.get("PreToolUse_Bash"):
        pre_tool_use.append(
            {
                "matcher": "Bash",
                "hooks": [build_hook_entry(n) for n in h["PreToolUse_Bash"]],
            },
        )
    if pre_tool_use:
        hooks["PreToolUse"] = pre_tool_use
    if h.get("PostToolUse_EditWriteMultiEdit"):
        hooks["PostToolUse"] = [
            {
                "matcher": "Edit|Write|MultiEdit",
                "hooks": [build_hook_entry(n) for n in h["PostToolUse_EditWriteMultiEdit"]],
            },
        ]
    return {
        "env": env,
        "model": manifest["model"],
        "permissions": manifest.get("permissions", {"allow": []}),
        "hooks": hooks,
        "enabledPlugins": manifest.get("enabledPlugins", {}),
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    json.loads(text)  # 回读校验


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从 .ai-hooks/manifest.json 生成 .ai-config/config/settings.json 和 settings.json.template。",
    )
    return parser.parse_args(argv)


def main() -> int:
    parse_args(sys.argv[1:])

    manifest = load_manifest()
    validate_hooks_exist(manifest)

    local_token = read_local_token()
    settings = build_settings(manifest, local_token)
    write_json(SETTINGS, settings)

    template = build_settings(manifest, TOKEN_PLACEHOLDER)
    write_json(TEMPLATE, template)

    hooks_count = sum(len(v) for v in manifest["hooks"].values())
    print(f"[regen_settings] OK — 写入 {SETTINGS.name} 和 {TEMPLATE.name},共注册 {hooks_count} 个 hook")
    print(f"  PreToolUse(Bash): {len(manifest['hooks'].get('PreToolUse_Bash', []))}")
    print(f"  PostToolUse(Edit|Write|MultiEdit): {len(manifest['hooks'].get('PostToolUse_EditWriteMultiEdit', []))}")

    if local_token == TOKEN_PLACEHOLDER:
        print(
            "[regen_settings] WARN — settings.json 中 token 是占位符,本地使用前请填入真实 OPENAI_API_KEY",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
