# 模块 4：决策层（Decision Engine Module）

建议文档名：

```text
docs/modules/40_decision_engine_module.md
```

---

## 1. 业务背景

规则层和 AI 层都只能提供“分析结果”，但系统真正需要的是一个最终决定：

- 这条通知是否要提醒
- 以什么级别提醒
- 现在提醒还是稍后汇总
- 哪个渠道最合适

如果没有统一决策层，会出现这些问题：

- 规则结果和 AI 结果各自为政
- 推送逻辑散落在多个模块
- 相同事件在不同场景下行为不一致
- 无法解释最终为何立即推送或忽略

因此决策层的业务意义是：

**整合多路分析结果、画像和策略，统一生成最终处理决策。**

它在整个系统里的位置是：

**`SourceEvent + RuleAnalysisResult + AIAnalysisResult + UserProfile` → 决策层 → `DecisionResult` → 发文层**

---

## 2. 模块职责

决策层只做这些事情：

1. **读取规则层和 AI 层分析结果**
2. **结合用户画像和策略配置做统一裁定**
3. **计算优先级和触达级别**
4. **决定推送、汇总、归档或忽略**
5. **输出可执行的决策结果**

决策层不做这些事情：

- 不采集通知
- 不执行规则匹配
- 不直接调用模型
- 不直接发送通知
- 不修改用户画像

一句话：

**决策层是“统一裁定入口”，不是“分析实现入口”或“发送执行入口”。**

---

## 3. 模块边界

### 3.1 上游依赖

决策层上游默认包括：

- `SourceEvent`
- `RuleAnalysisResult`
- `AIAnalysisResult`（可选）
- `UserProfile`
- 配置层提供的推送策略和阈值配置

---

### 3.2 下游依赖

决策层只向下游输出统一的：

- `DecisionResult`

下游默认是：

- 发文层
- 决策结果存储层
- 反馈层

---

### 3.3 边界约束

决策层必须满足：

- 允许只有规则结果没有 AI 结果的场景
- 决策依据必须可解释
- 最终裁决逻辑必须集中，不散落在其他模块
- 输出结果要稳定、幂等
- 必须可单独运行和测试

---

## 4. 模块对外接口定义

---

### 4.1 核心数据结构

#### `DecisionEvidence`

```python
from pydantic import BaseModel


class DecisionEvidence(BaseModel):
    source: str
    key: str
    value: str
```

---

#### `DecisionResult`

```python
from pydantic import BaseModel
from typing import Any, Optional


class DecisionResult(BaseModel):
    decision_id: str
    event_id: str
    user_id: str
    relevance_status: str
    priority_score: float
    priority_level: str
    decision_action: str
    delivery_timing: str
    delivery_channels: list[str] = []
    action_required: Optional[bool] = None
    deadline_at: Optional[str] = None
    reason_summary: str
    explanations: list[str] = []
    evidences: list[DecisionEvidence] = []
    policy_version: str
    metadata: dict[str, Any] = {}
    generated_at: str
```

语义说明：

- `decision_action` 建议值：`push_now` / `push_high` / `digest` / `archive` / `ignore`
- `delivery_timing` 建议值：`immediate` / `scheduled` / `digest_window`

---

### 4.2 模块主接口

```python
class DecisionEngineService:
    async def decide(
        self,
        event: SourceEvent,
        user_profile: UserProfile,
        rule_result: RuleAnalysisResult,
        ai_result: AIAnalysisResult | None = None,
        context: dict | None = None,
    ) -> DecisionResult:
        ...
```

说明：

- 决策层以规则结果为主输入
- AI 结果是可选补充输入

---

### 4.3 批量决策接口

```python
class DecisionEngineService:
    async def decide_batch(
        self,
        inputs: list[tuple[SourceEvent, UserProfile, RuleAnalysisResult, AIAnalysisResult | None]],
    ) -> list[DecisionResult]:
        ...
```

---

### 4.4 策略读取接口

```python
class DecisionPolicyProvider:
    async def get_active_policies(self) -> list[dict]:
        ...
```

---

## 5. 模块内部架构

建议决策层拆成 6 个子模块：

1. `PolicyLoader`
2. `EvidenceAggregator`
3. `PriorityCalculator`
4. `ActionResolver`
5. `ChannelResolver`
6. `DecisionRepository`

---

## 6. 子模块详细设计

---

### 6.1 PolicyLoader

#### 业务背景

不同通知类别、不同优先级和不同用户偏好，会影响最终动作。

#### 职责

- 加载推送策略
- 加载阈值和静默策略
- 向决策流程提供只读策略快照

#### 接口

```python
class PolicyLoader:
    async def load_policies(self) -> list[dict]:
        ...
```

---

### 6.2 EvidenceAggregator

#### 业务背景

决策必须能解释来源于哪些依据。

#### 职责

- 汇总规则证据
- 汇总 AI 补充证据
- 汇总画像和策略证据
- 形成统一证据列表

#### 接口

```python
class EvidenceAggregator:
    async def aggregate(
        self,
        rule_result: RuleAnalysisResult,
        ai_result: AIAnalysisResult | None,
        user_profile: UserProfile,
    ) -> list[DecisionEvidence]:
        ...
```

---

### 6.3 PriorityCalculator

#### 业务背景

系统需要把“相关性、动作、截止、风险”统一映射为优先级。

#### 职责

- 计算 `priority_score`
- 映射 `priority_level`
- 处理规则和 AI 结果冲突

#### 接口

