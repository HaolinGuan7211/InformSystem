# Rule Engine Module

模块 2 负责把单个 `SourceEvent + UserProfile` 组合转换成稳定、可解释的 `RuleAnalysisResult`。

## 当前实现

- `RuleConfigLoader` 从本地版本化 JSON 读取规则配置
- `EventPreprocessor` 统一标题、正文、HTML 和附件文本视图
- `SignalExtractor` 提取动作关键词与截止时间
- `AudienceMatcher` 结合画像和文本做相关性初判
- `ActionRiskEvaluator` 评估动作要求、紧急度和风险等级
- `AITriggerGate` 负责 `should_invoke_ai` 建议位
- `RuleAnalysisRepository` 把结果写入 SQLite `rule_analysis_results`

## 约束

- 默认不负责用户枚举和事件分发
- `analysis_id` 由 `event_id + user_id + rule_version` 稳定生成
- `generated_at` 默认复用 `event.collected_at`，也可以通过 `context.generated_at` 覆盖
- 当前配置实现是文件只读加载，语义对齐 `rule_configs` 表字段

## 主要样例

- 上游输入：
  - `mocks/rule_engine/upstream_inputs/graduation_material_submission__input__source_event.json`
  - `mocks/rule_engine/upstream_inputs/graduation_material_submission__input__user_profile.json`
- 输出样例：
  - `mocks/rule_engine/downstream_outputs/graduation_material_submission__output__rule_analysis_result.json`
