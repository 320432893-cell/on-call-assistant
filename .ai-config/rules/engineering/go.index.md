# Go 工程细则

本文件是 `AGENTS.md` § 9 在 Go 上的展开。仅在写入/重写 Go 代码并命中 § 6 审查门禁时读取，不作为启动仪式。

## 1. 工具链门禁

| 环节 | 工具 | 说明 |
|---|---|---|
| 包管理 | go mod（内置） | `go.mod` 锁版本 |
| 静态检查 | go vet + golangci-lint | golangci-lint 聚合多 linter，作为主门禁 |
| 格式化 | gofmt / goimports | 提交前 MUST 无差异，无商量 |
| 测试 | `go test -race` | 并发代码 MUST 带 `-race` |

## 2. 严谨度（Go 的强项）

Go 严谨度最高、抗腐化最强，是 `AGENTS.md` § 9 大项目场景的优选之一：

- 强类型 + 编译强制 + gofmt 统一风格，规模化时结构不易漂移。
- 短板是表达力较低、错误处理啰嗦、泛型生态年轻；选它须接受这份冗长换稳定。
- 不滥用 `interface{}` / `any`；边界类型显式建模。

## 3. 副作用与鲁棒性

- 错误 MUST 显式处理或显式忽略（`_`），不静默丢弃；包裹错误用 `%w` 保留链路。
- goroutine MUST 有明确生命周期与退出路径；用 `context` 控制取消与超时。
- 共享状态并发访问 MUST 经 channel 或 sync 原语保护；测试带 `-race`。
- 外部依赖经 interface 抽象，便于 mock、隔离失败。
- 结构坏味道、抽象取舍、范式判断走 `code.index.md`，本文件不重复。
