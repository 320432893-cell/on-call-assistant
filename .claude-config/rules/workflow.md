# 工作流

## 文件定位
- 本文件定义工作流执行约束、横切关注点协议、置信度阻断
- 任务判断原则、风险等级、修改门槛以`CLAUDE.md`为准
- 规则治理(写入/审计/冲突处理/规则词)见 `governance.md`

## 关于强制规则数
本文件遵守 `governance.md` § 4.2 的 ≤10 条强制上限,共 **8 条**(见下方索引表)。
单条规则内部可能包含 2-4 个具体阻断子项(如 § 3 测试存在性下含"未运行/失败/bug 用例/行为变更"4 个子项),按**规则索引表条目数计**,不按 `[阻断]` 字面出现次数计。
"附录推荐"块的内容是工程经验,不强制,只在相关场景做提醒。

---

## 强制规则索引(共 8 条)

| # | 规则 | 章节 |
|---|------|------|
| 1 | 回滚自检表必须出 | § 1 |
| 2 | 仓库根错位必须先报告 | § 2.1 |
| 3 | 工具链未识别不得执行包管理 | § 2.2 |
| 4 | 不可逆操作必须先问用户 | § 2.3 |
| 5 | **完成汇报必须列"未做的事"**(用户可直接打断"你没汇报 X") | § 2.4 |
| 6 | 测试存在则必须运行(含 bug/行为变更子项) | § 3 |
| 7 | 置信度 < 100 不得进入施工 | § 4 |
| 8 | 老项目门 1 必跑 | § 4 |

---

## § 1. 回滚自检表【强制 1】

### 触发条件
执行**高风险不可逆操作**前(满足任一即触发):
- 删除文件 / 删除分支 / `git reset --hard` / force push *(物理命令已由 `dangerous_bash.sh` hook 拦截,本规则补充思考层强制)*
- 重构涉及 ≥ 3 个文件
- 修改公开函数签名
- 数据库 schema 变更 / 批量数据写入

> 普通单文件 Edit/Write、新增功能、修复 bug 不触发。

### 必须输出
```
[回滚方案自检]
- 改动类型:____
- 当前状态保存:□ git stash □ git commit □ 文件备份(路径) □ 无需保存
- 回滚方式:□ git revert □ git reset --hard □ 恢复备份 □ 其他
- 回滚验证点:____(回滚后如何确认状态正确)
```

### 阻断条件(合并 3 子项)
**有未提交改动未保存** / **无回滚方式** / **回滚验证点未说明** → **[阻断] 改动前必须出完整回滚自检表**

---

## § 2. 横切关注点协议

### 2.1 开局体检【强制 2】
首次接触项目或切换工作目录时,AI 必须扫描以下项,**仅在触发异常条件时报告**。
**密钥/敏感文件类的具体清单已由 `git_commit_safety.sh` hook 在 commit 时强制查验**,本表只描述检查类别。

| 检查项 | 命令/方式 | 报告条件 |
|--------|----------|---------|
| 仓库根位置 | `git rev-parse --show-toplevel` | 仓库根 ≠ 项目目录 |
| `.gitignore` 完备性 | 读 `.gitignore` | 缺失或漏关键类别 |
| 暂存区状态 | `git status -s` | 含密钥/虚拟环境/IDE 元数据(具体清单见 hook) |
| 工具链信号 | 读 `pyvenv.cfg` / lock 文件 | 任务涉及包管理时必须先识别 |
| 远程仓库 | `git remote -v` | 用户提交/推送时报告 |

**.gitignore 范围规则**:子目录的 `.gitignore` 只对该子目录及其下生效。

**已 tracked 文件规则**:`.gitignore` 只对未跟踪文件生效,已进入 index 的文件必须 `git rm --cached`。

#### 阻断条件
- 仓库根错位且未报告 → **[阻断] 必须先报告仓库根位置异常并询问用户**

### 2.2 工具链识别【强制 3】
任务涉及包管理(pip / uv / poetry / npm / yarn 等)前,必须先识别项目用的是哪一套。

#### 阻断条件
- 工具链未识别就执行包管理命令 → **[阻断] 必须先读 pyvenv.cfg / lock 文件确认工具链**

### 2.3 不确定即问【强制 4】
横切关注点涉及任何不确定,**必须**先报告 + 询问。禁止行为:
- "先做后说"(先执行再汇报,给用户已成事实)
- 用"应该没事"替代实际检查
- 把横切问题混在任务汇报里一笔带过
- 自行决定删除 `.git/` / `.env` / 锁文件

#### 阻断条件
- 未问用户就执行不可逆操作 → **[阻断] 立即停止,向用户报告**

