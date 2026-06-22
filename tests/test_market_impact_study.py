# 生命周期：持久维护
# 覆盖的业务场景：市场影响研究辅助函数的日期清洗、事件分类、CAR 窗口、ML SSOT 和建模样本规则回归。
# 依赖的服务/环境：本地 Python、pandas、market-impact-study 下的脚本文件；不依赖外部网络和远程服务。
# 运行方式：uv run pytest tests/test_market_impact_study.py
# oracle 输出形状：pytest 断言失败给出期望/实际差异；业务步骤用例名描述场景，pytest 汇总用时。
"""Focused tests for market-impact study helper functions."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MARKET_DIR = ROOT / "market-impact-study"

# Scripts under MARKET_DIR import sibling modules (e.g. `from peer_universe import
# load_companies`). Running them as scripts puts that dir on sys.path[0]; importlib
# loading here does not, so add it explicitly to keep sibling imports resolvable.
if str(MARKET_DIR) not in sys.path:
    sys.path.insert(0, str(MARKET_DIR))


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
build_ml_readiness_tables = load_module("build_ml_readiness_tables", "build_ml_readiness_tables.py")
build_ml_ssot_tables = load_module("build_ml_ssot_tables", "build_ml_ssot_tables.py")
build_data_governance_tables = load_module("build_data_governance_tables", "build_data_governance_tables.py")
build_modeling_assets = load_module("build_modeling_assets", "build_modeling_assets.py")
apply_manual_review_overlay = load_module("apply_manual_review_overlay", "apply_manual_review_overlay.py")
build_event_intensity_features = load_module("build_event_intensity_features", "build_event_intensity_features.py")


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
