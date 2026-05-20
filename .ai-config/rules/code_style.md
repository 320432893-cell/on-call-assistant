# 代码风格规约

## 文件定位
- **按需加载**：代码结构、编码规范、思想范式相关任务时读取
- 本文件定义"代码怎么写"的硬规则，与 governance.md § 3.5 工具矩阵互补
- 工具能查的（命名/格式/类型/import）交给 ruff/mypy/import-linter，本文件只管**语义层**

---

## 1. 命名【强制】

> 机械层已由 `ruff N` 规则集物理拦截（snake_case / PascalCase / UPPER_CASE）。
> 本节补充 ruff 管不到的**语义命名**规则。

| 规则 | 示例 |
|------|------|
| 布尔变量/函数用 is_/has_/can_/should_ 前缀 | `is_valid`, `has_permission` |
| 集合变量用复数 | `documents`, `user_ids` |
| 禁止拼音（拼音缩写更禁止） | ❌ `wenben` ✅ `text` |
| 禁止无意义缩写（i/j/k/x/y 循环变量除外） | ❌ `proc_doc` ✅ `process_document` |
| 模块名反映职责，不反映实现 | ❌ `redis_helper.py` ✅ `cache.py` |

---

## 2. 异常处理【强制】

> 机械层：裸 except / blind except / try-except-pass / 缺 from → ruff 已拦。
> 本节定义**异常分层语义**。

### 2.1 三层异常体系

```
BaseAppError (项目根异常，继承 Exception)
├── ServiceError     (服务层：业务逻辑失败，可恢复)
│   ├── NotFoundError
│   ├── ValidationError
│   └── ConflictError
├── InfraError       (基础设施层：外部依赖失败，可重试)
│   ├── DatabaseError
│   ├── ExternalAPIError
│   └── TimeoutError
└── ConfigError      (配置层：启动时失败，不可恢复)
```

### 2.2 规则

| 规则 | 说明 |
|------|------|
| 每个项目必须定义 `BaseAppError` | 放在 `app/exceptions.py` |
| 服务层只抛 `ServiceError` 子类 | 不抛裸 Exception / HTTPException |
| 路由层负责把 ServiceError 映射为 HTTP 状态码 | 用 FastAPI exception_handler |
| `except Exception` 只允许在最外层兜底 | 必须 log + 转为 InfraError |
| 重试逻辑只针对 InfraError | ServiceError 不重试（业务错误重试无意义） |

---

## 3. 日志【强制】

> 机械层：`ruff T201` 禁 print、`ruff LOG/G` 检查 logging 格式。
> 本节定义**日志语义规范**。

### 3.1 工具选择

使用标准库 `logging`，不引入 structlog/loguru（减少依赖，标准库够用）。

### 3.2 级别语义

| 级别 | 何时用 | 示例 |
|------|--------|------|
| DEBUG | 开发调试，生产不开 | 变量值、中间状态 |
| INFO | 业务里程碑 | "索引构建完成，共 1234 条" |
| WARNING | 可恢复的异常状态 | "重试第 2 次"、"降级到备用方案" |
| ERROR | 不可恢复但不崩溃 | "外部 API 返回 500"、"文件解析失败跳过" |
| CRITICAL | 进程即将退出 | "数据库连接池耗尽" |

### 3.3 规则

| 规则 | 说明 |
|------|------|
| 禁止 print 作正式输出 | 用 `logger.info()`（ruff T201 已拦） |
| 每个模块顶部 `logger = logging.getLogger(__name__)` | 不用 root logger |
| 日志消息用英文（方便 grep） | 中文放在注释里 |
| 异常日志必须带 `exc_info=True` 或 `logger.exception()` | 不吞 traceback |
| 禁止在循环内高频 INFO | 用 DEBUG 或循环外汇总 |

---

## 4. Docstring【强制】

> 机械层：ruff ANN 检查类型注解存在性。
> 本节定义**何时写 docstring、写什么格式**。

### 4.1 格式：Google 风格

### 4.2 规则

| 规则 | 说明 |
|------|------|
| 公共函数/类必须写 docstring | 一行描述 + Args/Returns/Raises（复杂时） |
| 私有函数：复杂时写，简单时不写 | "复杂"= 超过 10 行或有非显然副作用 |
| docstring 写"为什么"和"边界"，不写"做什么" | 函数名已说明做什么 |
| 禁止 docstring 里写实现细节 | 实现会变，docstring 不会跟着改 |
| 模块级 docstring：只在模块职责不明显时写 | `__init__.py` 不写 |

