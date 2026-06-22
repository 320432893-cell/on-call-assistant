/* 移为通信市值解释 · 幻灯片(16:9,转PPT)。机器学习方法为主篇,模型发现为应用篇。ECharts 出图。 */
const Y = "#a32135", F = DATA.firms, YW = DATA.yiwei, TRI = DATA.tri, EX = DATA.explain, M = DATA.model, WB = DATA.whitebox;
let charts = {};
function mk(id, opt) { const d = document.getElementById(id); if (!d) return; const c = echarts.init(d); c.setOption(Object.assign({ textStyle: { fontFamily: '"Source Han Sans SC","Microsoft YaHei",sans-serif', fontSize: 18 } }, opt)); charts[id] = c; }
function axx(name, zero) { return { name, nameTextStyle: { color: "#6f6259", fontSize: 17 }, splitLine: { lineStyle: { color: "#e3d8c2" } }, axisLabel: { color: "#6f6259", fontSize: 17 }, axisLine: { onZero: !!zero, lineStyle: { color: "#a9926b", width: 1.5 } } }; }
function yaxx(name) { return { type: "value", name, nameLocation: "middle", nameGap: 50, nameTextStyle: { color: "#6f6259", fontSize: 17 }, splitLine: { lineStyle: { color: "#e3d8c2" } }, axisLabel: { color: "#6f6259", fontSize: 17 }, axisLine: { lineStyle: { color: "#a9926b", width: 1.5 } } }; }
function kpi(l, n, s) { return `<div class="metric"><div class="num">${n}</div><div class="cap"><b>${l}</b>　${s}</div></div>`; }
function kpis(arr) { return `<div class="metrics">${arr.join("")}</div>`; }
function pcard(l, v) { return `<div class="pcard"><div class="pl">${l}</div><div class="pv">${v}</div></div>`; }
function chip(t) { return `<span class="chip">${t}</span>`; }
function cssHeatmap(mat, names) {
  const ab = { "营业利润率": "营业利润", "资产周转率": "资产周转", "营收3年CAGR": "营收成长", "资产负债率": "资产负债", "海外收入占比": "海外占比" };
  const dn = names.map(x => ab[x] || x);
  const n = names.length;
  const cc = v => { const a = Math.min(1, Math.abs(v)); const bg = v >= 0 ? `rgba(163,33,53,${a.toFixed(2)})` : `rgba(29,53,87,${a.toFixed(2)})`; return `<div class="hm-cell" style="background:${bg};color:${a > 0.55 ? "#fff" : "#3a342f"}">${v.toFixed(2)}</div>`; };
  const head = `<div class="hm-cell hm-corner"></div>` + dn.map(nm => `<div class="hm-cell hm-col">${nm}</div>`).join("");
  const body = mat.map((row, i) => `<div class="hm-cell hm-row">${dn[i]}</div>` + row.map(cc).join("")).join("");
  return `<div class="heatmap" style="grid-template-columns:108px repeat(${n}, 1fr);grid-template-rows:84px repeat(${n}, 1fr)">${head}${body}</div>`;
}
function cssBars(cats, series, maxV) {
  const yax = [1, 0.75, 0.5, 0.25, 0].map(f => `<span>${+(maxV * f).toFixed(2)}</span>`).join("");
  const sets = cats.map((cat, i) => {
    const bars = series.map(s => `<div class="hbar-bar" style="height:${Math.max(3, (s.data[i] / maxV) * 100)}%;background:${s.color}"><span class="v">${s.data[i]}</span></div>`).join("");
    return `<div class="hbar-set">${bars}</div>`;
  }).join("");
  const catrow = cats.map(c => `<div>${c}</div>`).join("");
  const leg = series.map(s => `<span><i style="background:${s.color}"></i>${s.name}</span>`).join("");
  return `<div class="hbar"><div class="hbar-main"><div class="hbar-yaxis">${yax}</div>`
    + `<div class="hbar-right"><div class="hbar-plot">${sets}</div><div class="hbar-cats">${catrow}</div></div></div>`
    + `<div class="hbar-legend">${leg}</div></div>`;
}
function cssStack(segs, total) {
  const bar = segs.map(s => `<div class="hstack-seg" style="width:${(s.value / total * 100).toFixed(1)}%;background:${s.color}">+${s.value}<span>${Math.round(s.value / total * 100)}%</span></div>`).join("");
  const leg = segs.map(s => `<span><i style="background:${s.color}"></i>${s.name}</span>`).join("");
  return `<div class="hstack"><div class="hstack-bar">${bar}</div><div class="hstack-legend">${leg}</div></div>`;
}
function cssDonut(segs, centerLabel) {
  let acc = 0;
  const stops = segs.map(s => { const a = acc; acc += s.pct; return `${s.color} ${a}% ${acc}%`; }).join(",");
  const leg = segs.map(s => `<span><i style="background:${s.color}"></i>${s.name} ${s.pct}%</span>`).join("");
  return `<div class="donutbox"><div class="donut" style="background:conic-gradient(${stops})"><div class="donut-hole"><div class="donut-c"><b>${segs[0].pct}%</b><br>${centerLabel}</div></div></div><div class="donut-leg">${leg}</div></div>`;
}
function driversBars() {
  const rows = [["H1 成长被折价", TRI.H1.coef, TRI.H1.within, true], ["H2 低杠杆 \u2194 高估值", TRI.H2.coef, TRI.H2.within, true], ["H3 盈利率驱动", TRI.H3.coef, TRI.H3.within, false]];
  const mx = 0.55;
  const cards = rows.map(h => {
    const w1 = Math.min(100, Math.abs(h[1]) / mx * 100), w2 = Math.min(100, Math.abs(h[2]) / mx * 100);
    const tag = h[3] ? '<span style="color:#2e7d32">\u2713 稳健</span>' : '<span style="color:#a32135">\u2717 证伪</span>';
    return `<div style="flex:1;border:1.5px solid var(--frame);border-radius:6px;padding:14px 20px;background:#fdfbf6"><div style="font-weight:700;font-size:20px;margin-bottom:10px">${h[0]} ${tag}</div><div style="font-size:16px;color:var(--mute)">跨公司系数 ${h[1]}</div><div style="height:15px;background:#9a9a9a;width:${w1}%;border-radius:3px;margin:4px 0 9px"></div><div style="font-size:16px;color:var(--mute)">公司内系数 ${h[2]}</div><div style="height:15px;background:${h[3] ? "#a32135" : "#cfccc4"};width:${w2}%;border-radius:3px;margin:4px 0 0"></div></div>`;
  }).join("");
  return `<div style="display:flex;gap:24px;flex:none;margin:2px 0 8px">${cards}</div>`;
}
function cssHBars(rows, ref) {
  const mx = Math.max(...rows.map(r => r.value)) * 1.18;
  const bars = rows.map(r => `<div class="hbars-row"><div class="hbars-cat">${r.name}</div><div class="hbars-track"><div class="hbars-fill" style="width:${(r.value / mx * 100).toFixed(1)}%;background:${r.color}">×${r.value}</div></div>${r.desc ? `<div class="hbars-desc">${r.desc}</div>` : ""}</div>`).join("");
  const refLine = ref ? `<div class="hbars-ref" style="left:${(ref / mx * 100).toFixed(1)}%"><span>持平 ×${ref}</span></div>` : "";
  return `<div class="hbars"><div class="hbars-area">${refLine}<div class="hbars-rows">${bars}</div></div></div>`;
}

