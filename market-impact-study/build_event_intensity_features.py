"""构造非 RAG 事件强度特征。

唯一职责：从标题、摘要、事件组标题中抽取金额、比例、方向和事件类型强度特征，生成 enhanced v2 建模宽表。
不做什么：不读取公告正文/RAG chunk；不训练模型；不修改 SSOT 或人工复核结果。
允许依赖的层：只读取 enhanced v1 建模宽表。
谁不应 import：训练脚本不应 import 本入口脚本；应直接读取输出的 enhanced v2 宽表。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

MODELING_DIR = Path("market-impact-study/data/processed/modeling")
DOC_REPORTS_DIR = Path("market-impact-study/docs/reports")

INPUT_PATH = MODELING_DIR / "modeling_dataset_enhanced_v1.csv"
OUTPUT_PATH = MODELING_DIR / "modeling_dataset_enhanced_v2.csv"
PREVIOUS_MANIFEST_PATH = MODELING_DIR / "enhanced_feature_manifest.csv"
FEATURE_MANIFEST_PATH = MODELING_DIR / "event_intensity_feature_manifest.csv"
COMBINED_MANIFEST_PATH = MODELING_DIR / "enhanced_feature_manifest_v2.csv"
REPORT_PATH = DOC_REPORTS_DIR / "EVENT_INTENSITY_FEATURES_SUMMARY.md"

TEXT_COLUMNS = ["title", "summary", "group_titles_sample"]
MONEY_PATTERN = re.compile(r"(?<!\d)(-?\d+(?:\.\d+)?)(?:\s*)(亿元|亿|万元|万|元)")
PERCENT_PATTERN = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")
RANGE_SEPARATORS = r"(?:-|~|至|到|—|－)"
PROFIT_RANGE_PATTERN = re.compile(
    rf"(?:净利润|归母净利润|利润)(?:[^-\d]{{0,12}})(-?\d+(?:\.\d+)?)\s*{RANGE_SEPARATORS}\s*(-?\d+(?:\.\d+)?)(?:\s*)(亿元|亿|万元|万|元)?"
)


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"缺少输入文件：{path}")
    return pd.read_csv(path)


def event_text(row: pd.Series) -> str:
    parts = []
    for column in TEXT_COLUMNS:
        value = row.get(column)
        if pd.notna(value) and str(value) not in parts:
            parts.append(str(value))
    return " ".join(parts)


def money_to_yi(value: str, unit: str) -> float:
    number = float(value)
    if unit in {"亿元", "亿"}:
        return number
    if unit in {"万元", "万"}:
        return number / 10000
    return number / 100000000


def extract_money_values_yi(text: str) -> list[float]:
    return [money_to_yi(value, unit) for value, unit in MONEY_PATTERN.findall(text)]


def extract_percent_values(text: str) -> list[float]:
    return [float(value) / 100 for value in PERCENT_PATTERN.findall(text)]


def keyword_flag(text: str, keywords: tuple[str, ...]) -> int:
    return int(any(keyword in text for keyword in keywords))


def keyword_count(text: str, keywords: tuple[str, ...]) -> int:
    return sum(text.count(keyword) for keyword in keywords)


def profit_direction(text: str) -> int:
    if keyword_flag(text, ("预增", "略增", "扭亏", "续盈")):
        return 1
    if keyword_flag(text, ("预减", "略减", "首亏", "续亏")):
        return -1
    positive = ("预增", "略增", "扭亏", "续盈", "增长", "增加", "盈利", "上升")
    negative = ("预减", "略减", "首亏", "续亏", "亏损", "下降", "减少", "下滑")
    if keyword_flag(text, positive) and not keyword_flag(text, negative):
        return 1
    if keyword_flag(text, negative) and not keyword_flag(text, positive):
        return -1
    return 0


def extract_profit_range_yi(text: str) -> tuple[float, float]:
    matches = PROFIT_RANGE_PATTERN.findall(text)
    if not matches:
        return np.nan, np.nan
    low, high, unit = matches[0]
    unit = unit or ("万" if max(abs(float(low)), abs(float(high))) > 1000 else "亿")
    values = sorted([money_to_yi(low, unit), money_to_yi(high, unit)])
    return values[0], values[1]


def safe_ratio(numerator: float, denominator: object) -> float:
    try:
        denom = float(denominator)
    except (TypeError, ValueError):
        return np.nan
    if not np.isfinite(denom) or denom == 0 or not np.isfinite(numerator):
        return np.nan
    return numerator / denom


def text_intensity_features(row: pd.Series) -> dict[str, float]:
    text = event_text(row)
    money_values = extract_money_values_yi(text)
    pct_values = extract_percent_values(text)
    profit_low, profit_high = extract_profit_range_yi(text)
    max_money = max(money_values) if money_values else np.nan
    pre_mv = row.get("pre_total_mv_yi")

    return {
        "evt_money_count": float(len(money_values)),
        "evt_money_max_yi": max_money,
        "evt_money_sum_yi": float(np.nansum(money_values)) if money_values else np.nan,
        "evt_money_max_to_mv": safe_ratio(max_money, pre_mv),
        "evt_percent_count": float(len(pct_values)),
        "evt_percent_max_abs": max([abs(value) for value in pct_values]) if pct_values else np.nan,
        "evt_percent_mean": float(np.mean(pct_values)) if pct_values else np.nan,
        "evt_profit_direction": float(profit_direction(text)),
        "evt_profit_low_yi": profit_low,
        "evt_profit_high_yi": profit_high,
        "evt_profit_mid_yi": float(np.nanmean([profit_low, profit_high])) if not np.isnan(profit_low) else np.nan,
        "evt_profit_mid_to_mv": safe_ratio(float(np.nanmean([profit_low, profit_high])), pre_mv)
        if not np.isnan(profit_low)
        else np.nan,
        "evt_is_forecast": keyword_flag(
            text, ("业绩预告", "预计", "预增", "预减", "略增", "略减", "首亏", "续亏", "扭亏")
        ),
        "evt_is_earnings_report": keyword_flag(
            text, ("年度报告", "季度报告", "一季报", "半年报", "三季报", "业绩快报")
        ),
        "evt_is_repurchase": keyword_flag(text, ("回购公司股份", "股份回购", "回购股份")),
        "evt_is_pledge": keyword_flag(text, ("质押", "解押", "解除质押")),
        "evt_is_restructuring": keyword_flag(text, ("重大资产重组", "发行股份购买资产", "募集配套资金")),
        "evt_is_contract_order": keyword_flag(
            text, ("中标", "订单", "框架协议", "战略合作协议", "重大合同", "签订合同")
        ),
        "evt_is_inquiry": keyword_flag(text, ("问询函", "关注函", "监管函")),
        "evt_is_litigation_penalty": keyword_flag(text, ("诉讼", "仲裁", "处罚", "立案", "违规")),
        "evt_is_impairment": keyword_flag(text, ("减值", "商誉", "计提")),
        "evt_is_subsidy": keyword_flag(text, ("补助", "补贴", "政府资助")),
        "evt_is_ir_activity": keyword_flag(text, ("投资者关系", "调研", "业绩说明会", "电话会议", "线上会议")),
        "evt_is_product_launch": keyword_flag(text, ("新产品", "量产", "认证", "发布", "AI", "车联网", "智能座舱")),
        "evt_positive_word_count": float(keyword_count(text, ("增长", "增加", "提升", "中标", "扭亏", "盈利", "高增"))),
        "evt_negative_word_count": float(
            keyword_count(text, ("亏损", "下降", "减少", "下滑", "风险", "问询", "关注函", "处罚", "减值"))
        ),
    }


def build_event_intensity_dataset() -> tuple[pd.DataFrame, pd.DataFrame]:
    dataset = read_csv(INPUT_PATH)
    rows = [text_intensity_features(row) for _, row in dataset.iterrows()]
    feature_frame = pd.DataFrame(rows)
    enhanced = pd.concat([dataset.reset_index(drop=True), feature_frame], axis=1)

    manifest = pd.DataFrame(
        [
            {
                "feature": column,
                "non_null": int(enhanced[column].notna().sum()),
                "missing_rate": float(enhanced[column].isna().mean()),
                "source_group": "event_intensity",
                "leakage_risk": "low",
            }
            for column in feature_frame.columns
        ]
    ).sort_values("feature")
    return enhanced, manifest


def write_combined_manifest(manifest: pd.DataFrame) -> None:
    previous = read_csv(PREVIOUS_MANIFEST_PATH)
    combined = pd.concat([previous, manifest], ignore_index=True)
    combined.to_csv(COMBINED_MANIFEST_PATH, index=False, encoding="utf-8-sig")


def markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    rows = ["| " + " | ".join("" if pd.isna(value) else str(value) for value in row) + " |" for row in frame.to_numpy()]
    return "\n".join([header, divider, *rows])


def write_report(enhanced: pd.DataFrame, manifest: pd.DataFrame) -> None:
    feature_summary = (
        manifest.assign(coverage=1 - manifest["missing_rate"])
        .sort_values(["coverage", "feature"], ascending=[False, True])
        .head(20)
    )
    lines = [
        "# 事件强度特征摘要",
        "",
        "## 结论",
        "",
        f"- 已生成 enhanced v2 建模宽表：{len(enhanced)} 行，{len(enhanced.columns)} 列。",
        f"- 新增事件强度数值特征 {len(manifest)} 个，来源仅限标题、摘要和事件组标题。",
        "- 未读取公告正文或 RAG chunk；特征只描述事件披露文本中的金额、百分比、方向和类型旗标。",
        "",
        "## 覆盖率较高的新增特征",
        "",
        markdown_table(feature_summary[["feature", "non_null", "missing_rate", "coverage"]]),
        "",
        "## 输出产物",
        "",
        "| 产物 | 路径 | 用途 |",
        "| --- | --- | --- |",
        f"| enhanced v2 建模宽表 | `{OUTPUT_PATH}` | 下一轮模型训练入口 |",
        f"| 事件强度 manifest | `{FEATURE_MANIFEST_PATH}` | 记录新增强度特征 |",
        f"| 合并 manifest | `{COMBINED_MANIFEST_PATH}` | 训练脚本入模特征清单 |",
        "",
        "## 使用边界",
        "",
        "- 金额和百分比来自规则抽取，适合做弱结构化信号，不等同于严格财务口径字段。",
        "- 区间净利润特征优先识别含“净利润/利润”的表达；其他数字只进入通用金额/百分比统计。",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    enhanced, manifest = build_event_intensity_dataset()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    enhanced.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    manifest.to_csv(FEATURE_MANIFEST_PATH, index=False, encoding="utf-8-sig")
    write_combined_manifest(manifest)
    write_report(enhanced, manifest)
    result = {
        "rows": len(enhanced),
        "columns": len(enhanced.columns),
        "new_numeric_features": len(manifest),
        "output": str(OUTPUT_PATH),
        "combined_manifest": str(COMBINED_MANIFEST_PATH),
        "report": str(REPORT_PATH),
    }
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
