# 模块 1 线程提示词

以下内容可直接复制给独立 Codex 线程。

你当前负责 `D:\InformSystem` 的模块 1：接入层（Ingestion）。

你的工作目标：

- 基于系统总纲和契约文档，完成接入层的设计收口、接口一致性检查和必要的实现推进。
- 你的模块是整个系统的唯一通知入口，重点是“采集、标准化、接入去重、原始事件存储”。
- 默认不要把规则判断、AI 判断、推送决策塞进接入层。

请按以下顺序阅读文档：

1. `D:\InformSystem\00_system_overview.md`
2. `D:\InformSystem\01_shared_schemas.md`
3. `D:\InformSystem\02_workflow_orchestration.md`
4. `D:\InformSystem\05_database_schema.md`
5. `D:\InformSystem\04_mock_and_integration_conventions.md`
6. `D:\InformSystem\docs\modules\10_ingestion_module.md`
7. `D:\InformSystem\docs\modules\70_config_module.md`
8. `D:\InformSystem\docs\modules\20_rule_engine_module.md`

你在主链路中的位置：

- 外部来源 -> 接入层 -> `SourceEvent` -> 编排层 / 规则层
- 你负责生成 `SourceEvent`
- 你不负责事件和用户的配对，这属于编排层
- `replay` 的语义是“从 `SourceEvent` 之后重新进入主链路”，不是重新抓外部平台

你的上游参考：

- 外部通知来源
- 配置层提供的 `SourceConfig`

你的下游参考：

- 编排层
- 规则层
- `raw_events`

你必须重点保证：

- `SourceEvent` 严格对齐 `01_shared_schemas.md`
- 不泄漏平台细节给下游
- 支持 connector 抽象
- 支持 webhook、拉取型来源、手动导入和 replay
- 去重语义和 `raw_events` 表设计对齐 `05_database_schema.md`
- mock 输入输出和 golden flow 目录对齐 `04_mock_and_integration_conventions.md`

你绝对不要做：

- 不判断通知是否与用户相关
- 不判断是否重要
- 不调用 AI
- 不做最终推送决策
- 不在 connector 里写用户画像逻辑

如果发现冲突，按下面规则处理：

- 共享对象字段冲突：参考 `01_shared_schemas.md`，默认不要私自改字段名
- 主流程责任冲突：参考 `02_workflow_orchestration.md`，不要把事件-用户配对拉进接入层
- 存储字段冲突：参考 `05_database_schema.md`

本线程建议交付：

- 接入层设计收口结论
- 接入接口和 connector 抽象检查结果
- `SourceEvent` 对齐结果
- mock / 测试 / replay 方案
- 如果被要求实现，再提交代码、测试和 demo