/* ---- 业务图 ---- */
function o_yiwei() {
  return { grid: { left: 70, right: 40, top: 14, bottom: 30 }, tooltip: { valueFormatter: v => "×" + v },
    xAxis: axx("倍数(2017→2025)"), yAxis: { type: "category", data: ["市值", "估值倍数", "营收"], axisLabel: { color: "#4a423c", fontWeight: 600 } },
    series: [{ type: "bar", barWidth: "55%", data: [{ value: YW.mcap, itemStyle: { color: Y } }, { value: YW.ps, itemStyle: { color: "#9b2226" } }, { value: YW.rev, itemStyle: { color: "#2f5d50" } }],
      label: { show: true, position: "right", formatter: p => "×" + p.value, fontWeight: 700 },
      markLine: { silent: true, symbol: "none", data: [{ xAxis: 1 }], lineStyle: { color: "#4a423c", type: "dashed" }, label: { formatter: "持平=1", color: "#4a423c" } } }] };
}
function o_firms() {
  const fs = [...F].sort((a, b) => a.ln_rev + a.ln_ps - (b.ln_rev + b.ln_ps));
  return { grid: { left: 64, right: 26, top: 28, bottom: 24 }, legend: { top: 0, data: ["经营(营收)", "估值(再定价)"], textStyle: { fontSize: 17 } },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: p => { const f = fs[p[0].dataIndex]; return `${f.firm}<br>市值×${f.mcap} = 营收×${f.rev} × 倍数×${f.ps}`; } },
    xAxis: axx("市值对数变化 = 经营 + 估值", true),
    yAxis: { type: "category", data: fs.map(f => f.firm), axisLabel: { color: "#4a423c" } },
    series: [
      { name: "经营(营收)", type: "bar", stack: "t", itemStyle: { color: "#2f5d50" }, data: fs.map(f => ({ value: +f.ln_rev.toFixed(2), itemStyle: { color: f.is_yiwei ? "#2f5d50" : "rgba(47,93,80,.5)" } })) },
      { name: "估值(再定价)", type: "bar", stack: "t", itemStyle: { color: "#9b2226" }, data: fs.map(f => ({ value: +f.ln_ps.toFixed(2), itemStyle: { color: f.is_yiwei ? "#9b2226" : "rgba(155,34,38,.5)" } })) },
    ] };
}
function o_strategy() {
  const d = F.filter(f => f.ov_share != null && f.ov_cagr != null).map(f => ({
    value: [f.ov_share, f.ov_cagr, f.mcap, f.firm],
    itemStyle: { color: f.is_yiwei ? Y : "#1d3557", opacity: f.is_yiwei ? 1 : .6, borderColor: f.is_yiwei ? "#7d1828" : "rgba(0,0,0,.1)", borderWidth: f.is_yiwei ? 2.5 : .5 },
    label: { show: true, formatter: f.firm, position: "right", color: f.is_yiwei ? Y : "#6f6259", fontWeight: f.is_yiwei ? 700 : 500, fontSize: f.is_yiwei ? 12 : 10 } }));
  return { grid: { left: 84, right: 132, top: 14, bottom: 42 }, tooltip: { formatter: p => `${p.data.value[3]}<br>海外占比 ${p.data.value[0]}%<br>海外增速 ${p.data.value[1]}%<br>市值 ×${p.data.value[2]}` },
    xAxis: Object.assign(axx("海外收入占比 %"), { max: 108 }), yAxis: yaxx("海外营收增速 %"),
    series: [{ type: "scatter", data: d, symbolSize: v => Math.max(14, Math.sqrt(Math.max(v[2], .3)) * 14),
      markLine: { silent: true, symbol: "none", lineStyle: { color: "#9a9a9a", type: "dashed" }, data: [{ yAxis: 30, label: { formatter: "增速30%", color: "#9a9a9a" } }] } }] };
}
function o_pd() {
  const dep = EX.dependence["资产负债率"]; if (!dep) return {};
  const fp = dep.firms.map(f => ({ value: [f.x, f.y], itemStyle: { color: f.is_yiwei ? Y : "#9a9a9a", opacity: f.is_yiwei ? 1 : .7 },
    label: { show: f.is_yiwei, formatter: "移为", position: "top", color: Y, fontWeight: 700 } }));
  return { grid: { left: 56, right: 26, top: 24, bottom: 36 }, legend: { top: 0, data: ["模型隐含响应", "各家落点"], textStyle: { fontSize: 17 } },
    tooltip: { trigger: "item", formatter: p => p.seriesName === "各家落点" ? `${dep.firms[p.dataIndex].firm}<br>资产负债率 ${p.value[0]}%<br>超额估值 ${p.value[1]}` : `负债率 ${p.value[0]}%<br>隐含超额估值 ${p.value[1]}` },
    xAxis: axx("资产负债率 %"), yAxis: axx("超额估值", true),
    series: [
      { name: "模型隐含响应", type: "line", smooth: true, data: dep.curve.map(c => [c.x, c.y]), lineStyle: { color: "#1d3557", width: 3 }, symbol: "none", z: 1 },
      { name: "各家落点", type: "scatter", data: fp, symbolSize: 11, z: 2 },
    ] };
}
function o_mcap_cf() {
  const s = EX.mcap.scenarios;
  return { grid: { left: 50, right: 26, top: 20, bottom: 30 }, tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: p => { const d = s[p[0].dataIndex]; return `${d.scenario}<br>营收CAGR ${d.rev_cagr}%<br>市值 ×${d.mcap_mult}`; } },
    xAxis: { type: "category", data: s.map(d => d.scenario), axisLabel: { color: "#4a423c", fontWeight: 600 } }, yAxis: axx("市值倍数 ×"),
    series: [{ type: "bar", barWidth: "46%", data: s.map(d => ({ value: d.mcap_mult, itemStyle: { color: d.scenario === "移为实际" ? Y : "#2f5d50" } })),
      label: { show: true, position: "top", formatter: p => "×" + p.value, fontWeight: 700 } }] };
}
function o_pathmini(f) {
  const p = f.path;
  return { grid: { left: 6, right: 6, top: 8, bottom: 6 }, tooltip: { trigger: "axis", valueFormatter: v => (v >= 0 ? "+" : "") + v },
    xAxis: { type: "category", data: p.map(d => d.yr), show: false }, yAxis: { type: "value", show: false },
    series: [
      { type: "line", data: p.map(d => d.cum_rev), smooth: true, symbol: "none", lineStyle: { color: "#2f5d50", width: 1.5 } },
      { type: "line", data: p.map(d => d.cum_ps), smooth: true, symbol: "none", lineStyle: { color: "#9b2226", width: 1.5 } },
      { type: "line", data: p.map(d => d.cum_mv), smooth: true, symbol: "none", lineStyle: { color: f.is_yiwei ? Y : "#0f172a", width: 2.5 } },
    ] };
}

/* ---- ML 图 ---- */
function o_featgrp() {
  const g = [["盈利能力", 7], ["资本结构/偿债", 5], ["现金流质量", 5], ["所有权/资金面", 6], ["流动性/筹码", 5], ["成长性", 4], ["费用/研发", 4], ["营运效率", 3], ["趋势Δ", 2], ["海外营收占比", 1]];
  g.sort((a, b) => a[1] - b[1]);
  return { grid: { left: 130, right: 44, top: 8, bottom: 26 }, tooltip: { trigger: "item", formatter: p => p.name + ":" + p.value + " 项" },
    xAxis: axx("候选特征数"), yAxis: { type: "category", data: g.map(x => x[0]), axisLabel: { color: "#334155" } },
    series: [{ type: "bar", data: g.map(x => x[1]), itemStyle: { color: "#a32135" }, label: { show: true, position: "right", formatter: p => p.value, fontSize: 16, fontWeight: 700 } }] };
}
function o_l1() {
  const f = [...M.l1.features].sort((a, b) => a.coef - b.coef);
  return { grid: { left: 160, right: 44, top: 8, bottom: 28 },
    tooltip: { trigger: "item", formatter: p => { const x = f[p.dataIndex]; return `${x.feat}<br>L1 系数 ${x.coef}<br>${x.kept ? "✓ 选中" : "✕ 舍弃(压缩至零)"}`; } },
    xAxis: axx("L1 标准化系数(0 = 被剔除)", true),
    yAxis: { type: "category", data: f.map(x => x.feat), axisLabel: { color: "#3a342f", fontSize: 17 } },
    series: [{ type: "bar", data: f.map(x => ({ value: x.coef, itemStyle: { color: x.kept ? (x.coef < 0 ? "#a32135" : "#2f5d50") : "#d8d2c6" } })) }] };
}
function o_shap() {
  const d = [...M.shap].reverse();
  return { grid: { left: 120, right: 44, top: 8, bottom: 26 }, tooltip: { trigger: "item", formatter: p => `${p.name}<br>平均|SHAP| ${p.value}` },
    xAxis: axx("平均 |SHAP|(对超额估值的平均影响幅度)"), yAxis: { type: "category", data: d.map(x => x.feat), axisLabel: { color: "#4a423c" } },
    series: [{ type: "bar", data: d.map(x => ({ value: x.shap, itemStyle: { color: x.dir < 0 ? "#1d3557" : x.dir > 0 ? "#2f5d50" : "#9a9a9a" } })), label: { show: true, position: "right", formatter: p => p.value, fontSize: 17 } }] };
}
function o_r2val() {
  const r = M.r2;
  return { grid: { left: 50, right: 26, top: 22, bottom: 28 }, tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: ["样本内", "样本外 OOT", "留一家 LOFO"], axisLabel: { color: "#4a423c", fontWeight: 600 } }, yAxis: axx("R²"),
    series: [{ type: "bar", barWidth: "46%", data: [{ value: r.insample, itemStyle: { color: "#9a9a9a" } }, { value: r.oot, itemStyle: { color: "#1d3557" } }, { value: r.lofo, itemStyle: { color: "#2f5d50" } }],
      label: { show: true, position: "top", formatter: p => p.value, fontWeight: 700 } }] };
}
function o_learncurve() {
  const lc = M.lc; if (!lc || !lc.train_sizes) return {};
  return { grid: { left: 84, right: 34, top: 34, bottom: 36 },
    legend: { top: 2, data: ["训练集 R²", "交叉验证 R²"], textStyle: { fontSize: 17 } },
    tooltip: { trigger: "axis", valueFormatter: v => (v == null ? "—" : v) },
    xAxis: Object.assign(axx("训练样本量(观测数)"), { type: "category", data: lc.train_sizes, boundaryGap: false }),
    yAxis: Object.assign(yaxx("R²"), { min: 0, max: 1 }),
    series: [
      { name: "训练集 R²", type: "line", data: lc.train_r2, smooth: true, symbolSize: 8, lineStyle: { color: "#9a9a9a", width: 3 }, itemStyle: { color: "#9a9a9a" },
        label: { show: true, position: "bottom", formatter: p => p.value, color: "#9a9a9a", fontSize: 17 } },
      { name: "交叉验证 R²", type: "line", data: lc.cv_r2, smooth: true, symbolSize: 8, lineStyle: { color: Y, width: 3.5 }, itemStyle: { color: Y },
        label: { show: true, position: "top", formatter: p => p.value, color: Y, fontWeight: 700, fontSize: 17 } },
    ] };
}
function o_pva() {
  const pa = M.pva; if (!pa || !pa.length) return {};
  const all = pa.map(d => d.a).concat(pa.map(d => d.p));
  const lo = Math.floor(Math.min(...all) * 10) / 10, hi = Math.ceil(Math.max(...all) * 10) / 10;
  const oth = pa.filter(d => !d.yw).map(d => [d.a, d.p]);
  const yw = pa.filter(d => d.yw).map(d => [d.a, d.p]);
  return { grid: { left: 84, right: 30, top: 30, bottom: 42 },
    legend: { top: 2, data: ["其余公司", "移为通信", "理想线 y=x"], textStyle: { fontSize: 17 } },
    tooltip: { trigger: "item", formatter: p => p.seriesType === "scatter" ? `实际 ${p.value[0]}　预测 ${p.value[1]}` : "理想线 y=x" },
    xAxis: Object.assign(axx("实际超额估值"), { type: "value", min: lo, max: hi }),
    yAxis: Object.assign(yaxx("LOFO 预测超额估值"), { min: lo, max: hi }),
    series: [
      { name: "理想线 y=x", type: "line", data: [[lo, lo], [hi, hi]], symbol: "none", lineStyle: { color: "#9a9a9a", type: "dashed", width: 2 }, z: 1 },
      { name: "其余公司", type: "scatter", data: oth, symbolSize: 8, itemStyle: { color: "rgba(29,53,87,.5)" }, z: 2 },
      { name: "移为通信", type: "scatter", data: yw, symbolSize: 12, itemStyle: { color: Y, borderColor: "#7d1828", borderWidth: 1.5 }, z: 3 },
    ] };
}
function o_gap() {
  const g = M.screen && M.screen.yiwei_mispricing; if (!g || g.actual_excess == null) return {};
  const exp = g.fundamental_justified, sen = g.sentiment_gap;
  const ep = Math.round((g.explained_share || 0) * 100), sp = Math.round((g.sentiment_share || 0) * 100);
  return { grid: { left: 30, right: 44, top: 40, bottom: 40 },
    legend: { top: 4, data: ["基本面可解释", "情绪 / 未解释"], textStyle: { fontSize: 17 } },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: v => "+" + v },
    xAxis: Object.assign(axx("超额估值(对数)"), { type: "value", max: +(g.actual_excess * 1.15).toFixed(2) }),
    yAxis: { type: "category", data: ["移为实际溢价 +" + g.actual_excess], axisLabel: { color: "#4a423c", fontWeight: 700, fontSize: 17 } },
    series: [
      { name: "基本面可解释", type: "bar", stack: "x", barWidth: 64, data: [exp], itemStyle: { color: "#1d3557" },
        label: { show: true, formatter: `基本面 +${exp}（${ep}%）`, color: "#fff", fontWeight: 700, fontSize: 17 } },
      { name: "情绪 / 未解释", type: "bar", stack: "x", barWidth: 64, data: [sen], itemStyle: { color: "#a32135" },
        label: { show: true, formatter: `情绪 +${sen}（${sp}%）`, color: "#fff", fontWeight: 700, fontSize: 17 } },
    ] };
}
function o_roc() {
  const c = M.screen && M.screen.classification; if (!c || !c.roc) return {};
  const pts = c.roc.fpr.map((f, i) => [f, c.roc.tpr[i]]);
  return { grid: { left: 84, right: 30, top: 32, bottom: 44 },
    legend: { top: 2, data: ["ROC 曲线", "随机基准"], textStyle: { fontSize: 17 } },
    tooltip: { trigger: "axis", valueFormatter: v => v },
    xAxis: Object.assign(axx("假阳性率 FPR"), { type: "value", min: 0, max: 1 }),
    yAxis: Object.assign(yaxx("真阳性率 TPR"), { min: 0, max: 1 }),
    graphic: [{ type: "text", right: 64, bottom: 78, style: { text: "AUC = " + c.auc, fontSize: 24, fontWeight: 700, fill: Y } }],
    series: [
      { name: "随机基准", type: "line", data: [[0, 0], [1, 1]], symbol: "none", lineStyle: { color: "#9a9a9a", type: "dashed", width: 2 }, z: 1 },
      { name: "ROC 曲线", type: "line", data: pts, symbol: "none", lineStyle: { color: Y, width: 3 }, areaStyle: { color: "rgba(163,33,53,.08)" }, z: 2 },
    ] };
}
function o_wb() {
  const r = WB.r2_compare, L = r.linear_whitebox, G = r.gbt;
  return { grid: { left: 70, right: 34, top: 56, bottom: 36 },
    legend: { top: 8, data: ["线性(白盒)", "GBT(黑盒)"], textStyle: { fontSize: 17 } }, tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: ["样本内", "OOT", "LOFO"], axisLabel: { color: "#4a423c", fontWeight: 600, fontSize: 17 }, axisLine: { lineStyle: { color: "#cfccc4" } } },
    yAxis: { type: "value", min: 0, max: 1, name: "R²", nameLocation: "middle", nameGap: 46, nameTextStyle: { color: "#6f6259", fontSize: 17 }, splitLine: { lineStyle: { color: "#ece3d4" } }, axisLabel: { color: "#6f6259" } },
    series: [
      { name: "线性(白盒)", type: "bar", barWidth: "30%", data: [L.insample, L.oot, L.lofo], itemStyle: { color: "#1d3557" }, label: { show: true, position: "top", fontSize: 17, fontWeight: 700, formatter: p => p.value } },
      { name: "GBT(黑盒)", type: "bar", barWidth: "30%", data: [G.insample, G.oot, G.lofo], itemStyle: { color: "#9a9a9a" }, label: { show: true, position: "top", fontSize: 17, fontWeight: 700, formatter: p => p.value } },
    ] };
}
function o_ceiling() {
  const ex = Math.round((1 - M.unexplained) * 100), un = 100 - ex;
  return { tooltip: { formatter: "{b}: {c}%" }, legend: { bottom: 0, textStyle: { fontSize: 17 } },
    series: [{ type: "pie", radius: ["45%", "70%"], center: ["50%", "44%"], label: { formatter: "{b}\n{c}%", fontSize: 17 },
      data: [{ value: ex, name: "现有数据可解释", itemStyle: { color: "#1d3557" } }, { value: un, name: "未解释残差(推测含情绪等)", itemStyle: { color: "#cfccc4" } }] }] };
}

