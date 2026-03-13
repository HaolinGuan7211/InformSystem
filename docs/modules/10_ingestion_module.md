# 模块 1：接入层（Ingestion Module）

建议文档名：

```text
docs/modules/10_ingestion_module.md
```

---

## 1. 业务背景

校园通知的来源天然是分散的，而且同一条通知可能会出现在多个渠道：

- 企业微信群
- 学校官网通知
- 学院网站公告
- 教务系统公告页
- 邮件
- 手动转发

如果后续规则层、AI 层直接分别对接这些来源，系统会很快失控，因为会出现这些问题：

- 每种来源格式不同
- 同一条通知重复进入系统
- 后续模块要写很多平台适配逻辑
- 联调困难，模块间耦合严重

所以接入层的业务意义是：

**把所有外部信源统一变成标准通知事件，作为整个系统唯一入口。**

它在整个系统里的位置是：

**外部平台 → 接入层 → 标准事件 → 规则层**

---

## 2. 模块职责

接入层只做四件事：

1. **接收外部通知数据**
2. **清洗并标准化为统一事件**
3. **执行接入阶段去重**
4. **把结果写入原始事件存储，并交给后续模块**

接入层不做这些事情：

- 不判断通知是否重要
- 不判断是否与用户相关
- 不调用 AI
- 不决定是否推送
- 不做复杂业务分类

一句话：

**接入层是“采集与标准化入口”，不是“业务判断入口”。**

---

## 3. 模块边界

### 3.1 上游依赖

接入层面对的是外部来源，可能包括：

- 企业微信 webhook
- 网站抓取任务
- 邮件拉取器
- 手动录入 API
- RSS 轮询任务

这些都属于“接入层内部的输入来源”。

---

### 3.2 下游依赖

接入层只向下游输出统一的：

- `SourceEvent`

下游默认是：

- 规则层
- 原始事件存储层

---

### 3.3 边界约束

接入层必须满足：

- 不泄漏来源平台细节给下游
- 不输出不完整 schema
- 不依赖后续模块返回结果才能工作
- 必须可单独运行和测试

---

## 4. 模块对外接口定义

---

### 4.1 核心数据结构

#### `AttachmentInfo`

```python
from pydantic import BaseModel
from typing import Optional


class AttachmentInfo(BaseModel):
    name: str
    url: Optional[str] = None
    mime_type: Optional[str] = None
    storage_key: Optional[str] = None
```

---

#### `SourceEvent`

```python
from pydantic import BaseModel
from typing import Optional, Any


class SourceEvent(BaseModel):
    event_id: str
    source_id: str
    source_type: str
    source_name: str
    channel_type: str
    title: Optional[str] = None
    content_text: str
    content_html: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[str] = None
    collected_at: str
    url: Optional[str] = None
    attachments: list[AttachmentInfo] = []
    metadata: dict[str, Any] = {}
```

---

### 4.2 模块主接口

```python
class IngestionService:
    async def ingest(self, raw_input: dict, source_config: dict) -> list[SourceEvent]:
        ...
```

说明：

- 输入是一份原始数据和对应信源配置
- 输出是一组标准事件
- 某些来源一次可能产出多条事件，比如网站列表页抓取

---

### 4.3 连接器统一接口

```python
class Connector:
    async def fetch(self, source_config: dict) -> list[dict]:
        ...

    async def normalize(self, raw_data: dict, source_config: dict) -> list[SourceEvent]:
        ...

    async def health_check(self, source_config: dict) -> bool:
        ...
```

说明：

- `fetch` 用于拉取型来源
- webhook 型来源可以不直接暴露 `fetch`，由 API 层接收 payload 后直接调用 `normalize`
- 所有 connector 必须实现 `normalize`

---

### 4.4 Webhook 接口

用于企业微信等推送型来源。

```http
POST /api/v1/webhooks/{source_id}
Content-Type: application/json
```

输入示例：

```json
{
  "msgid": "raw_wecom_001",
  "chat_name": "计算机学院通知群",
  "sender": "辅导员A",
  "time": "2026-03-13 10:20:00",
  "text": "请2026届毕业生于3月15日前提交毕业资格审核材料"
}
```

返回示例：

```json
{
  "success": true,
  "accepted": 1
}
```

---

### 4.5 手动导入接口

```http
POST /api/v1/ingestion/manual
Content-Type: application/json
```

输入示例：

```json
{
  "source_name": "manual_input",
  "title": "毕业材料通知",
  "content_text": "请2026届毕业生于3月15日前提交毕业资格审核材料",
  "published_at": "2026-03-13T10:20:00+08:00"
}
```

返回示例：

```json
{
  "success": true,
  "event_ids": ["evt_manual_001"]
}
```

---

### 4.6 重放接口

