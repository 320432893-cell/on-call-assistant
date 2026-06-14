# 第一版基线模型摘要

## 结论

- 已在 reviewed 建模表上训练 4 个候选模型。
- 按验证集选择的模型：`dummy_mean`，test MAE = 0.0722，Spearman IC = 0.0000。
- 训练只使用 `reviewed_keep_for_training=1` 的主模型/clean 样本，未引入手工复核字段作为特征。
- 本次训练入口：`market-impact-study/data/processed/modeling/modeling_dataset_enhanced_v2.csv`，入模特征 136 个。
- 对线性/树模型均使用训练集 1%/99% 分位数截尾；原始财务规模列默认不入主模型，避免尺度和极端值污染。

## 数据规模

| split | rows |
| --- | --- |
| test | 164 |
| train | 300 |
| valid | 34 |

## 测试集模型对比

| model_name | n | mae | rmse | r2 | spearman_ic | directional_accuracy |
| --- | --- | --- | --- | --- | --- | --- |
| dummy_mean | 164.0 | 0.07222423075291447 | 0.10412667202073508 | -0.0032529999246024843 | 0.0 | 0.6158536585365854 |
| ridge | 164.0 | 0.09352848073710034 | 0.11883230777378766 | -0.30663880974604774 | 0.00892918479147749 | 0.4268292682926829 |
| elasticnet | 164.0 | 0.07222423075291447 | 0.10412667202073508 | -0.0032529999246024843 | 0.0 | 0.6158536585365854 |
| hist_gradient_boosting | 164.0 | 0.08099304795869326 | 0.10762620595805737 | -0.07182171667613613 | 0.08543057754157707 | 0.4329268292682927 |

## 特征组消融

| feature_set | model_name | feature_count | mae_valid | mae_test | spearman_ic_test | directional_accuracy_test |
| --- | --- | --- | --- | --- | --- | --- |
| base_plus_management | hist_gradient_boosting | 58 | 0.06660266887125739 | 0.07967288928201793 | 0.061250572194504055 | 0.5548780487804879 |
| base_only | dummy_mean | 46 | 0.06809253278448324 | 0.07222423075291447 | 0.0 | 0.6158536585365854 |
| base_plus_event_intensity | dummy_mean | 72 | 0.06809253278448324 | 0.07222423075291447 | 0.0 | 0.6158536585365854 |
| base_plus_financial_quality | dummy_mean | 58 | 0.06809253278448324 | 0.07222423075291447 | 0.0 | 0.6158536585365854 |
| base_plus_peer_market | dummy_mean | 86 | 0.06809253278448324 | 0.07222423075291447 | 0.0 | 0.6158536585365854 |
| base_plus_trading | dummy_mean | 63 | 0.06809253278448324 | 0.07222423075291447 | 0.0 | 0.6158536585365854 |
| full_safe | dummy_mean | 136 | 0.06809253278448324 | 0.07222423075291447 | 0.0 | 0.6158536585365854 |

## 误差较大的测试样本

