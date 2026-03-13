# 模块 2 线程提示词

以下内容可直接复制给独立 Codex 线程。

你当前负责 `D:\InformSystem` 的模块 2：规则层（Rule Engine）。

你的工作目标：

- 基于系统总纲和契约文档，完成规则层的设计收口，并在需要时推进实现。
- 你的模块负责“结构化分析与初筛”，不是最终决策模块。
- 重点是对单个 `(SourceEvent, UserProfile)` 对输出稳定、可解释的 `RuleAnalysisResult`。

请按以下顺序阅读文档：

1. `D:\InformSystem\00_system_overview.md`
2. `D:\InformSystem\01_shared_schemas.md`
3. `D:\InformSystem\02_workflow_orchestration.md`
4. `D:\InformSystem\05_database_schema.md`
5. `D:\InformSystem\04_mock_and_integration_conventions.md`
6. `D:\InformSystem\docs\modules\20_rule_engine_module.md`
7. `D:\InformSystem\docs\modules\10_ingestion_module.md`
8. `D:\InformSystem\docs\modules\60_user_profile_module.md`
9. `D:\InformSystem\docs\modules\30_ai_processing_module.md`
10. `D:\InformSystem\docs\modules\40_decision_engine_module.md`
11. `D:\InformSystem\docs\modules\70_config_module.md`

你在主链路中的位置：

- `SourceEvent + UserProfile -> RuleAnalysisResult`
- 你不负责枚举用户，也不负责把事件配给用户
- 事件与用户的配对责任属于编排层，不属于规则层
- 你可以输出 `should_invoke_ai`，但是否真的调用 AI 由编排层决定

你的上游参考：

- 接入层提供的 `SourceEvent`
- 用户画像层提供的 `UserProfile`
- 配置层提供的规则配置

你的下游参考：

- AI 处理层
- 决策层
- `rule_analysis_results`

你必须重点保证：

- `RuleAnalysisResult` 严格对齐 `01_shared_schemas.md`
- 规则输出必须可解释
- 对相同输入和相同规则版本输出稳定一致
- `should_invoke_ai` 只是建议标记，不是直接调用行为
- 规则配置语义和 `rule_configs` 表设计对齐 `05_database_schema.md`
- mock 至少覆盖 `SourceEvent + UserProfile -> RuleAnalysisResult`

你绝对不要做：

- 不要在规则层枚举所有用户
- 不要直接调用外部推送渠道
- 不要直接做最终 `decision_action`
- 不要把 AI 当成规则层内部强依赖

如果发现冲突，按下面规则处理：

- 如果你觉得接口应该变成“单事件对多用户”，先停下；这属于编排层问题，参考 `02_workflow_orchestration.md`
- 如果要新增共享字段，先提出变更建议，不要直接漂移 `RuleAnalysisResult`
- 如果类别、阈值、规则组织不清晰，优先约束在配置层，不要在规则层私有化

本线程建议交付：

- 规则层输入输出契约检查
- 规则执行边界说明
- 单用户分析主流程设计
- 可解释字段和 AI 门控策略
- 如果被要求实现，再提交规则执行器、配置读取、测试和 mock

