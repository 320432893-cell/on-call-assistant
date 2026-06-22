/* 标准 ML 报告(八段·因果版)。每段=KPI卡 + 内容卡(图/表/参数卡/特征chips)。ECharts 出图。 */
const Y = "#c0392b", CO = FIN.companies, YEARS = FIN.years, E = REPORT.eda, FI = REPORT.feat_importance;
let charts = {};
function mk(id, opt) { const d = document.getElementById(id); if (!d) return; const c = echarts.init(d); c.setOption(opt); charts[id] = c; }
function axx(name, onZero) { return { name, nameTextStyle: { color: "#64748b" }, splitLine: { lineStyle: { color: "#eef2f7" } }, axisLabel: { color: "#64748b" }, axisLine: { onZero: !!onZero, lineStyle: { color: "#cbd5e1" } } }; }
const ZL = { silent: true, symbol: "none", lineStyle: { color: "#334155" }, label: { show: false } };
function kpi(lab, num, sub, cls) { return `<div class="kpi ${cls || ""}"><div class="kl">${lab}</div><div class="kn">${num}</div><div class="ks">${sub}</div></div>`; }
function tbl(head, rows, hl) { return `<table class="t"><thead><tr>${head.map(h => `<th>${h}</th>`).join("")}</tr></thead><tbody>` + rows.map((r, i) => `<tr class="${hl === i ? "hl" : ""}">${r.map(c => `<td>${c}</td>`).join("")}</tr>`).join("") + "</tbody></table>"; }
function P(title, rows) { return `<div class="param"><div class="pt">${title}</div><table>${rows.map(r => `<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`).join("")}</table></div>`; }
function chips(arr) { return `<div class="chips">${arr.map(a => `<span class="fchip">${a}</span>`).join("")}</div>`; }

/* ---------- 图函数 ---------- */
function o_subtypes() { const s = E.subtypes; return { grid: { left: 50, right: 16, top: 12, bottom: 60 }, tooltip: {}, xAxis: { type: "category", data: s.map(x => x.name), axisLabel: { color: "#64748b", interval: 0, rotate: 22 } }, yAxis: axx("事件数"), series: [{ type: "bar", data: s.map(x => x.n), itemStyle: { color: "#2563eb" }, label: { show: true, position: "top" } }] }; }
function o_featimp() { const f = [...FI].reverse(); return { grid: { left: 96, right: 30, top: 12, bottom: 30 }, tooltip: { valueFormatter: v => v + "%" }, xAxis: axx("重要性 %(gain)"), yAxis: { type: "category", data: f.map(x => x.feat), axisLabel: { color: "#64748b" } }, series: [{ type: "bar", data: f.map(x => x.imp), itemStyle: { color: "#7c3aed" }, label: { show: true, position: "right", formatter: "{c}%" } }] }; }
function o_forest() { const F = CAUSAL.forest; return { grid: { left: 66, right: 28, top: 12, bottom: 40 }, tooltip: { trigger: "item" }, xAxis: axx("去混淆后因果效应 ATE %"), yAxis: { type: "category", data: F.map(f => f.name), axisLabel: { color: "#64748b" } }, series: [{ type: "custom", renderItem: (p, api) => { const yy = api.coord([0, api.value(0)])[1], x1 = api.coord([api.value(1), 0])[0], x2 = api.coord([api.value(2), 0])[0]; return { type: "line", shape: { x1, y1: yy, x2, y2: yy }, style: { stroke: "#94a3b8", lineWidth: 3 } }; }, data: F.map((f, i) => [i, f.lo, f.hi]) }, { type: "scatter", symbolSize: 16, data: F.map(f => ({ value: [f.ate, f.name], itemStyle: { color: f.name === "定增" ? "#2563eb" : f.name === "减持" ? "#db2777" : "#f59e0b" } })), label: { show: true, position: "top", formatter: p => p.value[0] + "%" }, markLine: { ...ZL, data: [{ xAxis: 0 }] }, z: 5 }] }; }
function o_overview() { const A = CAUSAL.overview; return { grid: { left: 46, right: 16, top: 28, bottom: 26 }, legend: { top: 0, textStyle: { fontSize: 11 } }, tooltip: { trigger: "axis", valueFormatter: v => v + "%" }, xAxis: { type: "category", data: A.map(a => a.name), axisLabel: { color: "#64748b" } }, yAxis: axx("效应 %", true), series: [{ name: "①直接算平均", type: "bar", data: A.map(a => a.desc), itemStyle: { color: "#94a3b8" } }, { name: "②因子CAR", type: "bar", data: A.map(a => a.factor), itemStyle: { color: "#0ea5e9" } }, { name: "③去混淆DML", type: "bar", data: A.map(a => a.dml), itemStyle: { color: "#7c3aed" } }] }; }
function o_nuis() { const N = CAUSAL.harden.nuisance; return { grid: { left: 40, right: 16, top: 28, bottom: 26 }, legend: { top: 0, textStyle: { fontSize: 11 } }, tooltip: { trigger: "axis" }, xAxis: { type: "category", data: N.map(n => n.name), axisLabel: { color: "#64748b" } }, yAxis: { ...axx(""), max: 1.08 }, series: [{ name: "倾向AUC(混淆)", type: "bar", data: N.map(n => n.auc), itemStyle: { color: "#f59e0b" }, label: { show: true, position: "top" } }, { name: "overlap(可比)", type: "bar", data: N.map(n => n.overlap), itemStyle: { color: "#16a34a" }, label: { show: true, position: "top" } }] }; }
function o_power() { const W = CAUSAL.power; return { grid: { left: 44, right: 16, top: 12, bottom: 48 }, tooltip: { trigger: "axis", valueFormatter: v => (v * 100).toFixed(0) + "%" }, xAxis: { type: "category", data: W.map(w => w.name), axisLabel: { color: "#64748b", interval: 0, rotate: 12 } }, yAxis: { ...axx("查出3%的把握"), max: 1.1 }, series: [{ type: "bar", data: W.map(w => ({ value: w.p3, itemStyle: { color: w.p3 >= .8 ? "#16a34a" : "#dc2626" } })), label: { show: true, position: "top", formatter: p => (p.value * 100).toFixed(0) + "%" }, markLine: { silent: true, symbol: "none", data: [{ yAxis: .8 }], lineStyle: { color: "#334155", type: "dashed" }, label: { formatter: "80%", color: "#334155" } } }] }; }
function o_infer() { const B = CAUSAL.bootstrap, Pl = CAUSAL.placebo, lo = Math.min(...B, ...Pl) - 1, hi = Math.max(...B, ...Pl) + 1, H = a => { const b = 24, w = (hi - lo) / b, c = new Array(b).fill(0); a.forEach(v => { let i = Math.floor((v - lo) / w); i = Math.max(0, Math.min(b - 1, i)); c[i]++; }); return c.map((n, i) => [+(lo + (i + .5) * w).toFixed(2), n]); }; return { grid: { left: 44, right: 16, top: 28, bottom: 30 }, legend: { top: 0, textStyle: { fontSize: 11 } }, tooltip: { trigger: "axis" }, xAxis: axx("重算的效应 %"), yAxis: axx("次数"), series: [{ name: "假动作(安慰剂)", type: "bar", barWidth: "92%", data: H(Pl), itemStyle: { color: "#94a3b8", opacity: .5 } }, { name: "真实·换公司重算150次", type: "bar", barWidth: "92%", data: H(B), itemStyle: { color: "#2563eb", opacity: .82 }, markLine: { silent: true, symbol: "none", label: { show: false }, data: [{ xAxis: CAUSAL.boot_ci[0], lineStyle: { color: Y, type: "dashed" } }, { xAxis: CAUSAL.boot_ci[1], lineStyle: { color: Y, type: "dashed" } }, { xAxis: 0, lineStyle: { color: "#334155" } }] } }] }; }
function o_spec() { const S = CAUSAL.spec, bx = a => { const s = [...a].sort((x, y) => x - y), q = p => s[Math.min(s.length - 1, Math.floor(p * (s.length - 1)))]; return [q(0), q(.25), q(.5), q(.75), q(1)]; }; return { grid: { left: 44, right: 16, top: 12, bottom: 26 }, tooltip: {}, xAxis: { type: "category", data: S.map(s => s.name), axisLabel: { color: "#64748b" } }, yAxis: axx("效应 %"), series: [{ type: "boxplot", data: S.map(s => bx(s.eff)), itemStyle: { color: "#e0e7ff", borderColor: "#2563eb" }, markLine: { ...ZL, data: [{ yAxis: 0 }] } }, { type: "scatter", data: S.flatMap((s, i) => s.eff.map(v => [i, v])), symbolSize: 5, itemStyle: { color: "rgba(37,99,235,.3)" } }] }; }
function o_sc() { const SC = CAUSAL.sc; return { grid: { left: 50, right: 24, top: 28, bottom: 30 }, legend: { top: 0, textStyle: { fontSize: 11 } }, tooltip: { trigger: "axis" }, xAxis: { type: "category", data: SC.x, name: "相对定增的交易日", axisLabel: { color: "#64748b" } }, yAxis: axx("市值指数(起点1)"), series: [{ name: "移为真实", type: "line", data: SC.treated, symbol: "none", lineStyle: { color: Y, width: 3 } }, { name: "合成反事实", type: "line", data: SC.synth, symbol: "none", lineStyle: { color: "#0ea5e9", width: 2.5, type: "dashed" }, markLine: { ...ZL, data: [{ xAxis: SC.x.indexOf(0) }], label: { formatter: "定增日", color: "#334155" } } }] }; }
function o_bubble() { const sz = v => Math.max(14, Math.sqrt(Math.max(v, 1)) * 5.2); const data = CO.filter(c => c.rev_cagr !== null && c.ni_cagr !== null).map(c => ({ value: [c.rev_cagr, c.ni_cagr, c.latest_rev || 5, c.name], itemStyle: { color: c.color, opacity: c.is_yiwei ? .95 : .66, borderColor: c.is_yiwei ? "#7f1d1d" : "rgba(0,0,0,.12)", borderWidth: c.is_yiwei ? 2.5 : .5 }, label: { show: true, formatter: p => p.data.value[3], color: c.is_yiwei ? Y : "#475569", fontWeight: c.is_yiwei ? 700 : 500, fontSize: c.is_yiwei ? 12 : 10, position: "right" } })); return { grid: { left: 56, right: 30, top: 12, bottom: 44 }, tooltip: { formatter: p => `${p.data.value[3]}<br>营收CAGR ${p.data.value[0]}%<br>净利CAGR ${p.data.value[1]}%` }, xAxis: axx("营收CAGR %"), yAxis: axx("净利CAGR %"), series: [{ type: "scatter", data, symbolSize: d => sz(d[2]), markLine: { ...ZL, lineStyle: { color: "#94a3b8", type: "dashed" }, data: [{ xAxis: 0 }, { yAxis: 0 }] } }] }; }
function o_mv() { return { grid: { left: 50, right: 80, top: 12, bottom: 28 }, tooltip: { trigger: "axis", valueFormatter: v => v == null ? "—" : v + "亿" }, xAxis: { type: "category", data: YEARS, axisLabel: { color: "#64748b" } }, yAxis: axx("年末市值 亿"), series: CO.map(c => ({ name: c.name, type: "line", connectNulls: true, symbol: "none", data: c.by_year.map(d => d.mv), lineStyle: { width: c.is_yiwei ? 4 : 1.2, color: c.color, opacity: c.is_yiwei ? 1 : .5 }, z: c.is_yiwei ? 20 : 1, endLabel: { show: c.is_yiwei, formatter: c.name, color: Y, fontWeight: 700 } })) }; }

