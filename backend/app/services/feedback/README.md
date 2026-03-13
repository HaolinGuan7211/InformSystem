# Feedback Module

模块 8 负责记录用户反馈、回收投递结果，并把这些事实沉淀成可导出的 `OptimizationSample`。

## 已实现内容

- `FeedbackReceiver` 负责把原始 payload 标准化为 `UserFeedbackRecord`
- `SQLiteFeedbackRepository` 和 `SQLiteOptimizationSampleRepository` 持久化反馈记录与优化样本
- `SQLiteDeliveryLogRepository` 回收 `DeliveryLog`，为反馈层组装样本提供查询入口
- `SampleAssembler` 将反馈、投递、规则、AI、决策结果拼接为结构化优化样本
- `FeedbackExporter` 提供按 `source` 和 `outcome_label` 的导出能力
- `FeedbackService` 统一封装用户反馈写入、delivery outcome 回流和样本导出
