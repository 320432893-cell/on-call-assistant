# 专题索引: 规则治理

本专题处理规则、hook、lint、CI、settings、memory 和规则索引怎么维护。

本文件只做规则治理路由。规则维护默认先讨论，不因读取本索引进入写入态。

## 触发入口

### 规则维护流程

命中以下任一场景，读取 `flow_rule_maintenance.index.md`:

- 准备新增、修改、删除、压缩、迁移规则文件。
- 修改 hook、settings、memory、规则索引、规则副本。
- 需要判断发散、收敛、ROI 剪枝、用户拍板边界和阶段总结。

### 规则治理原则

命中以下任一场景，读取 `governance.index.md`:

- 判断规则该放哪里、该不该写、该不该下放工具。
- 设计或调整索引、`*.index.md` / `*.details.md`、hook / lint / CI 分工。
- 设计或调整工具契约 registry、contract checker、人读工具总览。
- 需要检查规则层级、去重、已有覆盖、牺牲项和工具下放。

## 读取边界

- 用户只是问规则内容时，只读解释，不进入写入流程。
- 涉及写入规则、hook、settings、memory 或索引时，必须先确认用户已拍板。
- hook 只做单职责即时提醒，不承担业务语义分流。

## 维护重点

- 是否先讨论再写入，用户未拍板不落盘。
- 是否优先单文件和默认可执行 index，而不是过早物理解耦。
- 是否把索引写成触发路由器，而不是目录清单或第二份规则正文。
- 是否默认跨文件引用 index 或单一规则文件，并只在确实需要复杂展开时保留 details。
- 是否让阶段闭包只保留下一阶段需要的规则入口和主注意力，而不是展开历史讨论。
- 是否说明新增规则牺牲什么，以及牺牲是否值得。
- 是否把机械检查下放给成熟工具，而不是写成 AI 自觉规则。
- 是否同步维护 `.ai-config/tooling.registry.toml`、`.ai-config/check_rule_tool_contracts.py`、`.ai-hooks/manifest.json`、pre-commit 和 CI 的工具契约。
- 是否避免同一规则在多个文件主定义。
