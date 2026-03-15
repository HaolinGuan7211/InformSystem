# 02_workflow_orchestration.md

# 校园通知智能筛选系统主链路编排与责任矩阵

## 1. 文档目的

本文档用于定义：

- 系统主链路如何按阶段串联
- 每一步由哪个模块负责
- 哪些责任属于模块本身，哪些责任属于应用编排层
- 独立开发线程在发现跨模块冲突时应遵循什么规则

本文档不是模块详细设计文档，也不是数据库文档，而是：

**跨模块主流程和责任归属的权威说明。**

---

## 15. 相关性筛选架构调整补充（2026-03-15）

本文件补充冻结以下主链路调整，详细说明见 [07_relevance_filtering_architecture_adjustment.md](/D:/InformSystem/07_relevance_filtering_architecture_adjustment.md)。

### 15.1 新的阶段语义

- 规则层负责第一阶段粗筛
- AI 层负责第二阶段精筛
- 决策层负责输出与最终动作一致的结论文案

### 15.2 规则层职责收口

规则层默认只负责：

- 简单标签和硬条件命中
- 明确文本信号提取
- 明确失配排除
- 为 AI 输出候选集与 `required_profile_facets`

规则层不应继续扩张为“复杂画像推理主引擎”。

### 15.3 AI 触发语义调整

当规则层输出 `relevance_status = unknown` 时，其主语义是“候选通知”，而不是“已经与你相关”。

因此：

- `unknown` 的通知应优先进入 AI 精筛
- AI 层的 `relevance_hint` 应成为第二阶段相关性裁定输入
- 决策层不得把 `unknown` 直接翻译成最终用户语义“与你可能相关”

### 15.4 决策层消费约束

决策层必须显式消费 AI 的负向判断，至少满足：

- 规则层 `irrelevant`：可直接结束链路
- 规则层 `unknown` 且 AI `relevance_hint = irrelevant`：默认 `archive` 或 `ignore`
- 规则层 `unknown` 且 AI `relevance_hint = relevant`：继续进入正常优先级与动作裁定

### 15.5 reason_summary 语义约束

`DecisionResult.reason_summary` 是最终摘要，不是中间态解释。

因此：

- `archive` 结果不得直接写成“与你可能相关”
- `ignore` 结果不得带正向相关文案
- 对候选但未通过精筛的通知，应使用“规则粗筛命中候选范围，但未达到精筛触达阈值”一类表述

## 2. 编排层定位

系统整体采用模块化单体，但模块之间仍需要一个应用层编排者，把各模块调用顺序串起来。

第一阶段明确引入一个非业务模块概念：

**`PipelineOrchestrator` / `WorkflowOrchestrator`**

它的职责是：

- 串联各模块调用顺序
- 管理事件级和用户级 fan-out
- 处理跨模块重试和流程推进
- 记录流程状态

它不是新的业务判断模块，不负责替代规则层、AI 层或决策层。

推荐代码落点：

```text
backend/app/workflows/
backend/app/pipelines/
```

---

## 3. 文档优先级

独立线程在设计或实现时，建议按以下顺序读取文档：

1. `00_system_overview.md`
2. `01_shared_schemas.md`
3. `02_workflow_orchestration.md`
4. `05_database_schema.md`
5. 自己负责的 `docs/modules/X0_*.md`
6. 自己的上游 / 下游模块文档

规则说明：

- 共享对象问题，以 `01_shared_schemas.md` 为准
- 主流程归属问题，以 `02_workflow_orchestration.md` 为准
- 存储关系问题，以 `05_database_schema.md` 为准
- 模块内部实现问题，以对应模块文档为准

---

## 4. 第一阶段主链路

系统处理一条通知的主链路如下：

1. 接入层接收外部通知并生成 `SourceEvent`
2. 接入层完成初步去重并持久化 `raw_events`
3. 编排层读取新产生的 `event_id`
4. 编排层枚举本阶段需要评估的用户
5. 用户画像层为每个用户构建 `UserProfile` 快照
6. 规则层对每个 `(SourceEvent, UserProfile)` 对执行分析，生成 `RuleAnalysisResult`
7. 规则层在 `RuleAnalysisResult.required_profile_facets` 中输出后续所需的最小画像 facet 集合
8. 编排层根据 `RuleAnalysisResult.should_invoke_ai` 决定是否调用 AI 层
9. 如需 AI，编排层调用用户画像层的 `ProfileContextSelector`，从 `UserProfile` 快照中生成 `ProfileContext`
10. AI 层基于 `SourceEvent + RuleAnalysisResult + ProfileContext` 生成 `AIAnalysisResult`，或在降级场景下返回 `None`
11. 决策层对每个用户生成 `DecisionResult`
12. 发文层仅对需要触达的决策执行发送，生成 `DeliveryLog`
13. 反馈层回收投递结果，并接收用户反馈，生成优化样本

