# 01_shared_schemas.md

# 校园通知智能筛选系统共享协议文档

## 1. 文档目的

本文档用于冻结系统跨模块共享对象、字段语义、枚举值、ID 规则和基础字段约定。

它的目标不是展开每个模块内部实现，而是确保：

- 不同模块对同一个对象的理解一致
- 独立开发线程不会各自发明字段
- 上下游模块可以基于同一份契约独立设计和联调

---

## 9. 相关性筛选语义补充（2026-03-15）

本节补充现有共享对象在“规则粗筛 + AI 精筛”架构下的解释语义，不新增字段，只冻结既有字段的使用方式。

### 9.1 `RuleAnalysisResult.relevance_status`

`RuleAnalysisResult.relevance_status` 表示第一阶段粗筛结论。

- `irrelevant`
  - 存在明确硬失配
  - 规则层即可排除
- `relevant`
  - 存在明确硬命中
  - 规则层已能高置信度认定与用户相关
- `unknown`
  - 表示候选通知
  - 值得进入 AI 精筛
  - 不等价于最终“与你相关”

### 9.2 `RuleAnalysisResult.should_invoke_ai`

`should_invoke_ai` 的默认语义是：

**该通知是否需要进入第二阶段 AI 精筛。**

它不表示“AI 只是做摘要”，也不表示“AI 只在高风险场景补一句话”。

### 9.3 `AIAnalysisResult.relevance_hint`

`AIAnalysisResult.relevance_hint` 应按标准值解释：

- `relevant`
- `irrelevant`
- `uncertain`

允许保留附加自然语言解释，但下游模块消费时必须先按上述标准值理解。

### 9.4 `DecisionResult.reason_summary`

`reason_summary` 是最终动作摘要，不是规则层中间态翻译。

因此：

- 归档结果不应直接写成“与你可能相关”
- 忽略结果不应使用正向相关措辞
- 中间候选态必须在进入最终摘要前被转换成与 `decision_action` 一致的文案

## 2. 适用范围与优先级

本文件适用于以下跨模块共享对象：

- `AttachmentInfo`
- `SourceEvent`
- `CourseInfo`
- `NotificationPreference`
- `UserProfile`
- `ProfileContext`
- `MatchedRule`
- `RuleAnalysisResult`
- `AIExtractedField`
- `AIAnalysisResult`
- `DecisionEvidence`
- `DecisionResult`
- `DeliveryTask`
- `DeliveryLog`
- `UserFeedbackRecord`
- `OptimizationSample`

文档优先级约定：

1. `00_system_overview.md`：定义系统目标与总体方向
2. `01_shared_schemas.md`：定义共享对象、字段和枚举
3. `02_workflow_orchestration.md`：定义跨模块主链路与责任边界
4. `05_database_schema.md`：定义持久化契约
5. `docs/modules/X0_*.md`：定义模块内部职责和本模块专属接口

若模块文档与本文件冲突，以本文件为准；若本文件需要变更，应先更新本文件，再回写相关模块文档。

---

## 3. 全局字段约定

### 3.1 命名规则

- 所有共享字段统一使用 `snake_case`
- 所有对象名统一使用 `PascalCase`
- JSON 对象中的字段名不得混用驼峰和下划线

### 3.2 时间格式

- 所有时间字段统一使用 ISO 8601 字符串
- 所有时间必须带明确时区偏移，例如 `2026-03-13T10:20:00+08:00`
- 不允许在共享对象中输出无时区的时间字符串

### 3.3 ID 规则

共享对象 ID 采用前缀化字符串，不强制限定生成算法，但必须全局唯一。

建议前缀如下：

- `event_id`：`evt_`
- `canonical_notice_id`：`notice_`
- `analysis_id`：`rule_`
- `ai_result_id`：`ai_`
- `decision_id`：`dec_`
- `task_id`：`task_`
- `log_id`：`dlv_`
- `feedback_id`：`fb_`
- `sample_id`：`sample_`

### 3.4 `metadata` 规则

