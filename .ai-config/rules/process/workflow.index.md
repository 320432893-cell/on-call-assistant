# 工作流索引

本文件只做通用工作流路由。默认停在本文件，不自动读取 `workflow.details.md`。

## 1. 触发

- 准备改文件、运行会改变状态的命令、做验证或完成汇报。
- 中大任务、多阶段任务、多文件改动、用户纠偏或上下文压缩。
- 需要判断 Fast path / Normal path / Guarded path / Emergency path。

## 2. 轻量判断

默认先做:

- 仓库根、工作区状态、工具链、敏感文件的任务前体检。
- 判断是否存在执行前门禁、停止条件或验证门。
- 小任务只做必要验证和短汇报，不展开完整 taskwork。

## 3. 读取 details

命中以下任一场景，读取 `workflow.details.md`:

- 中大任务、规则维护、架构 / 工具链变更、多文件改动。
- 删除、覆盖、迁移、依赖安装、下载型工具、生产 / 数据 / 安全风险。
- 需要 taskwork 单步推进、阶段闭包、`RULE_ROUTE`、上下文耦合风险。
- 需要验证预算、完成汇报标准或停止条件。

## 4. 路由

- 老项目改动读取 `flow_legacy_project.index.md`。
- 新项目 / 新模块读取 `flow_new_project.index.md`。
- 救火读取 `flow_emergency.index.md`。
