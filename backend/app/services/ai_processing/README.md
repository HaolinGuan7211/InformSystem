# AI Processing Module

该目录提供 AI 处理层的最小可运行实现，遵循“规则优先、AI 辅助”的边界约束。

## 设计落点

- `service.py` 负责主流程，输入 `SourceEvent + RuleAnalysisResult + UserProfile`，输出 `AIAnalysisResult`
- `prompt_builder.py` 统一构造 prompt，并保留 `prompt_version`
- `model_gateway.py` 提供 `MockModelGateway` 和 `HTTPModelGateway`
- `result_validator.py` 负责结果校验、置信度清洗和人工复核标记
- `repositories/ai_analysis_repository.py` 负责 `ai_analysis_results` 与 `ai_call_logs` 的持久化
- `cache.py` 提供进程内缓存，避免相同自然键重复调用模型

## 降级与审计

- `AIProcessingService.analyze_or_fallback()` 在模型失败或输出非法时返回 `None`
- 失败不会阻塞主链路，并会写入 `ai_call_logs`
- 原始模型输出不会直接下传，只保留 `raw_response_ref`

## Mock 与 Golden Flow 对齐

- 模块 mock 放在 `mocks/ai_processing/`
- `graduation_material_submission` 场景与共享 golden flow `flow_001_graduation_material_submission` 对齐
- 集成测试会校验服务输出与 `mocks/shared/golden_flows/flow_001_graduation_material_submission/04_ai_analysis_result.json` 一致
