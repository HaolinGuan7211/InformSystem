# 模块开发线程提示词

这个目录用于存放可直接复制给独立 Codex 线程的模块开发提示词。

## 使用方式

1. 给某个线程分配模块时，先把对应文件内容完整复制给它。
2. 线程默认工作目录为 `D:\InformSystem`。
3. 线程必须先阅读共享契约，再阅读自己的模块文档。
4. 如果线程发现跨模块契约问题，默认先提出问题或方案，不要静默改接口。

## 所有线程的公共阅读顺序

1. `D:\InformSystem\00_system_overview.md`
2. `D:\InformSystem\01_shared_schemas.md`
3. `D:\InformSystem\02_workflow_orchestration.md`
4. `D:\InformSystem\05_database_schema.md`
5. `D:\InformSystem\04_mock_and_integration_conventions.md`
6. 自己负责的模块文档
7. 自己的上游模块文档
8. 自己的下游模块文档

## 当前可用提示词

- `10_ingestion_thread_prompt.md`
- `20_rule_engine_thread_prompt.md`
- `30_ai_processing_thread_prompt.md`
- `40_decision_engine_thread_prompt.md`
- `50_delivery_thread_prompt.md`
- `60_user_profile_thread_prompt.md`
- `70_config_thread_prompt.md`
- `80_feedback_thread_prompt.md`

## 公共规则

- 共享对象和字段语义以 `01_shared_schemas.md` 为准。
- 主链路责任归属以 `02_workflow_orchestration.md` 为准。
- 数据库存储关系以 `05_database_schema.md` 为准。
- mock 和 golden flow 约定以 `04_mock_and_integration_conventions.md` 为准。
- 默认不要擅自修改 `01/02/05`；如果确实必须修改，先在结果中明确说明原因和影响。
- 默认先完成本模块设计收口、接口一致性检查和联调准备；如果任务明确要求实现，再推进代码。