function o_firmlines() {
  const codes = ["300590.SZ", "300638.SZ", "603236.SH", "002881.SZ", "688159.SH", "300098.SZ", "002869.SZ", "002313.SZ"];
  const fm = codes.map(c => EX.per_firm.firms.find(f => f.code === c)).filter(Boolean);
  const series = fm.map(f => ({
    name: f.firm, type: "line", smooth: true, symbol: "none",
    data: f.path.map(p => [+p.yr, p.cum_mv]),
    lineStyle: { width: f.is_yiwei ? 4.5 : 2, color: f.is_yiwei ? Y : "rgba(120,110,95,.5)" },
    z: f.is_yiwei ? 9 : 2,
    endLabel: { show: true, formatter: f.firm, color: f.is_yiwei ? Y : "#8a7f72", fontSize: f.is_yiwei ? 19 : 15, fontWeight: f.is_yiwei ? 700 : 400 },
  }));
  return { grid: { left: 86, right: 150, top: 24, bottom: 48 }, tooltip: { trigger: "axis" },
    xAxis: Object.assign(axx("年份"), { type: "value", min: "dataMin", max: "dataMax", axisLabel: { color: "#6f6259", fontSize: 17, formatter: v => v.toFixed(0) } }),
    yAxis: yaxx("累积 ln 市值(首年=0)"), series };
}
/* ---- 三角验证卡 ---- */
function triCard(key) {
  const t = TRI[key], pk = t.passes, pass5 = Object.values(pk).filter(Boolean).length, ok = pass5 >= 4;
  const badges = Object.entries(pk).map(([k, v]) => `<span class="vbadge ${v ? "pass" : "fail"}" style="font-size:21px;margin:0 6px 8px 0">${v ? "✓" : "✗"} ${k}</span>`).join("");
  return `<div class="card" style="flex:1;justify-content:space-between;gap:16px;padding:26px 30px">
    <div><h3 style="font-size:24px;line-height:1.3;margin:0 0 12px">${t.name}</h3>
      <span class="vbadge ${ok ? "pass" : "fail"}" style="font-size:23px;padding:4px 16px;font-weight:700">五维通过 ${pass5}/5${ok ? "" : " · 不予支持"}</span></div>
    <div style="display:flex;flex-wrap:wrap">${badges}</div>
    <table class="t" style="font-size:20px">
      <tr><td>回归系数</td><td>${t.coef}</td></tr>
      <tr class="hl"><td>聚类自助 p(WCB)</td><td>${t.p_wcb}</td></tr>
      <tr><td>置换检验 p</td><td>${t.p_perm}</td></tr>
      <tr><td>安慰剂检验 p</td><td>${t.p_plac}</td></tr></table></div>`;
}
function bigchart(id, note) { return `<div class="srow"><div class="scol" style="flex:1.7"><div id="${id}" class="chart"></div></div><div class="scol" style="flex:1">${note}</div></div>`; }
/* ---- 逻辑图组件 ---- */
function flowbox(h, s) { return `<div class="flow-box"><div class="fb-h">${h}</div><div class="fb-s">${s}</div></div>`; }
const ARR = `<div class="flow-arrow">▶</div>`;
function ladstep(n, h, s, ht) { return `<div class="lad-step" style="min-height:${ht}px"><div class="ls-n">${n}</div><div class="ls-h">${h}</div><div class="ls-s">${s}</div></div>`; }
function identbox(h, v, s, big) { return `<div class="ident-box${big ? " big" : ""}"><div class="ib-h">${h}</div><div class="ib-v">${v}</div><div class="ib-s">${s}</div></div>`; }
function obj(n, h, s) { return `<div class="obj"><div class="on">${n}</div><div><div class="oh">${h}</div><div class="os">${s}</div></div></div>`; }
function lane(p, n, steps) { return `<div class="lane"><div class="lane-tag"><div class="lt-p">${p}</div><div class="lt-n">${n}</div></div><div class="lane-steps">${steps.map(s => `<div class="step"><div class="sp-h">${s[0]}</div><div class="sp-s">${s[1]}</div></div>`).join('<div class="step-arr">▶</div>')}</div></div>`; }

