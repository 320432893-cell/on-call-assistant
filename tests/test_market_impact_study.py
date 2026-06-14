# 生命周期：持久维护
# 覆盖的业务场景：市场影响研究辅助函数的日期清洗、事件分类、CAR 窗口、RAG 证据、ML SSOT 和建模样本规则回归。
# 依赖的服务/环境：本地 Python、pandas、market-impact-study 下的脚本文件；不依赖外部网络和远程服务。
# 运行方式：uv run pytest tests/test_market_impact_study.py
# oracle 输出形状：pytest 断言失败给出期望/实际差异；业务步骤用例名描述场景，pytest 汇总用时。
"""Focused tests for market-impact study helper functions."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MARKET_DIR = ROOT / "market-impact-study"


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, MARKET_DIR / filename)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


calculate_event_car = load_module("calculate_event_car", "calculate_event_car.py")
build_event_candidates = load_module("build_event_candidates", "build_event_candidates.py")
validate_market_outputs = load_module("validate_market_outputs", "validate_market_outputs.py")
build_management_signal_tables = load_module("build_management_signal_tables", "build_management_signal_tables.py")
build_rag_text_source_manifest = load_module("build_rag_text_source_manifest", "build_rag_text_source_manifest.py")
extract_rag_notice_texts = load_module("extract_rag_notice_texts", "extract_rag_notice_texts.py")
enrich_rag_query = load_module("enrich_rag_query", "enrich_rag_query.py")
compare_rag_chunk_experiments = load_module("compare_rag_chunk_experiments", "compare_rag_chunk_experiments.py")
build_rag_event_group_evidence = load_module("build_rag_event_group_evidence", "build_rag_event_group_evidence.py")
build_ml_readiness_tables = load_module("build_ml_readiness_tables", "build_ml_readiness_tables.py")
build_ml_ssot_tables = load_module("build_ml_ssot_tables", "build_ml_ssot_tables.py")
build_data_governance_tables = load_module("build_data_governance_tables", "build_data_governance_tables.py")
build_modeling_assets = load_module("build_modeling_assets", "build_modeling_assets.py")
apply_manual_review_overlay = load_module("apply_manual_review_overlay", "apply_manual_review_overlay.py")
train_baseline_models = load_module("train_baseline_models", "train_baseline_models.py")
build_event_intensity_features = load_module("build_event_intensity_features", "build_event_intensity_features.py")
analyze_sample_predictability = load_module("analyze_sample_predictability", "analyze_sample_predictability.py")


def test_normalize_date_handles_common_public_source_formats():
    assert build_event_candidates.normalize_date("20260518") == "2026-05-18"
    assert build_event_candidates.normalize_date("2026/5/8") == "2026-05-08"
    assert build_event_candidates.normalize_date("2026年5月8日 18:00") == "2026-05-08"
    assert build_event_candidates.normalize_date("") == ""


def test_event_title_classifiers_identify_excluded_market_mechanics():
    assert calculate_event_car.is_ipo_listing_related("首次公开发行股票并在创业板上市公告书")
    assert calculate_event_car.is_market_trading_related("股票交易异常波动公告")
    assert not calculate_event_car.is_market_trading_related("关于签署战略合作协议的公告")


def test_window_sum_clips_to_available_trading_days():
    stock = pd.DataFrame({"abret_peer": [0.01, 0.02, -0.01]})
    value, actual, expected = calculate_event_car.window_sum(stock, pos=1, start=0, end=5, column="abret_peer")
    assert round(value, 6) == 0.01
    assert actual == 2
    assert expected == 6


def test_build_window_metrics_peer_rank_and_average():
    panel = pd.DataFrame(
        {
            "ts_code": ["A", "A", "B", "B", "C", "C"],
            "trade_dt": pd.to_datetime(
                ["2026-01-01", "2026-01-02", "2026-01-01", "2026-01-02", "2026-01-01", "2026-01-02"]
            ),
            "total_mv": [100.0, 110.0, 100.0, 90.0, 100.0, 105.0],
        }
    )
    metrics = calculate_event_car.build_window_metrics(panel)
    metric = metrics[("A", pd.Timestamp("2026-01-01"), "p0_p5")]
    assert metric["rank"] == 1
    assert metric["total"] == 3
    assert round(metric["peer_avg_return"], 6) == -0.025


def test_validation_window_sum_matches_calculation_helper():
    stock = pd.DataFrame({"abret_peer": [0.03, -0.01, 0.02]})
    value, actual, expected = validate_market_outputs.window_sum(stock, 0, 0, 2, "abret_peer")
    assert round(value, 6) == 0.04
    assert actual == 3
    assert expected == 3


def test_management_signal_topics_and_group_detect_ir_question():
    topics = build_management_signal_tables.detect_topics("董秘您好，公司海外订单和AI车联网产品进展如何？")
    assert "互动问答" in topics
    assert "客户订单" in topics
    assert "产品技术" in topics
    assert build_management_signal_tables.signal_group("irm_qa", "管理层/投关信号", topics) == "互动问答"


def test_management_coverage_assessment_flags_recent_only_sources():
    status, limitation, recommendation = build_management_signal_tables.coverage_assessment(
        "eastmoney_ir", 10, "2025-01-01", "2025-12-31"
    )
    assert status == "部分覆盖"
    assert "上市以来" in limitation
    assert "补采" in recommendation


def test_management_signal_id_is_stable():
    first = build_management_signal_tables.make_signal_id("irm_qa", "移为通信", "2026-05-19", "订单情况")
    second = build_management_signal_tables.make_signal_id("irm_qa", "移为通信", "2026-05-19", "订单情况")
    assert first == second
    assert first.startswith("irm_qa:")


def test_management_market_alignment_marks_pre_listing():
    result = build_management_signal_tables.align_market_metrics(
        {},
        pd.DataFrame({"ts_code": ["300590.SZ"], "trade_dt": pd.to_datetime(["2017-01-11"])}),
        {"300590.SZ": "2017-01-11"},
        "300590.SZ",
        "2016-12-30",
    )
    assert result["market_response_status"] == "pre_listing"


def test_management_ir_date_prefers_disclosure_date(tmp_path, monkeypatch):
    source = tmp_path / "all_companies_ir.csv"
    source.write_text(
        "LOCAL_COMPANY_NAME,NOTICE_DATE,END_DATE,RECEIVE_START_DATE,EITIME,RECEIVE_WAY_EXPLAIN,"
        "RECEIVE_TIME_EXPLAIN,RECEIVE_OBJECT,RECEIVE_PLACE,NUMBERNEW,NUM,RECEPTIONIST\n"
        "移为通信,2026-05-20 00:00:00,2026-05-18 00:00:00,2026-05-18 00:00:00,"
        "2026-05-21 01:00:00,业绩说明会,15:00,投资者,线上,3,3,董秘\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(build_management_signal_tables, "EASTMONEY_IR_DIR", tmp_path)
    records = build_management_signal_tables.records_from_eastmoney_ir({}, pd.DataFrame(), {})
    assert records[0]["event_date"] == "2026-05-20"
    assert records[0]["occurred_date"] == "2026-05-18"
    assert records[0]["disclosed_date"] == "2026-05-20"
    assert records[0]["date_basis"] == "disclosed_date"


def test_rag_event_group_id_matches_car_grouping():
    frame = pd.DataFrame(
        {
            "symbol": ["300590"],
            "event_date": ["2026-05-20"],
            "primary_category": ["管理层/投关信号"],
        }
    )
    group_id = build_rag_event_group_evidence.make_analysis_group_id(frame)
    assert group_id.iloc[0] == "300590|2026-05-20|管理层/投关信号"


def test_rag_coverage_rollup_counts_groups_with_evidence():
    enhanced = pd.DataFrame(
        {
            "company": ["移为通信", "移为通信", "广和通"],
            "primary_category": ["业绩信号", "风险事件", "业绩信号"],
            "rag_evidence_hit_count": [2, 0, 3],
        }
    )
    coverage = build_rag_event_group_evidence.build_coverage(enhanced)
    overall = coverage[coverage["scope"] == "overall"].iloc[0]
    assert overall["event_group_count"] == 3
    assert overall["event_group_with_rag"] == 2
    assert overall["event_group_without_rag"] == 1


def test_rag_rule_match_prefers_direct_same_day_title():
    event = pd.Series(
        {
            "analysis_group_id": "300590|2026-05-20|资本动作",
            "event_id": "event-1",
            "event_date": "2026-05-20",
            "title": "关于以集中竞价交易方式回购公司股份的公告",
            "group_titles_sample": "关于回购公司股份的公告",
            "primary_category": "资本动作",
        }
    )
    chunks = [
        {
            "title": "移为通信:关于以集中竞价交易方式回购公司股份的公告",
            "normalized_title": build_rag_event_group_evidence.normalize_title(
                "关于以集中竞价交易方式回购公司股份的公告"
            ),
            "haystack": "移为通信关于以集中竞价交易方式回购公司股份的公告",
            "publish_date": "2026-05-20",
            "page_start": 1,
            "text": "公司拟以集中竞价交易方式回购公司股份。",
            "pdf_url": "https://example.com/a.pdf",
            "local_path": "a.pdf",
            "date_diff_days": 0,
            "chunk_index": 1,
        }
    ]
    match = build_rag_event_group_evidence.best_rule_match(chunks, event)
    assert match is not None
    assert match["rag_match_method"] == "direct_title_date"
    assert match["rag_match_strength"] == "strong"


def test_rag_text_source_manifest_skips_notice_api_when_pdf_exists(tmp_path):
    pdf_path = tmp_path / "AN202605151822350865.pdf"
    pdf_path.write_bytes(b"%PDF-1.7")
    events = [
        {
            "event_id": "event-1",
            "company": "移为通信",
            "symbol": "300590",
            "event_date": "2026-05-15",
            "source_type": "announcement",
            "title": "投资者关系管理信息",
            "source_url": "https://data.eastmoney.com/notices/detail/300590/AN202605151822350865.html",
        },
        {
            "event_id": "event-2",
            "company": "移为通信",
            "symbol": "300590",
            "event_date": "2026-05-19",
            "source_type": "irm_qa",
            "title": "订单是否饱满",
            "summary": "目前在手订单饱满。",
        },
    ]
    pdf_manifest = [
        {
            "company": "移为通信",
            "symbol": "300590",
            "announcement_code": "AN202605151822350865",
            "title": "投资者关系管理信息",
            "notice_date": "2026-05-15",
            "source_url": "https://data.eastmoney.com/notices/detail/300590/AN202605151822350865.html",
            "pdf_url": "https://pdf.dfcfw.com/pdf/H2_AN202605151822350865_1.pdf",
            "local_path": str(pdf_path),
            "status": "ok",
        }
    ]
    rows, stats = build_rag_text_source_manifest.build_manifest(events, pdf_manifest)

    assert stats["pdf_rows"] == 1
    assert stats["notice_api_rows"] == 0
    assert stats["structured_rows"] == 1
    assert [row["text_source"] for row in rows] == ["pdf", "irm_qa"]
    assert rows[1]["evidence_strength"] == "auxiliary"


def test_structured_rag_chunks_preserve_source_and_strength():
    rows = [
        {
            "document_id": "irm_qa:300590:event-2",
            "company": "移为通信",
            "symbol": "300590",
            "source_type": "irm_qa",
            "title": "订单是否饱满",
            "publish_date": "2026-05-19",
            "source_text": (
                "标题：订单是否饱满\n摘要：目前在手订单饱满，产能能够满足业务交付需求。"
                "传统业务领域需求保持稳健，其他市场产品反馈良好，公司可动态调整订单分配。"
                "公司生产环节采用委外加工形式，国内外均布局生产基地，产能结构与订单规模匹配。"
            ),
            "text_source": "irm_qa",
            "evidence_strength": "auxiliary",
            "event_candidate_id": "event-2",
        }
    ]
    chunks, stats = extract_rag_notice_texts.extract_chunks(rows)

    assert stats["documents_structured_text"] == 1
    assert chunks[0]["text_source"] == "irm_qa"
    assert chunks[0]["evidence_strength"] == "auxiliary"
    assert chunks[0]["event_candidate_id"] == "event-2"


def test_rag_experiment_chunks_add_prefix_and_keep_metadata():
    rows = [
        {
            "document_id": "irm_qa:300590:event-2",
            "company": "移为通信",
            "symbol": "300590",
            "source_type": "irm_qa",
            "title": "订单是否饱满",
            "publish_date": "2026-05-19",
            "source_text": (
                "标题：订单是否饱满\n摘要：目前在手订单饱满，产能能够满足业务交付需求。"
                "传统业务领域需求保持稳健，其他市场产品反馈良好，公司可动态调整订单分配。"
                "公司生产环节采用委外加工形式，国内外均布局生产基地，产能结构与订单规模匹配。"
            ),
            "text_source": "irm_qa",
            "evidence_strength": "auxiliary",
            "event_candidate_id": "event-2",
        }
    ]
    chunks, stats = extract_rag_notice_texts.extract_experiment_chunks(rows, max_chars=120, overlap=40)

    assert stats["documents_structured_text"] == 1
    assert len(chunks) >= 2
    assert chunks[0]["has_prefix"] == "1"
    assert chunks[0]["preprocess"] == "enhanced"
    assert chunks[0]["text"].startswith("公司：移为通信")
    assert chunks[0]["text"].count("标题：订单是否饱满") == 1


def test_enhanced_clean_text_removes_complete_legal_boilerplate():
    text = (
        "本公司及董事会全体成员保证信息披露内容的真实、准确和完整，没有虚假记载、\n"
        "误导性陈述或者重大遗漏。\n"
        "日海智能科技股份有限公司收到深圳证券交易所问询函。"
    )

    cleaned = extract_rag_notice_texts.enhanced_clean_text(text)

    assert "虚假记载" not in cleaned
    assert "误导性陈述" not in cleaned
    assert "重大遗漏" not in cleaned
    assert "问询函" in cleaned


def test_rag_query_enrichment_expands_company_intent_and_metrics():
    result = enrich_rag_query.enrich_query("移为回购市场反应如何")

    assert "移为通信" in result["companies"]
    assert "回购" in result["intents"]
    assert "300590" in result["expanded_query"]
    assert "股份回购" in result["expanded_query"]
    assert "市值变化" in result["expanded_query"]
    assert result["filters"]["symbol"] == ["300590"]


def test_rag_chunk_experiment_summary_reports_growth():
    chunks = [
        {"text": "公司：移为通信 正文：回购事项", "n_chars": 18, "document_id": "doc-1"},
        {"text": "后续市场反应", "n_chars": 6, "document_id": "doc-1"},
    ]
    stats = {"input_rows": 1, "documents_with_chunks": 1, "documents_failed": 0}
    strategy = {
        "strategy": "enhanced_prefix_1200_240",
        "preprocess": "enhanced",
        "has_prefix": True,
        "max_chars": 1200,
        "overlap": 240,
    }

    summary = compare_rag_chunk_experiments.chunk_summary(strategy, stats, chunks)

    assert summary["chunks"] == 2
    assert summary["total_chars"] == 24
    assert summary["chunks_per_document"] == 2
    assert summary["has_prefix"] == "1"


def test_rag_rule_match_marks_structured_sources_as_auxiliary():
    event = pd.Series(
        {
            "analysis_group_id": "300590|2026-05-19|管理层/投关信号",
            "event_id": "event-2",
            "event_date": "2026-05-19",
            "title": "订单是否饱满",
            "group_titles_sample": "订单是否饱满",
            "primary_category": "管理层/投关信号",
        }
    )
    chunks = [
        {
            "title": "订单是否饱满",
            "normalized_title": build_rag_event_group_evidence.normalize_title("订单是否饱满"),
            "haystack": "订单是否饱满目前在手订单饱满投资者互动",
            "publish_date": "2026-05-19",
            "page_start": "",
            "text": "目前在手订单饱满，产能能够满足业务交付需求。",
            "pdf_url": "",
            "local_path": "",
            "date_diff_days": 0,
            "chunk_index": 1,
            "text_source": "irm_qa",
        }
    ]
    match = build_rag_event_group_evidence.best_rule_match(chunks, event)

    assert match is not None
    assert match["rag_best_text_source"] == "irm_qa"
    assert match["rag_best_evidence_strength"] == "auxiliary"
    assert match["rag_match_strength"] == "auxiliary"


def test_capital_action_subtype_avoids_false_share_repurchase():
    assert (
        build_ml_readiness_tables.classify_capital_action_subtype(
            {"title": "关于以集中竞价交易方式回购公司股份的进展公告"}
        )
        == "股份回购"
    )
    assert (
        build_ml_readiness_tables.classify_capital_action_subtype({"title": "关于控股股东进行质押式回购交易的公告"})
        == "股权质押/解押"
    )
    assert (
        build_ml_readiness_tables.classify_capital_action_subtype(
            {"title": "关于回购注销部分限制性股票暨通知债权人的公告"}
        )
        == "股权激励/员工持股"
    )


def test_same_company_overlap_marks_short_window_contamination():
    events = pd.DataFrame(
        {
            "ts_code": ["300590.SZ", "300590.SZ", "300590.SZ", "300638.SZ"],
            "aligned_trade_date": ["2026-01-02", "2026-01-05", "2026-01-20", "2026-01-03"],
            "pre_trade_date": ["2026-01-01", "2026-01-02", "2026-01-19", "2026-01-02"],
            "end_trade_date_m1_p1": ["2026-01-05", "2026-01-06", "2026-01-21", "2026-01-04"],
            "end_trade_date_p0_p5": ["2026-01-09", "2026-01-12", "2026-01-27", "2026-01-10"],
            "end_trade_date_p0_p20": ["2026-02-01", "2026-02-04", "2026-02-19", "2026-02-03"],
            "end_trade_date_p0_p60": ["2026-04-01", "2026-04-04", "2026-04-19", "2026-04-03"],
            "primary_category": ["资本动作", "业绩信号", "风险事件", "资本动作"],
            "title": ["回购公告", "业绩预告", "风险提示", "定增公告"],
        }
    )

    result = build_ml_readiness_tables.add_same_company_overlap(events)

    assert result.loc[0, "overlap_event_count_p0_p5"] == 1
    assert result.loc[0, "overlap_categories_p0_p5"] == "业绩信号"
    assert not result.loc[0, "is_overlap_clean_p0_p5"]
    assert result.loc[2, "overlap_event_count_p0_p5"] == 0
    assert result.loc[2, "is_overlap_clean_p0_p5"]


def test_ml_ssot_split_policy_uses_time_order_and_excludes_unlabeled():
    assert build_ml_ssot_tables.split_by_event_date("2022-12-31", "ok")[0] == "train"
    assert build_ml_ssot_tables.split_by_event_date("2023-06-01", "ok")[0] == "valid"
    assert build_ml_ssot_tables.split_by_event_date("2024-01-01", "ok")[0] == "test"
    assert build_ml_ssot_tables.split_by_event_date("2024-01-01", "pre_listing")[0] == "excluded_unlabeled"


def test_ml_ssot_relative_reaction_label_has_neutral_band():
    assert build_ml_ssot_tables.relative_reaction_label(0.021) == "positive_revaluation"
    assert build_ml_ssot_tables.relative_reaction_label(-0.021) == "negative_shock"
    assert build_ml_ssot_tables.relative_reaction_label(0.0) == "neutral"


def test_ml_ssot_text_signal_features_are_interpretable_counts():
    features = build_ml_ssot_tables.text_signal_features("公司订单增长20%，投资者调研关注车联网产品风险")
    assert features["text_percent_count"] == 1
    assert features["text_has_growth_keyword"] == 1
    assert features["text_has_ir_keyword"] == 1
    assert features["text_has_tech_keyword"] == 1


def test_data_governance_sample_policy_splits_main_clean_and_overlap_cases():
    clean_row = pd.Series(
        {
            "has_main_label": 1,
            "is_ipo_listing_related": "0",
            "is_market_trading_related": "0",
            "is_default_training_candidate": 1,
            "is_clean_p0_p20": 1,
            "overlap_event_count_p0_p20": 0,
        }
    )
    dirty_row = clean_row.copy()
    dirty_row["is_clean_p0_p20"] = 0
    dirty_row["overlap_event_count_p0_p20"] = 3
    missing_label = clean_row.copy()
    missing_label["has_main_label"] = 0

    assert build_data_governance_tables.sample_policy_for(clean_row)[0] == "main_clean_sensitivity"
    assert build_data_governance_tables.sample_policy_for(dirty_row)[0] == "robustness_or_case"
    assert build_data_governance_tables.sample_policy_for(missing_label)[0] == "exclude_from_model"


def test_data_governance_review_action_prioritizes_other_category():
    row = pd.Series(
        {
            "primary_category": "其他",
            "title": "关于业务进展的公告",
            "group_titles_sample": "",
            "is_ipo_listing_related": "0",
            "is_market_trading_related": "0",
            "overlap_event_count_p0_p20": 0,
            "relative_mv_return_p0_p20": 0.01,
        }
    )

    assert build_data_governance_tables.suggested_action(row) == "优先人工重分类"


def test_data_governance_review_action_excludes_trading_mechanics_title():
    row = pd.Series(
        {
            "primary_category": "其他",
            "title": "股票交易异常波动公告",
            "group_titles_sample": "",
            "is_ipo_listing_related": "0",
            "is_market_trading_related": "0",
            "overlap_event_count_p0_p20": 0,
            "relative_mv_return_p0_p20": 0.01,
        }
    )

    assert build_data_governance_tables.suggested_action(row) == "排除默认建模，保留为审计/案例"


def test_modeling_assets_join_ssot_and_policy_without_row_loss():
    tables = {
        "event": pd.DataFrame(
            {
                "analysis_group_id": ["a", "b"],
                "event_date": ["2023-01-01", "2024-01-01"],
                "company": ["A", "B"],
            }
        ),
        "label": pd.DataFrame(
            {
                "analysis_group_id": ["a", "b"],
                "event_date": ["2023-01-01", "2024-01-01"],
                "car_status": ["ok", "ok"],
                "relative_mv_return_p0_p20": [0.1, -0.1],
            }
        ),
        "feature": pd.DataFrame(
            {
                "analysis_group_id": ["a", "b"],
                "event_date": ["2023-01-01", "2024-01-01"],
                "as_of_date": ["2023-01-01", "2024-01-01"],
                "source_count": [1, 2],
            }
        ),
        "split": pd.DataFrame(
            {
                "analysis_group_id": ["a", "b"],
                "event_date": ["2023-01-01", "2024-01-01"],
                "split": ["valid", "test"],
            }
        ),
        "sample_policy": pd.DataFrame(
            {
                "analysis_group_id": ["a", "b"],
                "sample_policy": ["main_model_with_overlap_flag", "main_clean_sensitivity"],
                "policy_reason": ["轻度重叠", "clean"],
            }
        ),
    }

    dataset = build_modeling_assets.build_modeling_dataset(tables)

    assert len(dataset) == 2
    assert "relative_mv_return_p0_p20" in dataset.columns
    assert set(dataset["modeling_scope"]) == {"main", "clean_sensitivity"}


def test_modeling_assets_histogram_bins_counts_values():
    result = build_modeling_assets.histogram_bins(pd.Series([0.1, 0.2, 0.3, None]), bins=3)

    assert int(result["count"].sum()) == 3


def test_manual_review_overlay_translates_numeric_codes():
    review = pd.DataFrame(
        {
            "review_rank": [1, 2],
            "analysis_group_id": ["a", "b"],
            "company": ["A", "B"],
            "symbol": ["1", "2"],
            "event_date": ["2024-01-01", "2024-01-02"],
            "title": ["股票交易异常波动公告", "回购股份方案"],
            "primary_category": ["其他", "其他"],
            "keep_code": [0, 1],
            "noise_code": [1, 0],
            "category_code": [8, 2],
            "confidence_code": [1, 2],
            "note_code": [0, 1],
        }
    )

    overlay = apply_manual_review_overlay.build_overlay(apply_manual_review_overlay.normalize_code_columns(review))

    assert overlay.loc[0, "manual_review_status"] == "noise"
    assert overlay.loc[0, "manual_corrected_category"] == "交易机制/IPO"
    assert overlay.loc[1, "manual_review_status"] == "reclassified"
    assert overlay.loc[1, "manual_corrected_category"] == "资本动作"


def test_manual_review_keep_one_does_not_promote_dirty_scope_to_main():
    modeling = pd.DataFrame(
        {
            "analysis_group_id": ["a", "b", "c"],
            "primary_category": ["其他", "资本动作", "业绩信号"],
            "modeling_scope": ["robustness_or_case", "main", "robustness_or_case"],
        }
    )
    overlay = pd.DataFrame(
        {
            "analysis_group_id": ["a", "b"],
            "manual_review_status": ["reclassified", "noise"],
            "manual_keep_for_model": [1, 0],
            "manual_is_noise": [0, 1],
            "manual_corrected_category": ["资本动作", "交易机制/IPO"],
            "manual_confidence": ["很确定", "很确定"],
            "manual_note_label": ["无特殊备注", "无特殊备注"],
            "manual_reviewer": ["user", "user"],
            "manual_review_date": ["2026-06-14", "2026-06-14"],
        }
    )

    dataset = apply_manual_review_overlay.build_reviewed_modeling_dataset(modeling, overlay)

    assert dataset.loc[dataset["analysis_group_id"] == "a", "reviewed_modeling_scope"].item() == "robustness_or_case"
    assert dataset.loc[dataset["analysis_group_id"] == "b", "reviewed_modeling_scope"].item() == "case_or_audit_only"
    assert dataset.loc[dataset["analysis_group_id"] == "c", "reviewed_modeling_scope"].item() == "robustness_or_case"


def test_baseline_feature_columns_exclude_post_event_fields():
    dataset = pd.DataFrame(
        {
            "analysis_group_id": ["a"],
            "event_date": ["2024-01-01"],
            "as_of_date": ["2024-01-01"],
            "source_count": [1],
            "relative_mv_return_p0_p20": [0.1],
            "car_p0_p20": [0.2],
        }
    )
    dictionary = pd.DataFrame(
        {
            "table": ["feature_master", "feature_master"],
            "column": ["source_count", "car_p0_p20"],
            "leakage_risk": ["low", "target"],
        }
    )

    columns = train_baseline_models.feature_columns(dataset, dictionary)

    assert columns == ["source_count"]


def test_baseline_feature_columns_exclude_raw_scale_enhanced_fields():
    dataset = pd.DataFrame(
        {
            "analysis_group_id": ["a"],
            "source_count": [1],
            "bal_total_assets": [1000000000.0],
            "bal_current_ratio": [1.5],
        }
    )
    dictionary = pd.DataFrame(
        {
            "table": ["feature_master"],
            "column": ["source_count"],
            "leakage_risk": ["low"],
        }
    )
    manifest = pd.DataFrame(
        {
            "feature": ["bal_total_assets", "bal_current_ratio"],
            "source_group": ["financial", "financial"],
            "leakage_risk": ["low", "low"],
        }
    )

    columns = train_baseline_models.feature_columns(dataset, dictionary, manifest)

    assert columns == ["source_count", "bal_current_ratio"]


def test_quantile_clipper_learns_bounds_from_fit_data():
    clipper = train_baseline_models.QuantileClipper(lower=0.25, upper=0.75)
    clipper.fit(pd.DataFrame({"x": [0.0, 10.0, 20.0, 30.0]}))

    result = clipper.transform(pd.DataFrame({"x": [-100.0, 15.0, 100.0]}))

    assert result[:, 0].tolist() == [7.5, 15.0, 22.5]


def test_event_intensity_extracts_profit_and_money_scale():
    row = pd.Series(
        {
            "title": "预增 预计净利润11200-14200万",
            "summary": "公司拟回购股份，金额不低于1亿元且不超过2亿元。",
            "group_titles_sample": "2024年度业绩预告",
            "pre_total_mv_yi": 100.0,
        }
    )

    features = build_event_intensity_features.text_intensity_features(row)

    assert features["evt_profit_direction"] == 1.0
    assert features["evt_profit_low_yi"] == 1.12
    assert features["evt_profit_high_yi"] == 1.42
    assert features["evt_money_max_yi"] == 2.0
    assert features["evt_money_max_to_mv"] == 0.02
    assert features["evt_is_repurchase"] == 1


def test_event_intensity_handles_first_loss_and_avoids_contract_false_positive():
    row = pd.Series(
        {
            "title": "首亏 预计净利润-119000~-118500万",
            "summary": "关于签署资产管理合同的公告",
            "group_titles_sample": "首亏 预计净利润-119000~-118500万",
            "pre_total_mv_yi": 100.0,
        }
    )

    features = build_event_intensity_features.text_intensity_features(row)

    assert features["evt_profit_direction"] == -1.0
    assert features["evt_profit_low_yi"] == -11.9
    assert features["evt_profit_high_yi"] == -11.85
    assert features["evt_is_contract_order"] == 0


def test_baseline_feature_sets_include_event_intensity_group():
    features = ["source_count", "evt_money_max_yi"]
    manifest = pd.DataFrame(
        {
            "feature": ["evt_money_max_yi"],
            "source_group": ["event_intensity"],
            "leakage_risk": ["low"],
        }
    )

    sets = train_baseline_models.feature_sets(features, manifest)

    assert sets["base_plus_event_intensity"] == ["source_count", "evt_money_max_yi"]
    assert "evt_money_max_yi" in sets["full_safe"]


def test_baseline_metrics_helpers_behave_sensibly():
    y_true = pd.Series([0.1, -0.2, 0.3])
    y_pred = pd.Series([0.2, -0.1, 0.4])

    metrics = train_baseline_models.compute_metrics(y_true, y_pred)

    assert metrics["mae"] > 0
    assert metrics["directional_accuracy"] == 1.0
    assert metrics["spearman_ic"] > 0
    assert metrics["rmse"] > 0


def test_sample_predictability_label_bucket_uses_neutral_band():
    assert analyze_sample_predictability.label_bucket(0.021) == "positive"
    assert analyze_sample_predictability.label_bucket(-0.021) == "negative"
    assert analyze_sample_predictability.label_bucket(0.0) == "neutral"


def test_sample_predictability_category_diagnostics_marks_ready_categories():
    frame = pd.DataFrame(
        {
            "reviewed_primary_category": ["资本动作"] * 35 + ["客户/订单"] * 6,
            "split": ["train"] * 20 + ["valid"] * 5 + ["test"] * 10 + ["train"] * 6,
            "relative_mv_return_p0_p20": [0.03] * 35 + [-0.03] * 6,
            "reviewed_modeling_scope": ["main"] * 41,
        }
    )
    frame["label_bucket"] = frame["relative_mv_return_p0_p20"].map(analyze_sample_predictability.label_bucket)

    diagnostics = analyze_sample_predictability.category_label_diagnostics(frame)

    ready = diagnostics.set_index("category").loc["资本动作", "category_model_ready"]
    not_ready = diagnostics.set_index("category").loc["客户/订单", "category_model_ready"]
    assert ready == 1
    assert not_ready == 0