| model_name | analysis_group_id | split | y_true | y_pred | abs_error | primary_category | title |
| --- | --- | --- | --- | --- | --- | --- | --- |
| elasticnet | 002970|2026-01-28|产品/技术创新 | test | 0.4762822064175547 | -0.01900901670280843 | 0.4952912231203631 | 产品/技术创新 | 锐明技术 线上 2026年1月28日 |
| elasticnet | 002970|2026-01-28|管理层/投关信号 | test | 0.4762822064175547 | -0.01900901670280843 | 0.4952912231203631 | 管理层/投关信号 | 投资者关系管理信息20260128 |
| dummy_mean | 002970|2026-01-28|管理层/投关信号 | test | 0.4762822064175547 | -0.01900901670280843 | 0.4952912231203631 | 管理层/投关信号 | 投资者关系管理信息20260128 |
| dummy_mean | 002970|2026-01-28|产品/技术创新 | test | 0.4762822064175547 | -0.01900901670280843 | 0.4952912231203631 | 产品/技术创新 | 锐明技术 线上 2026年1月28日 |
| hist_gradient_boosting | 002970|2026-01-28|产品/技术创新 | test | 0.4762822064175547 | 0.06434412345166796 | 0.41193808296588674 | 产品/技术创新 | 锐明技术 线上 2026年1月28日 |
| hist_gradient_boosting | 002970|2026-01-28|管理层/投关信号 | test | 0.4762822064175547 | 0.06434412345166796 | 0.41193808296588674 | 管理层/投关信号 | 投资者关系管理信息20260128 |
| ridge | 002970|2026-01-28|产品/技术创新 | test | 0.4762822064175547 | 0.10930222473832668 | 0.366979981679228 | 产品/技术创新 | 锐明技术 线上 2026年1月28日 |
| ridge | 002970|2026-01-28|管理层/投关信号 | test | 0.4762822064175547 | 0.12823047185447595 | 0.34805173456307875 | 管理层/投关信号 | 投资者关系管理信息20260128 |
| ridge | 002970|2025-01-15|业绩信号 | test | -0.2908361002854698 | 0.05239959213683341 | 0.34323569242230323 | 业绩信号 | 预增 预计:净利润28000-29700 |
| ridge | 300098|2025-01-04|其他 | test | -0.2901091398318361 | 0.029587008061642994 | 0.3196961478934791 | 其他 | 关于下属孙公司为控股子公司申请银行授信提供担保的公告 |
| hist_gradient_boosting | 300098|2025-01-04|其他 | test | -0.2901091398318361 | 0.002882219678842839 | 0.29299135951067895 | 其他 | 关于下属孙公司为控股子公司申请银行授信提供担保的公告 |
| hist_gradient_boosting | 603236|2025-01-24|管理层/投关信号 | test | -0.226961817489418 | 0.05277303241254493 | 0.2797348499019629 | 管理层/投关信号 | 投资者关系活动记录表2025年1月 |
| ridge | 603236|2025-01-24|管理层/投关信号 | test | -0.226961817489418 | 0.051300046181605226 | 0.27826186367102324 | 管理层/投关信号 | 投资者关系活动记录表2025年1月 |
| elasticnet | 002970|2025-01-15|业绩信号 | test | -0.2908361002854698 | -0.01900901670280843 | 0.2718270835826614 | 业绩信号 | 预增 预计:净利润28000-29700 |
| dummy_mean | 002970|2025-01-15|业绩信号 | test | -0.2908361002854698 | -0.01900901670280843 | 0.2718270835826614 | 业绩信号 | 预增 预计:净利润28000-29700 |
| dummy_mean | 300098|2025-01-04|其他 | test | -0.2901091398318361 | -0.01900901670280843 | 0.2711001231290277 | 其他 | 关于下属孙公司为控股子公司申请银行授信提供担保的公告 |
| elasticnet | 300098|2025-01-04|其他 | test | -0.2901091398318361 | -0.01900901670280843 | 0.2711001231290277 | 其他 | 关于下属孙公司为控股子公司申请银行授信提供担保的公告 |
| hist_gradient_boosting | 002970|2025-01-15|业绩信号 | test | -0.2908361002854698 | -0.023108427216795444 | 0.26772767306867434 | 业绩信号 | 预增 预计:净利润28000-29700 |
| ridge | 300590|2024-12-30|产品/技术创新 | test | -0.2190197526698241 | 0.04443810244513389 | 0.263457855114958 | 产品/技术创新 | 关于理财产品到期赎回及继续使用闲置募集资金和自有资金进行现金管理的公告 |
| ridge | 300590|2025-02-10|资本动作 | test | -0.1458921511594333 | 0.10598466332728929 | 0.2518768144867226 | 资本动作 | 关于公司控股股东、实际控制人及部分高级管理人员股份减持计划的预披露公告 |

## 模型注册表