```http
POST /api/v1/ingestion/replay/{event_id}
```

作用：

- 将历史原始事件重新送入后续流程
- 便于联调规则层、AI 层和决策层

---

## 5. 模块内部架构

建议接入层拆成 7 个子模块：

1. `SourceRegistry`
2. `ConnectorManager`
3. `WebhookReceiver`
4. `Scheduler`
5. `Normalizer`
6. `Deduplicator`
7. `RawEventRepository`

---

## 6. 子模块详细设计

---

### 6.1 SourceRegistry

#### 业务背景

系统需要支持多个信源，而且信源配置经常变化，比如：

- 新增学校网站
- 新增学院通知页
- 修改抓取频率
- 更新企业微信 token

因此信源配置不能写死在代码里，必须统一存储和管理。

#### 职责

- 维护信源配置
- 提供已启用信源列表
- 按 `source_id` 获取配置

#### 接口

```python
class SourceRegistry:
    async def list_enabled_sources(self) -> list[dict]:
        ...

    async def get_source_by_id(self, source_id: str) -> dict | None:
        ...
```

#### 输入

无或 `source_id`

#### 输出

`SourceConfig`

#### `SourceConfig` 示例

```json
{
  "source_id": "wecom_cs_notice_group",
  "source_name": "计算机学院通知群",
  "source_type": "wecom",
  "connector_type": "wecom_webhook",
  "enabled": true,
  "auth_config": {
    "token": "xxx"
  },
  "parse_config": {},
  "polling_schedule": null,
  "authority_level": "high",
  "priority": 100
}
```

#### 开发约束

- 不直接访问业务逻辑
- 只做配置读取
- 应支持数据库与本地配置双实现

---

### 6.2 ConnectorManager

#### 业务背景

不同来源需要不同连接器实现，但下游不能知道具体来源差异。

#### 职责

- 根据 `source_type` / `connector_type` 返回对应 connector 实例

#### 接口

```python
class ConnectorManager:
    def get_connector(self, connector_type: str) -> Connector:
        ...
```

#### 示例映射

- `wecom_webhook` → `WecomWebhookConnector`
- `website_html` → `WebsiteHtmlConnector`
- `email_imap` → `EmailImapConnector`
- `manual_input` → `ManualConnector`

#### 开发约束

- 必须使用注册式映射，不允许大段 if-else 散在业务代码
- 新增 connector 时不应影响已有 connector

---

### 6.3 WebhookReceiver

#### 业务背景

企业微信类来源是实时推送，不需要系统主动轮询。

#### 职责

- 接收 webhook
- 校验来源合法性
- 调用对应 connector 标准化
- 将结果写入原始事件仓库

#### 接口

```python
class WebhookReceiver:
    async def receive(self, source_id: str, payload: dict) -> list[SourceEvent]:
        ...
```

#### 输入

- `source_id`
- 外部 webhook payload

#### 输出

- 标准事件列表

#### 设计细节

- 支持签名校验
- 支持异常 payload 拒绝
- 支持幂等处理

---

### 6.4 Scheduler

#### 业务背景

网站、RSS、邮箱这类来源通常没有 webhook，需要系统定时拉取。

#### 职责

- 按配置调度拉取型 connector
- 触发抓取任务
- 记录成功 / 失败状态

#### 接口

```python
class Scheduler:
    async def run_source(self, source_id: str) -> int:
        ...

    async def run_all_enabled_sources(self) -> int:
        ...
```

#### 输入

- `source_id` 或所有启用信源

#### 输出

- 本次生成的事件数量

#### 技术建议

第一阶段：

- APScheduler 或 Celery Beat

后续：

- Celery Beat + Worker

#### 开发约束

- 抓取失败不应影响其他来源
- 支持重试
- 支持来源级别熔断

---

### 6.5 Normalizer

#### 业务背景

不同来源字段完全不同，必须统一为同一个 schema。

#### 职责

- 清洗标题、正文、作者、时间、附件等字段
- 统一成 `SourceEvent`

#### 接口

```python
class Normalizer:
    async def normalize(self, raw_data: dict, source_config: dict) -> list[SourceEvent]:
        ...
```

#### 输入

原始结构化或半结构化数据

#### 输出

`SourceEvent[]`

#### 设计细节

- 时间统一 ISO 8601
- 附件信息统一列表结构
- 不能识别的原始字段进 `metadata`
- 不在此处做“是否重要”判断

---

### 6.6 Deduplicator

#### 业务背景

多端接入后，同一通知可能重复进入系统。

#### 职责

- 在接入阶段做初步去重
- 计算内容 hash
- 分配 `canonical_notice_id`

#### 接口

```python
class Deduplicator:
    async def is_duplicate(self, event: SourceEvent) -> bool:
        ...

    async def assign_canonical_id(self, event: SourceEvent) -> str:
        ...
```