/* ============ 内容幻灯片(封面/目录/分隔页由引擎生成) ============ */
const CONTENT = [
  // ---- PART 01 研究背景与问题 ----
  { b: () => ({
    title: "研究问题与目标",
    headline: "将公司估值的解释界定为<b>可证伪的监督学习任务</b>,而非主观财务研判。",
    html: `<div class="srow">
      <div class="scol" style="flex:0.85">
        <div class="qhero">运用可解释机器学习,<br>自公开财务数据解释公司「超额估值」之横截面差异,<br><span style="color:var(--brand)">识别实质驱动因子、量化可解释程度、界定解释力边界。</span></div>
        ${obj("①", "模型构建", "构建可解释回归模型,识别估值的实质性驱动因子")}
        ${obj("②", "稳健甄别", "经多重稳健性检验,区分真实关联与机械(算术)假象")}
        ${obj("③", "边界与实证", "量化可解释性上界,并迁移至典型样本企业的实证分析")}
      </div>
      <div class="scol" style="flex:1.15">
        <div class="panel data"><div class="panel-h">ML 任务定义 · Problem Framing</div>
        <table class="t">
        <tr><td>任务类型</td><td>监督学习 —— 公司横截面回归</td></tr>
        <tr class="hl"><td>目标变量 Y</td><td>超额估值:log(PS) 剥离年度固定效应与规模后之残差</td></tr>
        <tr><td>研究样本</td><td>模组/终端行业 ${M.n_firms} 家;面板 ${M.n_obs} 观测;${M.y0}–${M.y1}</td></tr>
        <tr><td>特征集</td><td>候选 ${M.n_all} 项,经 L1(Lasso)折内选择保留 ${M.n_sel} 项;财务理论分组,严格 PIT</td></tr>
        <tr><td>评估方案</td><td>样本外时序外推(OOT)与留一公司(LOFO);R² / RMSE / MAE 多指标</td></tr>
        <tr><td>成功判据</td><td>样本外 R² 显著为正,且关键驱动通过多方法稳健性检验</td></tr></table></div>
        <div class="panel data"><div class="panel-h">方法特色 · Methodological Highlights</div>
        <table class="t">
        <tr><td>可解释优先</td><td>单调性约束 + 线性白盒对照,黑白盒交叉印证驱动方向</td></tr>
        <tr><td>稳健推断</td><td>wild cluster bootstrap 三角验证,适配 N 小样本</td></tr>
        <tr><td>去伪机制</td><td>污染防火墙:定义级剔除含营收/市值之机械(算术)假象</td></tr>
        <tr><td>诚实边界</td><td>量化不可解释上界,不夸大模型解释力</td></tr></table></div>
      </div></div>` }) },
  { b: () => ({
    title: "研究设计 · 技术路线",
    headline: "数据准备 → 建模与验证 → 结果应用 三阶段闭环;<b>防泄漏 / 防过拟合 / 防污染</b>机制贯穿全程。",
    html: `<div class="swim">
      ${lane("PHASE 01", "数据准备", [["① 数据采集", "Tushare Pro 12 类接口全量(行情·三表·指标·主营·筹码)"], ["② 特征工程", "财务理论分组 · PIT 时点对齐"], ["③ 标签构建", "超额估值 = 剥 β + 规模 残差"]])}
      ${lane("PHASE 02", "建模与验证", [["④ 模型选型", "单调 GBT + 线性对照 + SHAP"], ["⑤ 训练优化", "嵌套 CV · L1 · 单调约束"], ["⑥ 模型评估", "OOT / LOFO · R²/RMSE/MAE"], ["⑦ 可解释", "SHAP 归因 + 白盒证明"], ["⑧ 严谨性", "WCB 三角 + 污染防火墙"]])}
      ${lane("PHASE 03", "结果与应用", [["⑨ 驱动解读", "全样本价值驱动规律"], ["⑩ 案例实证", "典型企业估值诊断"]])}
      <div class="guard"><div class="g-l">全流程防控</div><div class="g-i">防泄漏(PIT · 折内选特征)　·　防过拟合(嵌套 CV · 单调约束 · 强正则)　·　防污染(定义级防火墙剔除机械假象)</div></div>
    </div>` }) },
  // ---- PART 02 / 03 机器学习方法 ----
  { b: () => ({
    title: "① 数据来源",
    headline: "全部数据来自 <b>Tushare Pro</b>(2000 积分),<b>12 类专业接口全量采集</b>,统一按公告日 <b>PIT</b> 对齐,杜绝未来函数。",
    html: kpis([kpi("研究样本", M.n_firms + " 家", "模组/终端行业"), kpi("面板观测", M.n_obs + " 行", "公司 × 报告期"), kpi("时间跨度", M.y0 + "–" + M.y1, "逾十年"), kpi("数据接口", "12 类", "Tushare Pro 全量")])
      + `<div class="srow">
      <div class="scol" style="flex:1.45"><div class="panel"><div class="panel-h">Tushare Pro · 12 类专业接口</div>
      <table class="t">
      <tr><td>行情与估值</td><td>daily 日线;daily_basic(PS / PB / PE / 市值 / 换手 / 量比 / 振幅)</td></tr>
      <tr><td>财务三表</td><td>income · balancesheet · cashflow(完整科目)</td></tr>
      <tr class="hl"><td>财务指标</td><td>fina_indicator —— 108 字段现成比率</td></tr>
      <tr><td>主营构成</td><td>fina_mainbz(海外收入占比 / 分产品)</td></tr>
      <tr><td>筹码与资金</td><td>hk_hold 北向 · margin_detail 融资融券 · moneyflow 资金流</td></tr>
      <tr><td>股东结构</td><td>stk_holdernumber 户数 · top10_floatholders 前十大流通</td></tr>
      <tr><td>公司信息</td><td>stock_company(员工数 → 人均产出)</td></tr></table></div></div>
      <div class="scol"><div class="panel"><div class="panel-h">采集口径与质量</div>
      <table class="t">
      <tr><td>时点对齐</td><td>merge_asof 按 ann_date,严格 PIT</td></tr>
      <tr><td>覆盖</td><td>${M.n_firms} 家 · ${M.n_obs} 观测 · ${M.y0}–${M.y1}</td></tr>
      <tr><td>质量核对</td><td>关键财务项与公开源交叉核对一致</td></tr></table></div>
      <div class="panel"><div class="panel-h">数据特点</div>
      <table class="t">
      <tr><td>多维覆盖</td><td>基本面 + 行情 + 筹码 + 资金面,四维齐全</td></tr>
      <tr><td>比率现成</td><td>fina_indicator 108 字段,免重复计算</td></tr>
      <tr><td>长面板</td><td>跨逾十年,含完整行业周期</td></tr>
      <tr><td>严格 PIT</td><td>任一特征只用公告日前可得信息,杜绝泄漏</td></tr></table></div></div></div>` }) },
  { b: () => { const e = M.eda || {}, st = e.stats || [], th = e.target_hist || [];
    return { title: "② 数据探索 · 描述统计与目标分布",
      headline: `样本 ${M.n_obs} 观测 \u00d7 ${M.n_firms} 家公司;目标(超额估值)均值\u22480、近似对称单峰,无极端长尾。`,
      html: `<div class="srow" style="flex:1">
        <div class="scol"><div class="note">关键变量描述统计(目标 Y + 主要特征):</div>
          <div class="panel data"><div class="panel-h">描述性统计</div><table class="t"><tr><th>变量</th><th>n</th><th>均值</th><th>标准差</th><th>最小</th><th>中位</th><th>最大</th></tr>${st.map((r, i) => `<tr${i === 0 ? ' class="hl"' : ""}><td>${r.name}</td><td>${r.n}</td><td>${r.mean}</td><td>${r.std}</td><td>${r.min}</td><td>${r.median}</td><td>${r.max}</td></tr>`).join("")}</table></div></div>
        <div class="scol"><div class="note">目标变量(超额估值)分布直方图:近似对称、单峰,适合回归建模。</div>${cssBars(th.map(b => b.x), [{ name: "频数", color: "#1d3557", data: th.map(b => b.c) }], Math.max(1, ...th.map(b => b.c)))}</div></div>` };
  } },
  { b: () => { const e = M.eda || {};
    return { title: "③ 数据探索 · 相关性与缺失值",
      headline: "盈利类特征高度共线(净利率 \u2194 营业利润率 r=0.99),印证 L1 降维的必要性;部分市场面特征缺失率较高。",
      html: `<div class="srow" style="flex:1">
        <div class="scol" style="flex:1.3"><div class="note">特征相关性热力图(红=正相关,蓝=负相关,色深=强):盈利簇高度共线。</div>${cssHeatmap(e.corr || [], e.corr_names || [])}</div>
        <div class="scol"><div class="note">缺失率最高的特征(按公告日 PIT;建模时折内以中位数填补):</div>
          <div class="panel data"><div class="panel-h">缺失率 Top 10</div><table class="t"><tr><th>特征</th><th>缺失率</th><th>分布</th></tr>${(e.missing || []).map(m => `<tr><td>${m.feat}</td><td>${m.pct}%</td><td><div style="height:14px;width:${m.pct}%;background:#a32135;border-radius:3px"></div></td></tr>`).join("")}</table></div></div></div>` };
  } },
  { b: () => ({
    title: "④ 标签设计 · 定义解释目标 Y",
    headline: `将"公司估值的相对高低"定义为可建模的连续目标 —— <b>超额估值</b>:剥离行业与规模后、公司特异的估值溢价/折让。`,
    html: `<div class="ident" style="flex:none;margin-bottom:18px">
      <div class="ident-box"><div class="ib-h">观测值</div><div class="ib-v" style="font-size:32px">log(PS)</div><div class="ib-s">市销率对数</div></div>
      <div class="ident-op">=</div>
      <div class="ident-box"><div class="ib-h">剥离 ①</div><div class="ib-v" style="font-size:26px">年度固定效应</div><div class="ib-s">行业同步重估(de-rating/re-rating)</div></div>
      <div class="ident-op">+</div>
      <div class="ident-box"><div class="ib-h">剥离 ②</div><div class="ib-v" style="font-size:26px">log 规模</div><div class="ib-s">大小盘系统差异</div></div>
      <div class="ident-op">+</div>
      <div class="ident-box big"><div class="ib-h">目标 Y</div><div class="ib-v" style="font-size:30px">超额估值</div><div class="ib-s">公司特异溢价/折让 = 残差</div></div>
    </div>
    <div class="srow">
      <div class="scol"><div class="panel"><div class="panel-h">目标 Y 的定义依据</div><table class="t">
      <tr><td>直接用 PS</td><td>混入全行业估值水平 + 规模效应 → 非公司特异</td></tr>
      <tr><td>剥年度 FE</td><td>去除行业同步重估(de-rating/re-rating;时间共同成分)</td></tr>
      <tr><td>剥 log 规模</td><td>去大小盘系统差异</td></tr>
      <tr class="hl"><td>残差 = Y</td><td>纯公司特异溢价/折让 = 真正要解释的对象</td></tr></table></div></div>
      <div class="scol"><div class="panel"><div class="panel-h">口径选择</div><table class="t">
      <tr><td>采用 PS 的理由</td><td>对亏损公司仍适用;本行业以营收为主要锚定</td></tr>
      <tr><td>采用残差的理由</td><td>使解释力目标真实可达,隔离公司特异问题</td></tr>
      <tr><td>任务类型</td><td>连续目标 → 回归;样本外 OOT / LOFO 评估</td></tr>
      <tr><td>不预测项</td><td>不预测股价时序(市场近似有效,旧预测线样本外 IC≈0.14,已弃用)</td></tr></table></div></div></div>` }) },
  { b: () => ({
    title: "⑤ 特征工程 · 理论分组",
    headline: M.n_all + " 个候选驱动按<b>财务理论分组</b>;对模型<b>单调方向施加理论先验约束</b>,并对全部特征施加<b>严格 PIT(时点)约束</b>。",
    html: `<div class="srow">
      <div class="scol"><div class="note" style="font-size:23px;font-weight:700;color:var(--ink)">特征族与理论依据</div>
      <table class="t"><tr><th>特征族</th><th>财务理论依据</th></tr>
      <tr><td>盈利能力</td><td>杜邦分解 —— 盈利质量驱动价值</td></tr>
      <tr><td>资本结构 / 偿债</td><td>资本结构理论 —— 高杠杆↑风险↓估值</td></tr>
      <tr><td>成长性</td><td>成长性溢价 —— 增长预期定价</td></tr>
      <tr><td>现金流质量 / 营运效率</td><td>现金流贴现本质 / 营运资本管理</td></tr>
      <tr><td>费用 / 研发</td><td>费用管控;研发 → 无形资产与期权价值</td></tr>
      <tr><td>流动性 / 筹码 / 资金面</td><td>市场微观结构 —— 仅作残差解释,标注反向因果</td></tr></table>
      <div class="note" style="margin-top:10px">污染控制:对在目标 Y=ln(PS) 中与营收、市值存在算术关联的特征施加<b>定义级标记</b>,排除其作为可操作驱动的解释(详见稳健性页)。</div></div>
      <div class="scol"><div class="note" style="font-size:23px;font-weight:700;color:var(--ink)">各特征族候选数(共 ${M.n_all} 项)</div><div id="c_fg" class="chart"></div></div></div>` }) },
  { b: () => ({
    title: "⑥ 特征选择 · L1(Lasso)正则化",
    headline: `特征标准化 → GroupKFold 5 折折内 LassoCV 自动选 <b>α=${M.l1.alpha}</b> → 保留非零系数:<b>${M.n_all} → ${M.n_sel}</b>;舍弃项逐一给出共线原因。`,
    html: `<div class="callout" style="flex:none;margin-bottom:14px">采用 <b>L1(Lasso)</b>正则化:L1 将冗余特征系数压缩至 <b>0</b>,实现自动特征选择,得到<b>稀疏且可解释</b>的特征子集。在本任务的<b>高共线性</b>(净利率与营业利润率 r=0.99)与<b>小样本</b>(N=14)条件下,稀疏化对抑制过拟合、提升可解释性具有必要性;L2(Ridge)仅缩小系数而不归零,无法实现特征筛选。</div>
    <div class="srow">
      <div class="scol"><div class="note">L1 系数图:彩条=选中(红负/绿正),灰=被压缩至 0 剔除;可见 16 项保留、26 项归零。</div><div id="c_l1" class="chart"></div></div>
      <div class="scol" style="flex:1.1"><div class="panel data"><div class="panel-h">✕ 舍弃 ${M.dropped.length} 项 · 系数被压缩至零的原因</div>
      <table class="t"><tr><th>特征</th><th>系数</th><th>舍弃原因</th><th>|r|</th></tr>${M.l1.features.filter(r => !r.kept).map(r => { const c = r.reason && r.reason.r >= 0.6; return `<tr><td>${r.feat}</td><td>${r.coef}</td><td>${c ? "共线于 " + r.reason.with : "弱信号 · 边际≈0"}</td><td>${c ? r.reason.r : "—"}</td></tr>`; }).join("")}</table></div></div></div>` }) },
  { ch: "机器学习", b: () => {
    const p = M.params;
    return { title: "⑦ 模型选型 · 单调约束 GBT + 线性对照",
      headline: "单调约束 GBT 为<b>本数据</b>的适配选择 —— 各项优势均对应本研究的实际约束。",
      html: `<div class="arch" style="margin:2px 0 14px;gap:14px;flex:none">
        <div class="arch-box" style="min-width:160px;padding:14px 18px"><div class="ab-h" style="font-size:21px">输入 X · ${M.n_sel} 特征</div></div>
        <div class="arch-op">▶</div>
        <div class="arch-box main" style="min-width:320px;padding:16px 26px"><div class="ab-h" style="font-size:25px">单调约束 GBT(主模型)</div></div>
        <div class="arch-op">▶</div>
        <div class="arch-box" style="min-width:150px;padding:14px 18px"><div class="ab-h" style="font-size:21px">ŷ 超额估值</div></div>
        <div class="arch-box" style="min-width:230px;padding:14px 18px;border-top-color:var(--navy)"><div class="ab-h" style="font-size:18px;color:var(--navy)">并行 ElasticNet 白盒<br>下游 SHAP 归因</div></div>
      </div>
      <div class="srow">
        <div class="scol" style="flex:1.3"><div class="panel"><div class="panel-h">GBT 适配本数据的依据:优点 ↔ 实际契合</div><table class="t">
        <tr><th>模型优点</th><th>结合本研究实际(契合依据)</th></tr>
        <tr><td>非线性 + 变量交互</td><td>估值–杠杆关系非线性(低杠杆区间溢价斜率大、高杠杆区间趋平),纯线性无法刻画</td></tr>
        <tr><td>原生处理混合量纲/缺失</td><td>${M.n_all} 个不同量纲财务比率,免繁重预处理</td></tr>
        <tr class="hl"><td>单调约束注入经济先验</td><td>N=14 极小,无约束会学出"负债率↑→估值↑"等反经济关系 → 强制单调防拟合无经济意义关系</td></tr>
        <tr><td>浅树 + 强正则抗过拟合</td><td>${M.n_obs} 观测 / 14 簇,小配置以降低方差(样本外未显著退化)</td></tr>
        <tr><td>原生 SHAP 归因</td><td>满足可解释要求,可逐特征 / 逐家拆解</td></tr>
        <tr><td>可与线性白盒交叉验证</td><td>树的驱动符号须与 ElasticNet 一致方予采信(双重校验)</td></tr></table></div></div>
        <div class="scol"><div class="panel"><div class="panel-h">候选模型对比 · 未采用其余方案的理由</div><table class="t">
        <tr><td>纯线性 OLS/Lasso</td><td>无法刻画非线性与交互 → 仅作白盒对照</td></tr>
        <tr><td>随机森林</td><td>非线性但难以注入单调先验、归因偏弱</td></tr>
        <tr><td>深度神经网络</td><td>样本量过小易过拟合、黑箱、无法注入先验 ✗</td></tr>
        <tr class="hl"><td>→ 选 LightGBM</td><td>原生支持单调约束、训练快、SHAP 兼容 ✓</td></tr></table>
        <div class="note" style="margin-top:10px">关键超参经嵌套交叉验证自动选取;采用浅树与强正则配置(${p.num_leaves} 叶、min_child ${p.min_child_samples}),以在小样本下抑制过拟合。</div></div></div></div>` };
  } },
  { ch: "机器学习", b: () => ({
    title: "⑧ 训练与防过拟合",
    headline: "<b>三重防线</b>与<b>学习曲线</b>:训练 R² ~0.84、交叉验证 R² 收敛于 <b>~0.49</b> 且未随样本量衰减,表明过拟合受控;二者稳定差值反映结构性解释上限,而非样本规模约束。",
    html: `<div class="flow" style="flex:none;height:162px;margin-bottom:14px">${[
      flowbox("① 嵌套 CV", "外层估泛化 · 内层选参 · 分数从未用于选择模型(无选择偏置)"),
      flowbox("② L1 折内选特征", "特征选择在各折内独立进行,不接触测试集,避免数据泄漏"),
      flowbox("③ 单调约束 + 强正则", "经济先验 + 浅树小配置 → 降方差"),
      flowbox("结果", "样本内 " + M.r2.insample + " / 样本外 " + M.r2.oot + ":差距为结构性上限,非过拟合失控"),
    ].join(ARR)}</div>
    <div class="srow">
      <div class="scol"><div class="note">学习曲线:灰线为训练集 R²(~0.84),红线为交叉验证 R²(GroupKFold 按公司分组、汇集留出预测,<b>与 LOFO 同口径</b>)。交叉验证 R² 收敛于 <b>~0.49</b> 且未随样本量衰减,表明过拟合受控;训练与交叉验证 R² 的稳定差值反映<b>结构性解释上限</b>(横截面估值约半数不可由现有特征解释),构成模型解释力的结构性约束。</div><div id="c_lc" class="chart"></div></div>
      <div class="scol"><div class="panel"><div class="panel-h">"样本内外存在差距 ≠ 过拟合失控"的依据</div><table class="t">
      <tr><td>无选择偏置</td><td>外层 GroupKFold 估泛化、内层选参,报告分数从未用于选择模型</td></tr>
      <tr><td>差距来源</td><td>N=14 / ${M.n_obs} 低信号:横截面估值约半数固有不可解释(非记忆噪声)</td></tr>
      <tr class="hl"><td>已控证据</td><td>强正则 + 单调约束后,样本外 R² 稳定为正 ${M.r2.oot}、LOFO ${M.r2.lofo} 未显著退化</td></tr>
      <tr><td>反证</td><td>若过拟合失控,样本外应 ≈0 或转负;实测稳定为正 → 已得到控制</td></tr></table>
      <div class="note" style="margin-top:10px">注:LOFO(留一公司)较 OOT 更严苛 —— 留出整家公司仍达 ${M.r2.lofo},表明模型学到跨公司可迁移规律,而非记忆特定公司。</div></div></div>` }) },
  { ch: "机器学习", b: () => {
    const mt = M.metrics || {}, mr = (lbl, o) => `<tr><td>${lbl}</td><td>${o && o.r2 != null ? o.r2 : "—"}</td><td>${o && o.rmse != null ? o.rmse : "—"}</td><td>${o && o.mae != null ? o.mae : "—"}</td></tr>`;
    return {
      title: "⑨ 模型评估:多指标 + 样本外 + 天花板",
      headline: "三数据集 × 三指标(R²/RMSE/MAE)+ <b>预测-实际散点</b>;OOT <b>" + M.r2.oot + "</b> / LOFO <b>" + M.r2.lofo + "</b>;约 <b>" + Math.round(M.unexplained * 100) + "%</b> 不可约。",
      html: `<div class="srow">
        <div class="scol" style="flex:1.4"><div class="note">预测值对实际值(LOFO 留出外推):每点为一个公司-报告期观测,越接近虚线 <b>y=x</b> 表示外推误差越小;移为(红)。用于评估拟合优度与残差结构。</div><div id="c_pva" class="chart"></div></div>
        <div class="scol"><div class="note">样本内 / 样本外 R²(折内重选特征防泄漏):</div>
        ${cssBars(["样本内", "OOT", "LOFO"], [{ name: "R\u00b2", color: "#1d3557", data: [(mt.insample && mt.insample.r2) || 0, (mt.oot && mt.oot.r2) || 0, (mt.lofo && mt.lofo.r2) || 0] }], 1)}
        <div class="note" style="font-size:18px;margin:6px 0 0">RMSE / MAE \u2014 样本内 ${(mt.insample||{}).rmse} / ${(mt.insample||{}).mae} \u00b7 OOT ${(mt.oot||{}).rmse} / ${(mt.oot||{}).mae} \u00b7 LOFO ${(mt.lofo||{}).rmse} / ${(mt.lofo||{}).mae}</div>
        <div class="note" style="font-size:18px;margin:4px 0 6px">朴素基线(均值预测):R\u00b2=0、RMSE\u22480.68(=Y 标准差);本模型样本外 R\u00b2=${M.r2.oot}、RMSE 更低,<b>显著优于基线</b>。</div><div class="panel data" style="margin-top:8px"><div class="panel-h">解释力构成与天花板</div><table class="t">
        <tr><th>组成</th><th>占比</th><th>说明</th></tr>
        <tr class="hl"><td>现有数据可解释</td><td>~${Math.round((1 - M.unexplained) * 100)}%</td><td>财务 + 市场特征已充分利用,样本外稳定</td></tr>
        <tr><td>不可约残差</td><td>~${Math.round(M.unexplained * 100)}%</td><td>推测含情绪、叙事等不可观测成分,未直接度量</td></tr>
        <tr><td>性质</td><td>结构性上限</td><td>增加特征仅拟合噪声,属信号上限而非分析不足</td></tr></table></div></div></div>`,
    };
  } },
  { ch: "机器学习", b: () => {
    const pva = M.pva || [], res = pva.map(d => d.a - d.p);
    const lo = Math.min(...res), hi = Math.max(...res), nb = 11, bw = (hi - lo) / nb || 1;
    const counts = Array(nb).fill(0); res.forEach(r => { counts[Math.min(nb - 1, Math.max(0, Math.floor((r - lo) / bw)))]++; });
    const hx = counts.map((c, i) => +(lo + bw * (i + 0.5)).toFixed(2));
    const byf = {}; pva.forEach(d => { (byf[d.firm] = byf[d.firm] || []).push(Math.abs(d.a - d.p)); });
    const fe = Object.entries(byf).map(([f, a]) => ({ firm: f, mae: a.reduce((sm, x) => sm + x, 0) / a.length, n: a.length })).sort((a, b) => b.mae - a.mae);
    const rows = fe.map(x => `<tr${x.firm === "移为通信" ? ' class="hl"' : ""}><td>${x.firm}</td><td>${x.mae.toFixed(3)}</td><td>${x.n}</td></tr>`).join("");
    return { title: "⑩ 误差与残差分析",
      headline: "LOFO 留出残差近似零均值、无强系统性偏差;误差较大者集中于上市历史短、波动较高的公司。",
      html: `<div class="srow" style="flex:1">
        <div class="scol"><div class="note">残差(实际 \u2212 预测,LOFO 留出外推)分布:近似以 0 为中心,无明显偏态。</div>${cssBars(hx, [{ name: "频数", color: "#1d3557", data: counts }], Math.max(1, ...counts))}</div>
        <div class="scol"><div class="note">逐家平均绝对误差(MAE,降序;移为高亮):误差大者多为次新股 / 高波动公司。</div>
          <div class="panel data"><div class="panel-h">逐家误差(MAE)</div><table class="t"><tr><th>公司</th><th>MAE</th><th>n</th></tr>${rows}</table></div></div></div>` };
  } },
  { ch: "机器学习", b: () => {
    const c = (M.screen && M.screen.classification) || {}, cm = c.confusion || {};
    return { title: "⑪ 错误定价筛查 · 分类评估",
      headline: "将回归模型转化为<b>高估/低估二分类筛查器</b>(阈值=0 区分溢价/折让),服务投资标的初筛;留出外推 <b>AUC=" + c.auc + "</b>。",
      html: kpis([kpi("AUC", c.auc, "排序区分能力"), kpi("准确率", c.accuracy, "整体分类正确率"), kpi("精确率", c.precision, "预测溢价中实为溢价之比"), kpi("召回率", c.recall, "实际溢价被正确识别之比"), kpi("F1", c.f1, "精确率与召回率调和均值")])
        + `<div class="srow">
        <div class="scol"><div class="note">ROC 曲线(LOFO 留出外推):曲线越趋左上、曲线下面积(AUC)越大,排序区分能力越强;灰色虚线为随机基准。</div><div id="c_roc" class="chart"></div></div>
        <div class="scol"><div class="note">混淆矩阵(判别阈值=0;样本溢价基准占比 ${Math.round((c.base_rate_premium || 0) * 100)}%):</div>
        <table class="t"><tr><th></th><th>预测:溢价</th><th>预测:折让</th></tr>
        <tr><td>实际:溢价</td><td style="background:#f2f7f2;color:#2e7d32;font-weight:700">真阳 TP ${cm.tp}</td><td style="background:#fbf3e8;color:#a32135">假阴 FN ${cm.fn}</td></tr>
        <tr><td>实际:折让</td><td style="background:#fbf3e8;color:#a32135">假阳 FP ${cm.fp}</td><td style="background:#f2f7f2;color:#2e7d32;font-weight:700">真阴 TN ${cm.tn}</td></tr></table>
        <div class="panel" style="margin-top:10px"><div class="panel-h">应用定位 · 投资标的初筛</div><table class="t">
        <tr><td>前提</td><td>分类标签为<b>模型定义的超额估值正负</b>(溢价/折让),非市场可观测真值;判别阈值=0;指标基于 LOFO 留出外推、无前视泄漏;基准溢价占比 ${Math.round((c.base_rate_premium || 0) * 100)}%,各指标均高于随机基线</td></tr>
        <tr><td>功能</td><td>对候选公司预测基本面应得估值,识别实际估值显著偏离应得水平者</td></tr>
        <tr><td>口径</td><td>与回归同一模型、同一留出外推口径,分类仅为决策层呈现</td></tr>
        <tr><td>边界</td><td>有效簇仅 ${M.n_firms},指标置信区间较宽,且标签依赖横截面定价模型;定位为<b>方向性初筛</b>,不构成定价或择时结论</td></tr></table></div></div></div>`,
    };
  } },
  { ch: "机器学习", b: () => {
    const incr = (WB.r2_compare.blackbox_incremental_oot * 100).toFixed(1), w = WB.r2_compare;
    const wbBars = cssBars(["样本内", "OOT", "LOFO"], [
      { name: "线性(白盒)", color: "#1d3557", data: [w.linear_whitebox.insample, w.linear_whitebox.oot, w.linear_whitebox.lofo] },
      { name: "GBT(黑盒)", color: "#9a9a9a", data: [w.gbt.insample, w.gbt.oot, w.gbt.lofo] },
    ], 1.0);
    return { title: "⑫ 可解释性 — SHAP + 白盒证明",
      headline: "SHAP 度量驱动方向(蓝=负向/绿=正向);<b>白盒证明</b>:透明线性与黑盒同协议比较,样本外仅高出 " + incr + "%。",
      html: `<div class="srow"><div class="scol"><div class="note">SHAP 重要性:各驱动对超额估值的平均影响幅度,<b>杠杆居首</b>。<span style="margin-left:8px;white-space:nowrap"><span style="color:#1d3557">■</span> 负向影响　<span style="color:#2f5d50">■</span> 正向影响</span></div><div id="c_shap" class="chart"></div></div>
        <div class="scol"><div class="note">白盒与黑盒同协议 R² 对比(HTML 矢量绘制):黑盒样本外几乎无增量 → <b>结论不依赖黑盒</b>,树模型仅作非线性佐证。</div>${wbBars}</div></div>` };
  } },
  { ch: "机器学习", b: () => {
    const gd = EX.guardrail, refusedNames = gd.refused_levers.map(r => r.feat).join("、");
    return { title: "⑬ 稳健性检验 — 五维一致性(consilience)",
      headline: "同一假设须在<b>推断 / 设定 / 识别 / 证伪 / 泛化</b>五类独立证据下结论一致方认定为稳健(显著性以 p<0.05 为参照阈值);任一维度不一致即记为未通过。",
      html: `<div class="note" style="flex:none;font-size:19px;line-height:1.5">五维对应方法:<b>推断</b> 聚类自助(wild cluster bootstrap,少簇稳健 p 值) · <b>设定</b> 多设定下系数符号一致 · <b>识别</b> 公司固定效应 + 领先-滞后 · <b>证伪</b> 安慰剂 / 置换检验 · <b>泛化</b> 留一公司(LOFO)外推一致</div>
        <div class="srow" style="flex:1">${["H1", "H2", "H3"].map(k => `<div class="scol">${triCard(k)}</div>`).join("")}</div>
        <div class="callout" style="flex:none;font-size:20px;line-height:1.5"><b>算术污染控制</b>:对位于 Y=ln(PS) 分母的含营收特征及含市值特征作定义级标记,排除其反事实解读(共 ${gd.refused_levers.length} 项:${refusedNames});特征重要性(SHAP)仅作初筛,最终判定以上述五维检验为准。</div>` };
  } },
  // ---- PART 04 结果解释与实务建议 ----
  { b: () => ({
    title: "分析框架 · 市值的恒等分解",
    headline: "市值 = 营收 × 估值倍数(PS);取对数后变动<b>可加分解</b>为 经营通道 + 再定价通道,会计恒等、逐家精确。",
    html: `<div class="ident" style="flex:none;margin:2px 0 8px">${[
      identbox("市值", "Market Cap", "公司总市值", true),
      `<div class="ident-op">=</div>`,
      identbox("营收", "Revenue", "经营通道", false),
      `<div class="ident-op">×</div>`,
      identbox("估值倍数", "PS = 市值 / 营收", "再定价通道", false),
    ].join("")}</div>
    <div class="note" style="flex:none">对数形式(可加):<b>Δln 市值 = Δln 营收 + Δln(PS)</b> —— 将市值变动精确拆为"经营贡献"与"估值再定价贡献",可逐家归因。</div>
    <div class="srow" style="flex:1">
      <div class="scol"><div class="panel"><div class="panel-h">经营通道 · 营收</div><table class="t">
        <tr><td>含义</td><td>把生意规模做大(量 × 价)</td></tr>
        <tr><td>驱动因素</td><td>终端需求、市场份额、产能与新品</td></tr>
        <tr class="hl"><td>本研究衡量</td><td>营收复利增速(CAGR)、营收倍数</td></tr>
        <tr><td>判读</td><td>增速领先同行 → 经营通道贡献为正</td></tr></table></div></div>
      <div class="scol"><div class="panel"><div class="panel-h">再定价通道 · 估值倍数(PS)</div><table class="t">
        <tr><td>含义</td><td>市场为每元营收支付的倍数</td></tr>
        <tr><td>驱动因素</td><td>成长预期、盈利质量、风险(杠杆)、情绪</td></tr>
        <tr class="hl"><td>本研究衡量</td><td>超额估值 = log(PS) 剥年度+规模之残差(即 ML 目标 Y)</td></tr>
        <tr><td>判读</td><td>倍数扩张为正;行业性压缩则形成拖累</td></tr></table></div></div></div>
    <div class="callout" style="flex:none">该框架把"市值为何变化"拆为两个可归因问题 —— <b>生意是否做大、市场是否重定价</b>;本章据此对全样本逐家分解,并落到移为诊断。</div>` }) },
  { b: () => ({
    title: "结论筛选流程 · 从候选信号到稳健结论",
    headline: "候选信号经<b>四个递增严格的环节</b>逐级筛除,由数十项收敛至 <b>2 条稳健价值驱动</b>;高剔除率体现方法的严格性。",
    html: `<div class="flow" style="flex:none;height:158px;margin-bottom:6px">${[
      flowbox("环节一 · 特征入选", "42 → 16(L1 剔除冗余与共线)"),
      flowbox("环节二 · 污染剔除", "剔除含营收、含市值的算术假象"),
      flowbox("环节三 · 公司内检验", "剔除幸存者偏差项"),
      flowbox("环节四 · 五维一致性", "命题 3 → 2 通过"),
    ].join(ARR)}</div>
    <div class="srow" style="flex:1">
      <div class="scol" style="flex:1.35"><div class="panel"><div class="panel-h">各环节剔除内容(示例)</div><table class="t">
        <tr><th>环节</th><th>剔除类型</th><th>示例</th></tr>
        <tr><td>环节一</td><td>冗余 / 共线</td><td>净利率与营业利润率 r=0.99 等 26 项系数归零</td></tr>
        <tr><td>环节二</td><td>算术假象</td><td>含营收(毛利率、净利率)、含市值项定义级剔除</td></tr>
        <tr class="hl"><td>环节三</td><td>幸存者偏差</td><td>研发强度、海外占比:跨公司显著、公司内不显著</td></tr>
        <tr><td>环节四</td><td>未通过验证</td><td>H3 盈利率:安慰剂 p=0.775,予以证伪</td></tr></table></div></div>
      <div class="scol"><div class="panel"><div class="panel-h">稳健留存</div><table class="t">
        <tr class="hl"><td>H1 成长被折价</td><td>五维 5/5</td></tr>
        <tr class="hl"><td>H2 低杠杆 ↔ 高估值</td><td>五维 5/5</td></tr>
        <tr><td>H3 盈利率驱动</td><td>1/5,证伪</td></tr></table>
        <div class="callout" style="margin-top:16px;font-size:21px;line-height:1.55">候选信号由数十项收敛至 <b>2 条稳健驱动</b>;特征重要性(SHAP)仅作初筛,最终判定以五维一致性为准。较高的剔除比例与多数候选未通过检验,与小样本下控制过拟合及假阳性的预期一致。</div></div></div>` }) },
  { ch: "模型发现", b: () => {
    const b1 = DATA.elasticity.beta_2wayFE;
    const card = (no, name, ok, verdict, big, bigSub, mean, theory, test) => `<div class="scol"><div class="card" style="flex:1;justify-content:space-between;gap:14px;padding:28px 30px">
      <div><h3 style="font-size:25px;line-height:1.3;margin:0 0 10px">${no} ${name}</h3>
        <span class="vbadge ${ok ? "pass" : "fail"}" style="font-size:22px;padding:4px 16px;font-weight:700">${verdict}</span></div>
      <div style="font-size:38px;font-weight:700;color:${ok ? "#1d3557" : "#a32135"};line-height:1.1">${big}<span style="font-size:18px;color:#6f6259;font-weight:400"> ${bigSub}</span></div>
      <div style="font-size:21px;line-height:1.5"><b>经济含义</b>:${mean}</div>
      <div style="font-size:21px;line-height:1.5"><b>财务理论</b>:${theory}</div>
      <div class="note" style="font-size:18px;margin:0">检验:${test}</div></div></div>`;
    return { title: "发现① 三条价值驱动结论",
      headline: "三条结论经五维一致性检验:成长被折价、低杠杆 ↔ 高估值 <b>成立(5/5)</b>;盈利率驱动估值 <b>证伪(1/5)</b>。",
      html: `${driversBars()}
        <div class="note" style="flex:none;font-size:18px">图示各假设的<b>跨公司系数 vs 公司内时序系数</b>:H1、H2 公司内仍显著(稳健),H3 公司内趋零并反号(证伪)。"五维 X/5" 指通过 推断/设定/识别/证伪/泛化 五类检验的项数,方法见第 20 页。</div>
        <div class="srow" style="flex:1">
        ${card("①", "成长被折价", true, "五维通过 5/5", "β ≈ " + b1, "(市值对营收弹性 &lt;1)", `营收每增长 10%,市值仅增长约 ${Math.round(b1 * 10)}%,营收增长未获等比例的市值提升。`, "行业商品化,增长缺乏稀缺性,难获成长溢价。", `Δln(PS) ~ Δln营收 斜率 ${TRI.H1.coef};WCB p=${TRI.H1.p_wcb};公司内 ${TRI.H1.within}`)}
        ${card("②", "低杠杆 ↔ 高估值", true, "五维通过 5/5", TRI.H2.coef, "(超额估值 ~ 资产负债率)", "资产负债率越低,超额估值越高;领先-滞后检验偏正向,削弱反向因果疑虑。", "资本结构理论:低杠杆降低财务困境风险与资本成本,支撑更高估值倍数。", `β=${TRI.H2.coef};WCB p=${TRI.H2.p_wcb};公司内 ${TRI.H2.within};属相关性,非因果`)}
        ${card("③", "盈利率驱动估值", false, "五维通过 1/5 · 证伪", "≈ 0", "(剔除营收算术相关后)", "剔除与营收的算术相关后,盈利率对估值无独立解释力。", "市场为可持续质量与实质成长定价,而非账面利润率。", `β=${TRI.H3.coef};WCB p=${TRI.H3.p_wcb};安慰剂 p=${TRI.H3.p_plac}(均不显著)`)}
      </div>
      <div class="callout" style="flex:none">与财务理论的一致性:成长被折价 合行业商品化;低杠杆 ↔ 高估值 合资本结构理论;盈利率不独立驱动(证伪)合"市场为质量与成长而非账面利润率定价"。三者方向均与理论吻合。</div>` };
  } },
  { ch: "模型发现", b: () => {
    const g = (M.screen && M.screen.yiwei_mispricing) || {};
    return { title: "发现② 移为估值诊断 + 错误定价分解",
      headline: "市值 ×" + YW.mcap + " = 营收 ×" + YW.rev + " × 估值倍数 ×" + YW.ps + ";估值已属行业前列,<b>当前溢价约四成由市场情绪支撑</b>。",
      html: `<div class="srow" style="flex:1">
        <div class="scol"><div class="note">恒等分解(2017→2025):市值 = 营收 × 估值倍数。营收<b>增速低于同行</b>、估值倍数<b>受行业压缩</b>,两通道均不占优。</div>${cssHBars([{ name: "营收(经营通道)", value: YW.rev, color: "#2f5d50", desc: `经营通道:营收累计增至 ×${YW.rev}` }, { name: "估值倍数(再定价)", value: YW.ps, color: "#9b2226", desc: `再定价通道:倍数压缩至 ×${YW.ps}(行业 de-rating)` }, { name: "市值", value: YW.mcap, color: "#7d1828", desc: `两通道相乘 → 市值仅 ×${YW.mcap},几近停滞` }], 1)}</div>
        <div class="scol"><div class="note">超额估值分解(同行 LOFO 定价模型外推):基本面应得 <b>+${g.fundamental_justified}</b>,实际 +${g.actual_excess},差额 <b>+${g.sentiment_gap}</b> 属情绪/未解释。</div>
          ${cssStack([{ name: "基本面可解释", color: "#1d3557", value: g.fundamental_justified }, { name: "情绪 / 未解释", color: "#a32135", value: g.sentiment_gap }], g.actual_excess)}
          <div class="panel"><div class="panel-h">移为关键定位</div><table class="t">
            <tr class="hl"><td>超额估值</td><td>+${g.actual_excess} · 行业前列(溢价)</td></tr>
            <tr><td>资产负债率</td><td>约 13.5% · 行业最低(估值正向项)</td></tr>
            <tr><td>海外营收占比 / 增速</td><td>${YW.ov_share}% / ${YW.ov_cagr}%(领先企业海外增速 +50~69%)</td></tr>
            <tr><td>营收三年复利增速</td><td>${YW.rev_cagr}% · 低于领先企业水平</td></tr></table></div></div></div>
        <div class="callout" style="flex:none">移为估值已属行业前列:约 ${Math.round((g.explained_share || 0) * 100)}% 由基本面支撑、约 ${Math.round((g.sentiment_share || 0) * 100)}% 由情绪支撑。<b>提升空间在营收规模而非估值倍数;下行风险集中于情绪部分。</b></div>` };
  } },
  { ch: "模型发现", b: () => ({
    title: "发现③ 全行业对标与战略画像",
    headline: "将模型结论置于全行业:成长被折价 → 领先企业以营收放量跨越估值压缩;移为<b>经营通道受海外增速制约</b>。",
    html: `<div class="srow" style="flex:1">
      <div class="scol"><div class="note">市值变动恒等分解(绿=经营/营收,红=再定价/估值;移为深色)。<b>印证模型结论 H1</b>:营收增长被估值倍数压缩(β&lt;1),领先企业须以充分营收放量取胜。</div><div id="c_fs" class="chart"></div></div>
      <div class="scol"><div class="note">战略画像(海外占比 × 增速,气泡=市值倍数)。<b>解释移为经营通道为何偏弱</b>:海外占比高(97%)、增速低(6%),即模型所指营收增速约束的根源。</div><div id="c_st" class="chart"></div></div></div>
    <div class="callout" style="flex:none;margin-top:12px">与模型的关系:ML 模型解释的是<b>再定价通道</b>(超额估值 Y);本页将其并入<b>经营通道</b>的恒等分解与战略画像,据此定位移为短板在经营侧(海外增长),而非估值。</div>` }) },
  { ch: "模型发现", b: () => {
    const rows = [...F].sort((a, b) => b.mcap - a.mcap).map(f => `<tr${f.is_yiwei ? ' class="hl"' : ""}><td>${f.firm}</td><td>×${f.mcap}</td><td>×${f.rev}</td><td>${f.rev_cagr}%</td></tr>`).join("");
    return { title: "发现④ 逐家市值路径与倍数对照",
      headline: "各公司累积市值路径(首年=0):领先企业持续上行,<b>移为(红)长期低平</b>;路径斜率由营收放量主导。",
      html: `<div class="srow" style="flex:1">
        <div class="scol" style="flex:1.5"><div class="note">折线 = 各代表公司累积 ln 市值随年份变化(首年归零);<b class="hot">移为(红)</b>长期低平,广和通 / 移远 / 美格等持续抬升。斜率越大 = 市值复利越快。</div><div id="c_fl" class="chart"></div></div>
        <div class="scol" style="flex:1"><div class="note">全 13 家市值 / 营收倍数(按市值倍数降序,移为高亮);领先企业以营收放量抬升市值。</div>
          <div class="panel data" style="flex:1"><div class="panel-h">逐家倍数与营收增速</div><table class="t" style="font-size:16px"><tr><th>公司</th><th>市值 ×</th><th>营收 ×</th><th>营收 CAGR</th></tr>${rows}</table></div></div></div>` };
  } },
  // ---- 实务建议 ----
  { ch: "模型发现", b: () => {
    const g = (M.screen && M.screen.yiwei_mispricing) || {};
    const rec = (tag, color, title, action, basis, note) => `<div class="scol"><div class="card" style="flex:1;justify-content:flex-start;gap:11px;padding:22px 28px;border-top:7px solid ${color}">
      <h3 style="font-size:24px;margin:0"><span style="color:${color}">【${tag}】</span> ${title}</h3>
      <div style="font-size:20px;line-height:1.5"><b>建议</b>:${action}</div>
      <div style="font-size:19px;line-height:1.5"><b>依据</b>:${basis}</div>
      <div class="note" style="font-size:17px;margin:0">${note}</div></div></div>`;
    return { title: "实务建议 · 维持 / 扩张 / 规避 / 监测",
      headline: "由模型结论导出的可操作建议:估值已处最优(维持)、营收增长是唯一引擎(扩张)、规避无效的估值动作(规避)、持续监测错误定价(监测)。",
      html: `<div class="srow" style="flex:1">
        ${rec("维持", "#1d3557", "资本结构与预期管理", "维持保守的资产负债结构,审慎评估并购加杠杆;并主动管理投资者预期与信息披露。", "低杠杆是唯一通过五维检验的估值正向因子,移为资产负债率约 13.5% 居行业最低;当前估值溢价约 " + Math.round((g.sentiment_share || 0) * 100) + "% 由市场情绪支撑,稳定性较低。", "性质:稳健相关(非因果)。理论依据:资本结构理论 + 行为金融。")}
        ${rec("扩张", "#a32135", "扩张海外市场份额", "将资本与资源由财务优化转向海外市场份额扩张,以扩大营收规模基数。", "市值 = 营收 × 估值倍数;移为估值倍数已居行业前列、接近上限,故抬升市值的主要路径为营收增长。移为海外营收增速仅 6%,领先企业为 +50~69%。", "边界:倍数接近上限属会计恒等(确定);份额扩张能否转化为估值提升,不作因果承诺。")}
      </div>
      <div class="srow" style="flex:1">
        ${rec("规避", "#8a7f72", "规避无效的估值动作", "不将研发强度、毛利率、费用率视为估值杠杆;不以再定价为目的实施财务优化。", "上述指标在跨公司层面显著、但在公司内时序检验中不显著(幸存者偏差),调整之并不改变估值;低杠杆与流动性亦已处于最优区间。", "理论依据:内生性 / 幸存者偏差。经营层面研发投入仍应正常进行。")}
        ${rec("监测", "#2e7d32", "持续监测错误定价", "以「实际溢价 − 基本面应得」缺口构建季度监测看板,辅助投资者沟通与决策。", "当前缺口为 +" + g.sentiment_gap + "(情绪偏高),提示回调风险;缺口转负则提示低估。", "用途:决策支持 / 持续投资者关系工具(复用本模型 LOFO 外推)。")}
      </div>` };
  } },
  // ---- 结语 ----
  { ch: "结语", b: () => ({
    title: "局限与边界",
    headline: "本研究为<b>解释性建模,而非因果推断</b>;受样本规模约束,结论以保守口径表述,并明确其适用边界与不可解释部分。",
    html: `<div class="srow" style="flex:1"><div class="scol"><div class="panel"><div class="panel-h">研究局限与边界声明</div><table class="t">
      <tr><th>局限维度</th><th>具体表现</th><th>本研究的处理 / 边界声明</th></tr>
      <tr><td>因果识别</td><td>N=14、缺乏外生冲击,IV/DiD 估计噪声较大</td><td>仅实施准因果(公司内固定效应 + 领先-滞后 + 安慰剂);结论声明为稳健相关,不主张因果</td></tr>
      <tr class="hl"><td>样本规模</td><td>14 家公司、有效簇少,横截面解释上限约 50%</td><td>采用 wild cluster bootstrap 少簇推断;明确标注不可约残差,不夸大解释力</td></tr>
      <tr><td>截面外推</td><td>逐家分析深度受上市历史长度限制</td><td>次新股结果仅供参考;以留一公司(LOFO)验证跨公司可迁移性</td></tr>
      <tr><td>预测边界</td><td>预测过拟合属结构性问题(信号低)</td><td>仅报告稳健的跨公司外推 R²≈0.5,不追求测试集择时 IC</td></tr>
      <tr><td>适用范围</td><td>样本限于模组 / 终端行业,截至 2025</td><td>结论限定于样本期与本行业,外推至其他行业需谨慎</td></tr></table></div></div></div>
    <div class="callout" style="flex:none;margin-bottom:10px;background:#f3f6f3;border-left-color:#2e7d32;color:#2e5d32">未来工作:\u2460 扩大样本(更多模组 / 通信设备公司与行业)以提升横截面统计功效;\u2461 引入外生冲击(政策 / 事件)开展因果识别(IV / DiD);\u2462 纳入文本与另类数据,补充情绪、叙事等当前不可观测成分;\u2463 将错误定价缺口看板滚动更新为持续监测工具。</div>
    <div class="callout" style="flex:none">研究定位:以剔除伪规律、白盒可复算、明确标识不可解释残差为方法准则,提供经稳健性检验的解释性结论,而非可直接套用的估值提升公式。</div>` }) },
];

