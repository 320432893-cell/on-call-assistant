# 职责：契约 schema 只增不改硬闸——快照 app/models 里 Pydantic 模型的字段名+类型，对比基线；
#       删字段/改名/改类型=破坏性→阻塞，加字段=允许(additive)。
# 不做什么：不改模型、不校验字段语义/默认值；标 `# experimental` 的字段豁免(流动前沿,可 reshape)。
# 允许依赖层：标准库(ast/json)、被扫描的模型源文件、schema baseline。
# 谁不应该 import：正式业务代码、测试夹具、应用入口不应 import 本检查脚本。
"""Contract schema additive-only gate: snapshot Pydantic model fields (name+type) under
app/models, diff vs baseline. Removed/renamed/retyped field = breaking → block; added
field = allowed. Fields whose source line carries `# experimental` are exempt (fluid frontier)."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILES = [ROOT / "app" / "models" / "schemas.py"]
BASELINE_PATH = ROOT / ".ai-config" / "config" / "schema.baseline.json"


def extract() -> dict[str, dict[str, str]]:
    models: dict[str, dict[str, str]] = {}
    for path in SCHEMA_FILES:
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        lines = src.splitlines()
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.ClassDef):
                continue
            fields: dict[str, str] = {}
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    line = lines[stmt.lineno - 1] if 0 <= stmt.lineno - 1 < len(lines) else ""
                    if "# experimental" in line:  # 流动前沿字段豁免
                        continue
                    fields[stmt.target.id] = ast.unparse(stmt.annotation)
            if fields:
                models[node.name] = fields
    return models


def load_baseline() -> dict[str, dict[str, str]]:
    if not BASELINE_PATH.exists():
        return {}
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8")).get("models", {})
    except (json.JSONDecodeError, OSError):
        return {}


def write_baseline(models: dict[str, dict[str, str]]) -> None:
    payload = {
        "reason": "契约 schema 稳定核心：app/models Pydantic 模型字段名+类型，只增不改。",
        "clear_by": "破坏性改(删/改名/改类型)走③晋升门承重决策;加字段后运行 --update-baseline 锁新核心。",
        "registered": "2026-06-20",
        "ratchet": "只增不改：删/改名/改类型字段=阻塞;加字段=允许。标 `# experimental` 的字段豁免(流动前沿)。",
        "models": models,
    }
    BASELINE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def breaking_changes(baseline: dict[str, dict[str, str]], current: dict[str, dict[str, str]]) -> list[str]:
    out: list[str] = []
    for model, fields in baseline.items():
        if model not in current:
            out.append(f"{model}: 整个模型消失(契约破坏)")
            continue
        for fname, ftype in fields.items():
            if fname not in current[model]:
                out.append(f"{model}.{fname}: 字段删除/改名(契约破坏)")
            elif current[model][fname] != ftype:
                out.append(f"{model}.{fname}: 类型 {ftype} → {current[model][fname]}(契约破坏)")
    return out


def main(argv: list[str]) -> int:
    current = extract()
    if "--update-baseline" in argv:
        write_baseline(current)
        field_n = sum(len(f) for f in current.values())
        sys.stdout.write(f"[schema] baseline 已写入：{len(current)} 模型 / {field_n} 字段\n")
        return 0
    baseline = load_baseline()
    if not baseline:
        write_baseline(current)
        sys.stdout.write("[schema] 无基线，已 seed 当前 schema 为稳定核心。\n")
        return 0
    breaking = breaking_changes(baseline, current)
    if breaking:
        sys.stderr.write("[schema] 契约破坏性改动(只增不改棘轮失败)——走③晋升门承重决策，或字段标 `# experimental`：\n")
        for item in breaking:
            sys.stderr.write(f"  X {item}\n")
        return 1
    added = sum(1 for m, fs in current.items() for f in fs if f not in baseline.get(m, {}))
    added += sum(1 for m in current if m not in baseline)
    if added:
        sys.stdout.write(f"[schema] 仅新增 {added} 项、无破坏;加字段后可运行 --update-baseline 锁核心。\n")
    else:
        sys.stdout.write("[schema] 契约稳定核心未变。\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
