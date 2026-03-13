# 模块 8：反馈层（Feedback Module）

建议文档名：

```text
docs/modules/80_feedback_module.md
```

---

## 1. 业务背景

系统要持续优化，就必须知道：

- 哪些通知推送得对
- 哪些通知推送得太晚
- 哪些通知其实与用户无关
- 哪些高价值通知被漏掉了

如果没有反馈层，系统会长期停留在“只能输出结果、无法校正结果”的状态。

因此反馈层的业务意义是：

**采集用户反馈、投递结果和误判样本，为规则、AI 和策略优化提供闭环依据。**

它在整个系统里的位置是：

**决策结果 / 投递结果 / 用户操作 → 反馈层 → 反馈记录 / 优化样本**

---

## 2. 模块职责

反馈层只做这些事情：

1. **记录用户反馈**
2. **记录投递结果回收**
3. **沉淀误判和漏判样本**
4. **输出可供规则和 AI 优化使用的样本**
5. **支持基础效果分析**

反馈层不做这些事情：

- 不重新执行规则判断
- 不直接修改决策结果
- 不直接发送通知
- 不直接训练模型
- 不替代配置层发布新规则

一句话：

**反馈层是“优化输入闭环”，不是“线上主判断链路”。**

---

## 3. 模块边界

### 3.1 上游依赖

反馈层上游可能包括：

- 用户主动反馈
- 发文层投递日志
- 决策层决策结果
- 管理员人工标注

---

### 3.2 下游依赖

反馈层向下游输出：

- `UserFeedbackRecord`
- `OptimizationSample`

下游默认是：

- 规则优化流程
- AI 优化流程
- 效果分析与运营查看

---

### 3.3 边界约束

反馈层必须满足：

- 原始反馈不可丢失
- 反馈记录与线上主链路解耦
- 支持结构化导出
- 支持用户反馈和系统行为数据统一汇总
- 必须可独立测试

---

## 4. 模块对外接口定义

---

### 4.1 核心数据结构

#### `UserFeedbackRecord`

```python
from pydantic import BaseModel
from typing import Any, Optional


class UserFeedbackRecord(BaseModel):
    feedback_id: str
    user_id: str
    event_id: str
    decision_id: Optional[str] = None
    delivery_log_id: Optional[str] = None
    feedback_type: str
    rating: Optional[int] = None
    comment: Optional[str] = None
    metadata: dict[str, Any] = {}
    created_at: str
```

语义说明：

- `feedback_type` 建议值：
  - `useful`
  - `not_relevant`
  - `too_late`
  - `too_frequent`
  - `missed_important`

---

#### `OptimizationSample`

```python
from pydantic import BaseModel
from typing import Any, Optional


class OptimizationSample(BaseModel):
    sample_id: str
    event_id: str
    user_id: str
    rule_analysis_id: Optional[str] = None
    ai_result_id: Optional[str] = None
    decision_id: Optional[str] = None
    delivery_log_id: Optional[str] = None
    outcome_label: str
    source: str
    metadata: dict[str, Any] = {}
    generated_at: str
```

---

### 4.2 模块主接口

```python
class FeedbackService:
    async def record_user_feedback(self, payload: dict) -> UserFeedbackRecord:
        ...

    async def record_delivery_outcome(self, delivery_log: DeliveryLog) -> None:
        ...

    async def export_optimization_samples(self, limit: int = 1000) -> list[OptimizationSample]:
        ...
```

---

### 4.3 用户反馈 API

```http
POST /api/v1/feedback
Content-Type: application/json
```

输入示例：

```json
{
  "user_id": "stu_001",
  "event_id": "evt_001",
  "decision_id": "dec_001",
  "delivery_log_id": "dlv_001",
  "feedback_type": "useful",
  "rating": 5,
  "comment": "这条提醒很及时"
}
```

返回示例：

```json
{
  "success": true,
  "feedback_id": "fb_001"
}
```

---

## 5. 模块内部架构

建议反馈层拆成 6 个子模块：

1. `FeedbackReceiver`
2. `DeliveryOutcomeCollector`
3. `SampleAssembler`
4. `FeedbackRepository`
5. `SampleRepository`
6. `FeedbackExporter`

---

## 6. 子模块详细设计

---

### 6.1 FeedbackReceiver

#### 业务背景

用户主动反馈是系统优化最直接的信号来源。

#### 职责

- 接收用户反馈
- 校验输入
- 生成标准反馈记录

#### 接口

```python
class FeedbackReceiver:
    async def receive(self, payload: dict) -> UserFeedbackRecord:
        ...
```

---

### 6.2 DeliveryOutcomeCollector

#### 业务背景

不仅要记录用户主观反馈，也要记录系统是否成功送达。

#### 职责