### 2.4 主动汇报"未做的事"【强制 5 — 重点保留】

**为什么是强制 5**:这是用户发现 AI 漏规则的**唯一系统性反馈机制**。AI 自评"☑全部通过"不可靠,必须靠主动汇报暴露漏洞。

任务完成汇报时,除"我做了什么"外,必须主动列出符合下列任一**枚举条件**的事:
- 开局体检发现的异常(仓库根错位 / .gitignore 缺项 / 暂存区含密钥 / 工具链识别失败)
- 上下文耦合评估升级为中/高风险
- 本次改动残留的未提交状态(stash / 未跟踪新文件 / 已 tracked 但未一起提交的关联改动)
- **本次自我豁免的规则**(走了快速通道、跳了某项自检、拍脑袋的决定)

**禁止汇报**:纯审美建议、与任务无关的发现、用户已表态不关心的事。

#### 阻断条件
- 完成汇报命中任一枚举条件却未列入 → **[阻断] 用户可直接打断"你没汇报 X",AI 必须立即补全**

> **给用户**:发现 AI 没主动汇报"未做的事"时,直接打断说"你漏了 X" — 这是设计好的纠偏机制,不是冒犯。

---

## § 3. 测试存在性【强制 6】

### 触发条件(满足任一即触发)
- 修改 `src/某模块.py` 且 `tests/test_某模块.py` 存在(可机械匹配,`pytest-cov` pre-commit 覆盖率门禁)
- 修改的函数被某测试文件 import (Grep 可查)

> 项目无测试基础设施时不触发。

### 必须输出
```
[测试存在性自检]
- 修改文件:____
- 对应测试文件:____
- 测试运行:□ 已通过 □ 已失败(处理:____) □ 未运行(阻断)
- 用例覆盖:
  □ 已有测试覆盖(用例名:____)
  □ bug 修复 → 已加复现该 bug 的用例
  □ 行为变更 → 已调整对应用例
  □ 纯重构 → 测试无需调整,运行通过即可
```

### 阻断条件(子项合并)
- 对应测试文件存在但未运行 → **[阻断] 先 pytest 跑一次**
- 测试失败但未处理 / bug 修复未加复现用例 / 行为变更未调整用例 → **[阻断] 按对应子项处理**

---

## § 4. 置信度终止判定【强制 7-8】

### 触发条件
进入新项目流程`flow_new_project.md`的"信息穷究阶段",或老项目流程`flow_legacy_project.md`的"现状盘点阶段"。

### 跨文件引用(主定义所在,本文件不重复)
- 置信度计算与三机制 → `risk_reasoning.md` § 6
- 诊断报告"我不会用什么" → `flow_new_project.md` § 4
- 推理日志公开 → `risk_reasoning.md` § 5
- 范式落地汇报 → `CLAUDE.md` § 4.6
- 老项目门 1/2/3 → `flow_legacy_project.md` § 2-§ 4
- 用户二次补充后再推理 → `risk_reasoning.md` § 7

### 阻断条件(本文件主管 2 条)
- **置信度 < 100,直接进入诊断/施工** → **[阻断 7] 列出具体缺口,继续走 risk_reasoning.md / info_guidance.md**
- **老项目未跑门 1 直接改动** → **[阻断 8] 先跑 legacy_health_check.sh,门 1 是基础设施红线无任何豁免**

### 紧急通道豁免
用户显式声明"急,跳过"时:
- 上述阻断部分豁免
- 但**降级声明** + **未识别风险清单** + **未验证假设清单**仍必须输出
- 老项目门 1 豁免无效(必跑)
- 救火型(`flow_emergency.md`)反向规则**不豁免**

---

## § 5. 上下文耦合风险评估(辅助,不算强制)

评估单个任务风险等级时,不仅看任务本身,还要看**当前项目状态是否会放大副作用**。

| 单任务等级 | 升级触发条件 | 升级后等级 |
|-----------|-------------|----------|
| 低 | 暂存区已混乱、用户可能随手 commit | 中 |
| 低 | 涉及 `.env`/密钥/锁文件残留 | 中 |
| 中 | 改动叠加 `.git` 删除/分支重写 | 高 |

升级后按 `CLAUDE.md` § 1.5 流程处理(高等级必须用户确认)。

---

## § 6. 任务链显式化(辅助,不算强制)

当用户单次请求展开为 **≥ 3 个连续步骤**时,**建议**用 `TaskCreate` 或 `TodoWrite` 显式列出。

判定标准(任一满足):
- 步骤之间存在依赖
- 跨越不同领域(代码 / 版本控制 / 文档 / 规则 / 配置)
- 单步阻塞需等用户决策

