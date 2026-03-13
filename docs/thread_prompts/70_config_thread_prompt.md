# 模块 7 线程提示词

以下内容可直接复制给独立 Codex 线程。

你当前负责 `D:\InformSystem` 的模块 7：配置层（Config）。

你的工作目标：

- 基于系统总纲和契约文档，完成配置层的设计收口，并在需要时推进实现。
- 你的模块是系统统一配置源，负责版本、审计和读取，不负责执行业务逻辑。
- 重点是让各模块通过统一接口读取来源配置、规则配置、类别配置和推送策略。

请按以下顺序阅读文档：

1. `D:\InformSystem\00_system_overview.md`
2. `D:\InformSystem\01_shared_schemas.md`
3. `D:\InformSystem\02_workflow_orchestration.md`
4. `D:\InformSystem\05_database_schema.md`
5. `D:\InformSystem\04_mock_and_integration_conventions.md`
6. `D:\InformSystem\docs\modules\70_config_module.md`
7. `D:\InformSystem\docs\modules\10_ingestion_module.md`
8. `D:\InformSystem\docs\modules\20_rule_engine_module.md`
9. `D:\InformSystem\docs\modules\40_decision_engine_module.md`
10. `D:\InformSystem\docs\modules\50_delivery_module.md`

你在主链路中的位置：

- 你不在主链路上直接处理通知
- 你的工作是为接入层、规则层、决策层和发文层提供统一配置对象
- 你需要保证配置读取稳定、版本明确、变更可审计

你的上游参考：

- 管理后台
- 本地配置
- 运维或开发维护

你的下游参考：

- 接入层读取 `SourceConfig`
- 规则层读取 `RuleConfig`
- 决策层读取 `PushPolicyConfig`
- 发文层读取渠道和模板配置

你必须重点保证：

- 配置对象语义和模块文档一致
- 配置版本和审计清晰
- 支持数据库与本地文件双实现
- `source_configs`、`rule_configs`、`notification_category_configs`、`push_policy_configs`、`config_change_logs` 与 `05_database_schema.md` 对齐
- 不让各模块维护私有规则副本

你绝对不要做：

- 不要在配置层执行业务规则
- 不要把推送逻辑直接写进配置管理流程
- 不要修改配置后没有版本记录
- 不要让每个模块各自扩展一套不兼容的配置结构

如果发现冲突，按下面规则处理：

- 如果不同模块对同一配置对象理解不一致，优先统一契约，不要给每个模块单独兼容
- 如果你要新增跨模块配置对象，先确认是否需要补 `01_shared_schemas.md`
- 如果你发现某配置只是某个模块内部细节，可以留在模块内部，不要强行公共化

本线程建议交付：

- 配置对象边界收口
- 配置版本和审计方案
- 双实现读取方案
- 配置 mock 和发布 / 回滚流程
- 如果被要求实现，再提交 config service、repository、cache、测试和 mock

