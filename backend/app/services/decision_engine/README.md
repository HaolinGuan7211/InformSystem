# Decision Engine

模块 4 负责把规则结果、AI 结果、用户画像和推送策略统一收束为 `DecisionResult`。

## 已实现内容

- `PolicyLoader` + `FileDecisionPolicyProvider` 读取版本化推送策略
- `PriorityCalculator` 统一计算 `priority_score` 和 `priority_level`
- `ActionResolver` 负责最终 `decision_action` 收口
- `ChannelResolver` 处理渠道偏好、digest 和静默时段调度
- `EvidenceAggregator` 生成可解释证据
- `SQLiteDecisionRepository` 持久化 `decision_results`
- `DecisionEngineService` 提供单条和批量决策入口

## 当前约束

- 决策层允许 `ai_result = None`，会走规则优先的降级路径
- 策略读取当前先使用 mock 文件，后续可切换到配置层数据库表
- 决策结果只输出动作和触达建议，不直接发送消息