- `metadata` 仅用于承载暂未进入共享协议的扩展字段
- `metadata` 的 key 必须使用 `snake_case`
- `metadata` 中不得覆盖标准字段语义
- `metadata` 必须是可 JSON 序列化的内容

### 3.5 空值约定

- “字段不存在”优先使用 `null`
- 多值字段无值时优先使用空数组 `[]`
- 字典字段无值时优先使用空对象 `{}`
- 不允许用空字符串替代 `null` 表示“未知”

### 3.6 不可变约定

以下对象一旦生成，原则上视为审计结果，不做原地覆盖式修改：

- `SourceEvent`
- `RuleAnalysisResult`
- `AIAnalysisResult`
- `DecisionResult`
- `DeliveryLog`
- `UserFeedbackRecord`
- `OptimizationSample`

用户画像和配置对象允许更新，但下游分析链路应尽量基于快照读取。

---

## 4. 枚举值约定

### 4.1 `relevance_status`

- `relevant`
- `irrelevant`
- `unknown`

### 4.2 `urgency_level`

- `low`
- `medium`
- `high`
- `critical`

### 4.3 `risk_level`

- `low`
- `medium`
- `high`
- `critical`

### 4.4 `priority_level`

- `low`
- `medium`
- `high`
- `critical`

### 4.5 `decision_action`

- `push_now`
- `push_high`
- `digest`
- `archive`
- `ignore`

语义说明：

- `push_now`：立即提醒
- `push_high`：高优先级提醒，但可走高优先级队列或特殊渠道
- `digest`：进入汇总提醒
- `archive`：保留结果但不主动提醒
- `ignore`：结束当前用户的处理链路，不进入发文层

### 4.6 `delivery_timing`

- `immediate`
- `scheduled`
- `digest_window`

### 4.7 `delivery_status`

- `pending`
- `sent`
- `failed`
- `skipped`

### 4.8 `feedback_type`

- `useful`
- `not_relevant`
- `too_late`
- `too_frequent`
- `missed_important`

### 4.9 `profile_facet`

- `identity_core`
- `current_courses`
- `academic_completion`
- `graduation_progress`
- `activity_based_credit_gap`
- `online_platform_credit_gap`
- `custom_watch_items`
- `notification_preference`

### 4.10 `module_completion_status`

- `completed`
- `in_progress`
- `not_started`

### 4.11 `profile_freshness_status`

- `fresh`
- `stale`
- `unknown`

### 4.12 `pending_item_status`

- `pending`
- `completed`
- `waived`
- `unknown`

---

## 5. 共享对象定义

---

### 5.1 `AttachmentInfo`

```python
from pydantic import BaseModel


class AttachmentInfo(BaseModel):
    name: str
    url: str | None = None
    mime_type: str | None = None
    storage_key: str | None = None
```

字段语义：

- `name`：附件显示名称，必填
- `url`：附件原始访问地址，可选
- `mime_type`：附件类型，可选
- `storage_key`：对象存储键，可选

---

### 5.2 `SourceEvent`

```python
from pydantic import BaseModel, Field
from typing import Any


class SourceEvent(BaseModel):
    event_id: str
    source_id: str
    source_type: str
    source_name: str
    channel_type: str
    title: str | None = None
    content_text: str
    content_html: str | None = None
    author: str | None = None
    published_at: str | None = None
    collected_at: str
    url: str | None = None
    attachments: list[AttachmentInfo] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

字段语义：

- `event_id`：接入层生成的标准事件 ID
- `source_id`：来源配置标识
- `source_type`：来源类型，例如 `wecom`、`website`、`email`
- `source_name`：来源显示名
- `channel_type`：来源渠道语义，例如 `group_message`、`website_notice`
- `content_text`：标准纯文本正文，必填
- `content_html`：原始 HTML 或富文本，可选
- `published_at`：原始发布时间，可选
- `collected_at`：系统采集时间，必填
- `metadata`：原始平台扩展信息

扩展语义：

- 接入去重产生的 `canonical_notice_id`、`content_hash`、`unique_source_key` 可以先进入 `metadata`

---

### 5.3 `CourseInfo`

```python
from pydantic import BaseModel