/* ---- 篇章 / 目录 ---- */
const PART_OF = [1, 1, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4];
const PARTS = {
  1: { t: "研究背景与问题", en: "BACKGROUND", desc: "选题价值、案例选择与研究问题界定" },
  2: { t: "数据与特征工程", en: "DATA & FEATURES", desc: "数据来源、预处理与结合财务理论的特征构建" },
  3: { t: "模型构建·训练·评估", en: "MODELING", desc: "模型选型、优化、多指标评估与可解释性" },
  4: { t: "结果解释与实务建议", en: "FINDINGS", desc: "模型发现、案例公司诊断与可操作建议" },
};
const TOC = [
  ["01", "研究背景与问题", "选题、案例与研究问题", "BACKGROUND"],
  ["02", "数据与特征工程", "数据源、预处理、财务理论特征", "DATA & FEATURES"],
  ["03", "模型构建·训练·评估", "选型、优化、多指标评估、可解释", "MODELING"],
  ["04", "结果解释与实务建议", "模型发现、案例诊断、实务建议", "FINDINGS"],
];

function coverHtml(n) {
  return `<section class="slide cover"><div class="brand"></div><div class="cover-square"></div>
    <h1 class="cover-title">基于机器学习的公司估值建模与价值驱动分析</h1><div class="cover-rule"></div>
    <div class="cover-sub">《大数据财务分析》小组案例　·　以移为通信(300590)为例</div>
    <div class="cover-members">组员:林震 · 郁思雨 · 甘元 · 马雨佳 · 潘润斌</div>
    <div class="cover-no">${String(n).padStart(2, "0")}</div></section>`;
}
function tocHtml(n) {
  const rows = TOC.map((r, i) => `<div class="toca-row"><div class="tr-no">${r[0]}</div><div class="tr-name">${r[1]}</div><div class="tr-note">${r[2]}</div><div class="tr-dots"></div><div class="tr-en">${r[3]}</div></div>`).join("");
  return `<section class="slide toc"><div class="brand"></div><div class="toca-grid">
    <aside class="toca-side"><div class="toca-en">CONTENTS</div><h2 class="toca-title">目录</h2><div class="toca-rule"></div>
      <p class="toca-lead">以可解释机器学习对公司估值横截面建模,识别价值驱动,并应用于案例公司的实务建议。</p><div class="toca-meta">全文 · 四个部分</div></aside>
    <div class="toca-list">${rows}</div></div><div class="cover-no">${String(n).padStart(2, "0")}</div></section>`;
}
function dividerHtml(part, n) {
  const p = PARTS[part], pn = String(part).padStart(2, "0");
  return `<section class="slide pdiv"><div class="pd-block"><span class="pd-bignum">${pn}</span></div>
    <div class="pd-left"><div class="pd-part">PART ${pn}</div><h2 class="pd-title">${p.t}</h2><div class="pd-en">${p.en}</div><div class="pd-rule"></div><p class="pd-desc">${p.desc}</p></div>
    <div class="cover-no">${String(n).padStart(2, "0")}</div></section>`;
}
function thanksHtml(n) {
  return `<section class="slide cover"><div class="brand"></div><div class="cover-square"></div>
    <h1 class="cover-title">感谢观看</h1><div class="cover-rule"></div>
    <div class="cover-sub">THANK YOU　·　欢迎批评指正</div>
    <div class="cover-members">基于机器学习的公司估值建模与价值驱动分析　·　以移为通信(300590)为例</div>
    <div class="cover-no">${String(n).padStart(2, "0")}</div></section>`;
}
function autodetect(h) {
  return [
    h.includes('id="c_yw"') && ["c_yw", o_yiwei], h.includes('id="c_fs"') && ["c_fs", o_firms],
    h.includes('id="c_st"') && ["c_st", o_strategy], h.includes('id="c_pd"') && ["c_pd", o_pd],
    h.includes('id="c_mcf"') && ["c_mcf", o_mcap_cf], h.includes('id="c_shap"') && ["c_shap", o_shap],
    h.includes('id="c_r2"') && ["c_r2", o_r2val], h.includes('id="c_wb"') && ["c_wb", o_wb],
    h.includes('id="c_lc"') && ["c_lc", o_learncurve], h.includes('id="c_pva"') && ["c_pva", o_pva],
    h.includes('id="c_fl"') && ["c_fl", o_firmlines],
    h.includes('id="c_roc"') && ["c_roc", o_roc], h.includes('id="c_gap"') && ["c_gap", o_gap],
    h.includes('id="c_ceil"') && ["c_ceil", o_ceiling], h.includes('id="c_fg"') && ["c_fg", o_featgrp],
    h.includes('id="c_l1"') && ["c_l1", o_l1],
  ].filter(Boolean);
}