```json
{
  "target": "relative_mv_return_p0_p20",
  "input_dataset": "market-impact-study/data/processed/modeling/modeling_dataset_enhanced_v2.csv",
  "selection_split": "valid",
  "training_splits": [
    "train",
    "valid",
    "test"
  ],
  "feature_count": 136,
  "features": [
    "source_count",
    "evidence_count",
    "group_event_count",
    "group_source_count",
    "group_evidence_count",
    "keyword_score_num",
    "source_weight_num",
    "signal_strength_num",
    "has_pdf_num",
    "pre_total_mv_yi",
    "text_char_len",
    "text_digit_count",
    "text_percent_count",
    "text_money_word_count",
    "text_risk_keyword_count",
    "text_has_risk_keyword",
    "text_growth_keyword_count",
    "text_has_growth_keyword",
    "text_capital_keyword_count",
    "text_has_capital_keyword",
    "text_ir_keyword_count",
    "text_has_ir_keyword",
    "text_tech_keyword_count",
    "text_has_tech_keyword",
    "text_order_keyword_count",
    "text_has_order_keyword",
    "text_policy_keyword_count",
    "text_has_policy_keyword",
    "text_finance_keyword_count",
    "text_has_finance_keyword",
    "category_业绩信号",
    "category_产品/技术创新",
    "category_其他",
    "category_客户/订单",
    "category_政策/行业",
    "category_管理层/投关信号",
    "category_资本动作",
    "category_风险事件",
    "source_has_announcement",
    "source_has_express",
    "source_has_forecast",
    "source_has_institution_survey",
    "source_has_irm_qa",
    "source_has_news",
    "source_has_repurchase",
    "source_has_research_report",
    "bal_current_ratio",
    "bal_liability_to_assets",
    "cf_operating_cash_to_assets",
    "fin_bps",
    "fin_days_since_report",
    "fin_grossprofit_margin",
    "fin_netprofit_margin",
    "fin_ocfps",
    "fin_rd_exp",
    "fin_roa",
    "fin_roe",
    "inc_net_margin_calc",
    "mgmt_institution_count_sum_m180",
    "mgmt_institution_count_sum_m30",
    "mgmt_institution_count_sum_m90",
    "mgmt_ir_qa_count_m180",
    "mgmt_ir_qa_count_m30",
    "mgmt_ir_qa_count_m90",
    "mgmt_signal_count_m180",
    "mgmt_signal_count_m30",
    "mgmt_signal_count_m90",
    "mgmt_survey_count_m180",
    "mgmt_survey_count_m30",
    "mgmt_survey_count_m90",
    "volume_ratio_pre",
    "amount_avg_m20_m1",
    "amount_avg_m5_m1",
    "amount_avg_m60_m1",
    "log_total_mv_pre",
    "mkt_ret_m20_m1",
    "mkt_ret_m5_m1",
    "mkt_ret_m60_m1",
    "pb_pre",
    "pe_pre",
    "peer_avg_log_total_mv_pre",
    "peer_avg_pb_pre",
    "peer_avg_pe_pre",
    "peer_avg_ps_pre",
    "peer_avg_ret_m20_m1",
    "peer_avg_ret_m5_m1",
    "peer_avg_ret_m60_m1",
    "peer_avg_turnover_avg_m20_m1",
    "peer_avg_turnover_avg_m5_m1",
    "peer_avg_turnover_avg_m60_m1",
    "ps_pre",
    "rel_to_peer_log_total_mv_pre",
    "rel_to_peer_pb_pre",
    "rel_to_peer_pe_pre",
    "rel_to_peer_ps_pre",
    "rel_to_peer_ret_m20_m1",
    "rel_to_peer_ret_m5_m1",
    "rel_to_peer_ret_m60_m1",
    "rel_to_peer_turnover_avg_m20_m1",
    "rel_to_peer_turnover_avg_m5_m1",
    "rel_to_peer_turnover_avg_m60_m1",
    "ret_m20_m1",
    "ret_m5_m1",
    "ret_m60_m1",
    "turnover_avg_m20_m1",
    "turnover_avg_m5_m1",
    "turnover_avg_m60_m1",
    "volatility_m20_m1",
    "volatility_m5_m1",
    "volatility_m60_m1",
    "evt_is_contract_order",
    "evt_is_earnings_report",
    "evt_is_forecast",
    "evt_is_impairment",
    "evt_is_inquiry",
    "evt_is_ir_activity",
    "evt_is_litigation_penalty",
    "evt_is_pledge",
    "evt_is_product_launch",
    "evt_is_repurchase",
    "evt_is_restructuring",
    "evt_is_subsidy",
    "evt_money_count",
    "evt_money_max_to_mv",
    "evt_money_max_yi",
    "evt_money_sum_yi",
    "evt_negative_word_count",
    "evt_percent_count",
    "evt_percent_max_abs",
    "evt_percent_mean",
    "evt_positive_word_count",
    "evt_profit_direction",
    "evt_profit_high_yi",
    "evt_profit_low_yi",
    "evt_profit_mid_to_mv",
    "evt_profit_mid_yi"
  ],
  "excluded_raw_scale_features": [
    "bal_total_assets",
    "bal_total_cur_assets",
    "bal_total_cur_liab",
    "bal_total_hldr_eqy_inc_min_int",
    "bal_total_liab",
    "cf_c_cash_equ_end_period",
    "cf_n_cashflow_act",
    "circ_mv_pre",
    "inc_n_income_attr_p",
    "inc_total_revenue",
    "total_mv_pre"
  ],
  "models": [
    {
      "model_name": "dummy_mean",
      "selected_on": "valid",
      "feature_count": 136
    },
    {
      "model_name": "ridge",
      "selected_on": "valid",
      "feature_count": 136,
      "best_params": {
        "alpha": 100.0
      },
      "best_valid_mae": 0.07244758991786539
    },
    {
      "model_name": "elasticnet",
      "selected_on": "valid",
      "feature_count": 136,
      "best_params": {
        "alpha": 0.05,
        "l1_ratio": 0.5
      },
      "best_valid_mae": 0.06809253278448324
    },
    {
      "model_name": "hist_gradient_boosting",
      "selected_on": "valid",
      "feature_count": 136,
      "best_params": {
        "learning_rate": 0.03,
        "max_depth": 2,
        "max_iter": 200,
        "min_samples_leaf": 20
      },
      "best_valid_mae": 0.07135812896736024
    }
  ]
}
```

## 使用边界

- 这是一版可解释 baseline，不代表最终最优结果。
- 树模型使用 sklearn 原生实现，不依赖额外安装的 LightGBM/XGBoost。
- 模型选择只看验证集；测试集仅用于最终外推评估。
- 如果后续补充文本 embedding 或更强树模型，需重新做时间外评估。
