# AI Processing Module

这个目录提供 AI 处理层的当前阶段实现，遵守“规则粗筛优先，AI 两阶段精筛补充”的边界。

## 设计落点

- `service.py` 负责主流程。
  - 直接 `analyze()` 仍支持 `SourceEvent + RuleAnalysisResult + ProfileContext -> AIAnalysisResult`
  - `analyze_two_stage_or_fallback()` 负责“轻画像 Stage 1 + 重画像 Stage 2”
- `prompt_builder.py` 同时构造：
  - Stage 1：`event + rule_result + light_profile_tags`
  - Stage 2：`event + rule_result + profile_context (+ stage1_result)`
- `model_gateway.py` 提供 `MockModelGateway`、`HTTPModelGateway` 和 `KimiChatGateway`
- `result_validator.py` 负责结果校验、置信度清洗，以及把 `relevance_hint` 收口到 `relevant / irrelevant / uncertain`
- `repositories/ai_analysis_repository.py` 负责 `ai_analysis_results` 和 `ai_call_logs`
- `cache.py` 提供进程内缓存，避免相同自然键重复调用模型

## 两阶段语义

- Stage 1 默认只消费轻画像 tag：
  - `college`
  - `major`
  - `grade`
  - `degree_level`
  - `identity_tags`
  - `current_course_tags`
  - `current_task_tags`
- Stage 1 只负责输出：
  - `irrelevant / candidate / relevant`
  - `required_profile_facets`
  - 简短原因
- 只有 Stage 1 判定值得继续时，workflow 才会构建重画像 `ProfileContext`
- Stage 2 才消费 `ProfileContext.payload`，输出最终 `AIAnalysisResult`

## 契约边界

- AI 层默认只消费 `ProfileContext.payload`，不会直接读取完整 `UserProfile`
- `ProfileContext.facets` 需要和规则层输出的 `required_profile_facets` 对齐
- 如因兼容模式或上下文扩张引入额外画像信息，原因必须写入 `metadata`
- `analyze_or_fallback()` 和 `analyze_two_stage_or_fallback()` 都允许返回 `None`，AI 失败不应阻塞主链路

## Runtime 与审计

- `enabled=false` 时：
  - AI service 不触发 gateway
  - workflow 会在 AI 前短路
  - `ai_call_logs.status = "skipped"`
- `max_retries` 只作用于模型调用阶段，只对 `ModelGatewayError` 生效
- 双阶段结果会在 `metadata` 留下：
  - `analysis_stage`
  - `analysis_path`
  - `stage1_relevance_hint`
  - `stage1_required_profile_facets`

## Mock 与 Golden Flow

- 模块 mock 放在 `mocks/ai_processing/`
- `graduation_material_submission` 场景与共享 golden flow `flow_001_graduation_material_submission` 对齐
- AI golden 现在按共享契约输出标准化 `relevance_hint`
