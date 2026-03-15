# 模块 2：规则层（Rule Engine Module）

建议文档名：

```text
docs/modules/20_rule_engine_module.md
```

---

## 13. 相关性粗筛职责补充（2026-03-15）

本模块在相关性筛选主链路中的定位补充为：

- 规则层是第一阶段粗筛层
- 默认依赖简单画像和硬条件做初筛
- 不再以“复杂画像理解主引擎”为目标继续膨胀

### 13.1 规则层优先处理的画像信息

规则层优先使用：

- `identity_tags`
- `degree_level`
- `college`
- `major`
- `grade`
- 明确课程命中
- 明确当前待办命中

### 13.2 规则层不继续承担的内容

以下内容默认不再作为规则层扩张方向：

- 培养方案模块缺口的复杂推理
- 学业完成结构与长文本通知的复杂语义匹配
- 依赖复杂画像切片的细粒度受众判断

这些能力应转移给 AI 精筛阶段，通过 `required_profile_facets` 驱动 `ProfileContext` 选择后再处理。

### 13.3 `unknown` 的解释

规则层输出 `relevance_status = unknown` 时，默认解释为：

**该通知通过了粗筛，但仍需要 AI 精筛进一步判断。**

它不等价于最终“与你可能相关”。

## 1. 业务背景

校园通知系统的核心目标，不是把所有通知都收集起来，而是尽快判断：

- 这条通知是否与当前用户有关
- 这条通知是否要求用户采取行动
- 这条通知是否存在截止风险或高损失风险

如果接入层之后直接进入 AI 判断，会出现这些问题：

- 成本不可控
- 可解释性不足
- 稳定性不足
- 联调困难
- 很多本可由结构化规则识别的信号被浪费

因此规则层的业务意义是：

**对标准通知事件先做结构化分析，产出稳定、可解释、可配置的初步判断结果。**

它在整个系统里的位置是：

**接入层 `SourceEvent` → 规则层 → `RuleAnalysisResult` → AI 层 / 决策层**

---

## 2. 模块职责

规则层只做这些事情：

1. **读取标准通知事件**
2. **提取结构化信号**
3. **结合用户画像做相关性初判**
4. **识别动作要求、时间信号、风险信号**
5. **输出可解释的规则分析结果**
6. **输出后续所需的画像 facet 需求**
7. **决定是否需要进入 AI 补充分析**

规则层不做这些事情：

- 不直接采集外部通知
- 不直接调用外部推送渠道
- 不直接维护用户画像
- 不直接替代决策层做最终推送裁决
- 不把 AI 结果当作规则层内部依赖

一句话：

**规则层是“结构化分析与初筛入口”，不是“最终决策入口”。**

---

## 3. 模块边界

### 3.1 上游依赖

规则层上游默认包括：

- 接入层输出的 `SourceEvent`
- 用户画像层输出的 `UserProfile`
- 配置层输出的规则配置、类别配置和阈值配置

---

### 3.2 下游依赖

规则层只向下游输出统一的：

- `RuleAnalysisResult`

下游默认是：

- AI 处理层
- 决策层
- 规则分析结果存储层

---

### 3.3 边界约束

规则层必须满足：

- 输出结构稳定、可解释
- 支持规则配置化，不把核心规则硬编码在流程分支里
- 不依赖 AI 返回结果才能完成基础判断
- 对同一输入和同一规则版本，输出应稳定一致
- 只声明后续需要哪些画像语义，不负责自己切片画像上下文
- 必须可单独运行和测试

---

## 4. 模块对外接口定义

---

### 4.1 核心数据结构

#### `MatchedRule`

```python
from pydantic import BaseModel


class MatchedRule(BaseModel):
    rule_id: str
    rule_name: str
    dimension: str
    hit_type: str
    weight: float = 0.0
    evidence: list[str] = []
```

说明：

- `dimension` 例如 `audience`、`action`、`deadline`、`risk`
- `hit_type` 例如 `keyword`、`regex`、`profile_match`、`source_constraint`

---

#### `RuleAnalysisResult`

