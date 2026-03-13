# 模块 3 线程提示词

以下内容可直接复制给独立 Codex 线程。

你当前负责 `D:\InformSystem` 的模块 3：AI 处理层（AI Processing）。

你的工作目标：

- 基于系统总纲和契约文档，完成 AI 层的设计收口，并在需要时推进实现。
- 你的模块是“规则优先、AI 辅助”路线中的补充理解层，不是唯一判断层。
- 重点是把复杂语义理解、字段抽取和摘要生成，沉淀为结构化的 `AIAnalysisResult`。

请按以下顺序阅读文档：

1. `D:\InformSystem\00_system_overview.md`
2. `D:\InformSystem\01_shared_schemas.md`
3. `D:\InformSystem\02_workflow_orchestration.md`
4. `D:\InformSystem\05_database_schema.md`
5. `D:\InformSystem\04_mock_and_integration_conventions.md`
6. `D:\InformSystem\docs\modules\30_ai_processing_module.md`
7. `D:\InformSystem\docs\modules\20_rule_engine_module.md`
8. `D:\InformSystem\docs\modules\40_decision_engine_module.md`
9. `D:\InformSystem\docs\modules\60_user_profile_module.md`
10. `D:\InformSystem\docs\modules\70_config_module.md`

你在主链路中的位置：

- `SourceEvent + RuleAnalysisResult + UserProfile -> AIAnalysisResult`
- 你不会自行决定何时触发
- 规则层输出 `should_invoke_ai`，编排层才决定是否真的调用你
- 当 AI 失败或被跳过时，主链路仍必须继续

你的上游参考：

- `SourceEvent`
- `RuleAnalysisResult`
- `UserProfile`
- 配置层提供的模型配置和 Prompt 模板

你的下游参考：

- 决策层
- `ai_analysis_results`
- `ai_call_logs`

你必须重点保证：

- `AIAnalysisResult` 严格对齐 `01_shared_schemas.md`
- 输出必须保留 `model_name` 和 `prompt_version`
- 支持 mock 模型和真实模型网关双模式
- 输出必须可校验、可审计、可降级
- 原始模型输出不能直接泄漏给下游业务对象

你绝对不要做：

- 不要让 AI 自己触发自己
- 不要让 AI 直接输出最终 `decision_action`
- 不要绕过规则层直接主导线上裁决
- 不要把未经校验的自由文本直接交给决策层

如果发现冲突，按下面规则处理：

- 如果你觉得 AI 一定要参与主链路，先停下；这和 `02_workflow_orchestration.md` 冲突
- 如果你想新增字段，先判断是否属于共享对象，必要时先提共享契约修改建议
- 如果模型配置和 Prompt 版本管理不清晰，优先归口配置层

本线程建议交付：

- AI 层输入输出契约检查
- Prompt / model gateway / validator 设计
- AI 降级和缓存策略
- mock 响应和 golden flow 对齐方案
- 如果被要求实现，再提交网关抽象、mock 模型、测试和持久化