class CourseInfo(BaseModel):
    course_id: str
    course_name: str
    teacher: str | None = None
    semester: str | None = None
```

---

### 5.4 `NotificationPreference`

```python
from pydantic import BaseModel, Field


class NotificationPreference(BaseModel):
    channels: list[str] = Field(default_factory=list)
    quiet_hours: list[str] = Field(default_factory=list)
    digest_enabled: bool = True
    muted_categories: list[str] = Field(default_factory=list)
```

字段语义：

- `channels`：用户偏好的触达渠道
- `quiet_hours`：静默时间窗口，格式建议如 `23:00-07:00`
- `digest_enabled`：是否允许汇总提醒
- `muted_categories`：用户主动屏蔽的类别

---

### 5.5 `UserProfile`

```python
from pydantic import BaseModel, Field
from typing import Any


class UserProfile(BaseModel):
    user_id: str
    student_id: str
    name: str | None = None
    college: str | None = None
    major: str | None = None
    grade: str | None = None
    degree_level: str | None = None
    identity_tags: list[str] = Field(default_factory=list)
    graduation_stage: str | None = None
    enrolled_courses: list[CourseInfo] = Field(default_factory=list)
    credit_status: dict[str, Any] = Field(default_factory=dict)
    current_tasks: list[str] = Field(default_factory=list)
    notification_preference: NotificationPreference = NotificationPreference()
    metadata: dict[str, Any] = Field(default_factory=dict)
```

字段语义：

- `user_id`：系统内用户主键
- `student_id`：学号
- `identity_tags`：如 `毕业生`、`转专业`、`缓考`
- `graduation_stage`：如 `graduation_review`
- `credit_status`：结构化学分状态
- `current_tasks`：用户当前已知事项

---

### 5.5.1 `credit_status` 内部结构

`credit_status` 虽然在顶层对象中保留为 `dict[str, Any]`，但其第一阶段内部结构在共享协议层冻结为以下语义：

```python
credit_status = {
    "program_summary": {
        "program_name": str | None,
        "required_total_credits": float | None,
        "completed_total_credits": float | None,
        "outstanding_total_credits": float | None,
        "exempted_total_credits": float | None,
        "plan_version": str | None,
    },
    "module_progress": [
        {
            "module_id": str,
            "module_name": str,
            "parent_module_id": str | None,
            "parent_module_name": str | None,
            "module_level": str,
            "required_credits": float | None,
            "completed_credits": float | None,
            "outstanding_credits": float | None,
            "required_course_count": int | None,
            "completed_course_count": int | None,
            "outstanding_course_count": int | None,
            "completion_status": str,
            "attention_tags": list[str],
            "metadata": dict[str, Any],
        }
    ],
    "pending_items": [
        {
            "item_id": str,
            "item_type": str,
            "title": str,
            "module_id": str | None,
            "module_name": str | None,
            "credits": float | None,
            "status": str,
            "priority_hint": str | None,
            "metadata": dict[str, Any],
        }
    ],
    "attention_signals": [
        {
            "signal_type": str,
            "signal_key": str,
            "signal_value": str | None,
            "severity": str,
            "evidence": list[str],
        }
    ],
    "source_snapshot": {
        "school_code": str | None,
        "source_system": str | None,
        "synced_at": str | None,
        "source_version": str | None,
        "freshness_status": str,
        "metadata": dict[str, Any],
    },
}
```

字段语义补充：

- `program_summary`：培养方案总览，只承载总学分层面的稳定状态
- `module_progress`：模块级完成情况，支持父模块与子模块并存，但后续规则和 AI 默认优先消费子模块
- `pending_items`：待完成项，只承载仍对业务判断有价值的缺口事项，不等价于“全量未修课程”
- `attention_signals`：从学分与毕业状态中派生出的高价值结构化信号，供规则层和决策层优先消费
- `source_snapshot`：本次学业完成同步的来源快照和新鲜度状态

约束说明：

- `enrolled_courses` 只承载“当前在修 / 当前选课”的课程，不承载全量培养方案课程
- 学校侧原始字段如 `PYFADM`、`KZH`、`FKZH` 只能停留在 `metadata` 中，不进入共享业务字段
- “活动学分”“网课平台学分”等派生信号应优先进入 `attention_signals`，不应依赖 AI 临时猜测

---

### 5.5.2 `ProfileContext`

```python
from pydantic import BaseModel, Field
from typing import Any


