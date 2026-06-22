"""Build a self-contained ECharts dashboard: 财务对比(参考风格,芯片/标签/时间轴动画) + 因果分析(方法说明+训练动画)."""

# 职责：全项目两段式 ECharts 仪表板 = INV-026/028/029。财务段=移为vs14家逐年走势(时间轴播放)+ 增长气泡象限,
#       公司固定色芯片、数据点公司标签、标注模式、方法说明;因果段=去偏/加固/功效等 + 方法说明 + 训练过程动画。
#       ECharts 内联自包含。读 financial_panel + cate_14firm 产物。
# 不做什么：不重训/不做新估计;只可视化。
# 允许依赖层：标准库、pandas/numpy、peer_universe、cate_14firm/financial_panel 产物。
# 谁不应该 import：建模脚本不应 import 本入口。
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from peer_universe import load_companies

M = Path("market-impact-study/data/processed/modeling")
C = M / "cate_14firm"
OUT = Path("market-impact-study/data/processed/dashboard.html")
ECHARTS = Path("market-impact-study/docs/assets/echarts.min.js")
JS_TEMPLATE = Path("market-impact-study/docs/assets/dashboard.js")


def build_causal_bundle() -> dict:
    cate = json.loads((C / "cate_results.json").read_text(encoding="utf-8"))
    hard = json.loads((C / "cate_hardening.json").read_text(encoding="utf-8"))
    diag = json.loads((C / "training_diagnostics.json").read_text(encoding="utf-8"))
    scp = json.loads((C / "sc_path.json").read_text(encoding="utf-8"))
    het = pd.read_csv(M / "heterogeneity_14firm" / "heterogeneity_summary_14firm.csv")
    fcar = pd.read_csv(C / "factor_car_summary.csv")
    power = pd.read_csv(C / "power_analysis.csv")
    spec = pd.read_csv(C / "spec_curve.csv")
    nm = {"定增/再融资": "定增", "股东增减持/限售流通": "减持", "股份回购(首发)": "回购"}
    acts = ["定增/再融资", "股东增减持/限售流通", "股份回购(首发)"]
    descv = dict(zip(het["subtype"], het["all_pct"], strict=False))
    fcv = dict(zip(fcar["subtype"], fcar["car_factor_%"], strict=False))
    dmlv = {r["action"]: r["lindml"] for r in cate}
    cf = next(r for r in cate if r["action"] == "定增/再融资")["causalforest"]
    fwd, plc = hard["forward_causal"], hard["pre_event_placebo"]
    powc = power[power["维度"].str.contains("因果")]
    return {
        "overview": [
            {"name": nm[a], "desc": descv.get(a), "factor": fcv.get(a), "dml": dmlv[a]["ate_pct"]} for a in acts
        ],
        "forest": [
            {
                "name": nm[a],
                "ate": dmlv[a]["ate_pct"],
                "lo": dmlv[a]["ate_ci"][0],
                "hi": dmlv[a]["ate_ci"][1],
                "p": next(r["placebo_perm_p"] for r in cate if r["action"] == a),
            }
            for a in acts
        ],
        "cate": {
            "low": cf["cate_low_pct"],
            "low_ci": cf["cate_low_ci"],
            "high": cf["cate_high_pct"],
            "high_ci": cf["cate_high_ci"],
            "vi": cf.get("var_importance", {}),
        },
        "harden": {
            "analytic": [
                dmlv["定增/再融资"]["ate_ci"][0],
                dmlv["定增/再融资"]["ate_pct"],
                dmlv["定增/再融资"]["ate_ci"][1],
            ],
            "cluster": [fwd["cluster_ci90_pct"][0], fwd["point_pct"], fwd["cluster_ci90_pct"][1]],
            "placebo_pre": plc["point_pct"],
            "cluster_p": fwd["two_sided_p"],
            "nuisance": [
                {"name": nm[d["action"]], "auc": d["propensity_auc"], "overlap": d["overlap_frac"]}
                for d in hard["nuisance_diagnostics"]
            ],
        },
        "dml_resid": {
            "t": diag["dml_residual"]["t_res"],
            "y": diag["dml_residual"]["y_res"],
            "slope": diag["dml_residual"]["slope_pct"],
        },
        "bootstrap": diag["cluster_bootstrap"]["draws_pct"],
        "boot_ci": diag["cluster_bootstrap"]["ci90"],
        "placebo": diag["placebo_perm"]["null_pct"],
        "placebo_obs": diag["placebo_perm"]["observed_pct"],
        "power": [
            {
                "name": r["结论"][:2] + ("·聚类" if "聚类" in r["维度"] else ""),
                "p3": r["功效@3%"],
                "obs": r["观测%"],
                "mde": r["MDE@80%%"],
            }
            for _, r in powc.iterrows()
        ],
        "spec": [
            {
                "name": {
                    "定增/再融资": "定增",
                    "股东增减持/限售流通": "减持",
                    "股份回购(首发)": "回购",
                    "股权激励/员工持股": "激励",
                }.get(s, s[:2]),
                "eff": g["效应%"].tolist(),
            }
            for s, g in spec.groupby("结论")
        ],
        "sc": {
            "x": scp["x_rel_days"],
            "treated": scp["treated_index"],
            "synth": scp["synth_index"],
            "prefit": scp["pre_fit_rmspe"],
            "placebo_p": scp["placebo_p"],
        },
    }


