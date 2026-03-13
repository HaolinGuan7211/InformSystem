# 模块 4 线程提示词

以下内容可直接复制给独立 Codex 线程。

你当前负责 `D:\InformSystem` 的模块 4：决策层（Decision Engine）。

你的工作目标：

- 基于系统总纲和契约文档，完成决策层的设计收口，并在需要时推进实现。
- 你的模块是最终业务裁定入口，负责把规则结果、AI 结果、画像和策略统一收束为 `DecisionResult`。
- 重点是统一动作语义、优先级语义和可解释证据。

请按以下顺序阅读文档：

1. `D:\InformSystem\00_system_overview.md`
2. `D:\InformSystem\01_shared_schemas.md`
3. `D:\InformSystem\02_workflow_orchestration.md`
4. `D:\InformSystem\05_database_schema.md`
5. `D:\InformSystem\04_mock_and_integration_conventions.md`
6. `D:\InformSystem\docs\modules\40_decision_engine_module.md`
7. `D:\InformSystem\docs\modules\20_rule_engine_module.md`
8. `D:\InformSystem\docs\modules\30_ai_processing_module.md`
9. `D:\InformSystem\docs\modules\50_delivery_module.md`
10. `D:\InformSystem\docs\modules\60_user_profile_module.md`
11. `D:\InformSystem\docs\modules\70_config_module.md`

你在主链路中的位置：

- `SourceEvent + RuleAnalysisResult + AIAnalysisResult? + UserProfile -> DecisionResult`
- 你必须接受 `ai_result = None` 的情况
- 最终 `decision_action` 只能由你统一给出
- 发文层只执行你给出的动作，不重新做业务判断

你的上游参考：

- 规则层
- AI 层
- 用户画像层
- 配置层的推送策略

你的下游参考：

- 发文层
- 反馈层
- `decision_results`

你必须重点保证：

- `DecisionResult` 严格对齐 `01_shared_schemas.md`
- `decision_action`、`priority_level`、`delivery_timing` 必须使用共享枚举
- 决策依据可解释、可追溯
- 同一输入在同一 `policy_version` 下输出稳定一致
- `decision_results` 的自然幂等键和 `05_database_schema.md` 对齐

你绝对不要做：

- 不要直接发消息
- 不要把最终动作判断散到其他模块
- 不要要求 AI 一定存在
- 不要在决策层重新实现来源抓取或规则执行

如果发现冲突，按下面规则处理：

- 如果你想新增动作类型，先修改共享枚举设计再推进
- 如果你想让发文层重新判定动作，先停下，这违背当前主链路责任
- 如果你想让规则层直接输出最终动作，先停下，这违背当前分层约束

本线程建议交付：

- 决策层输入输出契约检查
- 优先级与动作映射说明
- 无 AI 降级策略
- 可解释证据结构
- 如果被要求实现，再提交决策服务、策略读取、测试和 mock

