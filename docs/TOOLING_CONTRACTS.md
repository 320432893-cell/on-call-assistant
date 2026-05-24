最后修改日期: 2026-05-24

# 自动检查怎么看

你只需要记住一句话：

**普通代码问题交给工具，业务取舍你拍板，工具和 hook 的维护让 AI 处理。**

## 一张图

打开备注：下面是 Mermaid 图，需要用支持 Mermaid 的 Markdown 预览打开，例如 GitHub、GitLab、VSCode Mermaid 插件或 Mermaid Live Editor。

```mermaid
flowchart TD
    ROOT[自动检查]

    ROOT --> CODE[写代码时]
    CODE --> RUFF[Ruff<br/>手动基线:格式 / import / 明显 bug]
    CODE --> TYPE[basedpyright<br/>手动基线:类型和接口]
    CODE --> LAYER[import-linter<br/>分层依赖]

    ROOT --> SAFE[安全]
    SAFE --> SECRET[detect-secrets<br/>密钥泄漏]
    SAFE --> AUDIT[pip-audit<br/>依赖漏洞]

    ROOT --> PROJECT[项目特殊规则]
    PROJECT --> SEMGREP[semgrep<br/>timeout / debug / bad smell / Playwright / RAG]

    ROOT --> AI[AI 操作安全带]
    AI --> HOOKS[hooks<br/>危险命令 / 高影响 git / 依赖下载 / 误提交 / RAG drift]

    ROOT --> TEST[功能验证]
    TEST --> PYTEST[pytest<br/>测试和覆盖率]

    classDef root fill:#f8fafc,stroke:#334155,stroke-width:2px,color:#0f172a
    classDef code fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    classDef safe fill:#fee2e2,stroke:#dc2626,color:#7f1d1d
    classDef project fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef ai fill:#ede9fe,stroke:#7c3aed,color:#3b0764
    classDef test fill:#dcfce7,stroke:#16a34a,color:#14532d

    class ROOT root
    class CODE,RUFF,TYPE,LAYER code
    class SAFE,SECRET,AUDIT safe
    class PROJECT,SEMGREP project
    class AI,HOOKS ai
    class TEST,PYTEST test
```

## 你看到报警时怎么判断

### 1. 看起来像代码小问题

交给 AI 修。

常见来源：import-linter、Ruff、basedpyright、radon、vulture、deptry。

当前状态：`import-linter` 是阻塞检查；`Ruff` 和 `basedpyright` 已接入但历史基线未清零，暂时只作为手动基线工具运行，避免提交和 CI 被已知 backlog 持续阻塞。

80/20 脏代码体检：`.ai-config/dirty_diff_review.py` 只看本次新增行；`radon` 看复杂度，`vulture` 看疑似死代码，`deptry` 看依赖脏账。它们用来触发人机讨论，不直接决定重构或删除。

你只需要问：这是机械问题，还是会改变业务行为？

### 2. 看起来像安全问题

先当真，不要直接提交。

常见来源：detect-secrets、pip-audit。

你只需要拍板：能不能升级依赖、能不能接受风险、这个值是不是敏感。

### 3. 看起来像项目特殊规则

先让 AI 解释为什么触发。

常见来源：semgrep。

它通常管 timeout、debug、坏味道、Playwright、RAG 这类项目约束。规则不合理时，应该改规则，不要在代码里硬绕。

### 4. 看起来像 AI 操作提醒

先暂停一下。

常见来源：`.ai-hooks/`。

它通常在提醒：命令危险、高影响 git 操作、依赖安装或下载需要确认、可能误提交、写后脏文件静态问题、改 RAG 后忘同步数据、改名后引用没跟上，以及本次改动应和用户确认采用的范式/思想。

### 5. 看起来像测试失败

让 AI 先判断失败类型。

常见来源：pytest。

测试失败可能是功能坏了、环境不对，也可能是测试过期。测试通过也不等于需求完整。

## 你不用记的事

这些由 AI 和 CI 维护：

- 哪个工具在 pre-commit 跑。
- 哪个工具在 CI 跑。
- 本地、pre-commit、CI 统一从 `tools/check.py` 调度，避免同一条命令散落多处。
- 只要改工具、hook、CI、pre-commit 或 Semgrep，pre-commit 会强制跑工具契约检查。
- hook 是否已注册。
- semgrep 文件是否已登记。
- registry 和文档是否漂移。

如果你怀疑这些东西乱了，直接让 AI 检查“工具契约”。

## 给 AI 维护时看的文件

- `.ai-config/tooling.registry.toml`：机器登记表。
- `tools/check.py`：统一检查入口。
- `.ai-config/check_rule_tool_contracts.py`：自动检查脚本。
- `.ai-hooks/manifest.json`：hook 注册源。
- `.pre-commit-config.yaml`：本地提交前检查。
- `.github/workflows/ci.yml`：CI 检查。

人优先看本文；AI 维护时必须看上面这些文件。
