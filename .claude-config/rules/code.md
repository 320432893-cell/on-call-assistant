# 代码规则强制版

## 文件定位
- 本文件管**写代码时的范式判断力**——给 AI 一套思想范式,让它在写代码时知道用什么、不用什么、为什么
- 不写"自检框",不要求 AI 每次改代码都填表;每个范式给定义/适用/不适用/反例,**完成时由 CLAUDE.md § 4.6 集中汇报**
- 老项目改动的范式问题(屎山/风格分裂)走 `flow_legacy_project.md` + `onboarding.md`,本文件不管
- 强制规则数 ≤ 10 条(governance.md § 5.2 上限),共 **6 条**(见索引)

## 跨文件分工
- 分层依赖、外部调用边界 → `architecture.md`
- 多步写入失败模式、数据契约、幂等、对账 → `data.md`
- GUI → `gui.md` / 前端 → `frontend.md` / 打包 → `package.md`
- Web 自动化 → `web-automation.md` / FastAPI 后端 → `backend.md`

---

## 强制规则索引(共 7 条)

| # | 范式 | 章节 |
|---|------|------|
| 1 | 范式落地通则(完成汇报必列"用了什么 / 不用什么") | § 〇 |
| 2 | 依赖倒置(DIP) | § 1 |
| 3 | 状态机 | § 2 |
| 4 | 注册表/策略 | § 3 |
| 5 | 异常分层捕获 | § 4 |
| 6 | 接口契约稳定性 | § 5 |
| 7 | 日志(与异常配对) | § 6 |

> 不变式与确定性、并发反模式、try-except 反模式 → 已由 ruff/mypy 物理接管,本文件不重复(详见 governance § 3.5 工具职责矩阵)

---

## § 〇 范式落地通则【强制 1】

### 触发
应用任何工程范式(状态机 / 注册表 / DIP / 幂等 / 检查点 / 失败模式 / 不变式)。

### 完成时必须输出(由 CLAUDE.md § 4.6 强制)
- **用了哪些范式**:每条 = 范式名 + 应用在哪个文件/函数 + 一句话怎么用
- **刻意不用哪些经典范式**:每条 = 范式名 + 不用的原因

### 阻断
- 声明使用范式但完成汇报段未列 → **[阻断 1] 补汇报**
- 汇报段无"不用什么经典范式" → **[阻断 1] 显式列出**

### 推荐(不强制)
代码相关位置加注释 `# 范式: <名> — <一句话>`,便于事后定位。

---

## § 1 依赖倒置(DIP)【强制 2】

### 一句话定义
高层依赖**抽象**(Protocol / ABC),不依赖**具体类**——尤其当具体类含 IO 或外部依赖时。

### 适用
- 类/模块被 ≥ 2 处依赖
- 需要 mock 测试
- 含 IO / 数据库 / HTTP / 文件 / 外部 API

### 不适用
- 一次性脚本、内部工具函数、无外部依赖
- 只有 1 处调用且不会扩展

### 反例(用错了什么样)
```python
# ❌ 服务层直接 import 具体的数据库实现
from src.db.postgres import PostgresClient
class OrderService:
    def __init__(self):
        self.db = PostgresClient()  # 上层硬绑底层,没法 mock,换库要全改
```

### 阻断
- 上层 `from X import 具体类` 且该类含 IO/外部依赖 → **[阻断 2] 改为依赖 Protocol/ABC**

> 跨层 import 物理违规由 `import-linter` 兜底,本规则只看语义层。项目级层级定义见 `.importlinter`。

---

## § 2 状态机【强制 3】

### 一句话定义
有显式生命周期的对象/任务,状态枚举 + 合法转移表 + 集中切换入口,不要散落 if/else。

### 适用
- 任务/订单/审批等有"未开始 / 进行中 / 已完成 / 失败 / 已撤销"类生命周期
- 出现 ≥ 3 个布尔标志位互相影响
- `if status == 'X'` 类分支 ≥ 3 处

### 不适用
- 简单 enum + 一次性赋值
- 状态只有 2 个且无非法转移可能(如 on/off)

### 反例
```python
# ❌ 状态散布,无人知道合法转移
order.is_paid = True
order.is_shipped = True   # 没付钱也能 shipped?
order.is_cancelled = True # 已 shipped 还能 cancel?
```

### 阻断
- 状态分散在多个 if/else,无显式状态枚举 + 转移表 → **[阻断 3] 集中**
- 存在不在转移表里的隐式状态切换 → **[阻断 3] 集中到状态表**

---

## § 3 注册表/策略【强制 4】

### 一句话定义
分支按 key 路由,从 `if/elif` 改为 `dict[key, handler]`,扩展时改一处而不是改几处。

### 适用
- `if x == 'a': ... elif x == 'b': ...` 分支 ≥ 3 个
- **且未来可能扩展新分支**(用户加 / 插件 / 配置驱动)

### 不适用
- 分支数固定且业务上不会再加(如"周一到周日"7 个分支)
- 每个分支逻辑差异极大,共享接口反而别扭

### 反例
```python
# ❌ 加新数据源要找好几处改
if source == "csv": data = read_csv(path)
elif source == "json": data = read_json(path)
elif source == "xlsx": data = read_xlsx(path)
# 加 parquet → 这里改 + 校验那里改 + 文档那里改
```