def main() -> None:
    list(load_companies())  # 确保 universe 可加载(口径一致)
    fin = json.loads((M / "financial_panel.json").read_text(encoding="utf-8"))
    report = json.loads((C / "report_bundle.json").read_text(encoding="utf-8"))
    peer = json.loads((C / "peer_learning.json").read_text(encoding="utf-8"))
    cfo = json.loads((C / "cfo_case.json").read_text(encoding="utf-8"))
    train = json.loads((C / "training_process.json").read_text(encoding="utf-8"))
    causal = build_causal_bundle()
    js = JS_TEMPLATE.read_text(encoding="utf-8")
    lib = ECHARTS.read_text(encoding="utf-8") if ECHARTS.exists() else ""
    html = (
        SHELL.replace("__ECHARTS__", lib)
        .replace("__FIN__", json.dumps(fin, ensure_ascii=False))
        .replace("__CAUSAL__", json.dumps(causal, ensure_ascii=False))
        .replace("__REPORT__", json.dumps(report, ensure_ascii=False))
        .replace("__PEER__", json.dumps(peer, ensure_ascii=False))
        .replace("__CFO__", json.dumps(cfo, ensure_ascii=False))
        .replace("__TRAIN__", json.dumps(train, ensure_ascii=False))
        .replace("__APP__", js)
    )
    OUT.write_text(html, encoding="utf-8")
    print(f"saved -> {OUT}  ({OUT.stat().st_size // 1024} KB)")


