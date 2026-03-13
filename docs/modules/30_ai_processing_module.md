# 模块 3：AI 处理层（AI Processing Module）

建议文档名：

```text
docs/modules/30_ai_processing_module.md
```

---

## 1. 业务背景

校园通知中存在大量半结构化和非结构化文本，仅靠规则很难稳定处理这些场景：

- 表达隐晦的动作要求
- 模糊的目标人群描述
- 分散在正文中的截止时间
- 长文本通知摘要
- 模糊类别归类

但系统第一阶段的原则不是“AI 全权裁决”，而是：

**规则优先，AI 辅助。**

因此 AI 层的业务意义是：

**在规则层之后，对复杂语义做补充理解和字段抽取，为决策层提供额外参考。**

它在整个系统里的位置是：

**`SourceEvent + RuleAnalysisResult (+ UserProfile)` → AI 层 → `AIAnalysisResult` → 决策层**

---

## 2. 模块职责

AI 处理层只做这些事情：

1. **做复杂语义理解**
2. **抽取关键字段**
3. **生成简要摘要**
4. **辅助类别判定**
5. **输出结构化 AI 分析结果**

AI 处理层不做这些事情：

- 不替代接入层做采集
- 不替代规则层做基础初筛
- 不直接做最终推送决策
- 不直接触发消息发送
- 不直接维护用户画像和系统配置

一句话：

**AI 处理层是“语义理解补充模块”，不是“唯一判断模块”。**

---

## 3. 模块边界

### 3.1 上游依赖

AI 层上游默认包括：

- `SourceEvent`
- `RuleAnalysisResult`
- `UserProfile`
- 配置层提供的模型配置、提示词模板和阈值配置

---

### 3.2 下游依赖

AI 层只向下游输出统一的：

- `AIAnalysisResult`

下游默认是：

- 决策层
- AI 分析结果存储层

---

### 3.3 边界约束

AI 层必须满足：

- 输出结构必须稳定
- 输出必须可回溯模型和提示版本
- 允许被跳过，不应成为主链路单点依赖
- 不能把原始大模型返回直接泄漏给下游业务
- 必须可使用 mock 替代真实模型进行联调

---

## 4. 模块对外接口定义

---

### 4.1 核心数据结构

#### `AIExtractedField`

```python
from pydantic import BaseModel
from typing import Any


class AIExtractedField(BaseModel):
    field_name: str
    field_value: Any
    confidence: float = 0.0
```

---

#### `AIAnalysisResult`

```python
from pydantic import BaseModel
from typing import Any, Optional


class AIAnalysisResult(BaseModel):
    ai_result_id: str
    event_id: str
    user_id: str
    model_name: str
    prompt_version: str
    summary: Optional[str] = None
    normalized_category: Optional[str] = None
    action_items: list[str] = []
    extracted_fields: list[AIExtractedField] = []
    relevance_hint: Optional[str] = None
    urgency_hint: Optional[str] = None
    risk_hint: Optional[str] = None
    confidence: float = 0.0
    needs_human_review: bool = False
    raw_response_ref: Optional[str] = None
    metadata: dict[str, Any] = {}
    generated_at: str
```

语义说明：

- `summary` 是给后续系统和用户展示的短摘要，不是全文改写
- `relevance_hint` 是 AI 的补充判断，不是最终裁决
- `raw_response_ref` 用于审计和排障，不直接下传到业务层

---

### 4.2 模块主接口

```python
class AIProcessingService:
    async def analyze(
        self,
        event: SourceEvent,
        rule_result: RuleAnalysisResult,
        user_profile: UserProfile,
    ) -> AIAnalysisResult:
        ...
```

说明：

- 输入是一条事件、规则结果和用户画像
- 输出是一条 AI 分析结果

---

### 4.3 模型网关接口

```python
class ModelGateway:
    async def invoke(self, prompt: dict, model_config: dict) -> dict:
        ...
```

说明：

- AI 层内部应通过统一网关访问模型
- 不允许在业务代码中散落模型调用细节

