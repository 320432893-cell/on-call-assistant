# TODO

## 当前阶段:CFO 拍板"先做一个事件看看"

range:**移为通信(我们公司) × 1 个事件**(具体哪个事件待选,见决策点 Q1)
工期:5 个全职工作日(单事件做透,SCM 第一次上手吃时间)
交付:一份 Jupyter notebook → nbconvert 双输出 HTML + PDF,7 个章节(见下)

---

## 单事件 demo — Day 1-5

### Day 1 — 事件选定 + 数据准备

- [ ] 与 CFO 确认/我提议:**移为通信最近一次成功定增**(数据新鲜、市场记忆清晰)
- [ ] tushare 拉取:
  - 移为通信 + 8 家同行的日频股价(前复权)、成交量、换手率
  - 申万通信指数成分股,**用于剔除 9 家后构造行业基准**
  - tushare `anns_d` 公告数据,查事件公告日 + 公告时间(精确到盘前/盘中/盘后)
- [ ] 事件卡(Excel):日期、定增金额、发行价折扣率、用途、是否成功、公告时间(精确到盘前/盘中/盘后)
- [ ] 输出:`market-impact-study/data/event_card.xlsx`

### Day 2 — 事件研究法主结果

- [ ] 估计窗口:[-250, -21] 天(rolling 250 日 β)
- [ ] 事件窗口:[-1, +5] 天
- [ ] 行业基准:**申万通信指数剔除 9 家后等权重新构造**(不用沪深 300,不用原始申万通信)
- [ ] 市场模型:`R_i = α + β × R_m + ε`,β 用 rolling 250 日估计
- [ ] 计算:AR、CAR + **bootstrap 95% CI**(`scipy.stats.bootstrap`)
- [ ] 残差诊断:正态性检验、自相关检验,记录在 notebook
- [ ] 工具:Python + pandas + statsmodels + scipy
- [ ] 输出:
  - 事件卡表(Day 1)+ CAR + bootstrap 95% CI + N
  - AR 柱状图 + CAR 折线双坐标(plotly HTML / matplotlib PDF 双版本)
  - 市场模型诊断图(残差 QQ + ACF)

### Day 3 — 合成控制反事实图 + placebo

- [ ] 工具:`pysyncon`(自带 placebo 功能)
- [ ] 输入:移为通信股价 + 同行业 8 家股价 + 行业基准
- [ ] 训练窗口 [-250, -21],预测窗口 [-1, +20]
- [ ] **placebo test 强制**:对 8 家**没有同期同类事件**的对照公司分别跑一遍 SCM
- [ ] 实线(移为通信)落在 placebo 分布外才算可信
- [ ] 输出:
  - SCM 反事实图(含 placebo 分布带,灰线)
  - placebo p 值表(实线偏离量 vs placebo 分布百分位)

### Day 4 — RAG 取证 + 报告骨架

- [ ] 用现有 RAG 栈(`app/services/{embedder,vectorstore,report_indexer}`)对移为通信近 3 年年报建索引
- [ ] 给定事件日期前后,查询年报里相关段落(如定增对应"募资用途""非公开发行"章节)
- [ ] 输出格式:`{事件 id, 年报年份, 章节, 原文片段, 相似度 score}` JSON
- [ ] 在 notebook 报告里嵌入相关段落作为原文锚点
- [ ] 报告骨架搭起来(7 章节,见 README 输出形态)

### Day 5 — nbconvert 输出 + CFO 演示彩排

- [ ] notebook 整体 review,Executive Summary 1 段
- [ ] nbconvert 输出 HTML(plotly 互动)+ PDF(matplotlib 静态)
- [ ] 验证两个版本视觉效果一致,关键图都能看
- [ ] backup 一张静态截图防演示翻车
- [ ] **彩排 10 分钟讲法**:事件描述 → CAR → SCM → 取证段落 → 结论 + 局限

---

## 第一周后状态盘点

**应有**:
- 1 份 Jupyter notebook(双输出 HTML + PDF)
- 1 张 CAR 事件窗口图 + bootstrap 95% CI
- 1 张 SCM 反事实图 + placebo 分布带
- 1 个事件配套年报原文锚点(2-3 段)
- 残差诊断 + placebo p 值表
- CFO 10 分钟演示稿

**不应有**(不要做):
- 完整 9 家公司 × 10 年事件库(属于第 2-4 周)
- GBoost / SHAP 模型(主线跑通后才加,样本量不够也不该现在做)
- Streamlit dashboard(第 3-4 周才做)
- LLM 自动归因 / 自然语言查询(整个项目不做,LLM 抽取由外部 claw 工具负责)

---

## 第 2-4 周(暂定,等第一周复盘后再细化)

- [ ] 扩展事件类型:定增 → 回购 / 股权激励 / 重大资产重组 / 大客户合同
- [ ] 扩展公司范围:1 家同行 → 9 家全覆盖
- [ ] **外部 claw 工具固定 schema 抽取事件库**(我们这边接收 JSON/Excel,人工校验 50-100 条作为评测金标准)
- [ ] 第二个研究问题:同行事件对我们公司的**传导效应**(注意:板块联动 vs 真实竞争效应难区分,需要更严谨的识别策略)
- [ ] 第三个研究问题:跨公司对标分析

## 第 5-6 周(暂定)

- [ ] GBoost + SHAP 作为**假设生成器**:
  - 跨 ≥5 seed 报告 importance 排名波动
  - 触发的新假设回到 CAR 子样本验证
- [ ] 9 公司热力图 + 雷达图 + 事件时间轴
- [ ] 预警 dashboard(规则触发,不需 LLM)

## 第 7-8 周(暂定)

- [ ] 终稿报告
- [ ] CFO 评审 + 迭代
- [ ] 可视化精修
- [ ] 项目交接文档

---

## 待回答的问题(决策点)

- [ ] **Q1**:第一个事件是哪个?提议"移为通信最近一次成功定增",待 CFO 确认或指定
- [ ] **Q2**:外部 claw 抽事件的 schema 是什么?我提议初版字段:
  ```
  {event_id, company, event_type, announce_date, announce_time(盘前/盘中/盘后),
   raw_text_anchor(年报章节锚点), amount, status, source_url}
  ```
  确认后我把它写成 Pydantic 模型作为数据契约
- [ ] **Q3**:`pysyncon` 第一次上手单天能跑完吗?backup 方案是 `causalimpact`(Bayesian 结构时间序列,API 更简单),要不要预留半天容错?
- [ ] **Q4**:CFO 验收节奏 — 每周一次 / 第一周末 / 阶段性?

---

## 规则建设(与 demo 并行,**不提前写**)

按 `.ai-config/rules/process/workflow.index.md` 和 `.ai-config/rules/rule_governance/governance.index.md` 的规则过滤原则,规则等真实踩坑后再写:

- 每完成一天 demo,把当天踩的坑记录到本 TODO 末尾
- 第一周结束后,提取真实痛点 → 更新 `.ai-config/rules/delivery/data.index.md`、`.ai-config/rules/engineering/code.index.md` 或新增已登记的专题规则
- 预计 2-3 份规则更新,总强制 ≤ 12 条
