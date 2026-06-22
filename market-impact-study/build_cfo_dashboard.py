"""Build the final CFO market-cap dashboard — ONLY triangulation-passed conclusions, self-contained ECharts."""

# 职责：把"经得起审"的硬结论做成给 CFO 看的自包含仪表板 = INV-042。只画过 consilience 的结论:
#   ① 移为诊断(市值=营收×倍数,病根=营收慢+行业估值压缩)② 13家逐家乘法分解 ③ 战略画像(海外占比×增速)
#   ④ 验证过的硬结论(H1成长打折5/5、H2低杠杆5/5;H3盈利证伪诚实展示)⑤ 能解释vs情绪天花板 ⑥ 方法透明(WCB/三角/SHAP降级)。
# 不做什么：不重算(只读 JSON);不画未过三角验证的 SHAP 裸排名/伪规律。
# 允许依赖层：标准库、json;读 cate_14firm 的 mcap_attribution/drivers_triangulation/attribution_rigorous。
# 谁不应该 import：建模脚本不应 import 本入口。
from __future__ import annotations

import base64
import json
import math
from pathlib import Path

C = Path("market-impact-study/data/processed/modeling/cate_14firm")
ECHARTS = Path("market-impact-study/docs/assets/echarts.min.js")
LOGO = Path("market-impact-study/docs/assets/ecnu_logo.svg")
OUT = Path("market-impact-study/data/processed/cfo_dashboard.html")
YIWEI = "300590.SZ"


def bundle() -> dict:
    mc = json.loads((C / "mcap_attribution.json").read_text(encoding="utf-8"))
    tri = json.loads((C / "drivers_triangulation.json").read_text(encoding="utf-8"))
    exp = json.loads((C / "driver_explanation.json").read_text(encoding="utf-8"))
    wb = json.loads((C / "whitebox_proof.json").read_text(encoding="utf-8"))
    val = json.loads((C / "valuation_model.json").read_text(encoding="utf-8"))
    rig = json.loads((C / "attribution_rigorous.json").read_text(encoding="utf-8"))
    firms = []
    for p in mc["per_firm"]:
        firms.append(
            {
                "firm": p["firm"],
                "is_yiwei": p["code"] == YIWEI,
                "mcap": p["mcap_mult"],
                "rev": p["rev_mult"],
                "ps": p["ps_mult"],
                "ln_rev": round(math.log(max(p["rev_mult"], 1e-3)), 3),
                "ln_ps": round(math.log(max(p["ps_mult"], 1e-3)), 3),
                "rev_cagr": p["rev_cagr"],
                "ov_share": p.get("overseas_share"),
                "ov_cagr": p.get("overseas_cagr"),
                "tag": p.get("strategy_tag", "—"),
            }
        )
    yw = next(f for f in firms if f["is_yiwei"])
    return {
        "firms": firms,
        "yiwei": yw,
        "elasticity": mc["mcap_rev_elasticity"],
        "channel": mc["overall_channel"],
        "rerating_r2": mc["rerating_r2_with_firm_fe"],
        "tri": {
            k: {
                "name": v["name"],
                "verdict": v["verdict"],
                "passes": v["passes"],
                "p_wcb": v["p_wcb"],
                "p_perm": v["p_perm"],
                "p_plac": v["p_placebo"],
                "coef": v.get("slope", v.get("beta")),
                "within": v.get("within_firm_slope", v.get("within_firm_beta")),
                "leadlag": v.get("leadlag"),
            }
            for k, v in tri.items()
        },
        "explain": {
            "guardrail": exp["guardrail"],
            "yiwei_level": exp["counterfactual_level"]["by_firm"].get("移为通信", {}),
            "level_note": exp["counterfactual_level"]["note"],
            "mcap": exp["counterfactual_mcap"],
            "dependence": exp["dependence"],
            "narratives": exp["firm_narratives"],
            "rerating": exp["rerating_triggers"],
            "per_firm": exp["per_firm_analysis"],
        },
        "whitebox": wb,
        "model": {
            "n_obs": val["n_obs"], "n_firms": val["n_firms"], "y0": val["year_min"], "y1": val["year_max"],
            "target": val["target"], "n_all": val["n_features_all"], "n_sel": val["n_features_selected"],
            "selected": val["selected_features"], "dropped": val["dropped_features"], "params": val["gbt_params"],
            "l1": val.get("l1_selection", {}),
            "r2": {"insample": val["insample_r2"], "oot": val["oot_r2"], "lofo": val["lofo_r2"]},
            "metrics": val.get("metrics", {}),
            "unexplained": val["unexplained_share"], "shap": val["shap_importance"][:10],
            "elasticnet": val["elasticnet_coef"][:8], "fe": val["fe_validation"],
            "contam": rig["feature_contamination_tags"],
            "screen": val.get("mispricing_screen", {}),  # 错误定价筛查:分类多指标 + 移为情绪缺口(M4/应用页用)
            "lc": val.get("learning_curve", {}),  # 学习曲线(实验图,训练页用)
            "pva": val.get("pred_actual", []),  # LOFO 预测vs实际散点(实验图,评估页用)
            "eda": val.get("eda", {}),  # 探索性数据分析(EDA 页用)
        },
    }