---

### 4.4 降级接口

```python
class AIProcessingService:
    async def analyze_or_fallback(
        self,
        event: SourceEvent,
        rule_result: RuleAnalysisResult,
        user_profile: UserProfile,
    ) -> AIAnalysisResult | None:
        ...
```

说明：

- 当模型不可用、超时或成本策略不允许时，可以返回 `None`
- 决策层必须支持没有 AI 结果的情况

---

## 5. 模块内部架构

建议 AI 层拆成 7 个子模块：

1. `PromptBuilder`
2. `ModelGateway`
3. `FieldExtractor`
4. `SummaryGenerator`
5. `ResultValidator`
6. `AICache`
7. `AIAnalysisRepository`

---

## 6. 子模块详细设计

---

### 6.1 PromptBuilder

#### 业务背景

不同任务的 AI 提示词应分离，例如字段抽取、摘要生成、类别辅助判定。

#### 职责

- 组装任务提示词
- 注入事件、规则结果和画像上下文
- 输出统一 Prompt Payload

#### 接口

```python
class PromptBuilder:
    async def build(self, event: SourceEvent, rule_result: RuleAnalysisResult, user_profile: UserProfile) -> dict:
        ...
```

#### 开发约束

- 不在业务代码里硬编码完整 Prompt
- 必须带 `prompt_version`

---

### 6.2 ModelGateway

#### 业务背景

后续模型供应商、模型版本、调用参数可能变化，业务层不应感知这些细节。

#### 职责

- 封装模型调用
- 统一超时、重试和错误结构
- 统一返回原始模型响应

#### 接口

```python
class ModelGateway:
    async def invoke(self, prompt: dict, model_config: dict) -> dict:
        ...
```

---

### 6.3 FieldExtractor

#### 业务背景

AI 的核心价值之一，是抽取规则难以稳定获取的关键信息。

#### 职责

- 抽取动作要求
- 抽取截止时间
- 抽取目标对象描述
- 抽取材料 / 步骤 / 风险提示

#### 接口

```python
class FieldExtractor:
    async def extract(self, raw_response: dict) -> list[AIExtractedField]:
        ...
```

---

### 6.4 SummaryGenerator

#### 业务背景

长通知不利于快速理解，系统需要一个统一短摘要。

#### 职责

- 生成简明摘要
- 保持语义准确，不夸大
- 避免加入系统未确认的虚构信息

#### 接口

```python
class SummaryGenerator:
    async def summarize(self, raw_response: dict) -> str | None:
        ...
```

---

### 6.5 ResultValidator

#### 业务背景

模型输出不稳定，必须进行结构校验和结果约束。

#### 职责

- 校验字段完整性
- 过滤非法值
- 对低置信度结果加标记
- 必要时触发降级

#### 接口

```python
class ResultValidator:
    async def validate(self, ai_result: AIAnalysisResult) -> AIAnalysisResult:
        ...
```

---

### 6.6 AICache

#### 业务背景

同一事件在短时间内反复进入 AI 会浪费成本。

#### 职责

- 基于事件内容和模型版本做缓存
- 优先返回已存在结果
- 控制重复请求

#### 接口

```python
class AICache:
    async def get(self, cache_key: str) -> AIAnalysisResult | None:
        ...

    async def set(self, cache_key: str, result: AIAnalysisResult) -> None:
        ...
```

---

### 6.7 AIAnalysisRepository

#### 业务背景

AI 结果必须持久化，便于审计、联调、效果评估和后续优化。

#### 职责

- 存储 `AIAnalysisResult`
- 支持按事件 / 用户查询
- 支持导出样本

#### 接口

```python
class AIAnalysisRepository:
    async def save(self, result: AIAnalysisResult) -> None:
        ...

    async def get_by_event_and_user(self, event_id: str, user_id: str) -> AIAnalysisResult | None:
        ...
```

---

## 7. 数据存储设计

AI 层至少依赖两类表：