> 这条曾是强制,降级理由:TodoWrite 已是工作习惯,显式规则约束意义不大。但建议保留这个习惯。

---

## § 7. 新项目接手

**接手流程见 `onboarding.md`**(读文档/找入口/画调用链/识层级/标状态机/生成 PROJECT_CONTEXT.md)。

---

## § 8. 专题规则激活清单

- 全局层(CLAUDE.md)和本文件规则**每次任务必触发**
- 专题层规则**按需激活**:由 CLAUDE.md 项目类型判定、用户明确要求、或 `rule_activator.sh` hook 关键词命中触发

| 专题文件 | 激活条件 |
|----------|---------|
| `flow_new_project.md` | 探索型项目 |
| `flow_legacy_project.md` | 收敛型项目 |
| `flow_emergency.md` | 救火型(线上故障) |
| `risk_reasoning.md` | 风险识别阶段 |
| `info_guidance.md` | 信息缺口 |
| `code.md` | 编码、思想范式 |
| `gui.md` | PySide6/Qt GUI |
| `frontend.md` | Vue 3 + ECharts |
| `backend.md` | FastAPI / Starlette 后端 |
| `data.md` | 数据处理 |
| `architecture.md` | 分层架构、封装 |
| `package.md` | PyInstaller 打包 |
| `web-automation.md` | Playwright 爬虫 |
| `onboarding.md` | 首次接手项目 |
| `governance.md` | 规则文件改动 |

---

## 附录 A:工具执行推荐(不强制)

- Windows 环境**避免**用 Bash + Python 处理文件修改,走 Edit/Write
- `run_in_background` **避免**用于 uvicorn / playwright server 等长驻服务
- 大文件 >300 行尽量分批写入
- `Edit` 失败先 `Read` 确认,内容不对则 `Write` 重写
- `Edit` 匹配 Unicode 字符连续两次失败,改用 `Write`
- 简单搜索用 `Glob`/`Grep`,不启动 Agent
- 单文件读取直接用 `Read`,不包装成 Agent
- Agent 仅用于多步骤复杂任务、并行搜索、避免结果污染主上下文

## 附录 B:hook 已强制接管的事项

- `rm -rf` / `git reset --hard` / `git push --force` / `git clean -fd` / `rm .git` → `dangerous_bash.sh` 物理拦
- commit 含 `.env` / `*.key` / 虚拟环境 / IDE 元数据 / >5MB 大文件 → `git_commit_safety.sh` 物理拦
- `.py` 改后 ruff/mypy 不过 → `ruff` / `mypy`(pre-commit)阻断
- `.py` 改后对应 `test_*.py` 存在 → `pytest-cov`(pre-commit)覆盖率门禁
- `.json` / `.jsonl` 改后语法非法 → `check-json`(pre-commit)阻断
- 用户 prompt 含场景关键词 → `rule_activator.sh` 注入对应规则文件路径
- 跨层 import 违规(`routers > services > models > config`) → `import-linter`(pre-commit)阻断
- 工程缺口(.gitignore / 大文件 / 大函数 / 循环依赖 / 死代码 / .vue >300 行) → `engineering_audit.sh` 6h 内首次会话报全景
- 改名/删除后旧名残留 → `rename_audit.sh` 在 Edit/MultiEdit 后自动 grep
- 新项目首迭代 >50 行 → `first_iter_lines.sh` 提醒(老项目仅新建文件触发)
- Playwright 文件含 `time.sleep(` → `playwright_no_sleep.sh` 报告
- HTTP 客户端调用无 `timeout=` → `http_timeout.sh` ast 解析后报告(requests/httpx/urllib)
- 标准库 `random.*` 用于业务输出无 `random.seed()` → `ruff`(pre-commit)拦截
- FastAPI/Flask `debug=True` 硬编码 / CORS `allow_origins=["*"]` / uvicorn `reload=True` → `fastapi_debug.sh` ast 解析报告
- RAG 反模式(双塔 embedder 漏 is_query / COSINE 配 normalize=False / top_k=1) → `rag_hygiene.sh` ast 解析报告
- RAG 数据契约漂移(EMBEDDING_MODEL/chunk_size/Distance 等关键字段在 git 改动) → `rag_drift.sh` 提醒重灌 collection
- 时序 ML 反模式(train_test_split 用在时序 / xgb/sklearn 缺 random_state / .shift(-N)+fit 共存自查) → `ml_timeseries.sh` ast 解析报告

> hook 失败时 AI 仍按本文件强制规则的思考层兜底,不依赖 hook 单点。