/* 组装:封面 + 目录 + (每篇分隔页 + 内容页) */
const deck = [{ type: "cover" }, { type: "toc" }];
let cp = 0;
CONTENT.forEach((c, i) => {
  const part = PART_OF[i];
  if (part !== cp) { cp = part; deck.push({ type: "divider", part }); }
  deck.push({ type: "content", c, part });
});
deck.push({ type: "thanks" });

function build() {
  let pg = 0;
  const html = deck.map(s => {
    pg++;
    if (s.type === "cover") return coverHtml(pg);
    if (s.type === "toc") return tocHtml(pg);
    if (s.type === "divider") return dividerHtml(s.part, pg);
    if (s.type === "thanks") return thanksHtml(pg);
    const d = s.c.b(); s.c._d = d;
    return `<section class="slide"><div class="brand"></div><div class="header"><div class="kicker">${PARTS[s.part].t}</div><h2 class="title">${d.title}</h2>${d.headline ? `<div class="subtitle">${d.headline}</div>` : ""}</div><div class="body">${d.html}</div><div class="cover-no">${String(pg).padStart(2, "0")}</div></section>`;
  }).join("");
  document.getElementById("deck").innerHTML = html;
  deck.filter(s => s.type === "content").forEach(s => (s.c._d.charts || autodetect(s.c._d.html)).forEach(([id, fn]) => mk(id, fn())));
}
build();
window.addEventListener("resize", () => Object.values(charts).forEach(c => c && c.resize()));