```python
from pydantic import BaseModel
from typing import Any, Optional


class RuleAnalysisResult(BaseModel):
    analysis_id: str
    event_id: str
    user_id: str
    rule_version: str
    candidate_categories: list[str] = []
    matched_rules: list[MatchedRule] = []
    extracted_signals: dict[str, Any] = {}
    required_profile_facets: list[str] = []
    relevance_status: str
    relevance_score: float
    action_required: Optional[bool] = None
    deadline_at: Optional[str] = None
    urgency_level: str = "low"
    risk_level: str = "low"
    should_invoke_ai: bool = False
    should_continue: bool = True
    explanation: list[str] = []
    metadata: dict[str, Any] = {}
    generated_at: str
```

语义说明：

- `relevance_status` 建议值：`relevant` / `irrelevant` / `unknown`
- `required_profile_facets` 使用共享协议中的 `profile_facet` 枚举，描述“后续需要哪些画像语义”
- `should_invoke_ai` 表示规则层认为需要 AI 进一步补充理解
- `should_continue` 表示是否还值得继续送入后续模块

---

### 4.2 模块主接口

```python
class RuleEngineService:
    async def analyze(
        self,
        event: SourceEvent,
        user_profile: UserProfile,
        context: dict | None = None,
    ) -> RuleAnalysisResult:
        ...
```

说明：

- 输入是一条标准事件和一个用户画像
- 输出是一条规则分析结果
- `context` 用于注入额外上下文，例如学期信息、规则版本、来源策略

---

### 4.3 画像切片需求语义

规则层在第一阶段新增一项显式输出：

- `required_profile_facets`

它的作用是：

- 告诉编排层和用户画像层，后续 AI 或复杂决策真正需要哪些画像上下文
- 避免把整份 `UserProfile` 默认喂给 AI
- 让“相关画像上下文选择”成为可测试、可审计的结构化契约

典型示例：

- 调课 / 考试通知：`identity_core` + `current_courses`
- 培养方案缺口通知：`identity_core` + `academic_completion`
- 毕业审核通知：`identity_core` + `graduation_progress`
- 活动学分认定通知：`identity_core` + `activity_based_credit_gap`

约束说明：

- 规则层只输出 facet 需求，不生成 `ProfileContext`
- 规则层不得把学校侧字段名直接写进 `required_profile_facets`
- 若规则层无法确定，可输出保守集合，但应避免默认返回全量 facet

---

### 4.4 批量接口

```python
class RuleEngineService:
    async def analyze_batch(
        self,
        events: list[SourceEvent],
        user_profile: UserProfile,
    ) -> list[RuleAnalysisResult]:
        ...
```

说明：

- 用于对同一用户的多条事件批量分析
- 规则层输出仍保持“单事件单结果”语义

---

### 4.5 规则加载接口

```python
class RuleConfigProvider:
    async def get_active_rules(self, scene: str | None = None) -> list[dict]:
        ...
```

说明：

- 规则层不直接管理规则配置，只读取已发布规则
- 规则配置的权威来源在配置层

---

## 5. 模块内部架构

建议规则层拆成 8 个子模块：

1. `RuleConfigLoader`
2. `EventPreprocessor`
3. `SignalExtractor`
4. `AudienceMatcher`
5. `ActionRiskEvaluator`
6. `ProfileFacetPlanner`
7. `AITriggerGate`
8. `RuleAnalysisRepository`

---

## 6. 子模块详细设计

---

### 6.1 RuleConfigLoader

#### 业务背景

规则内容、阈值、关键词和策略会持续变化，不能写死在代码里。

#### 职责

- 加载当前有效规则
- 按场景或版本提供规则集
- 向执行层提供只读规则快照

#### 接口

```python
class RuleConfigLoader:
    async def load_rules(self, scene: str | None = None) -> list[dict]:
        ...
```

#### 开发约束

- 不负责规则执行
- 不负责规则编辑
- 必须支持版本化读取

---

### 6.2 EventPreprocessor

#### 业务背景

规则匹配前，需要对标题、正文、附件名、来源信息做统一预处理，避免规则表达混乱。

#### 职责

- 统一标题与正文候选文本
- 清洗无效空白和格式噪声
- 组合用于规则匹配的文本视图

#### 接口

```python
class EventPreprocessor:
    async def build_rule_view(self, event: SourceEvent) -> dict:
        ...
```

---

### 6.3 SignalExtractor

