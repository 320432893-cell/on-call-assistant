# 生命周期：持久维护
# 覆盖的业务场景：HTTP request_id 透传、健康检查诊断信息、统一错误响应格式。
# 依赖的服务/环境：本地 FastAPI TestClient；不依赖外部网络、Redis、Qdrant 或 LLM Provider。
# 运行方式：uv run pytest tests/test_observability.py
# oracle 输出形状：pytest 断言失败给出期望/实际差异；业务用例名描述请求场景，pytest 汇总用时。
"""Observability contract tests for the FastAPI entrypoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_health_response_includes_request_id_and_diagnostics():
    client = TestClient(app)

    response = client.get("/health", headers={"X-Request-ID": "req-test-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-test-123"
    body = response.json()
    assert body["app"] == "On-Call Assistant"
    assert body["status"] in {"ok", "degraded"}
    assert set(body["paths"]) == {"raw_data", "processed_data", "tantivy_index", "qdrant_index"}
    assert set(body["dependencies"]) == {"embedding_configured", "qdrant"}


def test_http_error_response_has_stable_shape_and_request_id():
    client = TestClient(app)

    response = client.get("/v1/search", headers={"X-Request-ID": "req-empty-query"})

    assert response.status_code == 422
    assert response.headers["X-Request-ID"] == "req-empty-query"
    body = response.json()
    assert body["error_code"] == "validation_error"
    assert body["status_code"] == 422
    assert body["request_id"] == "req-empty-query"
    assert body["message"]