SHELL = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>移为市值影响研究 — 傻瓜式分步讲解</title>
<script>__ECHARTS__</script>
<style>
:root{--ink:#1e293b;--mute:#64748b;--line:#e2e8f0;--bg:#eef2f7}
*{box-sizing:border-box}
body{font-family:system-ui,'Microsoft YaHei',sans-serif;margin:0;background:var(--bg);color:var(--ink)}
header{background:#0f172a;color:#fff;padding:14px 26px}
header h1{margin:0;font-size:18px}
header p{margin:4px 0 0;font-size:12px;color:#94a3b8}
.chaps{display:flex;flex-wrap:wrap;gap:8px;padding:11px 26px;background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:9}
.chap{border:1px solid var(--line);background:#f8fafc;border-radius:9px;padding:8px 15px;cursor:pointer;font-size:13px;color:#334155;font-weight:600}
.chap:hover{background:#f1f5f9}
.chap.on{background:#0f172a;color:#fff;border-color:#0f172a}
.steps{display:flex;align-items:center;gap:7px;padding:14px 26px 4px}
.dot{width:26px;height:26px;border-radius:50%;border:2px solid var(--line);background:#fff;color:#94a3b8;font-size:12px;display:flex;align-items:center;justify-content:center;cursor:pointer;font-weight:700}
.dot.on{background:#0f172a;color:#fff;border-color:#0f172a}
.dot.done{background:#dbeafe;color:#2563eb;border-color:#bfdbfe}
.dline{flex:0 0 22px;height:2px;background:var(--line)}
.stepname{margin-left:10px;font-size:13px;color:var(--mute)}
.wiz{display:flex;gap:22px;padding:14px 26px 26px;max-width:1680px;align-items:stretch}
.narr{flex:0 0 460px;display:flex;flex-direction:column;background:#fff;border:1px solid var(--line);border-radius:16px;padding:22px 24px}
.narr .ic{font-size:30px;line-height:1}
.narr h2{margin:8px 0 12px;font-size:21px;line-height:1.35}
.narr .body{font-size:15px;line-height:1.95;color:#334155;flex:1 1 auto}
.narr .body b{color:#0f172a}
.narr .body .hot{color:#c0392b;font-weight:700}
.param{margin-top:14px;background:#0f172a;color:#e2e8f0;border-radius:12px;padding:13px 15px;font-size:12.5px;line-height:1.7}
.param .pt{color:#7dd3fc;font-weight:700;font-size:11px;letter-spacing:1px;margin-bottom:6px}
.param table{width:100%;border-collapse:collapse}
.param td{padding:3px 2px;vertical-align:top}
.param td:first-child{color:#94a3b8;white-space:nowrap;padding-right:10px}
.fml{background:#f8fafc;border:1px solid var(--line);border-left:3px solid #7c3aed;border-radius:8px;padding:9px 14px;margin:8px 0;font-family:'Cambria Math','Latin Modern Math','Times New Roman',serif;font-size:15.5px;color:#1e293b;line-height:2;overflow-x:auto}
.fml i{color:#7c3aed;font-style:italic}.fml .wh{color:#64748b;font-size:11.5px;font-family:system-ui;font-style:normal}
.nav{display:flex;gap:10px;margin-top:18px}
.nav button{flex:1;border:1px solid var(--line);background:#f8fafc;border-radius:10px;padding:11px;cursor:pointer;font-size:14px;font-weight:600;color:#334155}
.nav button.primary{background:#0f172a;color:#fff;border-color:#0f172a}
.nav button:disabled{opacity:.4;cursor:default}
.viz{flex:1 1 auto;min-width:0;background:#fff;border:1px solid var(--line);border-radius:16px;padding:14px;display:flex;flex-direction:column}
.viz .vt{font-size:12px;color:var(--mute);margin:0 0 4px}
.chart{flex:1 1 auto;min-height:520px}
.viz.empty{align-items:center;justify-content:center;color:#cbd5e1;font-size:14px}
.nav2{display:flex;flex-wrap:wrap;gap:7px;padding:11px 26px;background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:9}
.nav2 button{border:1px solid var(--line);background:#f8fafc;border-radius:8px;padding:8px 13px;cursor:pointer;font-size:12.5px;color:#334155;font-weight:600}
.nav2 button.on{background:#0f172a;color:#fff;border-color:#0f172a}
.content{padding:18px 26px 44px;max-width:1500px}
.sechead{margin:4px 0 14px}
.sechead h2{margin:0;font-size:22px} .sechead .sub{font-size:13px;color:var(--mute);margin-top:4px;line-height:1.6;max-width:1000px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(176px,1fr));gap:14px;margin-bottom:16px}
.kpi{background:#fff;border:1px solid var(--line);border-radius:14px;padding:13px 16px;border-left:4px solid #94a3b8}
.kpi .kl{font-size:11px;color:var(--mute);font-weight:600;letter-spacing:.5px}
.kpi .kn{font-size:29px;font-weight:800;line-height:1.1;margin:3px 0}
.kpi .ks{font-size:12px;color:#475569}
.kpi.good{border-left-color:#16a34a}.kpi.good .kn{color:#16a34a}
.kpi.pos{border-left-color:#2563eb}.kpi.pos .kn{color:#2563eb}
.kpi.warn{border-left-color:#f59e0b}.kpi.warn .kn{color:#d97706}
.kpi.bad{border-left-color:#dc2626}.kpi.bad .kn{color:#dc2626}
.cards{display:grid;grid-template-columns:repeat(12,1fr);gap:16px}
.card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:15px 18px;grid-column:span 12}
.card.h4{grid-column:span 4}.card.h5{grid-column:span 5}.card.h6{grid-column:span 6}.card.h7{grid-column:span 7}.card.h8{grid-column:span 8}
.card h3{margin:0 0 3px;font-size:15px}.card .note{font-size:12px;color:var(--mute);margin:0 0 10px;line-height:1.55}
.card .chart{height:340px}
.card p{font-size:13.5px;line-height:1.85;color:#334155;margin:0 0 8px}.card p b{color:#0f172a}.hot{color:#c0392b;font-weight:700}
table.t{width:100%;border-collapse:collapse;font-size:12.5px}
table.t th{text-align:left;color:var(--mute);font-weight:600;border-bottom:1px solid var(--line);padding:6px 7px}
table.t td{padding:6px 7px;border-bottom:1px solid #f5f7fa;color:#334155;font-variant-numeric:tabular-nums}
table.t tr.hl td{background:#fef2f2;color:#c0392b;font-weight:700}
.chips{display:flex;flex-wrap:wrap;gap:7px;margin:6px 0}
.fchip{background:#eef2ff;border:1px solid #c7d2fe;color:#3730a3;border-radius:999px;padding:4px 11px;font-size:12px;font-weight:600}
.param{background:#0f172a;color:#e2e8f0;border-radius:12px;padding:12px 14px;font-size:12.5px;line-height:1.7}
.param .pt{color:#7dd3fc;font-weight:700;font-size:11px;letter-spacing:1px;margin-bottom:6px}
.param table{width:100%}.param td{padding:3px 2px;vertical-align:top}.param td:first-child{color:#94a3b8;padding-right:12px;white-space:nowrap}
@media(max-width:1100px){.card.h4,.card.h5,.card.h6,.card.h7,.card.h8{grid-column:span 12}}
</style></head><body>
<header><h1>移为通信(300590)市值影响研究 · 因果 ML 报告</h1>
<p>按标准 ML 报告八段组织(因果版:学习曲线→nuisance诊断、准确率→ATE+CI、混淆矩阵→稳健性/功效)。口径承自 DECISION_LEDGER INV-013~030。</p></header>
<div class="nav2" id="nav"></div>
<div class="content" id="content"></div>
<script>
const FIN=__FIN__, CAUSAL=__CAUSAL__, REPORT=__REPORT__, PEER=__PEER__, CFO=__CFO__, TRAIN=__TRAIN__;
__APP__
</script></body></html>"""

if __name__ == "__main__":
    main()