class ProfileContext(BaseModel):
    user_id: str
    facets: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    generated_at: str
```

字段语义：

- `facets`：本次切片实际包含的画像 facet 集合，必须使用 `profile_facet` 枚举值
- `payload`：最小相关画像上下文，只承载本次规则 / AI 需要消费的业务语义
- `metadata`：切片来源、快照时间、降级说明等辅助信息

约束说明：

- `ProfileContext` 是 `UserProfile` 的派生切片，不是新的主画像对象
- AI 层默认消费 `ProfileContext`，而不是完整 `UserProfile`
- 未被 `required_profile_facets` 选中的画像内容不应默认进入 `payload`

---

### 5.6 `MatchedRule`

```python
from pydantic import BaseModel, Field


class MatchedRule(BaseModel):
    rule_id: str
    rule_name: str
    dimension: str
    hit_type: str
    weight: float = 0.0
    evidence: list[str] = Field(default_factory=list)
```

---

### 5.7 `RuleAnalysisResult`

```python
from pydantic import BaseModel, Field
from typing import Any


class RuleAnalysisResult(BaseModel):
    analysis_id: str
    event_id: str
    user_id: str
    rule_version: str
    candidate_categories: list[str] = Field(default_factory=list)
    matched_rules: list[MatchedRule] = Field(default_factory=list)
    extracted_signals: dict[str, Any] = Field(default_factory=dict)
    required_profile_facets: list[str] = Field(default_factory=list)
    relevance_status: str
    relevance_score: float
    action_required: bool | None = None
    deadline_at: str | None = None
    urgency_level: str = "low"
    risk_level: str = "low"
    should_invoke_ai: bool = False
    should_continue: bool = True
    explanation: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    generated_at: str
```

字段语义：

- `analysis_id`：规则分析结果 ID
- `event_id + user_id + rule_version`：规则结果的自然幂等键
- `candidate_categories`：候选通知类别
- `matched_rules`：命中的规则和证据
- `extracted_signals`：结构化信号结果
- `required_profile_facets`：如需进入 AI 或后续复杂决策时，建议选择的最小画像切片集合
- `should_invoke_ai`：规则层建议是否送 AI
- `should_continue`：是否值得继续进入决策流程

数值约束：

- `relevance_score` 约定范围为 `0.0 ~ 1.0`
- `required_profile_facets` 中的值必须来自 `profile_facet` 枚举；规则层只声明需求，不负责切片

---

### 5.8 `AIExtractedField`

```python
from pydantic import BaseModel
from typing import Any


class AIExtractedField(BaseModel):
    field_name: str
    field_value: Any
    confidence: float = 0.0
```

数值约束：

- `confidence` 约定范围为 `0.0 ~ 1.0`

---

### 5.9 `AIAnalysisResult`

```python
from pydantic import BaseModel, Field
from typing import Any


class AIAnalysisResult(BaseModel):
    ai_result_id: str
    event_id: str
    user_id: str
    model_name: str
    prompt_version: str
    summary: str | None = None
    normalized_category: str | None = None
    action_items: list[str] = Field(default_factory=list)
    extracted_fields: list[AIExtractedField] = Field(default_factory=list)
    relevance_hint: str | None = None
    urgency_hint: str | None = None
    risk_hint: str | None = None
    confidence: float = 0.0
    needs_human_review: bool = False
    raw_response_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    generated_at: str
```

字段语义：

- `model_name`：模型名称
- `prompt_version`：提示词版本
- `summary`：用于快速理解的短摘要
- `raw_response_ref`：原始模型输出引用，不直接泄漏业务层

数值约束：

- `confidence` 约定范围为 `0.0 ~ 1.0`

---

### 5.10 `DecisionEvidence`

```python
from pydantic import BaseModel


