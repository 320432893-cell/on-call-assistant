"""把候选事件级 RAG 命中增强到分析事件组和市值变化主表。"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

PROJECT_DIR = Path("market-impact-study")
PROCESSED_DIR = PROJECT_DIR / "data/processed"

DEFAULT_CANDIDATES = PROCESSED_DIR / "event_candidates_scored.csv"
DEFAULT_GROUPS = PROCESSED_DIR / "event_analysis_groups_scored.csv"
DEFAULT_RAG_SUMMARY = PROCESSED_DIR / "rag_event_evidence_summary.csv"
DEFAULT_CHUNKS = PROCESSED_DIR / "rag_notice_chunks.jsonl"
DEFAULT_OUTPUT = PROCESSED_DIR / "rag_event_group_evidence_enhanced.csv"
DEFAULT_COVERAGE = PROCESSED_DIR / "rag_event_group_evidence_coverage.csv"
DEFAULT_GAPS = PROCESSED_DIR / "rag_event_group_evidence_gaps.csv"

GROUP_COLUMNS = ["symbol", "event_date", "primary_category"]
MAX_DATE_DIFF_DAYS = 3
MAX_CHUNKS_PER_SYMBOL_DATE = 60
WEAK_CATEGORY_TERMS = {
    "业绩信号": ["业绩", "年度报告", "半年度报告", "季度报告", "业绩预告", "业绩快报", "利润", "营收"],
    "资本动作": ["回购", "分红", "权益分派", "股权激励", "员工持股", "定增", "募集资金", "减持", "增持"],
    "管理层/投关信号": ["投资者关系", "调研", "业绩说明会", "路演", "接待", "互动"],
    "产品/技术创新": ["产品", "研发", "技术", "车联网", "物联网", "AI", "卫星", "智能"],
    "客户/订单": ["客户", "订单", "中标", "合同", "合作", "项目"],
    "风险事件": ["风险", "问询函", "诉讼", "减值", "立案", "处罚", "异常波动", "退市"],
    "竞品动作": ["战略", "合作", "并购", "投资", "海外", "新产品", "客户"],
}
TITLE_STOPWORDS = {
    "公告",
    "的公告",
    "关于",
    "公司",
    "股份",
    "有限公司",
    "年度",
    "半年度",
    "季度",
    "报告",
    "全文",
    "摘要",
    "补充",
    "更正",
    "提示性",
    "进展",
}
EVENT_GROUP_FIELDS = [
    "analysis_group_id",
    "event_id",
    "company",
    "symbol",
    "event_date",
    "primary_category",
    "title",
    "source_type",
    "source_types",
    "group_event_count",
    "group_source_types",
    "group_evidence_count",
    "car_status",
    "pre_total_mv_yi",
    "actual_mv_change_yi_p0_p5",
    "actual_mv_change_yi_p0_p20",
    "actual_mv_change_yi_p0_p60",
    "actual_mv_return_p0_p5",
    "actual_mv_return_p0_p20",
    "actual_mv_return_p0_p60",
    "car_p0_p5",
    "car_p0_p20",
    "car_p0_p60",
    "abnormal_mv_impact_yi_p0_p20",
    "event_priority_score",
    "objective_change_score",
    "group_titles_sample",
]
RAG_OUTPUT_FIELDS = [
    "rag_coverage_status",
    "rag_event_count",
    "rag_evidence_hit_count",
    "rag_best_score",
    "rag_best_date_diff_days",
    "rag_best_publish_date",
    "rag_best_title",
    "rag_best_text_source",
    "rag_best_evidence_strength",
    "rag_best_pdf_url",
    "rag_best_local_path",
    "rag_best_page_start",
    "rag_evidence_refs",
    "rag_matched_event_ids",
    "rag_match_method",
    "rag_match_strength",
]
COVERAGE_FIELDS = [
    "scope",
    "company",
    "primary_category",
    "event_group_count",
    "event_group_with_rag",
    "event_group_without_rag",
    "rag_coverage_rate",
    "rag_evidence_hit_count",
    "strong_evidence_group_count",
    "auxiliary_evidence_group_count",
    "weak_evidence_group_count",
]
GAP_FIELDS = [
    "analysis_group_id",
    "company",
    "symbol",
    "event_date",
    "primary_category",
    "title",
    "source_type",
    "group_source_types",
    "event_priority_score",
    "objective_change_score",
    "actual_mv_change_yi_p0_p20",
    "title_char_len",
    "normalized_title_len",
    "same_day_chunk_count",
    "near_day_chunk_count",
    "gap_reason",
]


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str).fillna("")


def make_analysis_group_id(frame: pd.DataFrame) -> pd.Series:
    values = [frame[column].astype(str).fillna("") for column in GROUP_COLUMNS]
    return values[0] + "|" + values[1] + "|" + values[2]


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def parse_date(value: object) -> date | None:
    parsed = pd.to_datetime(str(value or ""), errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def date_diff_days(left: object, right: object) -> int | None:
    left_date = parse_date(left)
    right_date = parse_date(right)
    if left_date is None or right_date is None:
        return None
    return abs((left_date - right_date).days)


def normalize_title(value: object) -> str:
    text = re.sub(r"\s+", "", str(value or ""))
    text = re.sub(r"^[*ＳSTst日海移为通信远广和通高新兴锐明技术有方科技美格智能博实结:：]+", "", text)
    for word in TITLE_STOPWORDS:
        text = text.replace(word, "")
    return re.sub(r"[，,。；;：:（）()【】\[\]“”\"'、\-—_]", "", text)


def title_terms(*values: object) -> list[str]:
    terms: list[str] = []
    for value in values:
        for part in re.split(r"[，,。；;：:（）()【】\[\]“”\"'、\s]+", str(value or "")):
            normalized = normalize_title(part)
            if len(normalized) < 4 or normalized in terms:
                continue
            terms.append(normalized)
    return terms


def keyword_score(text: str, terms: list[str]) -> float:
    return float(sum(text.count(term) * len(term) for term in terms if term))


def compact_join(values: pd.Series, *, limit: int = 3) -> str:
    output: list[str] = []
    for value in values.astype(str):
        text = " ".join(value.split())
        if not text or text in output:
            continue
        output.append(text)
        if len(output) >= limit:
            break
    return " || ".join(output)


def chunk_haystack(chunk: dict[str, object]) -> str:
    return "\n".join(str(chunk.get(key, "")) for key in ["company", "symbol", "title", "publish_date", "text"]).replace(
        " ", ""
    )


ChunkIndex = dict[str, dict[str, list[dict[str, object]]]]


def load_chunk_index(path: Path) -> ChunkIndex:
    chunk_index: ChunkIndex = {}
    with path.open(encoding="utf-8") as file_obj:
        for line in file_obj:
            chunk = json.loads(line)
            chunk["normalized_title"] = normalize_title(chunk.get("title", ""))
            chunk["haystack"] = chunk_haystack(chunk)
            symbol = str(chunk.get("symbol", "")).strip()
            publish_date = str(chunk.get("publish_date", "")).strip()
            chunk_index.setdefault(symbol, {}).setdefault(publish_date, []).append(chunk)
    return chunk_index


def nearby_dates(value: object, max_date_diff_days: int) -> Iterable[tuple[str, int]]:
    center = parse_date(value)
    if center is None:
        return []
    output: list[tuple[str, int]] = []
    for offset in range(-max_date_diff_days, max_date_diff_days + 1):
        current = center + timedelta(days=offset)
        output.append((current.isoformat(), abs(offset)))
    return output


def candidate_chunks(
    chunk_index: ChunkIndex,
    event: pd.Series,
    *,
    max_date_diff_days: int = MAX_DATE_DIFF_DAYS,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    chunks_by_date = chunk_index.get(str(event.get("symbol", "")).strip(), {})
    for publish_date, diff_days in nearby_dates(event.get("event_date"), max_date_diff_days):
        for chunk in chunks_by_date.get(publish_date, []):
            candidates.append({**chunk, "date_diff_days": diff_days})
    return candidates[:MAX_CHUNKS_PER_SYMBOL_DATE]


def chunk_to_rag_row(chunk: dict[str, object], event: pd.Series, *, method: str, score: float) -> dict[str, object]:
    page = chunk.get("page_start", "")
    snippet = " ".join(str(chunk.get("text", "")).split())[:220]
    text_source = str(chunk.get("text_source", ""))
    evidence_strength = "strong" if text_source in {"pdf", "notice_api"} else "auxiliary"
    if method == "weak_category_date":
        evidence_strength = "weak"
    if not text_source and method in {"direct_title_date", "expanded_group_title"}:
        evidence_strength = "strong"
    return {
        "analysis_group_id": event.get("analysis_group_id", ""),
        "rag_event_count": 1,
        "rag_evidence_hit_count": 1,
        "rag_best_score": round(score, 6),
        "rag_best_date_diff_days": chunk.get("date_diff_days", ""),
        "rag_best_publish_date": chunk.get("publish_date", ""),
        "rag_best_title": chunk.get("title", ""),
        "rag_best_text_source": text_source,
        "rag_best_evidence_strength": evidence_strength,
        "rag_best_pdf_url": chunk.get("pdf_url", ""),
        "rag_best_local_path": chunk.get("local_path", ""),
        "rag_best_page_start": page,
        "rag_evidence_refs": f"{chunk.get('publish_date', '')}《{chunk.get('title', '')}》p{page}: {snippet}",
        "rag_matched_event_ids": event.get("event_id", ""),
        "rag_match_method": method,
        "rag_match_strength": evidence_strength,
    }


def best_rule_match(chunks: list[dict[str, object]], event: pd.Series) -> dict[str, object] | None:
    event_title = normalize_title(event.get("title", ""))
    group_terms = title_terms(event.get("title", ""), event.get("group_titles_sample", ""))
    category_terms = WEAK_CATEGORY_TERMS.get(str(event.get("primary_category", "")), [])
    scored: list[tuple[float, int, dict[str, object], str]] = []
    for chunk in chunks:
        chunk_title = str(chunk.get("normalized_title", ""))
        haystack = str(chunk.get("haystack", ""))
        diff_days = int(chunk.get("date_diff_days") or 999999)
        method = ""
        score = 0.0
        if event_title and (event_title in chunk_title or chunk_title in event_title):
            method = "direct_title_date"
            score = 1000 + len(event_title) * 2
        else:
            expanded_score = keyword_score(haystack, group_terms)
            category_score = keyword_score(haystack, category_terms)
            if expanded_score >= 12:
                method = "expanded_group_title"
                score = 500 + expanded_score
            elif category_score >= 8 and diff_days <= 1:
                method = "weak_category_date"
                score = 100 + category_score
        if method:
            scored.append((score, diff_days, chunk, method))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1], int(item[2].get("chunk_index") or 0)))
    score, _, chunk, method = scored[0]
    return chunk_to_rag_row(chunk, event, method=method, score=score)


def load_grouped_rag(candidates_path: Path, rag_summary_path: Path) -> pd.DataFrame:
    candidates = read_csv(candidates_path)
    rag = read_csv(rag_summary_path)
    candidates["analysis_group_id"] = make_analysis_group_id(candidates)
    mapped = rag.merge(
        candidates[["event_id", "analysis_group_id"]],
        left_on="event_candidate_id",
        right_on="event_id",
        how="left",
    )
    mapped = mapped[mapped["analysis_group_id"].astype(bool)].copy()
    if mapped.empty:
        return pd.DataFrame(columns=["analysis_group_id", *RAG_OUTPUT_FIELDS[1:]])

    mapped["evidence_count_num"] = numeric(mapped["evidence_count"]).fillna(0)
    mapped["best_score_num"] = numeric(mapped["best_score"]).fillna(0)
    mapped["best_date_diff_days_num"] = numeric(mapped["best_date_diff_days"]).fillna(999999)
    rows: list[dict[str, object]] = []
    for group_id, group in mapped.groupby("analysis_group_id", sort=False):
        sorted_group = group.sort_values(
            ["best_date_diff_days_num", "best_score_num", "evidence_count_num"],
            ascending=[True, False, False],
        )
        best = sorted_group.iloc[0]
        rows.append(
            {
                "analysis_group_id": group_id,
                "rag_event_count": group["event_candidate_id"].nunique(),
                "rag_evidence_hit_count": int(group["evidence_count_num"].sum()),
                "rag_best_score": best.get("best_score", ""),
                "rag_best_date_diff_days": best.get("best_date_diff_days", ""),
                "rag_best_publish_date": best.get("best_publish_date", ""),
                "rag_best_title": best.get("best_title", ""),
                "rag_best_text_source": "",
                "rag_best_evidence_strength": "strong",
                "rag_best_pdf_url": best.get("best_pdf_url", ""),
                "rag_best_local_path": best.get("best_local_path", ""),
                "rag_best_page_start": best.get("best_page_start", ""),
                "rag_evidence_refs": compact_join(sorted_group["evidence_refs"], limit=3),
                "rag_matched_event_ids": compact_join(sorted_group["event_candidate_id"], limit=8),
                "rag_match_method": "existing_summary",
                "rag_match_strength": "strong",
            }
        )
    return pd.DataFrame(rows)


def build_rule_enhancements(groups: pd.DataFrame, chunks_path: Path) -> pd.DataFrame:
    chunk_index = load_chunk_index(chunks_path)
    rows: list[dict[str, object]] = []
    missing = groups[groups["rag_evidence_hit_count"].fillna(0).astype(float) <= 0]
    for _, event in missing.iterrows():
        match = best_rule_match(candidate_chunks(chunk_index, event), event)
        if match:
            rows.append(match)
    return pd.DataFrame(rows)


def build_enhanced_table(
    groups_path: Path,
    candidates_path: Path,
    rag_summary_path: Path,
    chunks_path: Path = DEFAULT_CHUNKS,
) -> pd.DataFrame:
    groups = read_csv(groups_path)
    if "analysis_group_id" not in groups.columns:
        groups["analysis_group_id"] = make_analysis_group_id(groups)
    rag_grouped = load_grouped_rag(candidates_path, rag_summary_path)
    enhanced = groups.merge(rag_grouped, on="analysis_group_id", how="left")
    enhanced["rag_evidence_hit_count"] = numeric(
        enhanced.get("rag_evidence_hit_count", pd.Series(dtype=object))
    ).fillna(0)
    enhanced["rag_event_count"] = numeric(enhanced.get("rag_event_count", pd.Series(dtype=object))).fillna(0)
    enhanced["rag_coverage_status"] = enhanced["rag_evidence_hit_count"].map(
        lambda value: "has_rag_evidence" if value > 0 else "no_rag_evidence"
    )
    rule_enhancements = build_rule_enhancements(enhanced, chunks_path)
    if not rule_enhancements.empty:
        enhanced = enhanced.merge(rule_enhancements, on="analysis_group_id", how="left", suffixes=("", "_rule"))
        has_rule = enhanced["rag_evidence_hit_count_rule"].notna()
        for column in RAG_OUTPUT_FIELDS:
            rule_column = f"{column}_rule"
            if rule_column in enhanced.columns:
                enhanced[column] = enhanced[column].astype(object)
                enhanced.loc[has_rule, column] = enhanced.loc[has_rule, rule_column].astype(object)
                enhanced = enhanced.drop(columns=[rule_column])
        enhanced.loc[has_rule, "rag_coverage_status"] = "has_rule_enhanced_evidence"
    for column in RAG_OUTPUT_FIELDS:
        if column not in enhanced.columns:
            enhanced[column] = ""
    output_fields = [field for field in EVENT_GROUP_FIELDS if field in enhanced.columns] + RAG_OUTPUT_FIELDS
    return enhanced[output_fields]


def build_coverage(enhanced: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if "rag_best_evidence_strength" not in enhanced.columns:
        enhanced = enhanced.copy()
        enhanced["rag_best_evidence_strength"] = enhanced["rag_evidence_hit_count"].map(
            lambda value: "strong" if float(value or 0) > 0 else ""
        )
    dimensions = [
        ("overall", []),
        ("company", ["company"]),
        ("primary_category", ["primary_category"]),
        ("company_category", ["company", "primary_category"]),
    ]
    for scope, columns in dimensions:
        grouped = [((), enhanced)] if not columns else enhanced.groupby(columns, dropna=False, sort=True)
        for key, group in grouped:
            key_values = key if isinstance(key, tuple) else (key,)
            total = len(group)
            with_rag = int((numeric(group["rag_evidence_hit_count"]).fillna(0) > 0).sum())
            row = {
                "scope": scope,
                "company": "",
                "primary_category": "",
                "event_group_count": total,
                "event_group_with_rag": with_rag,
                "event_group_without_rag": total - with_rag,
                "rag_coverage_rate": round(with_rag / total, 6) if total else 0,
                "rag_evidence_hit_count": int(numeric(group["rag_evidence_hit_count"]).fillna(0).sum()),
                "strong_evidence_group_count": int((group["rag_best_evidence_strength"] == "strong").sum()),
                "auxiliary_evidence_group_count": int((group["rag_best_evidence_strength"] == "auxiliary").sum()),
                "weak_evidence_group_count": int((group["rag_best_evidence_strength"] == "weak").sum()),
            }
            row.update(dict(zip(columns, key_values, strict=False)))
            rows.append(row)
    return pd.DataFrame(rows, columns=COVERAGE_FIELDS)


def build_gaps(enhanced: pd.DataFrame, chunks_path: Path = DEFAULT_CHUNKS) -> pd.DataFrame:
    chunk_index = load_chunk_index(chunks_path)
    rows: list[dict[str, object]] = []
    missing = enhanced[enhanced["rag_evidence_hit_count"].fillna(0).astype(float) <= 0].copy()
    missing["priority_num"] = numeric(missing.get("event_priority_score", pd.Series(dtype=object))).fillna(0)
    missing = missing.sort_values("priority_num", ascending=False)
    for _, event in missing.iterrows():
        near_chunks = candidate_chunks(chunk_index, event)
        same_day = [chunk for chunk in near_chunks if int(chunk.get("date_diff_days") or 999999) == 0]
        normalized = normalize_title(event.get("title", ""))
        if not near_chunks:
            reason = "no_nearby_chunks"
        elif len(normalized) < 4:
            reason = "short_or_template_title"
        elif str(event.get("primary_category", "")) == "其他":
            reason = "weak_category_terms"
        else:
            reason = "title_terms_not_matched"
        rows.append(
            {
                "analysis_group_id": event.get("analysis_group_id", ""),
                "company": event.get("company", ""),
                "symbol": event.get("symbol", ""),
                "event_date": event.get("event_date", ""),
                "primary_category": event.get("primary_category", ""),
                "title": event.get("title", ""),
                "source_type": event.get("source_type", ""),
                "group_source_types": event.get("group_source_types", ""),
                "event_priority_score": event.get("event_priority_score", ""),
                "objective_change_score": event.get("objective_change_score", ""),
                "actual_mv_change_yi_p0_p20": event.get("actual_mv_change_yi_p0_p20", ""),
                "title_char_len": len(str(event.get("title", ""))),
                "normalized_title_len": len(normalized),
                "same_day_chunk_count": len(same_day),
                "near_day_chunk_count": len(near_chunks),
                "gap_reason": reason,
            }
        )
    return pd.DataFrame(rows, columns=GAP_FIELDS)


def main() -> int:
    enhanced = build_enhanced_table(DEFAULT_GROUPS, DEFAULT_CANDIDATES, DEFAULT_RAG_SUMMARY)
    coverage = build_coverage(enhanced)
    gaps = build_gaps(enhanced)
    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    enhanced.to_csv(DEFAULT_OUTPUT, index=False, encoding="utf-8-sig")
    coverage.to_csv(DEFAULT_COVERAGE, index=False, encoding="utf-8-sig")
    gaps.to_csv(DEFAULT_GAPS, index=False, encoding="utf-8-sig")
    print(f"wrote {DEFAULT_OUTPUT} rows={len(enhanced)}")
    print(f"wrote {DEFAULT_COVERAGE} rows={len(coverage)}")
    print(f"wrote {DEFAULT_GAPS} rows={len(gaps)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
