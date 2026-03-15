# Decision Engine

模块 4 负责把规则结果、AI 结果、用户画像和推送策略统一收束为 `DecisionResult`。

## 已实现内容

- `PolicyLoader` + `FileDecisionPolicyProvider` 读取版本化推送策略
- `PriorityCalculator` 统一计算 `priority_score` 和 `priority_level`
- `ActionResolver` 负责最终 `decision_action` 收口
- `ChannelResolver` 处理渠道偏好、digest 和静默时段调度
- `ProfileSignalResolver` 优先消费画像中的 `attention_signals` 和 `pending_items`
- `EvidenceAggregator` 生成可解释证据
- `SQLiteDecisionRepository` 持久化 `decision_results`
- `DecisionEngineService` 提供单条和批量决策入口

## 当前约束

- 决策层允许 `ai_result = None`，会走规则优先的降级路径
- 策略读取当前先使用 mock 文件，后续可切换到配置层数据库表
- 决策结果只输出动作和触达建议，不直接发送消息

## 当前阶段 AI 合并语义

- 规则层 `irrelevant` 或 `should_continue = false` 会直接落 `ignore`
- 规则层候选通知如果被 AI Stage 1 / Stage 2 判为 `irrelevant`，默认落 `archive`
- AI 判 `uncertain` 时，不再默认进入 `digest`；只有命中保留条件时才会进入 `digest`，否则落 `archive`
- 规则层 `unknown` 只有在 AI 明确判 `relevant` 后，才会转成最终正向相关结论
- AI 已确认相关但整体仍是低优先级时，最低会保留到 `digest`，避免被低分 `archive` 直接吞掉
- `unknown` 不会再直接翻译成“与你可能相关”这类最终正向文案

当前允许 `uncertain -> digest` 的保留场景主要包括：

- 命中画像缺口或待处理事项
- 与 `current_tasks` 存在弱相关线索
- 开放机会且存在明确截止时间
- 公共服务对学生日常生活影响较强

## 画像信号策略

当前决策层会把画像中的结构化缺口信号当成显式决策输入，而不是只把 `UserProfile` 当成偏好容器。

- 输入来源：优先消费 `user_profile.credit_status.attention_signals` 和 `pending_items`
- 显式命中：如果规则层在 `extracted_signals` 中给出 `attention_signal_keys` 或 `pending_item_ids`，决策层优先按这些键命中
- 回退命中：如果规则层没有给显式键，决策层会用事件正文、规则解释、AI 摘要和候选类别做文本 / 类别关键词匹配
- 状态过滤：`pending_items` 只有 `pending` 或 `unknown` 状态会进入匹配，已完成项不会参与提权

## 加分规则

- `attention_signals.severity` 加分：`critical=12`、`high=10`、`medium=6`、`low=3`
- `pending_items.priority_hint` 加分：`critical=8`、`high=8`、`medium=5`、`low=2`
- 同时命中两类信号时额外加 `2`
- 总画像加分封顶 `20`
- 最终优先级阈值：`critical >= 90`、`high >= 75`、`medium >= 55`

这意味着一条原本只会进入 `digest` 的中优先级通知，只要显式命中了画像缺口，就可能被抬升到 `push_high`。

## 对输出的影响

- `reason_summary`：命中画像缺口时，摘要优先使用“与你当前画像缺口匹配”，否则才回退到“与你身份匹配”
- `explanations`：会追加“命中画像 attention_signals 中的结构化缺口信号”或“命中画像 pending_items 中的待处理缺口项”
- `evidences`：会追加 `source="profile"` 的证据，常见为 `attention_signal`、`pending_item`、`identity_tag`
- `metadata`：会写入 `profile_signal_matches`，记录命中的 `attention_signal_keys` 和 `pending_item_ids`
- 降级路径：如果 `ai_result is None` 且规则层原本要求进 AI，仍会继续写入 `ai_degraded = true`

## 覆盖注意点

- 如果测试目标是验证纯规则 + 纯策略分支，例如 `digest`，需要构造不命中画像缺口的 `credit_status`
- 如果测试目标是验证学分 / 模块缺口驱动通知，建议显式给出 `attention_signal_keys` / `pending_item_ids`，避免依赖模糊文本匹配
- `required_profile_facets` 当前主要由规则层声明给 AI / 编排链路使用，决策层还没有直接按 facet 做二次裁定