---

## 5. 事件与用户的配对责任

这是第一阶段最重要的跨模块约束之一。

### 5.1 结论

第一阶段明确规定：

**事件与用户的配对责任属于编排层，不属于规则层，也不属于用户画像层。**

### 5.2 具体语义

- 用户画像层负责提供 `list_active_users()` 和 `build_snapshot(user_id)`
- 规则层只负责判断“这一条事件对这一个用户是否相关”
- 决策层只负责对“这一条事件 + 这一个用户”的分析结果做最终裁决
- 编排层负责把一条事件和一组待评估用户配起来

### 5.3 第一阶段策略

为了先稳定闭环，第一阶段采用：

**全量活跃用户枚举 + 单用户规则判断**

即：

1. 编排层调用用户画像层的 `list_active_users()`
2. 对每个用户构建 `UserProfile`
3. 逐个调用规则层

说明：

- 这在规模上不是最终形态，但语义最清晰
- 后续如需加入“候选用户预筛”，也属于编排层优化，不改变规则层输入输出契约

---

## 6. 画像切片责任

### 6.1 结论

第一阶段明确规定：

- 规则层负责输出 `required_profile_facets`
- 用户画像层负责把完整 `UserProfile` 派生成 `ProfileContext`
- 编排层负责在正确的时机调用 `ProfileContextSelector`
- AI 层默认消费 `ProfileContext`，不默认直吃完整 `UserProfile`

### 6.2 具体语义

- `required_profile_facets` 描述的是“后续处理需要哪些画像语义”，不是“如何切片”
- `ProfileContextSelector` 负责根据 `required_profile_facets` 从完整快照中抽取最小相关上下文
- 决策层仍然可以消费完整 `UserProfile`，因为它需要结合偏好、静默时间和动作策略做最终裁决

### 6.3 边界约束

- 规则层不得自己拼装 AI prompt 所需的画像 JSON
- AI 层不得自行回头读取完整 `UserProfile` 补全上下文
- 用户画像层不得自行决定哪些 facet 与某条通知相关
- 编排层不得绕过 `ProfileContextSelector` 直接把全量画像喂给 AI，除非进入显式降级模式并留下审计说明

---

## 7. AI 触发责任

### 7.1 结论

第一阶段明确规定：

- 规则层负责输出 `should_invoke_ai`
- 编排层负责决定是否真的执行 AI 调用
- AI 层不自行触发自己

### 7.2 触发语义

编排层可以在以下情况下跳过 AI，即使规则层建议触发：

- 模型服务不可用
- 成本预算不足
- 当前场景被配置为关闭 AI
- 规则结果已经足够确定

跳过 AI 时：

- `ai_result = None`
- 决策层仍然必须继续工作

---

## 8. 决策与发文责任

### 8.1 决策层责任

决策层必须对每个 `event_id + user_id` 输出一个明确的 `DecisionResult`，包括：

- 是否相关
- 优先级
- 最终动作
- 触达时机
- 触达渠道建议

### 8.2 发文层责任

发文层只处理以下动作：

- `push_now`
- `push_high`
- `digest`

以下动作不进入外部发送：

- `archive`
- `ignore`

说明：

- `archive` 代表需要保留，但不触达
- `ignore` 代表该用户对此事件的处理链路结束

---

## 9. Replay 语义

第一阶段明确规定：

**`replay/{event_id}` 的语义是“从接入层之后重新进入主链路”，不是“重新抓取原始平台数据”。**

具体流程：

1. 读取已存储的 `SourceEvent`
2. 从编排层开始重新 fan-out 到用户
3. 重新执行规则、AI、决策和发文链路

因此：

- replay 不重新做 connector 抓取
- replay 不重新生成 `event_id`
- replay 可以配合新规则版本、新策略版本进行联调

---

## 10. 幂等与自然键约定

为了支持多线程开发和后续异步任务，系统需要统一幂等语义。

### 10.1 接入层