---

## 5. 配置管理【强制】

> 本项目已使用 `pydantic-settings`（见 pyproject.toml）。

### 5.1 规则

| 规则 | 说明 |
|------|------|
| 所有配置集中在 `app/config.py` 的 Settings 类 | 禁止散落 `os.getenv()` |
| 环境变量命名：`APP_` 前缀 + UPPER_SNAKE | `APP_REDIS_URL`、`APP_DEBUG` |
| 敏感值（token/password）类型用 `SecretStr` | pydantic 自动脱敏 |
| 默认值只给开发环境安全的值 | 生产必须显式设置，缺失即报错 |
| `.env.example` 入仓，`.env` 不入仓 | .gitignore 已配 |

---

## 6. 类型注解【强制】

> 机械层：`mypy --strict` + `ruff ANN` 检查注解存在性。
> 本节定义**类型注解的语义规则**。

### 6.1 规则

| 规则 | 说明 |
|------|------|
| 公共函数签名必须完整标注（参数 + 返回值） | mypy --strict 已强制 |
| 私有函数：参数标注，返回值显式写 `-> None` 或具体类型 | 禁省略 |
| 禁止 `Any` 除非有 `# type: ignore[xxx]` + 注释说明原因 | 裸 Any = 类型系统漏洞 |
| 容器类型用具体泛型 | ❌ `list` ✅ `list[str]` |
| 返回 `dict` 必须用 TypedDict 或 Pydantic Model | 禁止裸 `dict[str, Any]` 作公共 API 返回 |
| Optional 显式写 `X \| None`（Python 3.10+ 语法） | 不用 `Optional[X]` |
| 渐进策略：旧代码允许 `# type: ignore[xxx]` + TODO | 禁止裸 `# type: ignore` |

---

## 7. 测试【强制】

> 机械层：`pytest-cov` 覆盖率门槛 80%（阶段 2 配置）。
> 本节定义**测试的语义规则**。

### 7.1 规则

| 规则 | 说明 |
|------|------|
| 测试文件结构镜像 src | `app/services/indexer.py` → `tests/services/test_indexer.py` |
| 每个公共函数至少 1 个正向测试 | 私有函数通过公共接口间接测 |
| 异常路径必须测 | 至少覆盖：输入非法、外部依赖失败、边界值 |
| 测试函数命名：`test_<行为>_when_<条件>` | `test_search_returns_empty_when_no_match` |
| fixture 优先于 setUp/tearDown | pytest 风格 |
| 禁止测试间依赖（顺序无关） | 每个测试独立可跑 |
| 禁止 `time.sleep` 等硬等待 | 用 mock / pytest-timeout |
| 集成测试与单元测试分目录 | `tests/unit/` + `tests/integration/` |

---

## 8. 项目结构【强制】

> 机械层：`import-linter`（.importlinter）检查分层依赖方向。
> 本节定义**目录和模块组织的语义规则**。

### 8.1 标准目录结构

```
project-root/
├── app/
│   ├── __init__.py
│   ├── main.py              # 入口（FastAPI app / CLI）
│   ├── config.py            # Settings（pydantic-settings）
│   ├── exceptions.py        # BaseAppError + 子类
│   ├── models/              # 数据模型（Pydantic / SQLAlchemy）
│   ├── services/            # 业务逻辑
│   └── routers/             # HTTP 路由（仅 FastAPI 项目）
├── tests/
│   ├── unit/
│   └── integration/
├── scripts/                 # 一次性 / 运维脚本
├── .ruff.toml
├── .mypy.ini
├── .importlinter
├── .pre-commit-config.yaml
├── pyproject.toml
└── uv.lock
```

### 8.2 规则

| 规则 | 说明 |
|------|------|
| 依赖方向单向：routers → services → models → config | import-linter 物理拦 |
| `config.py` 不 import 业务模块 | 配置是最底层 |
| `exceptions.py` 只被 import，不 import 业务模块 | 异常定义是纯数据 |
| 一个模块一个职责（≤500 行） | 超过则拆 |
| `__init__.py` 只做 re-export，不写逻辑 | 逻辑放具体模块 |
| 新项目第一个文件是 `config.py` + `exceptions.py` | 基础设施先行 |