### 7.1 `ai_analysis_results`

用于存储结构化 AI 分析结果。

### 7.2 `ai_call_logs`

用于记录模型调用日志、耗时、错误和供应商信息。

---

## 8. Mock 设计

本模块必须支持无真实模型条件下的独立联调。

---

### 8.1 Mock 上游输入

#### `SourceEvent`

```json
{
  "event_id": "evt_001",
  "content_text": "请2026届毕业生于3月15日前提交毕业资格审核材料"
}
```

#### `RuleAnalysisResult`

```json
{
  "analysis_id": "rule_001",
  "event_id": "evt_001",
  "user_id": "stu_001",
  "candidate_categories": ["graduation", "material_submission"],
  "relevance_status": "relevant",
  "action_required": true,
  "deadline_at": "2026-03-15T23:59:59+08:00",
  "should_invoke_ai": true
}
```

---

### 8.2 Mock 下游输出

#### `AIAnalysisResult`

```json
{
  "ai_result_id": "ai_001",
  "event_id": "evt_001",
  "user_id": "stu_001",
  "model_name": "gpt-5-mini",
  "prompt_version": "prompt_v1",
  "summary": "该通知要求2026届毕业生在3月15日前提交毕业资格审核材料。",
  "normalized_category": "graduation_material_submission",
  "action_items": ["提交毕业资格审核材料"],
  "extracted_fields": [
    {
      "field_name": "deadline_at",
      "field_value": "2026-03-15T23:59:59+08:00",
      "confidence": 0.94
    }
  ],
  "relevance_hint": "面向毕业生，与你当前身份高度相关",
  "urgency_hint": "存在明确截止时间",
  "risk_hint": "错过可能影响毕业审核进度",
  "confidence": 0.9,
  "needs_human_review": false,
  "raw_response_ref": "ai_raw_001",
  "metadata": {},
  "generated_at": "2026-03-13T10:22:00+08:00"
}
```

---

## 9. 测试要求

---

### 9.1 单元测试

至少包括：

1. Prompt 组装测试
2. mock 模型响应解析测试
3. 非法 JSON / 非法字段结果校验测试
4. 摘要生成测试
5. 低置信度标记测试
6. 缓存命中测试

---

### 9.2 集成测试

至少包括：

1. `SourceEvent + RuleAnalysisResult + UserProfile → AIAnalysisResult` 完整测试
2. 模型调用失败后的降级测试
3. AI 结果持久化测试
4. mock 模型与真实模型网关切换测试

---

### 9.3 验收标准

- 没有 AI 结果时，系统主链路仍可继续
- AI 结果结构稳定、可审计
- AI 输出不会替代规则结果，而是补充规则结果
- 支持 mock 联调

---

## 10. 开发约束

### 10.1 必须做

- 保留模型名和 Prompt 版本
- 输出结构化 `AIAnalysisResult`
- 支持结果校验与降级
- 支持 mock 模型联调

### 10.2 不要做

- 不要让 AI 直接做最终推送动作
- 不要把未经校验的原始模型文本直接交给决策层
- 不要把规则层可以稳定完成的工作全部迁移给 AI

### 10.3 推荐工程目录

```text
backend/app/services/ai_processing/
  __init__.py
  service.py
  prompt_builder.py
  model_gateway.py
  field_extractor.py
  summary_generator.py
  result_validator.py
  cache.py
  repositories/
    ai_analysis_repository.py
  tests/
    test_prompt_builder.py
    test_result_validator.py
    test_mock_gateway.py
```

---

## 11. 模块交付物

AI 处理层模块完成时，应该交付：

1. 代码实现
2. 模块 README
3. Prompt 模板
4. mock 输入输出文件
5. 单元测试
6. 模型网关抽象
7. 结果存储实现

---

## 12. 本模块一句话定义

**AI 处理层模块的核心业务，是在规则层之后补充复杂语义理解与字段抽取，为决策层提供可控、可审计的辅助分析结果。**

---

