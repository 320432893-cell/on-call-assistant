"""One-command reproducible pipeline: run the full market-cap explanation mainline in dependency order, across both venvs."""

# 职责：把主线(解释市值变动)的脚本按依赖顺序一键串跑 = INV-047。跨两个 venv(主 .venv / 隔离 .venv-causal)用子进程调度,
#   每步报 通过/失败 + 耗时 + 产物大小;任一步失败即停。默认跳过联网采集、含废弃事件线收口、仪表板放最后。
# 不做什么：不重实现任何分析(只编排已有脚本);不碰 git;采集步默认关(要 token+联网,加 --with-collect 才跑)。
# 允许依赖层：仅标准库(subprocess/argparse/time/pathlib)。不 import 任何项目模块(纯子进程,故能跨 venv)。
# 谁不应该 import：本入口不被任何脚本 import。
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent  # on-call-assistant-20260514(仓库根)
MIS = "market-impact-study"
PY = str(REPO / ".venv" / "bin" / "python")
PY_CAUSAL = str(REPO / ".venv-causal" / "bin" / "python")

# (名, venv python, 脚本, 产物相对路径, 是否默认跑)
STEPS = [
    ("采集(联网)", PY, "collect_tushare_extended.py", None, False),
    ("基本面面板", PY, "build_fundamental_panel.py", "data/processed/modeling/fundamental_panel.csv", True),
    ("估值解释", PY, "build_valuation_model.py", "data/processed/modeling/cate_14firm/valuation_model.json", True),
    ("市值分解", PY, "build_mcap_attribution.py", "data/processed/modeling/cate_14firm/mcap_attribution.json", True),
    (
        "严谨归因",
        PY,
        "build_attribution_rigorous.py",
        "data/processed/modeling/cate_14firm/attribution_rigorous.json",
        True,
    ),
    (
        "三角验证",
        PY,
        "verify_drivers_triangulation.py",
        "data/processed/modeling/cate_14firm/drivers_triangulation.json",
        True,
    ),
    ("解释层", PY, "build_driver_explanation.py", "data/processed/modeling/cate_14firm/driver_explanation.json", True),
    ("白盒证明", PY, "verify_whitebox_explanation.py", "data/processed/modeling/cate_14firm/whitebox_proof.json", True),
    (
        "事件线收口(废弃·留档)",
        PY_CAUSAL,
        "verify_event_dml_robust.py",
        "data/processed/modeling/cate_14firm/event_dml_robust.json",
        True,
    ),
    ("交付仪表板", PY, "build_cfo_dashboard.py", "data/processed/cfo_dashboard.html", True),
]


def _kb(rel: str | None) -> str:
    if not rel:
        return "—"
    p = REPO / MIS / rel
    return f"{p.stat().st_size // 1024} KB" if p.exists() else "缺失!"


def run_step(name: str, py: str, script: str, produces: str | None) -> tuple[bool, float]:
    if not Path(py).exists():
        print(f"  ✗ {name}: 找不到解释器 {py}")
        return False, 0.0
    t0 = time.perf_counter()
    r = subprocess.run([py, f"{MIS}/{script}"], cwd=REPO, check=False)  # noqa: S603
    dt = time.perf_counter() - t0
    ok = r.returncode == 0 and (produces is None or (REPO / MIS / produces).exists())
    print(f"  {'✓' if ok else '✗'} {name}  ({dt:.1f}s, 产物 {_kb(produces)})")
    return ok, dt


def main() -> None:
    ap = argparse.ArgumentParser(description="主线一键复现")
    ap.add_argument("--with-collect", action="store_true", help="包含联网采集步(需 token)")
    ap.add_argument("--no-event", action="store_true", help="跳过废弃事件线收口")
    ap.add_argument("--no-dashboard", action="store_true", help="跳过仪表板")
    a = ap.parse_args()

    plan = []
    for name, py, script, prod, default_on in STEPS:
        if script == "collect_tushare_extended.py" and not a.with_collect:
            continue
        if script == "verify_event_dml_robust.py" and a.no_event:
            continue
        if script == "build_cfo_dashboard.py" and a.no_dashboard:
            continue
        if default_on or a.with_collect:
            plan.append((name, py, script, prod))

    print(f"主线复现:{len(plan)} 步(仓库根 {REPO})")
    results, total = [], 0.0
    for i, (name, py, script, prod) in enumerate(plan, 1):
        print(f"[{i}/{len(plan)}] {script}")
        ok, dt = run_step(name, py, script, prod)
        results.append((name, ok))
        total += dt
        if not ok:
            print(f"\n失败于「{name}」,停止。修复后重跑(可单独跑该脚本)。")
            sys.exit(1)

    print(f"\n全链通过 {sum(ok for _, ok in results)}/{len(results)} 步,总耗时 {total:.1f}s。")
    print("交付:data/processed/cfo_dashboard.html" if not a.no_dashboard else "（已跳过仪表板）")


if __name__ == "__main__":
    main()