### 阻断
- if/elif ≥ 3 分支 + 预期会扩展 + 仍用 if/elif → **[阻断 4] 改注册表或在汇报段说明理由**

---

## § 4 异常分层捕获【强制 5】

### 一句话定义
不同层 catch 不同的事:**引擎层只 raise**,**服务层转译业务异常**,**边界层兜底转译用户可读信息**。

### 分层捕获规则
| 层 | 行为 |
|----|------|
| **引擎层**(纯计算/数据处理) | 只 raise,不 catch(除非真要降级,需明示业务理由) |
| **服务层**(业务逻辑编排) | catch 转译为业务异常(`BusinessError`) |
| **边界层**(CLI/HTTP/UI handler) | 必须 catch 兜底,转译为用户可见信息(不暴露 traceback) |

### 用 `except Exception` 宽捕的合法理由(三选一)
- 边界层兜底
- 任务隔离(一个任务挂不能拖垮其他)
- UI 顶层不让程序崩

### 反例
```python
# ❌ 引擎层吞错,上游永远不知道发生了什么
def calculate_tax(order):
    try:
        return engine.compute(order)
    except Exception:
        return 0  # 静默吞错,业务以为零税额
```

### 阻断
- `except Exception` 未在汇报段填宽捕原因 → **[阻断 5] 填三选一**
- 引擎层吞了异常未上报 → **[阻断 5] 改为 raise,catch 移到服务/边界层**
- 边界层未兜底导致 traceback 暴露给用户 → **[阻断 5] 边界层加 catch + 转译**
- 错误信息含敏感字段(密码 / token / key) → **[阻断 5] 移除**

> 裸 except / blind except / try-except-pass / 不带 from / TRY 反模式 → ruff 物理拦,不在此重复。

---

## § 5 接口契约稳定性【强制 6】

### 一句话定义
公开方法/跨模块函数/对外 API 的签名是**契约**——参数、返回结构、异常类型、副作用、性能量级,任一变就是破坏性变更。

### 适用
- 新增/修改公开方法(被外部模块调用)
- 修改跨模块调用的函数签名
- 暴露给前端/外部的 API

### 不适用
- 模块内私有函数(下划线开头)
- 一次性脚本内部函数
- 显式声明为实验性 / 不稳定的接口

### 五项稳定性核对

| 维度 | 检查点 |
|------|--------|
| 参数 | 增删 / 类型 / 默认值是否兼容 |
| 返回结构 | 字段是否稳定,新增/删除字段是否破坏调用方 |
| 异常类型 | 透传 / 转换语义是否一致 |
| 副作用 | 是否新增 IO / 状态修改 |
| 性能 | 复杂度量级是否变化 |

### 反例
```python
# ❌ 公开方法返回 dict,字段全靠口头约定,调用方猜
def get_user_info(user_id: int) -> dict:
    return {"name": "...", "age": 18, "email": "..."}  # 哪些字段必有?类型?改一个就崩
```

### 阻断
- 破坏性变更未列调用方影响清单 → **[阻断 6] grep 列全部调用方**
- 删除返回字段或改字段类型且未升版本 → **[阻断 6] 升版本或保留兼容字段**
- 公开方法返回 `dict` / `Any` 而非 `dataclass` / `TypedDict` / `Pydantic` → **[阻断 6] 用结构化类型**

---

## § 6 日志(与异常配对)【强制 7】

### 一句话定义
日志和异常是一对——**异常必带上下文日志,日志必关联异常上下文**。不是事后补,是埋好。

### 适用
- 任何 try/except 块(异常分支必带 logger)
- 关键业务节点(订单成交 / 状态转移 / 外部调用入出口)
- 错误响应返回前(留下追溯证据)

### 不适用
- 纯内部计算函数(没 IO / 没异常)
- 一次性脚本

### 关键要求
- 异常 log 必须 `logger.exception(...)` 或 `logger.error(..., exc_info=True)`(保留 traceback)
- 不准用 `print` 输出错误信息(`ruff T20` 物理拦)
- 不准用 root logger,模块内 `logger = logging.getLogger(__name__)`
- 日志含敏感字段(密码 / token / key / 身份证)必须脱敏

### 反例
```python
# ❌ 异常吞了 + print,出问题永远找不到根因
try:
    result = call_external_api(token=user_token)
except Exception as e:
    print(f"failed: {e}, token={user_token}")  # token 进了日志,traceback 丢了
    return None
```

### 阻断
- except 分支无 `logger.exception` / `exc_info=True` → **[阻断 7] 补 traceback 日志**
- 日志输出敏感字段未脱敏(token / password / key 等) → **[阻断 7] 脱敏后再输出**
- 用 `print` 输出错误信息 → **[阻断 7] 改用 logger**(ruff T20 兜底)

> root logger / 模块 logger 选型由 `ruff LOG` 物理拦截,不在此重复。

---

## 反模式

- ❌ 在过程中给 AI 填"自检框",AI 容易 ☑全通过糊弄过去
- ❌ 老项目里强行套新范式造成风格分裂(走 `flow_legacy_project.md`)
- ❌ 把可静态检测的规则塞进本文件(违反 governance § 3 双轨)
