# 模块 8 线程提示词

以下内容可直接复制给独立 Codex 线程。

你当前负责 `D:\InformSystem` 的模块 8：反馈层（Feedback）。

你的工作目标：

- 基于系统总纲和契约文档，完成反馈层的设计收口，并在需要时推进实现。
- 你的模块负责记录事实、沉淀样本和导出优化输入，不负责重写线上判断。
- 重点是把用户反馈、投递结果和误判样本沉淀成结构化对象。

请按以下顺序阅读文档：

1. `D:\InformSystem\00_system_overview.md`
2. `D:\InformSystem\01_shared_schemas.md`
3. `D:\InformSystem\02_workflow_orchestration.md`
4. `D:\InformSystem\05_database_schema.md`
5. `D:\InformSystem\04_mock_and_integration_conventions.md`
6. `D:\InformSystem\docs\modules\80_feedback_module.md`
7. `D:\InformSystem\docs\modules\50_delivery_module.md`
8. `D:\InformSystem\docs\modules\40_decision_engine_module.md`
9. `D:\InformSystem\docs\modules\20_rule_engine_module.md`
10. `D:\InformSystem\docs\modules\30_ai_processing_module.md`

你在主链路中的位置：

- 你位于主链路尾部
- 你消费 `DeliveryLog`、用户反馈、必要时也引用 `DecisionResult`、`RuleAnalysisResult`、`AIAnalysisResult`
- 你负责生成 `UserFeedbackRecord` 和 `OptimizationSample`

你的上游参考：

- 用户主动反馈
- 发文层投递日志
- 决策层结果
- 规则层和 AI 层结果

你的下游参考：

- 规则优化流程
- AI 优化流程
- 效果分析

你必须重点保证：

- `UserFeedbackRecord` 和 `OptimizationSample` 严格对齐 `01_shared_schemas.md`
- 原始反馈事实不可丢失
- 反馈层失败不应阻塞线上主链路
- `user_feedback` 和 `optimization_samples` 表设计对齐 `05_database_schema.md`
- mock 样例能回接 golden flow

你绝对不要做：

- 不要在反馈层直接修改线上决策结果
- 不要直接覆盖已有规则结论
- 不要只保留统计结果而丢失原始反馈
- 不要把优化逻辑耦合进线上投递流程

如果发现冲突，按下面规则处理：

- 如果你觉得某个反馈类型缺失，先检查 `01_shared_schemas.md` 的枚举
- 如果你想新增样本字段，先判断是否属于共享对象
- 如果你发现需要联动多张表，请以 `05_database_schema.md` 的主键和关联字段为准

本线程建议交付：

- 反馈对象和优化样本语义收口
- 用户反馈 API 设计
- delivery outcome 回流方案
- 样本导出方案和 mock
- 如果被要求实现，再提交 feedback service、repository、测试和导出能力

