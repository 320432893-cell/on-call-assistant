# 跨语言协作细则

本文件是 `AGENTS.md` 多语言约定的下放。仅在项目实际多语言配合、或改动跨语言边界时读取，单语言项目不读。

## 1. 跨语言契约

- 跨语言交互点 MUST 有显式契约：HTTP → OpenAPI；RPC → protobuf/gRPC；进程间/文件 → JSON Schema。
- 契约 MUST 单一真相源（SSOT）：定义放一处，各语言**生成**绑定，不手写多份会漂移的类型。
- 跨语言类型映射变化 = 公共契约变化 → 命中 `AGENTS.md` 完成卡的子 agent 审查 + 失败卡的三态机（契约通常是"依赖"级，不得静默改）。

## 2. 边界形态

优先级（SHOULD）：进程/服务边界 ＞ 同仓多语言子目录 ＞ FFI/嵌入调用（耦合最紧，最后选）。

- 每种语言代码 MUST 待在自己目录/模块内，边界只暴露契约，不泄漏语言特定类型。
- CI 门禁 MUST 分语言独立跑，一种语言的检查不掩盖另一种。

## 3. 语言严谨度参考

发散选型时的事实底材，非默认推荐（选型走 `AGENTS.md` 开工卡的拍板与选型）：

| 语言 | AI 擅长 | 严谨度 | 规模化短板 |
|---|---|---|---|
| Python | 最高 | 低：动态类型，大项目松散，运行时才暴露类型错误 | 大项目 MUST 配 pyright/mypy strict 补偿 |
| TypeScript | 高 | 中-高：strict 近静态语言，可被 `any` 击穿 | 运行时仍是 JS |
| Go | 高 | 高：强类型 + 编译强制 + gofmt 统一 | 表达力较低，错误处理啰嗦 |

## 4. 语言专项约束

- **Python**：优先清华源 `-i https://pypi.tuna.tsinghua.edu.cn/simple`；新项目 MUST 用虚拟环境
- **TypeScript**：lockfile MUST 提交；`tsconfig strict` MUST 开
- **Go**：`go.mod` 锁版本；提交前 `gofmt` 无差异
