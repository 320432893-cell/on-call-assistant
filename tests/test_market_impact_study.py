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
