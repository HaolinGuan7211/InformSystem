# 04_mock_and_integration_conventions.md

# 校园通知智能筛选系统 Mock 与联调约定

## 1. 文档目的

本文档用于统一：

- mock 文件的组织方式
- 跨模块联调样例的组织方式
- golden sample 的命名方式
- 独立线程产出 mock 时必须遵守的约定

它的目标是：

**让不同线程生成的 mock 能直接拼起来联调，而不是各自造一套样例。**

---

## 2. 基本原则

系统文档和开发流程采用：

**Contract-First + Mock-Driven Development**

因此每个模块交付时，都必须带：

- 上游输入 mock
- 下游输出 mock
- 至少一个可跨模块拼接的 golden sample

---

## 3. 目录约定

第一阶段建议统一使用以下目录结构：

```text
mocks/
  shared/
    golden_flows/
      flow_001_graduation_material_submission/
        01_source_event.json
        02_user_profile.json
        03_rule_analysis_result.json
        04_ai_analysis_result.json
        05_decision_result.json
        06_delivery_log.json
        07_user_feedback_record.json
  ingestion/
    raw_inputs/
    normalized_outputs/
  rule_engine/
    upstream_inputs/
    downstream_outputs/
  ai_processing/
    upstream_inputs/
    downstream_outputs/
  decision_engine/
    upstream_inputs/
    downstream_outputs/
  delivery/
    upstream_inputs/
    downstream_outputs/
  user_profile/
    upstream_inputs/
    downstream_outputs/
  config/
    upstream_inputs/
    downstream_outputs/
  feedback/
    upstream_inputs/
    downstream_outputs/
```

说明：

- `mocks/shared/golden_flows/` 是跨模块权威样例目录
- 每个模块目录只维护本模块所需输入输出样例
- 模块 mock 可以来源于 golden sample 的拆分，但不得改变共享字段语义

---

## 4. 文件命名约定

### 4.1 Golden Flow 目录命名

格式建议：

```text
flow_<三位编号>_<场景名>
```

例如：

- `flow_001_graduation_material_submission`
- `flow_002_course_schedule_change`
- `flow_003_credit_recognition_notice`

### 4.2 模块内文件命名

模块内样例文件建议使用：

```text
<scenario_slug>__<direction>__<object_name>.json
```

例如：

- `graduation_material_submission__input__source_event.json`
- `graduation_material_submission__output__rule_analysis_result.json`

---

## 5. Golden Sample 规则

### 5.1 权威性

`mocks/shared/golden_flows/` 下的样例是跨模块联调权威样例。

它的作用是：

- 定义一条完整业务链路的输入输出
- 让模块线程知道自己应该接什么、产出什么
- 让集成测试可以直接引用统一样例

### 5.2 禁止事项

模块线程不得：

- 修改其他阶段的 golden sample 语义
- 私自新增共享字段但不更新 `01_shared_schemas.md`
- 为了适配自己模块而修改上游对象结构

### 5.3 允许事项

模块线程可以：

- 在本模块目录新增更多边界测试样例
- 在不改变共享契约的前提下补充 `metadata`
- 为同一场景补充多条输入变体

---

## 6. 模块 mock 产出要求

每个模块至少应提供以下内容：

### 6.1 接入层

- 原始来源输入样例
- 标准化后的 `SourceEvent`

### 6.2 规则层

- `SourceEvent + UserProfile`
- `RuleAnalysisResult`

### 6.3 AI 层

- `SourceEvent + RuleAnalysisResult + UserProfile`
- `AIAnalysisResult`

### 6.4 决策层

- `SourceEvent + RuleAnalysisResult + AIAnalysisResult`
- `DecisionResult`

### 6.5 发文层

- `DecisionResult + SourceEvent + UserProfile`
- `DeliveryTask` 或 `DeliveryLog`

### 6.6 用户画像层

- 原始用户数据样例
- `UserProfile`

### 6.7 配置层

- 配置发布输入样例
- 配置对象样例

### 6.8 反馈层

- 用户反馈输入样例
- `UserFeedbackRecord`
- `OptimizationSample`

---

## 7. 联调约定

### 7.1 联调最小路径

第一阶段每条 golden flow 至少应支持以下最小联调路径：

1. `SourceEvent`
2. `UserProfile`
3. `RuleAnalysisResult`
4. `AIAnalysisResult` 或 `null`
5. `DecisionResult`
6. `DeliveryLog`

### 7.2 AI 可选联调

当联调不依赖真实模型时，`AIAnalysisResult` 可以来自 mock 文件。

### 7.3 Replay 联调

对于 replay 场景，统一从已生成的 `SourceEvent` 开始，不重新模拟 connector 抓取。

---

## 8. 测试文件与 mock 的关系

### 8.1 单元测试

- 优先使用模块目录下的 mock
- 测试本模块核心边界和异常场景

### 8.2 集成测试

- 优先使用 `mocks/shared/golden_flows/`
- 验证跨模块拼接是否一致

### 8.3 Golden Sample 更新规则

如果 golden sample 需要变更：

1. 先确认是否属于共享协议变更
2. 如涉及共享字段或枚举，先更新 `01_shared_schemas.md`
3. 如涉及流程责任变更，先更新 `02_workflow_orchestration.md`
4. 再统一更新 golden sample

---

## 9. 独立线程产出要求

一个独立 Codex 线程在完成自己模块设计或实现时，必须同时交付：

1. 模块详细设计文档
2. 至少一组本模块输入 mock
3. 至少一组本模块输出 mock
4. 至少一条可接入 golden flow 的映射说明
5. 至少一组单元测试样例

如果线程发现自己的上游或下游 mock 与共享协议冲突，应先修契约，不应私自兼容两套对象。

---

## 10. 本文档一句话定义

**Mock 与联调约定文档的核心作用，是统一样例目录、命名和 golden sample 规则，让多线程产出的模块可以直接拼起来联调。**

---