class DecisionEvidence(BaseModel):
    source: str
    key: str
    value: str
```

---

### 5.11 `DecisionResult`

```python
from pydantic import BaseModel, Field
from typing import Any


class DecisionResult(BaseModel):
    decision_id: str
    event_id: str
    user_id: str
    relevance_status: str
    priority_score: float
    priority_level: str
    decision_action: str
    delivery_timing: str
    delivery_channels: list[str] = Field(default_factory=list)
    action_required: bool | None = None
    deadline_at: str | None = None
    reason_summary: str
    explanations: list[str] = Field(default_factory=list)
    evidences: list[DecisionEvidence] = Field(default_factory=list)
    policy_version: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    generated_at: str
```

字段语义：

- `decision_id`：最终裁决 ID
- `event_id + user_id + policy_version`：决策结果的自然幂等键
- `priority_score`：优先级分值，建议范围 `0 ~ 100`
- `decision_action`：最终动作，必须使用本文件定义的枚举值

---

### 5.12 `DeliveryTask`

```python
from pydantic import BaseModel, Field
from typing import Any


class DeliveryTask(BaseModel):
    task_id: str
    decision_id: str
    event_id: str
    user_id: str
    action: str
    channel: str
    title: str
    body: str
    scheduled_at: str | None = None
    dedupe_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

---

### 5.13 `DeliveryLog`

```python
from pydantic import BaseModel, Field
from typing import Any


class DeliveryLog(BaseModel):
    log_id: str
    task_id: str
    decision_id: str
    event_id: str
    user_id: str
    channel: str
    status: str
    retry_count: int = 0
    provider_message_id: str | None = None
    error_message: str | None = None
    delivered_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

字段语义：

- `status`：必须使用 `delivery_status` 枚举值
- `retry_count`：从 `0` 开始累计

---

### 5.14 `UserFeedbackRecord`

```python
from pydantic import BaseModel, Field
from typing import Any


class UserFeedbackRecord(BaseModel):
    feedback_id: str
    user_id: str
    event_id: str
    decision_id: str | None = None
    delivery_log_id: str | None = None
    feedback_type: str
    rating: int | None = None
    comment: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
```

字段语义：

- `rating`：建议值范围 `1 ~ 5`
- `feedback_type`：必须使用本文件枚举值

---

### 5.15 `OptimizationSample`

```python
from pydantic import BaseModel, Field
from typing import Any


class OptimizationSample(BaseModel):
    sample_id: str
    event_id: str
    user_id: str
    rule_analysis_id: str | None = None
    ai_result_id: str | None = None
    decision_id: str | None = None
    delivery_log_id: str | None = None
    outcome_label: str
    source: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    generated_at: str
```

字段语义：

- `outcome_label`：例如 `false_positive`、`false_negative`、`useful_delivery`
- `source`：样本来源，例如 `user_feedback`、`delivery_outcome`、`manual_review`

---

### 5.16 `SourceConfig`

```python
from pydantic import BaseModel, Field
from typing import Any


class SourceConfig(BaseModel):
    source_id: str
    source_name: str
    source_type: str
    connector_type: str
    enabled: bool = True
    auth_config: dict[str, Any] = Field(default_factory=dict)
    parse_config: dict[str, Any] = Field(default_factory=dict)
    polling_schedule: str | None = None
    authority_level: str | None = None
    priority: int = 0
    version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

字段语义：

- `source_id`：配置层中来源配置的稳定主键
- `connector_type`：接入层选择连接器的唯一依据
- `version`：当前生效来源快照版本，可用于审计和回放定位

---

### 5.17 `RuleConfig`

```python
from pydantic import BaseModel, Field
from typing import Any


class RuleConfig(BaseModel):
    rule_id: str
    rule_name: str
    scene: str
    enabled: bool = True
    priority: int = 0
    conditions: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    version: str
    metadata: dict[str, Any] = Field(default_factory=dict)
```

