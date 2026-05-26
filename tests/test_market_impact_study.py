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
build_rag_event_group_evidence = load_module("build_rag_event_group_evidence", "build_rag_event_group_evidence.py")


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