- 事件级自然键：`unique_source_key` 或 `url` 或 `content_hash`
- 标准事件主键：`event_id`

### 10.2 规则层

- 自然幂等键：`event_id + user_id + rule_version`

### 10.3 AI 层

- 自然幂等键：`event_id + user_id + model_name + prompt_version`

### 10.4 决策层

- 自然幂等键：`event_id + user_id + policy_version`

### 10.5 发文层

- 自然幂等键：`decision_id + channel + delivery_timing`

### 10.6 反馈层

- 原始用户反馈允许多条并存
- 如果产品需要“同类型反馈覆盖”，应由反馈层单独定义，不应在其他模块隐式处理

---

## 11. 错误隔离与重试边界

### 11.1 接入层

- 单个来源失败不影响其他来源
- 单条原始输入失败不应阻塞整批输入

### 11.2 编排层

- 单个 `event_id + user_id` 对失败不应阻塞其他用户

### 11.3 规则层

- 规则分析失败应记录错误，并返回流程状态给编排层
- 不应在规则层内部悄悄吞掉严重错误

### 11.4 AI 层

- AI 失败默认降级，不阻塞决策层

### 11.5 决策层

- 决策失败应视为主链路失败，需要重试或人工介入

### 11.6 发文层

- 外部渠道失败由发文层负责重试和记录

### 11.7 反馈层

- 反馈层失败不应阻塞用户已发生的投递行为

---

## 12. 责任矩阵

| 责任事项 | 主责任方 | 非责任方说明 |
| --- | --- | --- |
| 外部通知接入 | 接入层 | 规则层 / AI 层 / 决策层不直接抓外部来源 |
| 标准事件生成 | 接入层 | 下游不得重写 `SourceEvent` |
| 事件去重 | 接入层 | 下游只做各自结果级幂等 |
| 用户枚举与事件配对 | 编排层 | 规则层不负责枚举用户 |
| 用户状态快照 | 用户画像层 | 决策层不自己拼画像 |
| 画像切片选择 | 用户画像层 + 编排层 | 规则层只输出 `required_profile_facets`，AI 层不自行回查全量画像 |
| 结构化分析 | 规则层 | AI 层不替代规则初筛 |
| AI 触发执行 | 编排层 | AI 层不自触发 |
| 复杂语义补充 | AI 层 | 决策层不直接调用模型细节 |
| 最终动作裁决 | 决策层 | 发文层不重做业务判断 |
| 外部发送 | 发文层 | 决策层不直接发消息 |
| 投递回收与用户反馈 | 反馈层 | 发文层只写日志，不做优化样本分析 |
| 配置发布与读取 | 配置层 | 各模块不维护私有配置副本 |

---

## 13. 独立线程工作规则

如果某个 Codex 线程只负责一个模块，它必须遵守以下规则：

1. 必须先阅读 `00 + 01 + 02 + 05 + 自己的 X0`
2. 可以参考上游和下游模块文档，但不得擅自改共享协议
3. 如果需要新增跨模块字段，先更新 `01_shared_schemas.md`
4. 如果需要改变流程责任归属，先更新 `02_workflow_orchestration.md`
5. 如果需要新增表关系或唯一键，先更新 `05_database_schema.md`
6. 模块线程可以补充本模块内部设计，但不能重写其他模块边界

---

## 14. 本文档一句话定义

**主链路编排文档的核心作用，是冻结跨模块调用顺序、责任归属和幂等边界，避免独立线程各自补脑出不同系统。**

---

## 16. 当前阶段个人工具方案补充（2026-03-15）

当前仓库虽然保留面向未来多用户扩展的主链路语义，但在 **当前阶段**，系统实际定位为个人单用户工具。

因此，当前实现和后续近期迭代应优先遵循 [08_current_phase_personal_tool_architecture.md](/D:/InformSystem/08_current_phase_personal_tool_architecture.md) 中定义的阶段性方案：

- 规则层只做轻量硬筛
- LLM 第一阶段只消费简单画像 tag 做粗筛
- 只有粗筛通过，才构建重画像 `ProfileContext`
- LLM 第二阶段再结合复杂画像做精筛

该补充不推翻本文件已有主链路责任划分，只是在 **当前单用户阶段** 明确：

- 不提前引入多用户路由复杂度
- 不把规则层扩张为重型 NLP 系统
- 不为了节约少量 token 而牺牲判断质量和维护成本

---
