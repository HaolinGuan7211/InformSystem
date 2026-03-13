# 模块 5：发文层（Delivery Module）

建议文档名：

```text
docs/modules/50_delivery_module.md
```

---

## 1. 业务背景

系统做出决策之后，真正产生用户价值的环节是“把正确的信息，以正确的方式，在正确的时间送达给用户”。

如果没有独立发文层，而是让决策层或其他模块直接发送通知，会出现这些问题：

- 推送渠道逻辑散乱
- 发送失败无法统一重试
- 相同决策可能重复投递
- 汇总通知和即时提醒难以统一管理
- 无法形成完整投递日志

因此发文层的业务意义是：

**把统一决策结果转化为实际触达动作，并记录完整的投递过程。**

它在整个系统里的位置是：

**`DecisionResult` → 发文层 → 外部渠道 / `DeliveryLog` → 反馈层**

---

## 2. 模块职责

发文层只做这些事情：

1. **读取统一决策结果**
2. **渲染适合渠道的通知内容**
3. **选择并调用实际投递渠道**
4. **处理重试、幂等和失败记录**
5. **输出完整投递日志**

发文层不做这些事情：

- 不做通知采集
- 不做规则分析
- 不调用 AI 进行主判断
- 不做最终是否推送的裁决
- 不直接修改用户画像和配置

一句话：

**发文层是“触达执行入口”，不是“业务判断入口”。**

---

## 3. 模块边界

### 3.1 上游依赖

发文层上游默认包括：

- `DecisionResult`
- `SourceEvent`
- `UserProfile`
- 配置层提供的渠道配置和模板配置

---

### 3.2 下游依赖

发文层向下游输出：

- 外部通知渠道调用
- `DeliveryLog`

下游默认是：

- 外部推送服务
- 反馈层
- 投递日志存储层

---

### 3.3 边界约束

发文层必须满足：

- 投递必须幂等
- 投递失败可重试
- 投递日志完整可追踪
- 渠道细节不能泄漏给上游业务层
- 支持即时提醒和汇总提醒两种模式

---

## 4. 模块对外接口定义

---

### 4.1 核心数据结构

#### `DeliveryTask`

```python
from pydantic import BaseModel
from typing import Any, Optional


class DeliveryTask(BaseModel):
    task_id: str
    decision_id: str
    event_id: str
    user_id: str
    action: str
    channel: str
    title: str
    body: str
    scheduled_at: Optional[str] = None
    dedupe_key: Optional[str] = None
    metadata: dict[str, Any] = {}
```

---

#### `DeliveryLog`

```python
from pydantic import BaseModel
from typing import Any, Optional


class DeliveryLog(BaseModel):
    log_id: str
    task_id: str
    decision_id: str
    event_id: str
    user_id: str
    channel: str
    status: str
    retry_count: int = 0
    provider_message_id: Optional[str] = None
    error_message: Optional[str] = None
    delivered_at: Optional[str] = None
    metadata: dict[str, Any] = {}
```

语义说明：

- `status` 建议值：`pending` / `sent` / `failed` / `skipped`

---

### 4.2 模块主接口

```python
class DeliveryService:
    async def dispatch(
        self,
        decision_result: DecisionResult,
        event: SourceEvent,
        user_profile: UserProfile,
    ) -> DeliveryLog:
        ...
```

说明：

- 输入是一条决策结果、事件和用户画像
- 输出是一条投递日志

---

### 4.3 批量接口

```python
class DeliveryService:
    async def dispatch_batch(
        self,
        items: list[tuple[DecisionResult, SourceEvent, UserProfile]],
    ) -> list[DeliveryLog]:
        ...
```

---

### 4.4 渠道网关接口

```python
class DeliveryChannelGateway:
    async def send(self, task: DeliveryTask, channel_config: dict) -> dict:
        ...
```

说明：

- 各种渠道实现都应通过统一网关抽象

---

## 5. 模块内部架构

建议发文层拆成 7 个子模块：

1. `DeliveryPlanner`
2. `MessageRenderer`
3. `ChannelRouter`
4. `GatewayManager`
5. `RetryManager`
6. `DigestComposer`
7. `DeliveryLogRepository`

---

## 6. 子模块详细设计

---

### 6.1 DeliveryPlanner

#### 业务背景

决策结果需要转成具体可执行任务，例如立即发送还是进入汇总队列。

#### 职责

- 生成 `DeliveryTask`
- 计算 `dedupe_key`
- 处理即时和汇总模式分流

#### 接口

```python
class DeliveryPlanner:
    async def build_task(
        self,
        decision_result: DecisionResult,
        event: SourceEvent,
        user_profile: UserProfile,
    ) -> DeliveryTask:
        ...
```

---

### 6.2 MessageRenderer

#### 业务背景

不同渠道展示能力不同，消息内容需要统一渲染。

#### 职责

- 生成消息标题和正文
- 针对渠道做格式适配
- 对长文本做必要裁剪

#### 接口

```python
class MessageRenderer:
    async def render(self, decision_result: DecisionResult, event: SourceEvent) -> dict:
        ...
```