function o_mult_bar() { const f = PEER.firms.filter(x => x.mult != null).slice().sort((a, b) => a.mult - b.mult); return { grid: { left: 72, right: 44, top: 10, bottom: 28 }, tooltip: { valueFormatter: v => v + "x" }, xAxis: axx("市值倍数 x(IPO→现)"), yAxis: { type: "category", data: f.map(x => x.name), axisLabel: { color: "#64748b", fontWeight: 600 } }, series: [{ type: "bar", data: f.map(x => ({ value: x.mult, itemStyle: { color: x.is_yiwei ? Y : x.color, opacity: x.is_yiwei ? 1 : .5 } })), label: { show: true, position: "right", formatter: "{c}x" }, markLine: { ...ZL, lineStyle: { color: "#94a3b8", type: "dashed" }, data: [{ xAxis: 1 }] } }] }; }
function o_peer_scatter() { const data = PEER.firms.filter(f => f.rev_cagr != null && f.mult != null).map(f => ({ value: [f.rev_cagr, f.mult, f.cur_mv || 30, f.name], itemStyle: { color: f.color, opacity: f.is_yiwei ? .95 : .6, borderColor: f.is_yiwei ? "#7f1d1d" : "rgba(0,0,0,.1)", borderWidth: f.is_yiwei ? 2.5 : .5 }, label: { show: f.is_yiwei || f.archetype === "真成长赢家", formatter: f.name, color: f.is_yiwei ? Y : "#475569", fontWeight: f.is_yiwei ? 700 : 600, fontSize: f.is_yiwei ? 13 : 10, position: "right" } })); return { grid: { left: 56, right: 40, top: 12, bottom: 44 }, tooltip: { formatter: p => `${p.data.value[3]}<br>营收CAGR ${p.data.value[0]}%<br>市值倍数 ${p.data.value[1]}x` }, xAxis: axx("营收CAGR %(真成长)"), yAxis: axx("市值倍数 x"), series: [{ type: "scatter", data, symbolSize: d => Math.max(13, Math.sqrt(d[2]) * 3.4), markLine: { ...ZL, lineStyle: { color: "#94a3b8", type: "dashed" }, data: [{ yAxis: 1 }] } }] }; }

function o_channels() { const ch = CFO.channels.filter(c => c.period !== "2017→2025"); const dom = c => Math.abs(c.pe_share) >= Math.abs(c.e_share); return { grid: { left: 50, right: 20, top: 30, bottom: 28 }, tooltip: { formatter: p => { const c = ch[p.dataIndex]; return `${c.period}<br>市值 ${c.mv_chg_pct}%<br>估值占 ${c.pe_share}% · 盈利占 ${c.e_share}%`; } }, xAxis: { type: "category", data: ch.map(c => c.period), axisLabel: { color: "#64748b" } }, yAxis: axx("市值变化 %", true), series: [{ type: "bar", data: ch.map(c => ({ value: c.mv_chg_pct, itemStyle: { color: dom(c) ? "#c0392b" : "#2563eb" } })), label: { show: true, position: "top", formatter: p => { const c = ch[p.dataIndex]; return (c.mv_chg_pct > 0 ? "+" : "") + c.mv_chg_pct + "%\n" + (dom(c) ? "估值主导" : "盈利主导"); }, color: "#334155", fontSize: 11, lineHeight: 14 }, markLine: { ...ZL, data: [{ yAxis: 0 }] } }] }; }