- 读取发文层投递日志
- 标记送达成功 / 失败 / 重试
- 为效果统计提供数据

#### 接口

```python
class DeliveryOutcomeCollector:
    async def collect(self, delivery_log: DeliveryLog) -> None:
        ...
```

---

### 6.3 SampleAssembler

#### 业务背景

反馈优化依赖“事件 + 分析结果 + 决策 + 投递 + 用户反馈”的组合视图。

#### 职责

- 组装优化样本
- 标记误判和漏判类型
- 输出 `OptimizationSample`

#### 接口

```python
class SampleAssembler:
    async def build_sample(self, event_id: str, user_id: str) -> OptimizationSample | None:
        ...
```

---

### 6.4 FeedbackRepository

#### 业务背景

用户反馈是原始事实数据，必须单独持久化。

#### 职责

- 存储 `UserFeedbackRecord`
- 支持按用户 / 事件查询
- 支持去重和幂等写入

#### 接口

```python
class FeedbackRepository:
    async def save(self, record: UserFeedbackRecord) -> None:
        ...

    async def list_by_user(self, user_id: str, limit: int = 100) -> list[UserFeedbackRecord]:
        ...
```

---

### 6.5 SampleRepository

#### 业务背景

优化样本常常由多表拼合而成，需要单独沉淀供后续分析使用。

#### 职责

- 存储 `OptimizationSample`
- 支持筛选导出
- 支持按结果标签查询

#### 接口

```python
class SampleRepository:
    async def save(self, sample: OptimizationSample) -> None:
        ...
```

---

### 6.6 FeedbackExporter

#### 业务背景

规则优化、AI 优化和效果分析需要结构化导出样本。

#### 职责

- 导出反馈样本
- 导出误判数据
- 生成基础分析统计

#### 接口

```python
class FeedbackExporter:
    async def export(self, limit: int = 1000) -> list[OptimizationSample]:
        ...
```

---

## 7. 数据存储设计

反馈层至少依赖：

### 7.1 `user_feedback`

用于存储用户反馈记录。

### 7.2 `optimization_samples`

用于存储后续优化样本。

---

## 8. Mock 设计

---

### 8.1 Mock 上游输入

#### 用户反馈

```json
{
  "user_id": "stu_001",
  "event_id": "evt_001",
  "decision_id": "dec_001",
  "delivery_log_id": "dlv_001",
  "feedback_type": "not_relevant",
  "rating": 1,
  "comment": "这条和我无关"
}
```

---

### 8.2 Mock 下游输出

#### `OptimizationSample`

```json
{
  "sample_id": "sample_001",
  "event_id": "evt_001",
  "user_id": "stu_001",
  "rule_analysis_id": "rule_001",
  "ai_result_id": "ai_001",
  "decision_id": "dec_001",
  "delivery_log_id": "dlv_001",
  "outcome_label": "false_positive",
  "source": "user_feedback",
  "metadata": {
    "feedback_type": "not_relevant"
  },
  "generated_at": "2026-03-13T10:30:00+08:00"
}
```

---

## 9. 测试要求

---

### 9.1 单元测试

至少包括：

1. 用户反馈写入测试
2. 反馈字段校验测试
3. 重复反馈幂等测试
4. 投递结果采集测试
5. 优化样本组装测试
6. 导出测试

---

### 9.2 集成测试

至少包括：

1. 用户反馈 API 测试
2. `DeliveryLog → Feedback` 回流测试
3. `Feedback → OptimizationSample` 生成测试
4. 反馈记录存储测试

---

### 9.3 验收标准

- 原始反馈完整可追踪
- 反馈层不影响线上主链路可用性
- 可输出用于规则和 AI 优化的样本
- 支持用户反馈与系统行为联合分析

---

## 10. 开发约束

### 10.1 必须做

- 支持用户反馈记录
- 支持投递结果回收
- 支持优化样本导出
- 保留原始反馈事实

### 10.2 不要做

- 不要在反馈层直接修改线上规则
- 不要在反馈层直接覆盖决策结果
- 不要只保留汇总统计而丢失原始反馈

### 10.3 推荐工程目录

```text
backend/app/services/feedback/
  __init__.py
  service.py
  receiver.py
  delivery_outcome_collector.py
  sample_assembler.py
  exporter.py
  repositories/
    feedback_repository.py
    sample_repository.py
  tests/
    test_feedback_receiver.py
    test_sample_assembler.py
    test_feedback_api.py
```

---

## 11. 模块交付物

反馈层模块完成时，应该交付：

1. 代码实现
2. 模块 README
3. mock 输入输出文件
4. 单元测试
5. 反馈接口
6. 样本导出实现

---

## 12. 本模块一句话定义

**反馈层模块的核心业务，是采集用户反馈和系统行为结果，形成可沉淀、可导出、可优化的反馈闭环数据。**

---

