# TypeScript 工程细则

本文件是 `AGENTS.md` § 7.3 在 TypeScript 上的展开。仅在写入/重写 TS 代码并命中 § 4 审查门禁时读取，不作为启动仪式。

## 1. 工具链门禁

| 环节 | `[当前]` | `[替代]` | 说明 |
|---|---|---|---|
| 包管理 | npm | pnpm | pnpm 省盘、装得快、对 monorepo 友好 |
| 静态检查 | eslint + `tsc --noEmit` | biome | biome 合并 lint+format，更快；代价是生态插件少 |
| 格式化 | prettier | biome | 与上一行配套二选一 |
| 测试 | vitest | jest | 新项目优先 vitest |

- lockfile MUST 提交。
- `tsconfig` 的 `strict` MUST 开（AGENTS.md § 8）。

## 2. 严谨度补偿

TS 严谨度中-高，但护栏可被击穿：

- `any` MUST 视为缺口：边界处用 `unknown` + 收窄，不用 `any` 穿透。
- 对外契约 MUST 显式类型；跨语言边界类型 MUST 由契约 SSOT 生成（见 `polyglot.index.md`），不手写。
- `strict` 下的 `noUncheckedIndexedAccess`、`exactOptionalPropertyTypes` SHOULD 开，进一步抗腐化。
- 类型体操过度复杂时优先简化数据结构，不为"类型完整"牺牲可读性。

## 3. 副作用与鲁棒性

- 运行时仍是 JS：编译期通过不代表运行期安全，外部输入 MUST 在边界校验（zod 或等价）。
- 异步错误 MUST 显式处理；不得吞掉 reject 或漏 await。
- 外部 IO 隔离在边界层，核心逻辑可 mock、可测试。
- 结构坏味道、抽象取舍、范式判断走 `code.index.md`，本文件不重复。
