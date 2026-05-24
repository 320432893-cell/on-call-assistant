# Hook 分类

本目录只放“执行时能立刻给出机械结论”的 hook。规则阅读、项目体检、业务判断、架构判断不放进 hook。

## 通用 hook

这些 hook 可跨项目保留，目标是挡高破坏动作或高频机械遗漏。

- `dangerous_bash.sh`: Bash 前置阻断高影响命令，包括递归强删、强制重置、推送、批量暂存、切换工作区、强制清理未跟踪文件、删除 `.git`、依赖安装 / 下载 / 工具链变更。Python 包安装默认提示使用清华源。
- `git_commit_safety.sh`: `git commit` 前检查暂存区是否含密钥、缓存、依赖目录、本地 AI/IDE 配置、日志截图、大文件。
- `dirty_static_review.sh`: 写文件后读取刚改的脏文件，做非修复静态检查，并提示本次改动应先和用户确认采用的范式/思想。
- `rename_audit.sh`: Edit/MultiEdit 删除或改名符号后，扫描项目其他文件是否仍引用旧名；只提醒，不阻断。

## 当前项目独有 hook

这些 hook 依赖本项目的 RAG/embedding 业务，不作为通用模板扩散。

- `rag_hygiene.sh`: Python RAG 文件中，BGE 双塔 embedding 调用 `encode` 时提醒显式区分 `is_query=True/False`。
- `rag_drift.sh`: 发现 embedding model、chunk 参数、向量 schema 等 RAG 数据契约改动时，调用 `scripts/check_rag_drift.py` 提醒是否需要 reindex。

## 不保留的 hook 类型

- prompt 提交时自动读规则：改由索引和任务上下文显式控制。
- 泛化项目体检：README、lock、tests、大文件这类检查改走手动体检、CI 或专门命令。
- 业务/架构语义判断：保留在规则讨论或代码审查中，不放进自动 hook。
