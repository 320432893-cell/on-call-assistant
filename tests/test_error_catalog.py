# 生命周期：持久维护
# 覆盖的业务场景：API error_code 使用必须登记在错误目录，避免错误响应语义漂移。
# 依赖的服务/环境：本地 Python ast 解析、docs/ERROR_CATALOG.md、app 源码；不依赖外部服务。
# 运行方式：uv run pytest tests/test_error_catalog.py
# oracle 输出形状：pytest 断言失败给出缺失 error_code 或检查脚本退出码的期望/实际；pytest 汇总用时。
"""Regression tests for the error catalog checker."""

from __future__ import annotations

from tools import check_error_catalog


def test_error_catalog_contains_all_runtime_error_codes():
    assert check_error_catalog.main() == 0


def test_error_catalog_lists_current_observability_codes():
    codes = check_error_catalog.catalog_codes()

    assert {"validation_error", "http_error", "internal_error"} <= codes