#### 去重策略

建议三层：

1. 源内唯一标识去重
2. URL 去重
3. 文本 hash / 标题 + 时间窗口去重

#### 开发约束

- 第一版先实现轻量去重
- 相似度去重可放第二阶段

---

### 6.7 RawEventRepository

#### 业务背景

必须保留接入后的原始标准事件，供规则层、联调、排障和重放使用。

#### 职责

- 存储 `SourceEvent`
- 支持按 `event_id` 查询
- 支持重放

#### 接口

```python
class RawEventRepository:
    async def save_events(self, events: list[SourceEvent]) -> None:
        ...

    async def get_event_by_id(self, event_id: str) -> SourceEvent | None:
        ...

    async def list_events(self, limit: int = 100) -> list[SourceEvent]:
        ...
```

#### 开发约束

- 必须持久化
- 不允许仅存在内存中
- 必须支持测试数据回放

---

## 7. 数据存储设计

接入层至少依赖两张表：

### 7.1 `source_configs`

用于存储信源配置。

### 7.2 `raw_events`

用于存储标准化后的原始事件。

建议字段这里直接沿用总文档里的版本，不在模块文档里再发散修改。

---

## 8. Mock 设计

为了支持 AI / 开发者独立实现接入层，本模块必须自带 mock 数据。

---

### 8.1 Mock 上游输入

#### 企业微信消息

```json
{
  "msgid": "raw_wecom_001",
  "chat_name": "计算机学院通知群",
  "sender": "辅导员A",
  "time": "2026-03-13 10:20:00",
  "text": "请2026届毕业生于3月15日前提交毕业资格审核材料"
}
```

#### 网站公告

```json
{
  "url": "https://xxx.edu.cn/notice/123",
  "title": "关于2026届本科毕业资格审核材料提交的通知",
  "html": "<html><body>请各学院于3月15日前组织毕业生提交相关材料</body></html>",
  "published_at": "2026-03-12 09:00:00",
  "attachments": [
    {
      "name": "毕业审核表.docx",
      "url": "https://xxx.edu.cn/files/a.docx"
    }
  ]
}
```

#### 手动输入

```json
{
  "source_name": "manual_input",
  "title": "学分讲座通知",
  "content_text": "本周五晚讲座可认定美育学分，请有需要的同学报名参加。",
  "published_at": "2026-03-13T12:00:00+08:00"
}
```

---

### 8.2 Mock 下游输出

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

---

## 9. 测试要求

接入层必须支持以下测试。

---

### 9.1 单元测试

至少包括：

1. 企业微信 payload → `SourceEvent`
2. 网站公告 payload → `SourceEvent`
3. 手动输入 → `SourceEvent`
4. 空标题 / 空作者 / 空附件边界情况
5. 非法时间格式处理
6. 去重逻辑测试

---

### 9.2 集成测试

至少包括：

1. webhook API 接入测试
2. scheduler 触发网站抓取测试
3. 数据库存储测试
4. replay 接口测试

---

### 9.3 验收标准

模块完成后，必须满足：

- 不依赖规则层即可独立运行
- 不依赖 AI 层即可独立运行
- 不依赖真实外部平台也可用 mock 测试
- 输出 schema 100% 符合共享协议
- 对相同输入输出稳定一致

---

## 10. 开发约束

给 Codex / AI 的明确要求可以写成：

### 10.1 必须做

- 严格使用共享 schema
- 提供 connector 抽象
- 提供至少一个 `wecom` connector 和一个 `website` connector
- 提供单元测试
- 提供 mock 数据

### 10.2 不要做

- 不要在接入层加入业务打分逻辑
- 不要直接调用规则层或 AI 层内部实现
- 不要在 connector 内部硬编码用户相关逻辑
- 不要把网站解析逻辑和业务逻辑混在一起

### 10.3 推荐工程目录

```text
backend/app/services/ingestion/
  __init__.py
  service.py
  registry.py
  connector_manager.py
  normalizer.py
  deduplicator.py
  connectors/
    base.py
    wecom_webhook.py
    website_html.py
    manual_input.py
  repositories/
    raw_event_repository.py
    source_config_repository.py
  tests/
    test_wecom_connector.py
    test_website_connector.py
    test_deduplicator.py
```

---

## 11. 模块交付物

接入层模块完成时，应该交付：

1. 代码实现
2. 模块 README
3. mock 输入输出文件
4. 单元测试
5. API 路由
6. 数据库存储实现
7. 可运行的本地 demo

---

## 12. 本模块一句话定义

**接入层模块的核心业务，是把多种外部通知来源统一转换成标准通知事件，为后续规则分析提供唯一入口。**

---