#### 业务背景

通知价值判断依赖大量结构化信号，例如：

- 是否包含动作动词
- 是否出现截止时间
- 是否出现特定学院 / 年级 / 毕业生范围
- 是否出现材料、报名、缴费、审核等关键词

#### 职责

- 抽取关键词信号
- 抽取正则模式信号
- 抽取来源与附件信号
- 产出结构化 `extracted_signals`

#### 接口

```python
class SignalExtractor:
    async def extract(self, rule_view: dict, rules: list[dict]) -> dict:
        ...
```

---

### 6.4 AudienceMatcher

#### 业务背景

一条通知对不同学生的价值完全不同，规则层必须先做基础匹配。

#### 职责

- 基于学院、专业、年级、身份标签做初步人群匹配
- 结合课程、毕业阶段、学分状态做相关性判断
- 给出 `relevance_status` 和 `relevance_score`

#### 接口

```python
class AudienceMatcher:
    async def match(self, event: SourceEvent, user_profile: UserProfile, signals: dict) -> dict:
        ...
```

#### 输出示例

```json
{
  "relevance_status": "relevant",
  "relevance_score": 0.92,
  "reasons": ["命中毕业生身份", "命中材料提交动作", "来源可信度高"]
}
```

---

### 6.5 ActionRiskEvaluator

#### 业务背景

系统不仅要知道“与你有关”，还要知道“是否需要你赶紧做事”。

#### 职责

- 判断是否存在动作要求
- 识别截止时间
- 评估紧急程度和风险等级
- 生成类别候选

#### 接口

```python
class ActionRiskEvaluator:
    async def evaluate(self, event: SourceEvent, signals: dict) -> dict:
        ...
```

---

### 6.6 ProfileFacetPlanner

#### 业务背景

规则层已经看过完整 `UserProfile`，但后续 AI 与复杂决策不应默认继续消费全量画像。

#### 职责

- 根据命中的规则、候选类别和结构化信号输出 `required_profile_facets`
- 保证 facet 需求与共享协议枚举一致
- 优先输出“最小够用”的画像语义集合

#### 接口

```python
class ProfileFacetPlanner:
    async def plan(self, event: SourceEvent, user_profile: UserProfile, signals: dict, matched_rules: list[MatchedRule]) -> list[str]:
        ...
```

---

### 6.7 AITriggerGate

#### 业务背景

AI 成本和延迟都应受控，不是所有事件都需要进入 AI。

#### 职责

- 根据规则结果判断是否触发 AI
- 对高确定性事件直接放行到决策层
- 对模糊、复杂、多义事件标记 `should_invoke_ai`

#### 接口

```python
class AITriggerGate:
    async def should_invoke_ai(self, analysis: RuleAnalysisResult) -> bool:
        ...
```

---

### 6.8 RuleAnalysisRepository

#### 业务背景

规则分析结果必须持久化，便于联调、排障、可解释展示和后续优化。

#### 职责

- 存储 `RuleAnalysisResult`
- 按事件 / 用户查询结果
- 支持结果重放与抽样

#### 接口

```python
class RuleAnalysisRepository:
    async def save(self, result: RuleAnalysisResult) -> None:
        ...

    async def get_by_event_and_user(self, event_id: str, user_id: str) -> RuleAnalysisResult | None:
        ...
```

---

## 7. 数据存储设计

规则层至少依赖两类数据：

### 7.1 `rule_configs`

用于存储规则配置、阈值、版本和启停状态。

### 7.2 `rule_analysis_results`

用于存储结构化分析结果。

---

## 8. Mock 设计

为了支持多人并行开发和联调，本模块必须自带 mock 数据。

---

### 8.1 Mock 上游输入

#### `SourceEvent`

```json
{
  "event_id": "evt_001",
  "source_id": "wecom_cs_notice_group",
  "source_type": "wecom",
  "source_name": "计算机学院通知群",
  "channel_type": "group_message",
  "title": null,
  "content_text": "请2026届毕业生于3月15日前提交毕业资格审核材料",
  "content_html": null,
  "author": "辅导员A",
  "published_at": "2026-03-13T10:20:00+08:00",
  "collected_at": "2026-03-13T10:20:03+08:00",
  "url": null,
  "attachments": [],
  "metadata": {
    "raw_msgid": "raw_wecom_001"
  }
}
```