```python
class PriorityCalculator:
    async def calculate(
        self,
        rule_result: RuleAnalysisResult,
        ai_result: AIAnalysisResult | None,
    ) -> dict:
        ...
```

---

### 6.4 ActionResolver

#### 业务背景

优先级不是最终动作，还要映射成业务动作。

#### 职责

- 判断最终 `decision_action`
- 决定立即提醒、汇总还是归档
- 结合静默策略和用户偏好调整输出

#### 接口

```python
class ActionResolver:
    async def resolve(
        self,
        event: SourceEvent,
        user_profile: UserProfile,
        priority: dict,
        policies: list[dict],
    ) -> dict:
        ...
```

---

### 6.5 ChannelResolver

#### 业务背景

同样是提醒，不同优先级和用户偏好下，渠道可能不同。

#### 职责

- 选择触达渠道
- 确定发送时机
- 输出标准化投递计划字段

#### 接口

```python
class ChannelResolver:
    async def resolve(self, decision_action: str, user_profile: UserProfile, policies: list[dict]) -> dict:
        ...
```

---

### 6.6 DecisionRepository

#### 业务背景

最终决策必须可追溯，否则系统无法解释为何提醒、为何未提醒。

#### 职责

- 存储 `DecisionResult`
- 支持按事件 / 用户查询
- 支持审计和联调

#### 接口

```python
class DecisionRepository:
    async def save(self, result: DecisionResult) -> None:
        ...

    async def get_by_event_and_user(self, event_id: str, user_id: str) -> DecisionResult | None:
        ...
```

---

## 7. 数据存储设计

决策层至少依赖：

### 7.1 `decision_results`

用于存储最终裁定结果。

### 7.2 `push_policy_configs`

用于存储推送策略、阈值和渠道策略。

---

## 8. Mock 设计

---

### 8.1 Mock 上游输入

#### `RuleAnalysisResult`

```json
{
  "analysis_id": "rule_001",
  "event_id": "evt_001",
  "user_id": "stu_001",
  "relevance_status": "relevant",
  "relevance_score": 0.92,
  "action_required": true,
  "deadline_at": "2026-03-15T23:59:59+08:00",
  "urgency_level": "high",
  "risk_level": "high"
}
```

#### `AIAnalysisResult`

```json
{
  "ai_result_id": "ai_001",
  "event_id": "evt_001",
  "user_id": "stu_001",
  "summary": "该通知要求毕业生在截止日前提交审核材料。",
  "risk_hint": "错过可能影响毕业进度",
  "confidence": 0.9
}
```

---

### 8.2 Mock 下游输出

#### `DecisionResult`

```json
{
  "decision_id": "dec_001",
  "event_id": "evt_001",
  "user_id": "stu_001",
  "relevance_status": "relevant",
  "priority_score": 95.0,
  "priority_level": "critical",
  "decision_action": "push_now",
  "delivery_timing": "immediate",
  "delivery_channels": ["app_push"],
  "action_required": true,
  "deadline_at": "2026-03-15T23:59:59+08:00",
  "reason_summary": "毕业审核材料提交通知，与你身份匹配，且存在明确截止时间。",
  "explanations": [
    "规则层判定高度相关",
    "存在明确动作要求",
    "存在明确截止时间",
    "AI 补充判断错过风险较高"
  ],
  "evidences": [
    {
      "source": "rule",
      "key": "relevance_status",
      "value": "relevant"
    },
    {
      "source": "ai",
      "key": "risk_hint",
      "value": "错过可能影响毕业进度"
    }
  ],
  "policy_version": "policy_v1",
  "metadata": {},
  "generated_at": "2026-03-13T10:23:00+08:00"
}
```

---

## 9. 测试要求

---

### 9.1 单元测试

至少包括：

1. 规则结果直接转 `push_now` 测试
2. AI 缺失时的降级决策测试
3. 规则和 AI 结果冲突处理测试
4. `digest` / `archive` / `ignore` 分支测试
5. 用户静默偏好影响测试
6. 证据解释生成测试

---

### 9.2 集成测试

至少包括：

1. `SourceEvent + RuleAnalysisResult + AIAnalysisResult → DecisionResult` 测试
2. 决策结果存储测试
3. 批量决策测试
4. 相同输入幂等输出测试

---

### 9.3 验收标准

- 最终动作语义集中在决策层
- 决策可解释、可追溯
- 无 AI 情况下也能完成主链路
- 决策结果可直接交给发文层执行

---

## 10. 开发约束

### 10.1 必须做

- 统一输出 `DecisionResult`
- 支持规则优先、AI 辅助
- 支持可解释证据
- 支持策略配置化

### 10.2 不要做

- 不要在决策层直接发送通知
- 不要在其他模块分散写最终推送判断
- 不要让 AI 单独决定最终动作

### 10.3 推荐工程目录

```text
backend/app/services/decision_engine/
  __init__.py
  service.py
  policy_loader.py
  evidence_aggregator.py
  priority_calculator.py
  action_resolver.py
  channel_resolver.py
  repositories/
    decision_repository.py
  tests/
    test_priority_calculator.py
    test_action_resolver.py
    test_decision_service.py
```

---

## 11. 模块交付物

决策层模块完成时，应该交付：

1. 代码实现
2. 模块 README
3. mock 输入输出文件
4. 单元测试
5. 决策结果存储实现
6. 可联调服务接口

---

## 12. 本模块一句话定义

**决策层模块的核心业务，是整合规则分析、AI 分析、画像和策略配置，生成统一、可执行、可解释的最终处理决策。**

---

