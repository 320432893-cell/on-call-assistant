# 规则治理索引

本文件只做规则治理原则路由。默认停在本文件，不自动读取 `governance.details.md`。

## 1. 触发

- 判断规则该放哪里、该不该写、该不该下放工具。
- 设计或调整索引、`*.index.md` / `*.details.md`、hook / lint / CI 分工。
- 设计或调整工具契约 registry、hook manifest、semgrep ruleset、pre-commit 或 CI 的对应关系。
- 检查规则层级、去重、读取路径、阶段解耦、牺牲项和反模式。

## 2. 轻量判断

默认先判断:

- 用户是否已明确进入写入态。
- 新规则是否真的影响架构、交付、数据、生产或跨模块行为。
- 是否能下放给成熟工具或已有配置。
- 是否会增加默认读取负担。

## 3. 读取 details

命中以下任一场景，读取 `governance.details.md`:

- 需要规则层级、冲突优先级、去重、读取路径与阶段解耦。
- 需要设计 index/details、hook 准入、工具层 vs 语义层。
- 需要维护 `.ai-config/tooling.registry.toml` 或 `.ai-config/check_rule_tool_contracts.py`。
- 需要新增规则过滤、牺牲项、写入格式、复查清单。
- 修改规则体系后需要完整反馈和一致性复查。

## 4. 路由

- 规则维护执行流程读取 `flow_rule_maintenance.index.md`。
- 修改具体专题规则时，同时读取对应专题 index。
