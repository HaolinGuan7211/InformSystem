# 模块 5 线程提示词

以下内容可直接复制给独立 Codex 线程。

你当前负责 `D:\InformSystem` 的模块 5：发文层（Delivery）。

你的工作目标：

- 基于系统总纲和契约文档，完成发文层的设计收口，并在需要时推进实现。
- 你的模块负责“执行触达”，不是“决定是否触达”。
- 重点是把 `DecisionResult` 转成实际投递动作，并保证幂等、重试和日志完整。

请按以下顺序阅读文档：

1. `D:\InformSystem\00_system_overview.md`
2. `D:\InformSystem\01_shared_schemas.md`
3. `D:\InformSystem\02_workflow_orchestration.md`
4. `D:\InformSystem\05_database_schema.md`
5. `D:\InformSystem\04_mock_and_integration_conventions.md`
6. `D:\InformSystem\docs\modules\50_delivery_module.md`
7. `D:\InformSystem\docs\modules\40_decision_engine_module.md`
8. `D:\InformSystem\docs\modules\60_user_profile_module.md`
9. `D:\InformSystem\docs\modules\80_feedback_module.md`
10. `D:\InformSystem\docs\modules\70_config_module.md`

你在主链路中的位置：

- `DecisionResult -> DeliveryTask / DeliveryLog -> 外部渠道`
- 你只执行 `push_now`、`push_high`、`digest`
- `archive` 和 `ignore` 不进入实际外部发送

你的上游参考：

- 决策层输出的 `DecisionResult`
- `SourceEvent`
- `UserProfile`
- 配置层提供的渠道配置和模板配置

你的下游参考：

- 外部发送渠道
- 反馈层
- `delivery_logs`

你必须重点保证：

- `DeliveryTask` 和 `DeliveryLog` 严格对齐 `01_shared_schemas.md`
- 只消费共享动作枚举，不自行发明动作
- 支持幂等和重试
- 支持即时提醒和 digest 两类任务
- 投递日志和 `delivery_logs` 表设计对齐 `05_database_schema.md`
- mock 输出能接到 golden flow

你绝对不要做：

- 不要重新判断通知是否重要
- 不要在发文层改变 `decision_action`
- 不要把渠道 SDK 调用散落到业务代码各处
- 不要丢失失败日志

如果发现冲突，按下面规则处理：

- 如果你觉得某类动作应直接忽略，请先回到决策层约束，不要在发文层临时处理
- 如果你想新增投递状态，先看 `01_shared_schemas.md`
- 如果你想调整 digest 语义，先确认不影响 `02_workflow_orchestration.md`

本线程建议交付：

- 发文层执行边界说明
- 渠道路由、消息渲染、幂等与重试方案
- 即时提醒与 digest 的接口收口
- mock 渠道和投递日志方案
- 如果被要求实现，再提交网关抽象、日志持久化、测试和 mock