#### `UserProfile`

```json
{
  "user_id": "stu_001",
  "student_id": "20260001",
  "college": "计算机学院",
  "major": "软件工程",
  "grade": "2022",
  "degree_level": "undergraduate",
  "identity_tags": ["毕业生"],
  "graduation_stage": "graduation_review",
  "enrolled_courses": [],
  "notification_preference": {
    "channels": ["app_push"],
    "digest_enabled": true
  }
}
```

---

### 8.2 Mock 下游输出

#### `RuleAnalysisResult`

```json
{
  "analysis_id": "rule_001",
  "event_id": "evt_001",
  "user_id": "stu_001",
  "rule_version": "v1",
  "candidate_categories": ["graduation", "material_submission"],
  "matched_rules": [
    {
      "rule_id": "rule_grad_001",
      "rule_name": "毕业生材料提交识别",
      "dimension": "action",
      "hit_type": "keyword",
      "weight": 1.0,
      "evidence": ["毕业生", "提交", "材料"]
    }
  ],
  "extracted_signals": {
    "audience": ["毕业生"],
    "action_keywords": ["提交", "审核材料"],
    "deadline_text": "3月15日前"
  },
  "required_profile_facets": ["identity_core", "graduation_progress"],
  "relevance_status": "relevant",
  "relevance_score": 0.92,
  "action_required": true,
  "deadline_at": "2026-03-15T23:59:59+08:00",
  "urgency_level": "high",
  "risk_level": "high",
  "should_invoke_ai": false,
  "should_continue": true,
  "explanation": [
    "命中毕业生身份标签",
    "命中材料提交动作",
    "存在明确截止时间"
  ],
  "metadata": {},
  "generated_at": "2026-03-13T10:21:00+08:00"
}
```

---

## 9. 测试要求

规则层必须支持以下测试。

---

### 9.1 单元测试

至少包括：

1. 标题 / 正文关键词规则命中测试
2. 学院 / 年级 / 身份标签匹配测试
3. 截止时间识别测试
4. 动作要求识别测试
5. 空标题 / 空附件 / 空画像边界测试
6. `required_profile_facets` 输出测试
7. `should_invoke_ai` 触发逻辑测试

---

### 9.2 集成测试

至少包括：

1. `SourceEvent + UserProfile → RuleAnalysisResult` 完整链路测试
2. 规则配置变更后的结果稳定性测试
3. 规则分析结果存储测试
4. 多条事件批量分析测试

---

### 9.3 验收标准

模块完成后，必须满足：

- 不依赖 AI 层即可独立完成基础分析
- 对相同输入和相同规则版本输出稳定一致
- 输出字段满足共享协议
- 能清楚解释为何判定相关 / 不相关 / 高风险

---

## 10. 开发约束

### 10.1 必须做

- 严格输出 `RuleAnalysisResult`
- 规则和阈值可配置
- 保留可解释证据
- 支持对用户画像做基础相关性判断
- 输出 `required_profile_facets`
- 支持是否触发 AI 的门控判断

### 10.2 不要做

- 不要在规则层直接发消息
- 不要在规则层直接做最终推送决策
- 不要把所有复杂语义判断都硬塞给规则
- 不要在规则层直接切片或拼装 AI 的画像上下文
- 不要依赖 AI 才能输出基础结果

### 10.3 推荐工程目录

```text
backend/app/services/rule_engine/
  __init__.py
  service.py
  config_loader.py
  preprocessor.py
  signal_extractor.py
  audience_matcher.py
  action_risk_evaluator.py
  ai_trigger_gate.py
  repositories/
    rule_analysis_repository.py
  tests/
    test_signal_extractor.py
    test_audience_matcher.py
    test_action_risk_evaluator.py
```

---

## 11. 模块交付物

规则层模块完成时，应该交付：

1. 代码实现
2. 模块 README
3. mock 输入输出文件
4. 单元测试
5. 结果存储实现
6. 可联调的服务接口

---

## 12. 本模块一句话定义

**规则层模块的核心业务，是对标准通知事件进行结构化分析与初筛，产出可解释、可配置、稳定的基础判断结果。**

---