function o_learncurve() { const y = TRAIN.y_curve, t = TRAIN.t_curve; return { grid: { left: 48, right: 54, top: 30, bottom: 30 }, legend: { top: 0, textStyle: { fontSize: 11 } }, tooltip: { trigger: "axis" }, xAxis: { type: "category", data: t.rounds, name: "训练轮次", nameTextStyle: { color: "#64748b" }, axisLabel: { color: "#64748b" } }, yAxis: [{ ...axx("倾向AUC(学混淆)"), min: 0.5, max: 1 }, { ...axx("反应误差L2"), splitLine: { show: false } }], series: [{ name: "做不做定增·可预测(AUC)↑", type: "line", smooth: true, symbol: "none", data: t.valid, lineStyle: { color: "#f59e0b", width: 3 }, yAxisIndex: 0 }, { name: "市值反应·误差(L2,降不动)", type: "line", smooth: true, symbol: "none", data: y.valid, lineStyle: { color: "#94a3b8", width: 2, type: "dashed" }, yAxisIndex: 1 }], animationDuration: 2600 }; }
function o_deconf() { const r = TRAIN.residual; return { grid: { left: 46, right: 16, top: 16, bottom: 28 }, tooltip: { valueFormatter: v => v + "%" }, xAxis: { type: "category", data: ["朴素(含混淆)", "去混淆后", "被抹掉的混淆"], axisLabel: { color: "#64748b", interval: 0, fontSize: 11 } }, yAxis: axx("定增效应估计 %", true), series: [{ type: "bar", data: [{ value: r.naive_slope, itemStyle: { color: "#94a3b8" } }, { value: r.deconf_slope, itemStyle: { color: "#7c3aed" } }, { value: r.confound_removed, itemStyle: { color: "#dc2626" } }], label: { show: true, position: "top", formatter: p => p.value + "%" }, markLine: { ...ZL, data: [{ yAxis: 0 }] } }] }; }
function bootHist(draws) { const B = CAUSAL.bootstrap, lo = Math.min(...B) - 1, hi = Math.max(...B) + 1, bins = 24, w = (hi - lo) / bins, c = new Array(bins).fill(0); draws.forEach(v => { let i = Math.floor((v - lo) / w); i = Math.max(0, Math.min(bins - 1, i)); c[i]++; }); return c.map((n, i) => [+(lo + (i + .5) * w).toFixed(2), n]); }
function o_boot(draws) { return { grid: { left: 40, right: 16, top: 14, bottom: 30 }, tooltip: {}, xAxis: axx("重算的定增效应 %"), yAxis: axx("次数"), series: [{ type: "bar", barWidth: "92%", data: bootHist(draws), itemStyle: { color: "#2563eb", opacity: .82 }, markLine: { silent: true, symbol: "none", label: { show: false }, data: [{ xAxis: 0, lineStyle: { color: "#334155" } }] } }] }; }
let _bt = null;
function playBoot() { const B = CAUSAL.bootstrap, ch = charts["c_boot"]; if (!ch) return; clearInterval(_bt); let n = 0; _bt = setInterval(() => { n += 4; if (n >= B.length) { n = B.length; clearInterval(_bt); } const sub = B.slice(0, n), m = sub.reduce((a, b) => a + b, 0) / sub.length, s = [...sub].sort((a, b) => a - b), lo = s[Math.floor(.05 * (s.length - 1))], hi = s[Math.floor(.95 * (s.length - 1))]; ch.setOption(o_boot(sub), false); const el = document.getElementById("bootnum"); if (el) el.innerHTML = `重算 <b>${n}</b>/${B.length} 次　点估 <b style="color:#2563eb">${m.toFixed(2)}%</b>　90%区间 [${lo.toFixed(1)}, ${hi.toFixed(1)}]`; }, 110); }

function o_dml(hl) { const D = CAUSAL.dml_resid, pts = D.t.map((tr, i) => [tr, D.y[i]]), xs = D.t, lo = Math.min(...xs), hi = Math.max(...xs); const s = [{ type: "scatter", data: pts, symbolSize: 5, itemStyle: { color: "rgba(37,99,235,.3)" }, markLine: { ...ZL, lineStyle: { color: "#94a3b8", type: "dashed" }, data: [{ xAxis: 0 }, { yAxis: 0 }] } }, { type: "line", data: [[lo, +(D.slope * lo).toFixed(2)], [hi, +(D.slope * hi).toFixed(2)]], symbol: "none", lineStyle: { color: Y, width: 2.5 } }]; if (hl) s.push({ type: "scatter", data: [hl], symbolSize: 18, itemStyle: { color: "#dc2626", borderColor: "#fff", borderWidth: 2 }, z: 10, label: { show: true, formatter: "选中", position: "top", color: "#dc2626", fontWeight: 700, fontSize: 11 } }); return { grid: { left: 50, right: 18, top: 14, bottom: 38 }, tooltip: { formatter: p => p.seriesType === "scatter" ? `T̃=${p.data[0]}, Ỹ=${p.data[1]}%` : "" }, xAxis: axx("处理残差 T̃ = T − Ê[T|W]"), yAxis: axx("反应残差 Ỹ = Y − Ê[Y|W] %"), series: s }; }
function showEvent(i) { const e = TRAIN.events[i]; if (!e) return; const feats = TRAIN.feat_names.map((n, k) => `<span class="fchip">${n} <b>${e.feats[k]}</b></span>`).join(""); const el = document.getElementById("evdetail"); if (el) el.innerHTML = `<p style="font-size:13.5px;margin:0 0 6px"><b style="color:#c0392b">${e.firm} · ${e.date}</b> — ${e.T ? "做了定增 (T=1)" : "对照 firm-day (T=0)"}　Y反应 <b>${e.Y > 0 ? "+" : ""}${e.Y}%</b></p><div class="fml">残差化:　Y = ${e.Y}% − Ê[Y|W] = ${e.Yhat}%　⟶　<b style="color:#7c3aed">Ỹ = ${e.Yres}%</b><br>　　　　　T = ${e.T} − p = Ê[T|W] = ${e.p}　⟶　<b style="color:#7c3aed">T̃ = ${e.Tres}</b></div><div class="note" style="margin:8px 0 4px">这 22 个特征值就是喂进 nuisance 模型、算出上面 Ê[Y|W] 与 p 的输入:</div><div class="chips">${feats}</div>`; if (charts["c_dml"]) charts["c_dml"].setOption(o_dml([e.Tres, e.Yres]), false); }