---

### 6.3 ChannelRouter

#### 业务背景

不同动作和用户偏好下，应选择不同渠道。

#### 职责

- 选择实际渠道
- 处理渠道降级
- 支持多渠道组合策略

#### 接口

```python
class ChannelRouter:
    async def resolve(self, decision_result: DecisionResult, user_profile: UserProfile) -> list[str]:
        ...
```

---

### 6.4 GatewayManager

#### 业务背景

发文层不应在业务流程里散落各家渠道 API 调用细节。

#### 职责

- 注册并获取具体渠道网关
- 屏蔽渠道差异
- 统一错误结构

#### 接口

```python
class GatewayManager:
    def get_gateway(self, channel: str) -> DeliveryChannelGateway:
        ...
```

---

### 6.5 RetryManager

#### 业务背景

外部渠道不稳定是常态，失败重试是基础能力。

#### 职责

- 控制重试次数
- 记录失败原因
- 支持指数退避或延迟重试

#### 接口

```python
class RetryManager:
    async def execute(self, task: DeliveryTask, sender) -> DeliveryLog:
        ...
```

---

### 6.6 DigestComposer

#### 业务背景

部分通知不适合立即打扰，而应进入汇总提醒。

#### 职责

- 收集 digest 类任务
- 按时间窗口合并内容
- 生成汇总消息

#### 接口

```python
class DigestComposer:
    async def enqueue(self, task: DeliveryTask) -> None:
        ...

    async def flush(self, user_id: str, window_key: str) -> DeliveryLog:
        ...
```

---

### 6.7 DeliveryLogRepository

#### 业务背景

必须保留投递日志，便于追踪“有没有发、何时发、为何失败”。

#### 职责

- 存储 `DeliveryLog`
- 支持按用户 / 事件 / 决策查询
- 支持重试记录追踪

#### 接口

```python
class DeliveryLogRepository:
    async def save(self, log: DeliveryLog) -> None:
        ...

    async def list_by_user(self, user_id: str, limit: int = 100) -> list[DeliveryLog]:
        ...
```

---

## 7. 数据存储设计

发文层至少依赖：

### 7.1 `delivery_logs`

用于存储投递日志。

### 7.2 `delivery_digest_jobs`

用于存储待发送的汇总任务。

---

## 8. Mock 设计

---

### 8.1 Mock 上游输入

#### `DecisionResult`

```json
{
  "decision_id": "dec_001",
  "event_id": "evt_001",
  "user_id": "stu_001",
  "decision_action": "push_now",
  "delivery_timing": "immediate",
  "delivery_channels": ["app_push"],
  "reason_summary": "毕业审核材料提交通知，存在明确截止时间。"
}
```

---

### 8.2 Mock 下游输出

#### `DeliveryLog`

```json
{
  "log_id": "dlv_001",
  "task_id": "task_001",
  "decision_id": "dec_001",
  "event_id": "evt_001",
  "user_id": "stu_001",
  "channel": "app_push",
  "status": "sent",
  "retry_count": 0,
  "provider_message_id": "msg_abc_001",
  "error_message": null,
  "delivered_at": "2026-03-13T10:24:00+08:00",
  "metadata": {}
}
```

---

## 9. 测试要求

---

### 9.1 单元测试

至少包括：

1. `DecisionResult → DeliveryTask` 生成测试
2. 渠道路由测试
3. 消息渲染测试
4. 失败重试测试
5. 幂等去重测试
6. digest 入队测试

---

### 9.2 集成测试

至少包括：

1. 即时推送完整链路测试
2. 汇总通知完整链路测试
3. 渠道发送失败后的重试测试
4. 投递日志持久化测试

---

### 9.3 验收标准

- 决策结果可直接进入发文层执行
- 发文层不包含最终裁决逻辑
- 投递可追踪、可重试、可幂等
- 支持 mock 渠道联调

---

## 10. 开发约束

### 10.1 必须做

- 统一输出 `DeliveryLog`
- 支持幂等投递
- 支持失败重试
- 支持至少一种即时渠道和一种汇总渠道

### 10.2 不要做

- 不要在发文层重新判断通知是否重要
- 不要把渠道 SDK 调用散在业务代码里
- 不要丢失失败日志

### 10.3 推荐工程目录

```text
backend/app/services/delivery/
  __init__.py
  service.py
  planner.py
  renderer.py
  channel_router.py
  gateway_manager.py
  retry_manager.py
  digest_composer.py
  gateways/
    base.py
    app_push.py
    email.py
  repositories/
    delivery_log_repository.py
  tests/
    test_planner.py
    test_retry_manager.py
    test_delivery_service.py
```

---

## 11. 模块交付物

发文层模块完成时，应该交付：

1. 代码实现
2. 模块 README
3. mock 输入输出文件
4. 单元测试
5. 渠道网关抽象
6. 投递日志实现

---

## 12. 本模块一句话定义

**发文层模块的核心业务，是把统一决策结果转化为实际触达动作，并以可幂等、可重试、可追踪的方式完成投递执行。**

---

