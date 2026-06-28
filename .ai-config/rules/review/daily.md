# 每日体检·执行(地板;人触发;范围=工作区 vs HEAD)

执行(机器跑+我收尾,默认不派子agent):
1. 跑 `./sweep`(=tools/sweep.py)→ 产 `logs/sweep-report-<ts>.md`(机器闸 ruff/import-linter/vulture/radon + 死码+扇入+漂移)。读它。
2. **死码(名单外)**:每条 grep 自验——全仓零 live caller、无 `getattr`/`__all__`/字符串动态分发。按报告 git 年龄:老=删、新=留(WIP)。≤3 条主循环 grep 删;>3 或牵连复杂→派 refuter。删后重跑 `./sweep` 收级联孤儿。
3. **放行 pending**:新提议分类(假阳性 / 预留API / 延迟清)写 `.vulture_whitelist.pending`,摆给人批;**闸保持红,不自动加白名单**。
4. **漂移红**(超行棘轮 / skip / 白名单涨):**不修**,记待办 → 提示人是否贴 `stage.md`。

禁:碰设计层(L1–L3 是 stage 的活)、批放行登记、动 main(改在工作分支)。

`[强制产物]`:`logs/sweep-report-<ts>.md` + `.vulture_whitelist.pending` + 待办(标:已删死码 / 漂移红是否转 stage)。