SHELL = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>移为通信 · 市值诊断(经三角验证)</title>
<script>__ECHARTS__</script><style>
:root{--ink:#2b2422;--dark:#4a211a;--mute:#6f6259;--line:#d4c7ac;--frame:#a9926b;--soft:#faf5ec;--brand:#a32135;--brand-dark:#7d1828;--gold:#d8b15a;--grn:#2e7d32;--w:1920px;--h:1080px;--ml:86px;--mr:86px}
*{box-sizing:border-box}
body{margin:0;background:#e9e2d4;font-family:"Source Han Sans SC","Microsoft YaHei","微软雅黑",Arial,sans-serif;color:var(--ink)}
.deck{padding:20px 0 50px}
.slide{width:var(--w);height:var(--h);margin:20px auto;position:relative;overflow:hidden;background:#fff;box-shadow:0 10px 32px rgb(0 0 0/16%);display:flex;flex-direction:column}
.slide::before,.slide::after{content:"";position:absolute;left:0;width:100%;height:7px;background:var(--brand);z-index:2}
.slide::before{top:0}.slide::after{bottom:0}
.brand{position:absolute;top:38px;right:76px;height:96px;width:520px;background:url('__LOGO__') right center/contain no-repeat;z-index:4}
.page{position:absolute;right:74px;bottom:32px;color:#9a8e80;font-size:20px;font-weight:700;z-index:5}
.header{padding:46px var(--mr) 10px var(--ml);flex:0 0 auto}
.kicker{font-size:20px;color:var(--brand);font-weight:700;margin-bottom:8px;letter-spacing:1px}
.title{font-size:44px;line-height:1.2;font-weight:700;color:var(--brand-dark);max-width:1480px;margin:0}
.title::after{content:"";display:block;width:240px;height:4px;background:var(--brand);margin-top:14px}
.subtitle{margin-top:14px;color:var(--mute);font-size:23px;line-height:1.5;max-width:1580px}.subtitle b{color:var(--brand)}
.body{flex:1;padding:16px var(--mr) 50px var(--ml);display:flex;flex-direction:column;gap:20px;overflow:hidden;justify-content:space-between}
.srow{display:flex;gap:36px;flex:1;min-height:0;align-items:stretch}.scol{flex:1;min-width:0;display:flex;flex-direction:column;justify-content:space-between;gap:18px}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:24px}
.metric{border-left:7px solid var(--brand);background:var(--soft);border-radius:6px;padding:24px 30px;display:flex;flex-direction:column;justify-content:center}
.metric .num{color:var(--brand);font-size:46px;line-height:1;font-weight:700}
.metric .cap{color:var(--mute);font-size:21px;line-height:1.4;margin-top:12px}.metric .cap b{color:var(--ink)}
.card{border:1.5px solid var(--frame);background:#fff;border-radius:6px;padding:24px 30px;display:flex;flex-direction:column;justify-content:center}
.card h3{font-size:27px;line-height:1.3;margin:0 0 12px;font-weight:700;color:var(--ink)}
p{font-size:23px;line-height:1.6;color:var(--mute);margin:0 0 12px}.hot{color:var(--brand);font-weight:700}p b{color:var(--ink)}
.callout{border-left:8px solid var(--brand);background:#fbf3e8;border-radius:0 6px 6px 0;padding:22px 30px;color:var(--brand);font-size:26px;line-height:1.5;font-weight:700}
.note{color:var(--mute);font-size:20px;line-height:1.6;margin:0 0 10px}
.chart{width:100%;min-height:360px;flex:1;border:1.5px solid var(--frame);border-radius:6px;background:#fdfbf6}
/* ===== HTML/CSS 柱状图(矢量清晰,替代部分 ECharts)===== */
.hbar{flex:1;min-height:320px;border:1.5px solid var(--frame);border-radius:6px;background:#fff;padding:24px 24px 16px;display:flex;flex-direction:column;gap:12px}
.hbar-main{flex:1;display:flex;gap:10px;min-height:0}
.hbar-yaxis{display:flex;flex-direction:column;justify-content:space-between;align-items:flex-end;width:54px;font-size:18px;color:var(--mute);padding-bottom:42px}
.hbar-right{flex:1;display:flex;flex-direction:column;min-width:0}
.hbar-plot{flex:1;display:flex;align-items:flex-end;justify-content:space-around;border-left:2px solid var(--frame);border-bottom:2px solid var(--frame);padding:0 14px;background:repeating-linear-gradient(to top,#e6dac4 0 1px,transparent 1px 25%),linear-gradient(to top,#f4efe3,#fffefb)}
.hbar-set{height:100%;display:flex;align-items:flex-end;gap:20px}
.hbar-bar{width:66px;border-radius:6px 6px 0 0;position:relative;display:flex;justify-content:center;align-items:flex-start;box-shadow:0 3px 9px rgba(0,0,0,.13)}
.hbar-bar .v{color:#fff;font-size:22px;font-weight:700;margin-top:10px}
.hbar-cats{display:flex;justify-content:space-around;padding:8px 14px 0;font-size:22px;color:var(--ink);font-weight:600}
.hbar-cats div{flex:1;text-align:center}
.hbar-legend{display:flex;justify-content:center;gap:36px;font-size:20px;color:var(--ink)}
.hbar-legend i{display:inline-block;width:22px;height:14px;border-radius:3px;margin-right:9px;vertical-align:middle}
/* 横向堆叠条 */
.hstack{border:1.5px solid var(--frame);border-radius:6px;background:linear-gradient(to top,#f4efe3,#fffefb);padding:28px 32px;display:flex;flex-direction:column;justify-content:center;gap:22px}
.hstack-bar{display:flex;height:104px;border-radius:8px;overflow:hidden;box-shadow:0 3px 9px rgba(0,0,0,.14)}
.hstack-seg{display:flex;flex-direction:column;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:24px;line-height:1.35;text-align:center;padding:0 8px}
.hstack-seg span{font-size:19px;font-weight:400;margin-top:3px}
.hstack-legend{display:flex;justify-content:center;gap:32px;font-size:19px;color:var(--ink)}
.hstack-legend i{display:inline-block;width:20px;height:13px;border-radius:3px;margin-right:8px;vertical-align:middle}
/* 环形图 */
.donutbox{border:1.5px solid var(--frame);border-radius:6px;background:linear-gradient(to top,#f4efe3,#fffefb);padding:18px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px}
.donut{width:200px;height:200px;border-radius:50%;display:flex;align-items:center;justify-content:center;box-shadow:0 3px 10px rgba(0,0,0,.13)}
.donut-hole{width:118px;height:118px;border-radius:50%;background:#fffefb;display:flex;align-items:center;justify-content:center}
.donut-c{text-align:center;font-size:18px;color:var(--ink);line-height:1.3}.donut-c b{font-size:32px;color:var(--brand-dark)}
.donut-leg{display:flex;flex-direction:column;gap:10px;font-size:18px;color:var(--ink)}
.donut-leg i{display:inline-block;width:18px;height:13px;border-radius:2px;margin-right:8px;vertical-align:middle}
/* 横向条形图(带参考线) */
.hbars{flex:1;min-height:480px;border:1.5px solid var(--frame);border-radius:6px;background:linear-gradient(to top,#f4efe3,#fffefb);padding:34px 34px;display:flex;flex-direction:column}
.hbars-desc{font-size:18px;color:var(--mute);margin-top:5px}
.hbars-area{position:relative;flex:1;display:flex;flex-direction:column}
.hbars-rows{flex:1;display:flex;flex-direction:column;justify-content:space-around;gap:20px}
.hbars-row{display:flex;flex-direction:column;gap:9px}
.hbars-cat{font-size:21px;color:var(--ink);font-weight:600}
.hbars-track{height:56px;background:rgba(120,100,70,.09);border-radius:7px;display:flex;align-items:center}
.hbars-fill{height:100%;border-radius:7px;display:flex;align-items:center;justify-content:flex-end;color:#fff;font-weight:700;font-size:23px;padding-right:16px;box-shadow:0 2px 7px rgba(0,0,0,.13);min-width:64px}
.hbars-ref{position:absolute;top:-10px;bottom:-10px;border-left:2px dashed #6b6155;z-index:4}
.hbars-ref span{position:absolute;top:-4px;left:8px;font-size:17px;color:#6b6155;font-weight:600;white-space:nowrap}
/* 相关性热力图 */
.heatmap{display:grid;gap:3px;flex:1;min-height:0}
.hm-cell{display:flex;align-items:center;justify-content:center;border-radius:3px;font-size:15px;font-weight:600;line-height:1.05;overflow:hidden;text-align:center}
.hm-corner{background:transparent}
.hm-row{justify-content:flex-end;padding-right:8px;color:var(--ink);font-size:14px}
.hm-col{color:var(--ink);font-size:14px;writing-mode:vertical-rl;text-orientation:upright;letter-spacing:1px;white-space:nowrap}
.pcard{border-left:7px solid var(--brand);background:var(--soft);border-radius:6px;padding:20px 28px;flex:1;display:flex;flex-direction:column;justify-content:center}
.pcard .pl{color:var(--brand);font-size:20px;font-weight:700}.pcard .pv{font-size:23px;color:var(--ink);margin-top:6px;line-height:1.45}
.chip{border:1px solid var(--line);background:var(--soft);border-radius:4px;padding:8px 16px;font-size:21px;color:var(--ink);margin:0 9px 12px 0;display:inline-block}
.chip.keep{border-color:var(--grn);color:var(--grn);background:#f2f7f2;font-weight:700}
.chip.drop{border-color:#d8d2c6;color:#9a9389;background:#f0efe9;text-decoration:line-through}
.vbadge{display:inline-block;border:2px solid;border-radius:4px;padding:2px 11px;font-size:20px;font-weight:700;margin-right:8px;background:transparent}
.pass{border-color:var(--grn);color:var(--grn)}.fail{border-color:var(--brand);color:var(--brand)}
table.t{width:100%;border-collapse:collapse;border:1.5px solid var(--frame);border-radius:6px;overflow:hidden;font-size:22px;background:#fff}
table.t th{background:var(--ink);color:#fff;text-align:left;padding:15px 14px;font-weight:700}
table.t td{border-top:1px solid var(--line);padding:14px 14px;font-variant-numeric:tabular-nums}
table.t tr.hl td{background:#fbf3e8;color:var(--brand);font-weight:700}
.sm{display:grid;grid-template-columns:repeat(4,1fr);gap:24px;flex:1}.sm .smc{border:1.5px solid var(--frame);border-radius:6px;padding:10px;background:#fff;display:flex;flex-direction:column;justify-content:center}.sm .smt{font-size:21px;text-align:center;color:var(--ink);margin-top:6px;font-weight:700}
/* ===== 封面 ===== */
.cover-square{position:absolute;width:72px;height:72px;top:86px;left:86px;background:var(--brand)}
.cover-title{position:absolute;left:0;right:0;top:372px;width:100%;text-align:center;font-size:70px;line-height:1.18;font-weight:700;color:var(--brand-dark);padding:0 160px}
.cover-rule{position:absolute;left:50%;top:560px;width:128px;height:5px;background:var(--brand);transform:translateX(-50%)}
.cover-sub{position:absolute;left:0;right:0;top:600px;text-align:center;color:var(--dark);font-size:33px;letter-spacing:4px}
.cover-members{position:absolute;left:0;right:0;top:690px;text-align:center;color:var(--ink);font-size:28px;font-weight:700}
.cover-no{position:absolute;right:96px;bottom:60px;color:#e6ddcf;font-size:112px;line-height:1;font-weight:700}
/* ===== 目录 ===== */
.toc .toca-grid{position:absolute;inset:7px 0;display:grid;grid-template-columns:660px 1fr}
.toc .toca-side{background:var(--brand-dark);color:#fff;padding:0 78px;display:flex;flex-direction:column;justify-content:center}
.toc .toca-en{font-size:22px;letter-spacing:8px;font-weight:700;color:#e9c7cc}
.toc .toca-title{font-size:96px;font-weight:700;line-height:1;margin:16px 0 28px;color:#fff}
.toc .toca-rule{width:88px;height:6px;background:var(--gold);margin-bottom:32px}
.toc .toca-lead{max-width:470px;font-size:25px;line-height:1.66;color:rgb(255 255 255/88%)}
.toc .toca-meta{margin-top:34px;font-size:20px;letter-spacing:3px;color:rgb(255 255 255/58%)}
.toc .toca-list{display:flex;flex-direction:column;padding:150px 78px 58px 72px}
.toc .toca-row{position:relative;flex:1;display:flex;align-items:center;gap:28px;border-bottom:1px solid var(--line);padding:0 16px}
.toc .toca-row:first-child{border-top:1px solid var(--line)}
.toc .tr-no{flex:none;width:86px;font-size:50px;font-weight:700;line-height:1;color:#d9cbb6}
.toc .tr-name{flex:none;width:230px;font-size:30px;font-weight:700;color:var(--ink)}
.toc .tr-note{flex:none;font-size:20px;color:var(--mute);white-space:nowrap}
.toc .tr-dots{flex:1;min-width:30px;margin-top:7px;border-bottom:2px dotted #d8cdb8}
.toc .tr-en{flex:none;font-size:17px;font-weight:700;letter-spacing:2px;color:#c9bca9}
.toc .toca-row.is-core{background:var(--soft)}
.toc .toca-row.is-core::before{content:"";position:absolute;left:0;top:0;bottom:0;width:5px;background:var(--brand)}
/* ===== 章节分隔 ===== */
.pdiv::before,.pdiv::after{display:none}
.pdiv .pd-block{position:absolute;top:0;bottom:0;right:0;width:600px;background:var(--brand-dark);clip-path:polygon(150px 0,100% 0,100% 100%,0 100%);display:flex;align-items:center;justify-content:center}
.pdiv .pd-bignum{font-size:340px;font-weight:700;line-height:1;color:rgb(255 255 255/13%);margin-left:110px}
.pdiv .pd-left{position:absolute;left:130px;top:0;bottom:0;display:flex;flex-direction:column;justify-content:center}
.pdiv .pd-part{font-size:26px;letter-spacing:8px;font-weight:700;color:var(--brand)}
.pdiv .pd-title{font-size:88px;font-weight:700;line-height:1.05;color:var(--ink);margin:18px 0 12px}
.pdiv .pd-en{font-size:24px;letter-spacing:5px;font-weight:700;color:#c9bca9}
.pdiv .pd-rule{width:92px;height:6px;background:var(--brand);margin:28px 0 24px}
.pdiv .pd-desc{font-size:24px;line-height:1.55;color:var(--mute);max-width:640px}
/* ===== 带框面板(规格表外框)===== */
.panel{border:1.5px solid var(--frame);border-radius:8px;overflow:hidden;background:#fff;display:flex;flex-direction:column}
.scol>.panel{flex:1}
.panel-h{background:var(--brand-dark);color:#fff;font-size:22px;font-weight:700;padding:14px 24px;letter-spacing:1px;flex:none}
.panel table.t{border:none;border-radius:0;flex:1;height:100%}
.panel table.t td{vertical-align:middle}
.panel table.t td:first-child{font-weight:700;color:var(--mute);width:160px;white-space:nowrap}
.panel.data table.t{height:auto}.panel.data table.t td:first-child{width:auto;white-space:normal;color:var(--ink);font-weight:400}
.panel.data table.t th{font-size:19px}.panel.data table.t td{padding:9px 12px;font-size:20px}
/* ===== 问题页:研究问题 hero + 干净目标列表 ===== */
.qhero{font-size:35px;line-height:1.5;font-weight:700;color:var(--brand-dark);margin:6px 0 34px}
.obj{display:flex;gap:22px;margin:0 0 26px}
.obj .on{font-size:44px;font-weight:700;color:var(--brand);line-height:1;flex:none;width:56px}
.obj .oh{font-size:26px;font-weight:700;color:var(--ink)}
.obj .os{font-size:21px;color:var(--mute);margin-top:6px;line-height:1.5}
/* ===== 模型架构图 ===== */
.arch{display:flex;align-items:center;justify-content:center;gap:22px;flex:none}
.arch-box{background:#fff;border:1px solid var(--line);border-top:6px solid var(--brand);border-radius:8px;padding:24px 28px;text-align:center;min-width:230px}
.arch-box.main{background:var(--brand);color:#fff;border:none;min-width:360px;padding:32px 38px}
.arch-box .ab-h{font-size:26px;font-weight:700;color:var(--brand-dark)}
.arch-box.main .ab-h{color:#fff;font-size:30px}
.arch-box .ab-s{font-size:19px;color:var(--mute);margin-top:10px;line-height:1.45}
.arch-box.main .ab-s{color:rgb(255 255 255/88%)}
.arch-op{font-size:38px;color:var(--brand);font-weight:700}
/* ===== 逻辑图:三阶段泳道技术路线 ===== */
.swim{display:flex;flex-direction:column;gap:18px;flex:1}
.lane{display:flex;flex:1;align-items:stretch}
.lane-tag{flex:none;width:240px;background:var(--brand-dark);color:#fff;border-radius:8px 0 0 8px;display:flex;flex-direction:column;justify-content:center;padding:0 28px}
.lane-tag .lt-p{font-size:19px;color:var(--gold);font-weight:700;letter-spacing:2px}
.lane-tag .lt-n{font-size:29px;font-weight:700;margin-top:8px}
.lane-steps{flex:1;display:flex;align-items:stretch;border:1px solid var(--line);border-left:none;border-radius:0 8px 8px 0;padding:14px 18px;background:var(--soft)}
.step{flex:1;background:#fff;border:1px solid var(--line);border-top:5px solid var(--brand);border-radius:6px;padding:18px 14px;display:flex;flex-direction:column;justify-content:center;text-align:center}
.step .sp-h{font-size:26px;font-weight:700;color:var(--brand-dark)}
.step .sp-s{font-size:20px;color:#3a342f;margin-top:10px;line-height:1.5}
.step-arr{display:flex;align-items:center;justify-content:center;color:var(--brand);font-size:30px;width:34px;flex:none}
.guard{display:flex;align-items:center;gap:20px;background:#fbf3e8;border:1px solid var(--line);border-left:7px solid var(--brand);border-radius:6px;padding:16px 24px}
.guard .g-l{font-family:'SimHei','Microsoft YaHei',sans-serif;font-weight:700;color:var(--brand);font-size:22px;flex:none}
.guard .g-i{font-size:20px;color:var(--ink)}
/* ===== 逻辑图:技术路线流程链(旧,留用)===== */
.flow{display:flex;flex-wrap:wrap;align-items:stretch;gap:6px 0;flex:1}
.flow-box{flex:1;min-width:160px;background:#fff;border:1px solid var(--line);border-top:6px solid var(--brand);border-radius:6px;padding:20px 14px;display:flex;flex-direction:column;justify-content:center;text-align:center}
.flow-box .fb-h{font-size:23px;font-weight:700;color:var(--brand-dark)}
.flow-box .fb-s{font-size:18px;color:var(--mute);margin-top:8px;line-height:1.4}
.flow-arrow{display:flex;align-items:center;justify-content:center;color:var(--brand);font-size:34px;font-weight:700;width:34px;flex:none}
/* ===== 逻辑图:递进阶梯 ===== */
.ladder{display:flex;align-items:flex-end;gap:22px;flex:1;padding-top:10px}
.lad-step{flex:1;background:var(--soft);border:1px solid var(--line);border-bottom:7px solid var(--brand);border-radius:6px;padding:24px 22px;display:flex;flex-direction:column;justify-content:flex-end}
.lad-step .ls-n{font-size:24px;color:var(--brand);font-weight:700;letter-spacing:2px}
.lad-step .ls-h{font-size:27px;font-weight:700;margin:10px 0 8px;color:var(--ink)}
.lad-step .ls-s{font-size:20px;color:var(--mute);line-height:1.5}
/* ===== 逻辑图:恒等分解 ===== */
.ident{display:flex;align-items:center;justify-content:center;gap:26px;flex:1}
.ident-op{font-size:64px;font-weight:700;color:var(--brand)}
.ident-box{background:#fff;border:1px solid var(--line);border-top:7px solid var(--brand);border-radius:8px;padding:34px 40px;text-align:center;min-width:300px}
.ident-box.big{border-top-color:var(--brand-dark);background:var(--soft)}
.ident-box .ib-h{font-size:26px;color:var(--mute);font-weight:700}
.ident-box .ib-v{font-size:58px;color:var(--brand-dark);font-weight:700;margin:10px 0}
.ident-box .ib-s{font-size:19px;color:var(--mute)}
@media print{@page{size:1920px 1080px;margin:0}html,body{margin:0!important;padding:0!important;background:#fff!important}.deck{padding:0!important;margin:0!important}.slide{width:1920px;height:1080px;margin:0!important;box-shadow:none!important;break-after:page;page-break-after:always}.slide:last-child{break-after:auto;page-break-after:auto}}
</style></head><body>
<div class="deck" id="deck"></div>
<script>const DATA=__DATA__;
__APP__
</script></body></html>"""


def app_js() -> str:
    return (Path("market-impact-study/docs/assets/cfo_dashboard.js")).read_text(encoding="utf-8")


def main() -> None:
    data = bundle()
    lib = ECHARTS.read_text(encoding="utf-8") if ECHARTS.exists() else ""
    logo = "data:image/svg+xml;base64," + base64.b64encode(LOGO.read_bytes()).decode() if LOGO.exists() else ""
    html = (
        SHELL.replace("__ECHARTS__", lib)
        .replace("__LOGO__", logo)
        .replace("__DATA__", json.dumps(data, ensure_ascii=False))
        .replace("__APP__", app_js())
    )
    OUT.write_text(html, encoding="utf-8")
    print(f"saved -> {OUT}  ({OUT.stat().st_size // 1024} KB)  firms={len(data['firms'])}")
    for k, t in data["tri"].items():
        print(f"  {k}: {t['verdict']}")


if __name__ == "__main__":
    main()