字段语义：

- `scene`：规则所属执行场景，例如 `rule_engine`
- `conditions`：只描述匹配条件，不承载规则执行结果
- `outputs`：只描述命中后要暴露给规则层的结构化信号

---

### 5.18 `NotificationCategoryConfig`

```python
from pydantic import BaseModel, Field


class NotificationCategoryConfig(BaseModel):
    category_id: str
    category_name: str
    parent_category: str | None = None
    keywords: list[str] = Field(default_factory=list)
    enabled: bool = True
    version: str | None = None
```

字段语义：

- `category_id`：跨模块统一类别标识，不允许各模块自造别名
- `parent_category`：用于表达类别层级，不表达业务路由

---

### 5.19 `PushPolicyConfig`

```python
from pydantic import BaseModel, Field
from typing import Any


class PushPolicyConfig(BaseModel):
    policy_id: str
    policy_name: str
    enabled: bool = True
    action: str
    conditions: dict[str, Any] = Field(default_factory=dict)
    channels: list[str] = Field(default_factory=list)
    version: str
```

字段语义：

- `action`：必须使用 `decision_action` 语义，不在配置层直接执行
- `conditions`：仅表达策略命中条件，不承载决策结果
- `channels`：描述允许的投递渠道集合，最终是否投递由决策层和发文层共同决定

---

### 5.20 `AIRuntimeConfig`

```python
from pydantic import BaseModel, Field
from typing import Any


class AIRuntimeConfig(BaseModel):
    config_id: str = "default"
    enabled: bool = True
    provider: str = "mock"
    model_name: str
    prompt_version: str
    template_path: str
    endpoint: str | None = None
    api_key: str | None = None
    timeout_seconds: float = 15.0
    max_retries: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    version: str
```

字段语义：

- `model_name`：本轮 AI 调用默认模型名
- `prompt_version`：与 `AIAnalysisResult.prompt_version` 对齐的提示词版本
- `template_path`：Prompt 模板路径，属于配置选择结果，不是运行时输出
- `version`：AI 运行配置快照版本，用于发布、回滚和审计

---

### 5.21 `DeliveryChannelConfig`

```python
from pydantic import BaseModel, Field
from typing import Any


class DeliveryChannelConfig(BaseModel):
    channel: str
    enabled: bool = True
    provider: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    version: str
```

字段语义：

- `channel`：发文层识别的渠道名，例如 `app_push`、`email`
- `provider`：当前渠道绑定的网关实现或供应商标识
- `config`：渠道默认配置，例如 mock 参数、超时或供应商侧元数据

---

## 6. 字段所有权约定

- 接入层拥有 `SourceEvent` 的生成权
- 配置层拥有 `SourceConfig`、`RuleConfig`、`NotificationCategoryConfig`、`PushPolicyConfig`、`AIRuntimeConfig`、`DeliveryChannelConfig` 的发布权
- 用户画像层拥有 `UserProfile` 的生成和更新权
- 用户画像层拥有 `ProfileContext` 的生成权
- 规则层拥有 `RuleAnalysisResult` 的生成权
- AI 层拥有 `AIAnalysisResult` 的生成权
- 决策层拥有 `DecisionResult` 的生成权
- 发文层拥有 `DeliveryTask` 和 `DeliveryLog` 的生成权
- 反馈层拥有 `UserFeedbackRecord` 和 `OptimizationSample` 的生成权

任何模块都不应擅自重写其他模块已经产出的共享对象语义。

---

## 7. 变更规则

如果独立线程需要调整共享协议，必须遵循以下规则：

1. 新增字段可以做，但必须先更新本文件
2. 删除字段、重命名字段、改变字段类型，必须先做契约评审
3. 新增枚举值前，必须确认不会影响上下游分支判断
4. 模块内部临时字段优先放入 `metadata`，不要直接污染共享对象

---

## 8. 本文档一句话定义

**共享协议文档的核心作用，是冻结系统跨模块公共对象与字段语义，防止独立开发线程在接口层发生漂移。**

---
