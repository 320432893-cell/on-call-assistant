# 生产事故台账（INCIDENTS）

本文件是生产事故的 SSOT。`tools/check_regression.py` 机械校验：每个 `status=fixed` 的事故，必须有引用其 ID 的回归测试（测试里写 `# regression: INC-NNN` 或测试函数名含 `inc_NNN`），否则 CI 阻塞——"标了修好却没回归测试"不算修好。

## 登记格式

每行一个事故，状态列只允许 `open` / `fixed`：

```
| INC-001 | <一句话根因> | open\|fixed | <修复方式/PR> |
```

新增事故时只追加表格行；修复后把状态从 `open` 改为 `fixed`，并在 `tests/` 下补一个引用该 ID 的回归测试。

## 事故表

| ID | 根因 | 状态 | 修复 |
|---|---|---|---|
| INC-000 | 占位示例：台账建立，无真实事故 | open | 模板行，出现首个真实事故后可删 |
