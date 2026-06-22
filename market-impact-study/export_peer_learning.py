"""Export peer-learning + 移为 diagnosis data (who grew how, what 移为 should copy) for the dashboard front sections."""

# 职责：把"同行谁把市值做大了/怎么做的 + 移为差在哪/该学谁/别踩坑"(INV-021/022 的正向结论)
#       提成结构化 JSON = INV-032,供仪表板把交付翻成"正向可学",因果当护栏。每家:市值倍数(IPO口径)/
#       营收净利CAGR/定增择时(估值分位+原始反应)/原型标签/一句教训;移为为主角。
# 不做什么：不做因果估计/不自算倍数;复用 peer_comparison.json(IPO口径,权威)+ financial_panel(配色)。
# 允许依赖层：标准库、peer_comparison.json、financial_panel.json。
# 谁不应该 import：建模脚本不应 import 本入口。先跑 build_peer_comparison.py 产 peer_comparison.json。
from __future__ import annotations

import json
from pathlib import Path

M = Path("market-impact-study/data/processed/modeling")
CATE = M / "cate_14firm"
OUT = CATE / "peer_learning.json"
YIWEI = "300590.SZ"


def archetype(mult: float | None, rev_cagr: float | None) -> tuple[str, str]:
    m = mult or 0
    g = rev_cagr if rev_cagr is not None else 0
    if m >= 2.5 and g >= 20:
        return ("真成长赢家", "靠真成长(高营收CAGR)撑估值,可持续——移为的榜样")
    if m >= 2.5:
        return ("高倍数·成长待证", "市值倍数高但成长一般,持续性存疑")
    if m < 1:
        return ("估值消退/缩水", "上市即高点或缺成长,警示'上市光环退潮'")
    if m < 1.6:
        return ("低成长", "成长不足,市值原地踏步")
    return ("成长中游", "有成长但不突出,需把盈利动量做实")


def main() -> None:
    pc = {r["code"]: r for r in json.loads((CATE / "peer_comparison.json").read_text(encoding="utf-8"))}
    fin = {c["code"]: c for c in json.loads((M / "financial_panel.json").read_text(encoding="utf-8"))["companies"]}
    firms = []
    for code, r in pc.items():
        fc = fin.get(code, {})
        ipo, cur = (None, None)
        if isinstance(r.get("mv"), str) and "→" in r["mv"]:
            a, b = r["mv"].split("→")
            ipo, cur = float(a), float(b)
        arch, note = archetype(r.get("mult"), r.get("rev_cagr"))
        firms.append(
            {
                "code": code,
                "name": r["name"],
                "is_yiwei": code == YIWEI,
                "color": fc.get("color", "#94a3b8"),
                "mult": r.get("mult"),
                "rev_cagr": round(r["rev_cagr"]) if r.get("rev_cagr") is not None else None,
                "ni_cagr": fc.get("ni_cagr"),
                "ipo_mv": ipo,
                "cur_mv": cur,
                "yrs": r.get("yrs"),
                "sso_n": r.get("fin_n", 0),
                "sso_valpct": r.get("fin_vp"),
                "sso_reaction": r.get("fin_rel"),
                "archetype": arch,
                "note": note,
            }
        )
    firms.sort(key=lambda x: -(x["mult"] or 0))
    yw = next(f for f in firms if f["is_yiwei"])
    winners = [f for f in firms if f["archetype"] == "真成长赢家"]
    wavg_mult = round(sum(f["mult"] for f in winners) / len(winners), 1) if winners else None
    wavg_g = round(sum(f["rev_cagr"] for f in winners) / len(winners)) if winners else None
    insights = [
        f"真成长赢家({'、'.join(f['name'] for f in winners)})平均 {wavg_mult}x 市值、营收CAGR≈{wavg_g}%,全靠真成长撑估值——不是公告技巧。",
        f"移为 {yw['mult']}x、营收CAGR {yw['rev_cagr']}%,处成长中游;盈利动量是瓶颈,不是融资技巧问题。",
        f"定增择时悖论:广和通/移远高估值(≈0.67)定增却 +8~10%,因带真成长动量;移为高估值(≈{yw['sso_valpct']})定增却 {yw['sso_reaction']}%——学了高位融资却没成长动量撑。",
        "要被市场奖励:需占'低估值'或'真成长故事'其一;移为两样都不占,所以被罚。该补的是成长,不是定增技巧。",
    ]
    OUT.write_text(
        json.dumps(
            {
                "firms": firms,
                "yiwei": yw,
                "winners": [f["name"] for f in winners],
                "wavg_mult": wavg_mult,
                "wavg_g": wavg_g,
                "insights": insights,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(
        f"peer_learning: {len(firms)} 家,赢家 {[f['name'] for f in winners]},移为 {yw['mult']}x CAGR{yw['rev_cagr']}%"
    )
    print("saved ->", OUT)


if __name__ == "__main__":
    main()
