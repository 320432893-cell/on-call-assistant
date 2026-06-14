# 错误目录与维修入口

目标：API 错误响应必须能被用户、日志和测试串起来，出问题时先按 `request_id` 定位，再按 `error_code` 查处置路径。

## 响应契约

所有 HTTP API 错误响应使用稳定形状：

| 字段 | 含义 |
|---|---|
| `error_code` | 稳定机器码，写入本目录 |
| `message` | 给调用方看的稳定说明，不暴露 traceback/raw exception |
| `status_code` | HTTP 状态码 |
| `request_id` | 与响应头 `X-Request-ID` 一致，用于串日志 |
| `extra` | 可选；只放安全的结构化诊断，不放密钥、traceback、原始三方响应 |

## 当前错误码

| error_code | HTTP | 触发位置 | 用户可见含义 | 排查入口 | 复现命令 |
|---|---:|---|---|---|---|
| `validation_error` | 422 | FastAPI 参数校验 | 请求参数格式或必填项不符合接口定义 | 看响应 `extra.errors` 和接口参数 | `uv run pytest tests/test_observability.py -q` |
| `http_error` | 路由指定 | 路由主动抛出的 `HTTPException` | 请求被业务或依赖状态拒绝 | 查对应路由、响应 `request_id`、应用日志 | `uv run pytest tests/test_observability.py -q` |
| `internal_error` | 500 | 未捕获异常兜底 | 服务内部错误 | 用 `request_id` 查 `app.unhandled` 日志 | `uv run pytest tests/test_observability.py -q` |

## 新增错误码规则

- 新增 `error_payload("new_code", ...)` 前，先在“当前错误码”表登记。
- `message` 写稳定用户语义，不拼接 `str(e)`、traceback、SQL、路径密钥、三方原始响应。
- 需要调试信息时写日志，并包含 `request_id`、业务主键、阶段名、外部依赖名。
- 可恢复错误用明确业务码；未知异常只走 `internal_error`。