/* ---------- 内容(移为诊断 + 同行学习 + 标准八段 + CFO行动)---------- */
const SECTIONS = [
  { t: "移为诊断 · 差在哪", sub: "主角=移为。先看它在14家里的位置:市值倍数、真成长、定增择时——病根在哪。",
    render: () => {
      const yw = PEER.yiwei;
      return {
        kpis: kpi("移为市值倍数", yw.mult + "x", "IPO→现(" + yw.ipo_mv + "→" + yw.cur_mv + "亿)", "warn") + kpi("营收CAGR", yw.rev_cagr + "%", "真成长(赢家≈" + PEER.wavg_g + "%)", "warn") + kpi("赢家均值", PEER.wavg_mult + "x", PEER.winners.join("/"), "good") + kpi("定增择时", yw.sso_valpct + " / " + yw.sso_reaction + "%", "高估值融资却被罚", "bad"),
        cards: [
          ["h7", "市值倍数:移为 vs 14家", `<div class="note">IPO→现市值倍数,移为(深红)处中游;真成长赢家在上。虚线=持平(1x)。</div><div id="c_mbar" class="chart" style="height:440px"></div>`],
          ["h5", "病根诊断", `<p><b>移为 ${yw.mult}x、营收CAGR ${yw.rev_cagr}%</b>,落后赢家(${PEER.wavg_mult}x、≈${PEER.wavg_g}%)。</p><p class="hot">病根=盈利/成长动量停滞,不是融资或公告技巧。</p>` + P("移为关键数", [["市值倍数", yw.mult + "x"], ["营收CAGR", yw.rev_cagr + "%"], ["定增次数", yw.sso_n], ["定增估值分位", yw.sso_valpct], ["定增原始反应", yw.sso_reaction + "%"], ["原型", yw.archetype]])],
          ["h12", "成长 vs 市值倍数:移为掉在哪", `<div class="note">横=营收CAGR(真成长),纵=市值倍数,气泡=现市值。移为(深红)在低成长区→市值倍数也上不去;真成长赢家在右上。</div><div id="c_pscat" class="chart"></div>`],
        ], charts: [["c_mbar", o_mult_bar], ["c_pscat", o_peer_scatter]],
      };
    } },
  { t: "同行学习 · 该学谁", sub: "其他13家不是陪衬:谁把市值做大了、怎么做的、移为该学什么、别照抄什么。",
    render: () => {
      const F = PEER.firms;
      const bad = F.filter(f => f.archetype === "估值消退/缩水").map(f => f.name).slice(0, 3).join("/");
      return {
        kpis: kpi("真成长赢家", PEER.winners.join("/"), "靠真成长撑估值", "good") + kpi("反面教材", bad || "—", "上市即高点/缺成长", "bad") + kpi("定增悖论", "高位也涨?", "广和通+8% vs 移为−1.3%", "warn") + kpi("总结论", "先补成长", "不是定增技巧", "pos"),
        cards: [
          ["h12", "14家:谁做得有效(按市值倍数)", `<div class="note">移为=高亮行。定增择时=该公司定增时的估值分位 + 原始反应。</div>` + tbl(["公司", "市值倍数", "营收CAGR", "定增n", "定增估值分位", "定增反应%", "原型"], F.map(f => [f.name, (f.mult == null ? "—" : f.mult + "x"), (f.rev_cagr == null ? "—" : f.rev_cagr + "%"), f.sso_n, f.sso_valpct == null ? "—" : f.sso_valpct, f.sso_reaction == null ? "—" : f.sso_reaction + "%", f.archetype]), F.findIndex(f => f.is_yiwei))],
          ["h7", "定增悖论 → 因果护栏", `<p><b>表面:</b>广和通/移远高估值(≈0.67)定增 <b>+8~10%</b>,移为高估值(${PEER.yiwei.sso_valpct})定增 <span class="hot">${PEER.yiwei.sso_reaction}%</span>——看着"高位定增也能涨"。</p><p><b>因果护栏(别照抄):</b>广和通正反应来自<b>真成长动量</b>,不是定增本身;DML 控掉动量后只剩"低估值才被奖励"。移为照抄高位融资却没动量撑 → 被罚。<b>这正是因果分析的价值:挡住"照抄同行表面动作"的坑。</b></p>`],
          ["h5", "移为该学什么", "<p>" + PEER.insights.map(s => "· " + s).join("</p><p>") + "</p>"],
        ], charts: [],
      };
    } },
  { t: "① 问题与目标", sub: "研究主体=移为(300590)+14家同行;命题=资本动作×公司因素→异常市值反应。这是因果(不是预测股价)。",
    render: () => ({
      kpis: kpi("研究主体", "移为 300590", "通信模组/IoT终端", "pos") + kpi("同行(对照)", E.n_firms + " 家", "纯模组/终端赛道", "") + kpi("事件样本", E.n_treated, "+ " + E.n_control + " 无动作对照", "") + kpi("时间跨度", E.year_min + "–" + E.year_max, "逐事件 20日窗口", ""),
      cards: [
        ["h6", "命题与脊柱", `<p><b>研究什么:</b>每次资本动作(定增/回购/减持/激励/业绩)在不同<b>公司因素</b>(估值/规模/成长)下,对事件后 20 日<b>相对同行</b>的异常市值反应有没有<b>因果</b>影响、什么条件下有效。</p><p><b>脊柱:</b>市值 = 盈利 × 估值倍数 × 股本 → 任何事件先归到这三通道。</p>`],
        ["h6", "为什么做因果、不做预测", `<p>本项目早期试过<b>预测</b>样本外排序(LightGBM,test IC ≈ 0.14),信号<span class="hot">很弱</span>——近有效市场里预测股价本就极难,已停用(账本 INV-009/010)。</p><p>所以转向<b>解释/因果</b>:不赌"会涨吗",而是估"<b>这个动作本身</b>把市值推动了多少",并转成 CFO 建议。</p>`],
        ["h12", "成功标准", `<p>① 能<b>可信地</b>估出动作的因果效应(去混淆 + 置信区间);② 经得起<b>稳健性拷问</b>(聚类自助/安慰剂/设定曲线/功效);③ 落成 CFO 可操作建议;④ <b>诚实报告 null</b>——没有就说没有。不追裸准确率。</p>`],
      ], charts: [],
    }) },
  { t: "② 数据 · EDA", sub: "数据源、样本规模、子类分布、标签定义与分布、缺失率。对应标准报告的数据探索。",
    render: () => ({
      kpis: kpi("处理样本", E.n_treated, "发生资本动作的事件", "pos") + kpi("对照样本", E.n_control, "无动作 firm-day", "") + kpi("标签均值", E.y_mean + "%", "20日剔同行异常反应", "") + kpi("标签波动", "±" + E.y_std + "%", "正" + E.y_pos_pct + "% / 负" + E.y_neg_pct + "%", "warn"),
      cards: [
        ["h7", "资本动作子类分布", `<div class="note">每类动作的事件数(回购/分红/业绩走tushare结构化全14家;定增/减持/激励靠公告,仅原9家)。</div><div id="c_sub" class="chart"></div>`],
        ["h5", "标签 Y(被解释量)", `<p><b>定义:</b>事件后 20 交易日,移为自身市值收益率 − 同期<b>剔除自身</b>的同行等权平均(剔掉行业共振)。</p>` + tbl(["分位", "值"], [["1%", E.y_q01 + "%"], ["中位", E.y_med + "%"], ["99%", E.y_q99 + "%"], ["正/负", E.y_pos_pct + "% / " + E.y_neg_pct + "%"]]) + `<p class="note" style="margin-top:8px">${E.winsor}</p>`],
        ["h6", "数据源", `<p>Tushare(日行情/估值/财务/指数)、AKShare+东方财富(公告/研报/新闻/机构调研)、巨潮披露。universe=peer_universe.csv 的 14 家(改 include 列即增减)。</p>` + chips(["日行情", "估值PE/PB/PS", "财务三表", "公告", "研报", "机构调研", "回购/分红/业绩(结构化)"])],
        ["h6", "特征缺失率", `<div class="note">入模特征的缺失比例(用中位数填补)。</div>` + tbl(["特征", "缺失%"], E.missing.map(m => [m.feat, m.miss_pct + "%"]))],
      ], charts: [["c_sub", o_subtypes]],
    }) },
  { t: "③ 特征工程", sub: "特征清单、构造逻辑、防泄漏(point-in-time)、特征重要性。",
    render: () => ({
      kpis: kpi("入模特征", REPORT.features.length + " 个", "价格技术+基本面+成长", "pos") + kpi("效应修饰", "六维", "估值/规模/ROE/杠杆/研发/成长", "") + kpi("防泄漏", "PIT 校验", "ann_date≤事件日,无未来信息", "good") + kpi("估值缺失", "0.4%", "PE→PB→PS 兜底(旧18.7%)", "good"),
      cards: [
        ["h6", "特征清单(" + REPORT.features.length + " 个)", `<p>三类共 ${REPORT.features.length} 个,都用<b>行业内相对/分位</b>表示让异体量公司可比:</p>` + chips(REPORT.features) + `<p class="note" style="margin-top:8px"><b>盈利能力</b>=ROE/ROA/毛利率/净利率;<b>质量</b>=研发强度/经营现金流占营收;<b>杠杆</b>=资产负债率/流动比率;<b>成长</b>=营收净利同比+2/3年CAGR;<b>估值分位</b>=PE(无效则PB/PS)在该公司全历史分位;<b>规模/动量/波动/换手</b>=市值与价格技术。<span class="hot">这套基本面早已算好却没接进因果,本次正式接入。</span></p>`],
        ["h6", "防泄漏与构造", `<p>① <b>point-in-time</b>:特征可用日 ≤ 事件日,黑名单+校验,杜绝"用未来预测过去"。</p><p>② <b>成长 CAGR</b> 按年报 ann_date 取,只用事件前已披露的财报。</p><p>③ 混淆控制变量(规模/动量/换手/波动/盈利/杠杆/成长)喂给 DML 的 nuisance,把"公司本来的状态"扣掉。</p>`],
        ["h12", "特征规范化:让异体量公司可比(截面秩等公式)", `<p>公司体量差几十倍(50亿 vs 5000亿),原始值不可比。早期预测线对每个底层信号造了 4 种 point-in-time 规范化变体(共 ~150 列):</p>
<div class="fml"><b>截面秩 xsrank</b>　<i>r</i><sub>i</sub> = rank<sub>季度同行</sub>(<i>f</i><sub>i</sub>) / <i>n</i><sub>q</sub> ∈ [0, 1]　<span class="wh">同季度、同行池内的百分位:0=最低、1=最高(88个变体走这种)</span></div>
<div class="fml"><b>公司内 z 分 selfz</b>　<i>z</i><sub>i</sub> = ( <i>f</i><sub>i</sub> − μ<sub>该公司过去</sub> ) ⁄ σ<sub>该公司过去</sub>　<span class="wh">用该公司自身历史(仅过去样本,shift)去基线</span></div>
<div class="fml"><b>同比 yoy</b>　Δ<i>f</i> = ( <i>f</i><sub>t</sub> − <i>f</i><sub>t−1y</sub> ) ⁄ | <i>f</i><sub>t−1y</sub> |　　<b>截面去中位 xsdemed</b>　<i>f</i><sub>i</sub> − median<sub>季度同行</sub>(<i>f</i>)</div>
<p class="note"><b>因果为何不用这 150 个变体(回答"特征怎么这么少"):</b>① 它们是<b>事件级</b>(6420事件)算的,<b>接不到对照 firm-day</b>;② 88个 xsrank、12个 selfz……是同 ~30 底层信号的<b>冗余变换</b>,塞进 nuisance 只会共线过拟合。因果改用 <b>firm-day 可接的原始 PIT 水平值</b>(估值分位 + 21 个混淆),可解释、可接对照——不是"收敛掉"了,是按因果需要精选。</p>`],
        ["h12", "特征重要性(预测市值反应的 gain)", `<div class="note">来自 DML 里"学公司状态→市值反应"的 LightGBM(gain 归一化)。注:这是<b>预测</b>反应的重要性,不等于因果效应;因果用途见⑥可解释性。</div><div id="c_fi" class="chart" style="height:300px"></div>`],
      ], charts: [["c_fi", o_featimp]],
    }) },
  { t: "④ 模型与训练", sub: "选哪个算法及为什么、超参数、训练流程(交叉拟合)、处理/对照设计。",
    render: () => ({
      kpis: kpi("主算法", "Double ML", "残差化去偏估因果", "pos") + kpi("异质效应", "因果森林", "每事件一个 CATE", "pos") + kpi("混淆控制 W", "16 个", "价格技术+基本面+成长", "good") + kpi("交叉拟合", "4 折", "防 nuisance 过拟合", "good"),
      cards: [
        ["h12", "为什么用这套(而不是预测模型)", `<p>这是<b>异质处理效应(CATE)</b>问题,不是预测问题:同一动作在不同公司因素下效应不同,且有<b>混淆</b>(做定增的公司本来盈利/杠杆/成长就不同)。直接算平均=把"公司本来的状态"算成动作功劳。所以用 <b>Double ML</b>(残差化去偏)+ <b>因果森林</b>(非参 CATE)。<span class="hot">刻意不用</span>"LightGBM+TreeSHAP 预测归因"——那解释的是预测值、会把相关当因果。<b>本次把 16 个混淆变量(含全套基本面)喂进去</b>,这是去偏可信度的关键。</p>`],
        ["h6", "", P("nuisance 模型(去混淆)", [["算法", "LightGBM 梯度提升树"], ["规模", "300 棵 · 每棵 ≤15 叶"], ["学习率", "0.05"], ["子采样", "0.8 行 / 0.8 列"], ["交叉拟合", "4 折(轮流,防偷看答案)"], ["混淆 W", "16 个:规模/动量/波动/换手 + ROE/ROA/毛利/净利率/负债率/流动比率/研发/现金流 + 成长"], ["随机种子", "0"]])],
        ["h6", "", P("因果森林 CausalForestDML", [["规模", "800 棵 · 每叶 ≥20 样本"], ["划分", "honest(分裂样本≠估计样本)"], ["输出", "每个事件一个 CATE + 置信区间"], ["效应修饰 X", "估值 / 规模 / ROE / 杠杆 / 研发强度 / 成长(六维)"], ["软件", "econml(隔离 venv,sklearn<1.7)"]])],
        ["h12", "训练流程 4 步", `<p><b>① 学 nuisance</b>:LightGBM 分别学"公司状态→反应"和"公司状态→是否定增"。<b>② 残差化</b>:两边都减掉预测值,留下"扣掉公司状态后"的残差。<b>③ 估效应</b>:反应残差 对 处理残差回归,斜率=去混淆的 ATE(LinearDML);因果森林在残差上长树估每个事件的 CATE。<b>④ 全程 5 折交叉拟合</b>。处理=做了动作的事件,对照=无动作 firm-day(±25日内无任何资本动作)。</p>`],
        ["h12", "因果识别与估计量(公式)", `<p><b>估计目标 estimand:</b></p>
<div class="fml"><b>CATE</b>　<i>τ</i>(<i>x</i>) = E[ <i>Y</i><sup>(1)</sup> − <i>Y</i><sup>(0)</sup> | <i>X</i> = <i>x</i> ]　，　<b>ATE</b> = E[ <i>τ</i>(<i>X</i>) ]　<span class="wh">做动作 vs 不做,对市值反应的(条件)平均因果效应</span></div>
<p><b>部分线性模型 + 残差化(Robinson / Double ML):</b></p>
<div class="fml"><i>Y</i> = <i>θ</i>·<i>T</i> + <i>g</i>(<i>W</i>) + <i>ε</i>　，　<i>T</i> = <i>m</i>(<i>W</i>) + <i>η</i>　<span class="wh">g、m=LightGBM 学的"公司状态→反应/处理"混淆函数</span></div>
<div class="fml"><i>Ỹ</i> = <i>Y</i> − Ê[<i>Y</i>|<i>W</i>]　，　<i>T̃</i> = <i>T</i> − Ê[<i>T</i>|<i>W</i>]　⟶　<i>θ̂</i> = ( Σ<sub>i</sub> <i>T̃</i><sub>i</sub> <i>Ỹ</i><sub>i</sub> ) ⁄ ( Σ<sub>i</sub> <i>T̃</i><sub>i</sub><sup>2</sup> )　<span class="wh">在残差上回归,斜率=去混淆效应</span></div>
<p><b>Neyman 正交 + 交叉拟合:</b>矩条件 E[ <i>ψ</i>(<i>θ</i><sub>0</sub>) ] = 0 对 nuisance 一阶不敏感;Ê[·|W] 用 K=5 折<b>样本外</b>预测(k 折外训练、k 折内预测),消除过拟合偏差。因果森林在残差上长 <b>honest</b> 树(分裂样本≠估计样本)估 <i>τ</i>(<i>x</i>)。</p>`],
      ], charts: [],
    }) },
  { t: "训练全过程 · 看模型怎么学", sub: "把黑箱摊开给不懂的人看:模型逐轮在学什么、去混淆抹掉了什么、同一结论重算150次怎么收敛、全部17个特征。",
    render: () => {
      const r = TRAIN.residual;
      return {
        kpis: kpi("市值反应可预测性", "R² " + r.y_r2, "≈0:反应本身就是噪声", "warn") + kpi("做不做定增可预测", "AUC " + r.propensity_auc, ">0.5:强混淆,必须去", "bad") + kpi("朴素→去混淆", r.naive_slope + "% → " + r.deconf_slope + "%", "抹掉 " + r.confound_removed + "% 全是混淆", "pos") + kpi("入模特征", TRAIN.n_feat + " 个", TRAIN.n_treated + " 定增 / " + TRAIN.n_control + " 对照", ""),
        cards: [
          ["h12", "训练集与设定(可复现)", P("数据与训练设定", [["处理组", TRAIN.n_treated + " 个定增事件"], ["对照组", TRAIN.n_control + " 个无动作 firm-day(±25日内无任何资本动作)"], ["入模特征", TRAIN.n_feat + " 个(21 混淆 W + 估值分位 X)"], ["标签 Y", "事件后20日市值收益 − 剔自身同行等权(剔行业共振)"], ["学习曲线划分", "75% 训练 / 25% 验证(按处理标签分层)"], ["去偏交叉拟合", "5 折 KFold / StratifiedKFold(shuffle, seed=0)"], ["nuisance 模型", "LightGBM 300树 · ≤15叶 · lr0.05 · 行/列子采样0.8"], ["因果森林", "800树 · 每叶≥20 · honest 划分"], ["Y winsorize", "1% / 99%;特征缺失→中位数填补"], ["随机种子", "0(全流程)"]])],
          ["h6", "① 学习曲线:模型逐轮在学什么", `<div class="note">橙=「做不做定增」越学越准(AUC 0.77→0.91)→确有强混淆;灰=「市值反应」误差降不动→反应近乎不可预测。<b>这正是不能预测、只能去混淆的原因。</b></div><div id="c_lc" class="chart"></div>`],
          ["h6", "② 去混淆抹掉了什么(数字怎么变)", `<div class="note">直接算定增效应 +${r.naive_slope}%(含混淆);残差化扣掉公司状态后只剩 +${r.deconf_slope}%——<b>中间 ${r.confound_removed}% 全是混淆</b>,被模型识别并抹掉。</div><div id="c_dec" class="chart"></div>`],
          ["h7", "②ᵃ 真实训练数据(样例:4处理+4对照)", `<div class="note">这就是喂进模型的<b>真实行</b>(每行一个事件)。T=1做了定增、T=0对照;Y=事件后20日剔同行异常反应%。</div>` + tbl(["公司", "日期", "估值分位", "ROE", "对数市值", "负债率", "营收CAGR3", "Y反应%", "T"], TRAIN.data_sample.map(s => [s.firm, s.date, s.val_pct, s.roe, s.log_mv, s.debt + "%", s.cagr3 + "%", (s.Y > 0 ? "+" : "") + s.Y, s.T]))],
          ["h5", "②ᵇ 残差化实算:公式落到真实数字", `<div class="note">同这几条事件:模型先预测 Ê[Y|W]、Ê[T|W],再相减得残差 Ỹ、T̃。</div>` + tbl(["公司", "Y", "Ê[Y|W]", "Ỹ残差", "T", "p", "T̃残差"], TRAIN.residual_sample.map(s => [s.firm, s.Y, s.Yhat, (s.Yres > 0 ? "+" : "") + s.Yres, s.T, s.That, s.Tres])) + `<p class="note" style="margin-top:8px">代入 <i>θ̂</i> = Σ<i>T̃Ỹ</i> ⁄ Σ<i>T̃</i>² ⟶ <b>${r.deconf_slope}%</b>(全样本去混淆效应)。</p>`],
          ["h12", "②ᶜ θ̂ 就是这堆残差点的斜率(全样本)", `<div class="note">横=处理残差 T̃,纵=反应残差 Ỹ(都已扣掉公司状态);<span class="hot">红线斜率 = 去混淆效应 θ̂ = ${CAUSAL.dml_resid.slope}%</span>。点云几乎水平=去混淆后定增没把反应推上去。</div><div id="c_dml" class="chart"></div>`],
          ["h12", "🔎 选一个事件 → 看它怎么过模型(交互)", `<div class="note">下拉任选一个真实事件:它的 <b>22 个特征值</b>、残差化 Ê[Y|W]→Ỹ、Ê[T|W]→T̃ 全显示出来,并在上面散点里<b style="color:#dc2626">红点高亮</b>它的位置。共 ${TRAIN.events.length} 个事件(全部定增+对照样本)。</div><select id="evsel" onchange="showEvent(this.value)" style="border:1px solid var(--line);border-radius:8px;padding:7px 12px;font-size:13px;max-width:360px;color:#334155">${TRAIN.events.map((e, i) => `<option value="${i}">${e.firm}　${e.date}　${e.T ? "定增" : "对照"}　Y=${e.Y > 0 ? "+" : ""}${e.Y}%</option>`).join("")}</select><div id="evdetail" style="margin-top:12px;min-height:40px"></div>`],
          ["h12", "③ 同一结论重算 150 次:看数字怎么收敛", `<div class="note">按整家公司重抽(聚类自助),每次重算定增效应——数字来回跳,逐渐收敛成一个区间。点播放看过程。</div><div style="margin:8px 0"><button onclick="playBoot()" style="border:1px solid #0f172a;background:#0f172a;color:#fff;border-radius:8px;padding:7px 16px;cursor:pointer;font-size:12.5px;font-weight:600">▶ 播放重算过程</button> <span id="bootnum" style="font-size:12.5px;color:#475569;margin-left:10px;font-variant-numeric:tabular-nums"></span></div><div id="c_boot" class="chart" style="height:300px"></div>`],
          ["h12", "④ 全部 " + TRAIN.n_feat + " 个入模特征(无黑箱)", `<div class="note">W=去混淆控制、X=效应修饰(W+X=两者兼);重要性=Y模型 gain;缺失=填补前原始缺失率。</div>` + tbl(["特征", "角色", "重要性%", "缺失%", "5分位", "95分位"], TRAIN.features.map(f => [f.name, f.role, f.imp, f.miss + "%", f.lo, f.hi]))],
        ], charts: [["c_lc", o_learncurve], ["c_dec", o_deconf], ["c_dml", o_dml], ["c_boot", () => o_boot(CAUSAL.bootstrap)]],
        after: () => showEvent(0),
      };
    } },
  { t: "⑤ 评估", sub: "因果版:ATE+CI(替代准确率)、vs 基线、nuisance 诊断(替代学习曲线)、稳健性、功效。",
    render: () => {
      const F = CAUSAL.forest, fz = F.find(f => f.name === "定增"); const H = CAUSAL.harden;
      return {
        kpis: kpi("定增 ATE", (fz.ate > 0 ? "+" : "") + fz.ate + "%", fz.lo * fz.hi > 0 ? "去混淆CI排除0" : "接基本面混淆后CI含0,不显著", fz.lo * fz.hi > 0 ? "pos" : "warn") + kpi("定增·聚类自助", "p≈" + H.cluster_p, "整簇重抽点估≈0,不坐实", "warn") + kpi("减持 / 回购", "≈0 n.s.", "去偏后无显著因果", "") + kpi("定增功效@3%", "23%", "查不动 → inconclusive", "bad"),
        cards: [
          ["h6", "主效应:ATE + 90%CI", `<div class="note">点=去混淆因果效应,横线=90%CI;碰竖零线=不显著。</div><div id="c_for" class="chart"></div>` + tbl(["动作", "ATE%", "90%CI", "安慰剂p"], F.map(f => [f.name, f.ate, `[${f.lo},${f.hi}]`, f.p]))],
          ["h6", "vs 基线:三种口径", `<div class="note">①直接算平均(含混淆)→②更干净测量(因子CAR)→③去混淆因果(DML)。看口径越严,定增怎么塌。</div><div id="c_ov" class="chart"></div>`],
          ["h6", "nuisance 诊断(替代学习曲线)", `<div class="note">DML 有效性前提:倾向AUC>0.5=动作可被状态预测(确有混淆,正是要去的偏);overlap≈1=处理/对照可比(positivity)。</div><div id="c_nu" class="chart"></div>`],
          ["h6", "统计功效(结果可信度)", `<div class="note">能查出3%效应的把握。绿≥80%门槛+观测≈0=可信null;红=查不动=inconclusive。</div><div id="c_pw" class="chart"></div>`],
          ["h6", "稳健性①:聚类自助 + 安慰剂", `<div class="note">把~8家做定增公司整簇重抽150次(蓝)vs 打乱标签的零分布(灰)。蓝擦0且与灰重叠=边际。</div><div id="c_inf" class="chart"></div>`],
          ["h6", "稳健性②:设定曲线", `<div class="note">每条结论在36种合理设定下的效应分布;箱体不跨零线=稳健。减持全负、回购骑零线、定增跨0。</div><div id="c_sp" class="chart"></div>`],
        ], charts: [["c_for", o_forest], ["c_ov", o_overview], ["c_nu", o_nuis], ["c_pw", o_power], ["c_inf", o_infer], ["c_sp", o_spec]],
      };
    } },
  { t: "⑥ 可解释性", sub: "因果森林变量重要性(谁最调节效应)、CATE 异质性、特征重要性。",
    render: () => {
      const ct = CAUSAL.cate, vi = ct.vi || {};
      const viS = Object.entries(vi).sort((a, b) => b[1] - a[1]);
      const lowSig = ct.low_ci[0] * ct.low_ci[1] > 0;
      return {
        kpis: kpi("定增·低估值 CATE", (ct.low > 0 ? "+" : "") + ct.low + "%", lowSig ? "CI排除0,显著" : "CI含0,方向性", lowSig ? "good" : "warn") + kpi("定增·高估值 CATE", (ct.high > 0 ? "+" : "") + ct.high + "%", "CI 含0,不显著", "warn") + kpi("最强调节因子", viS[0] ? viS[0][0] : "—", "最左右定增效应", "pos") + kpi("最弱调节", viS.length ? viS[viS.length - 1][0] : "—", "对效应影响小", ""),
        cards: [
          ["h6", "因果森林:谁最调节效应", `<p>因果森林给每个事件一个效应,再看<b>哪个公司因素</b>最能区分"效应大/小"(变量重要性,六维):</p>` + tbl(["因子", "重要性"], viS.map(([k, v]) => [k, v])) + `<p class="note" style="margin-top:6px">${viS.slice(0, 3).map(([k, v]) => k + "(" + v + ")").join(" > ")} ……<span class="hot">杠杆、研发、ROE 等基本面现已纳入调节维度</span>,不再只看估值/规模。</p>`],
          ["h6", "CATE 异质性:估值轴", `<p>同样是定增,<b>低估值</b>点估 <span class="hot">${ct.low > 0 ? "+" : ""}${ct.low}%</span> 高于<b>高估值</b> ${ct.high > 0 ? "+" : ""}${ct.high}%——方向上"低估值时融成长"更被奖励;但接进基本面混淆后<b>两者 CI 均含 0、欠功效</b>,只作方向性提示,不坐实。</p><p><b>含义:</b>移为过去定增多在高估值(≈0.66)→拿不到低估值那点溢价。</p>`],
          ["h12", "特征重要性(预测侧,见③)", `<p>预测市值反应的特征 gain(${FI.length} 个):动量/规模/估值领先,基本面(流动比率/经营现金流/毛利/研发/ROE)居中。注意这是<b>预测</b>重要性;因果上"什么条件下动作有效"以上面因果森林变量重要性为准。SHAP-on-CATE 在边际效应下不稳,暂未做。</p>` + chips(FI.slice(0, 12).map(f => f.feat + " " + f.imp + "%"))],
        ], charts: [],
      };
    } },
  { t: "⑦ 误差分析", sub: "哪里最容易错、为什么:混淆导致的假信号、样本不足的 inconclusive、单案例失败。",
    render: () => ({
      kpis: kpi("最大陷阱", "减持", "描述显著负→因果null=混淆", "bad") + kpi("欠功效", "定增", "仅~8家做过,坐实不了", "warn") + kpi("单案例失败", "合成控制", "pre-fit差→inconclusive", "warn") + kpi("噪声来源", "单公司", "逐家样本小、含噪", ""),
      cards: [
        ["h7", "误差①:减持——描述会骗你", `<p>直接算,减持反应 <b>−1.9%、p=0.002</b> 看着"显著负"。但 DML 去混淆后<b>塌成 +0.4% 不显著</b>、安慰剂 p=0.62。</p><p><b>为什么:</b>减持往往发生在<b>涨多了/特定状态</b>,那段本就会回调——裸数据把"状态"的锅算给了减持公告。倾向AUC 0.86(三类最高)=减持的混淆最重。<span class="hot">这是整个项目最大的"误差"来源:把混淆当因果。</span></p>`],
        ["h5", "误差②:定增——混淆 + 欠功效", `<p>定增原始描述 +3.7%,但<b>接进全套基本面混淆后塌到 ≈0</b>(LinearDML ${CAUSAL.forest.find(f => f.name === "定增").ate}%、聚类自助点估 ${CAUSAL.harden.cluster[1]}%,均不显著)——大半是<b>混淆</b>(做定增的公司盈利/杠杆/成长本就不同)。再叠加只 ~8 家做过、功效 23%,<b>既被混淆又欠功效</b>,诚实标 inconclusive。</p>`],
        ["h7", "误差③:合成控制——已完成,结论 inconclusive", `<div class="note">这是<b>跑完了的</b>单案例稳健性检验,不是 bug。移为2020定增反事实:红=真实,蓝虚=合成;事件前两线没贴合(pre-fit RMSPE ${CAUSAL.sc.prefit}>0.06)=造不出可信的反事实移为(2020 5G暴涨无法匹配)→诚实不下结论。</div><div id="c_scp" class="chart"></div>`],
        ["h5", "误差④:单公司噪声", `<p>逐家看动作反应=单公司小样本、含噪,方向常互相矛盾(同一动作有的家正有的负)。所以<b>因果级结论只在合并14家</b>下给,逐家只作描述参照。</p>`],
      ], charts: [["c_scp", o_sc]],
    }) },
  { t: "⑧ 局限与复现", sub: "识别假设、样本局限、可复现信息(Model Card)。",
    render: () => ({
      kpis: kpi("识别强度", "L3 应用级", "可观测混淆控制(最弱档)", "warn") + kpi("无准实验", "无 IV/DiD", "非随机/自然实验", "warn") + kpi("随机种子", "0", "全流程固定可复现", "good") + kpi("环境", "双 venv", "主.venv + 隔离.venv-causal", "good"),
      cards: [
        ["h6", "局限(诚实)", `<p>① <b>识别靠"可观测混淆控制"</b>:现已控住规模/动量/盈利/杠杆/研发/成长等 <b>16 个</b>混淆(本次升级),比原来强很多,但仍假设无<b>未测</b>混淆——因果识别仍属观测性<b>较弱档</b>,无 IV/DiD/断点等准实验,E-value 只能部分补。</p><p>② <b>样本小</b>:定增~8家、簇少,功效低——数据天花板,非方法可解。</p><p>③ 对照=无动作 firm-day,结果对对照设计敏感。④ 研发强度等基本面仍 ~30% 缺失(中位数填补)。</p>`],
        ["h6", "可复现(Model Card)", `<p><b>脚本链(仓库根运行):</b></p>` + chips(["build_fundamental_panel", "build_normalized_features", "analyze_capital_action_cate", "harden_cate_inference", "build_factor_car", "build_power_analysis", "build_spec_curve"]) + P("环境与复现", [["主环境", ".venv(pandas/lightgbm/sklearn1.8)"], ["因果环境", ".venv-causal(econml,sklearn<1.7)"], ["依赖锁", "requirements-causal.txt"], ["随机种子", "0(DML/森林/自助/置换)"], ["唯一真相", "DECISION_LEDGER.md INV-013~031"], ["静态闸", "tools/check.py changed = EXIT 0"]])],
        ["h12", "下一步(可升识别强度到 L4)", `<p>给移为某大事件上<b>合成控制/DiD</b>(借政策冲击或未受影响同行做准实验反事实);多估计量三角验证(DML+森林+DiD 同向);扩样本(更宽同行池增簇数)。但 A 股纯模组赛道本就~14家,扩样本有天花板。</p>`],
      ], charts: [],
    }) },
  { t: "CFO 行动建议", sub: "诊断→学习→证据之后的「那要做什么」:市值由哪条通道驱动、5 条可操作建议(带诚实边界)。",
    render: () => {
      const ch = CFO.channels;
      return {
        kpis: kpi("最大回撤", "−49%", "2021→22 纯估值杀(估值占109%)", "bad") + kpi("市值主驱动", "估值倍数", "非盈利;盈利是慢变量", "warn") + kpi("定增择时", "偏高 0.68", "踩在「不被奖励」区间", "warn") + kpi("2025 盈利", "净利腰斩", "1.59→0.75亿,成新拖累", "bad"),
        cards: [
          ["h7", "市值三通道:谁在驱动(估值 vs 盈利)", `<div class="note">市值=隐含倍数×盈利(精确恒等)。红=估值主导、蓝=盈利主导;最大回撤(2021→22)是<b>纯估值杀</b>。</div><div id="c_chan" class="chart"></div>`],
          ["h5", "精确占比(诚实)", tbl(["区间", "市值%", "估值占", "盈利占"], ch.map(c => [c.period, (c.mv_chg_pct > 0 ? "+" : "") + c.mv_chg_pct + "%", c.pe_share + "%", c.e_share + "%"]), ch.findIndex(c => c.period === "2021→2022")) + `<p class="note" style="margin-top:8px">${CFO.key_finding}</p>`],
          ["h12", "5 条 CFO 可操作建议", CFO.recs.map((r, i) => `<p><b>${i + 1}. ${r.t}:</b>${r.d}</p>`).join("") + `<p class="note"><b>诚实边界:</b>全链无一可下「统计显著因果」的强断言——定增边际、减持混淆、回购无效;按方向性参考使用。市值管理真正着力点在基本面,不在公告操作。</p>`],
        ], charts: [["c_chan", o_channels]],
      };
    } },
];

/* ---------- 引擎 ---------- */
let cur = 0;
function renderNav() { document.getElementById("nav").innerHTML = SECTIONS.map((s, i) => `<button class="${i === cur ? "on" : ""}" onclick="goSec(${i})">${s.t}</button>`).join(""); }
function renderSec() {
  Object.values(charts).forEach(c => c.dispose()); charts = {};
  const s = SECTIONS[cur], d = s.render();
  const cards = d.cards.map(([cls, title, body]) => `<div class="card ${cls}">${title ? `<h3>${title}</h3>` : ""}${body}</div>`).join("");
  document.getElementById("content").innerHTML =
    `<div class="sechead"><h2>${s.t}</h2><div class="sub">${s.sub}</div></div>` +
    `<div class="kpis">${d.kpis}</div><div class="cards">${cards}</div>`;
  (d.charts || []).forEach(([id, fn]) => setTimeout(() => mk(id, fn()), 20));
  if (d.after) setTimeout(d.after, 60);
}
function goSec(i) { cur = i; renderNav(); renderSec(); window.scrollTo(0, 0); }
window.addEventListener("resize", () => Object.values(charts).forEach(c => c.resize()));
renderNav(); renderSec();
