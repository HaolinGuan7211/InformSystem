# Ingestion Module

模块 1 负责把外部通知信源统一转换为标准 `SourceEvent`，并在接入阶段做轻量去重与持久化。

## 已实现内容

- `SourceRegistry` 读取 `source_configs`
- `ConnectorManager` 注册式连接器分发
- `WecomWebhookConnector`
- `WebsiteHtmlConnector`
- `ManualConnector`
- `Normalizer` 统一时间、正文、附件和额外字段
- `Deduplicator` 基于源内唯一标识、URL、内容 hash 去重
- `RawEventRepository` 基于 SQLite 的持久化
- `WebhookReceiver`、`Scheduler`、`IngestionService`

## 当前约束

- 网站抓取先用 mock 文件模拟
- scheduler 先提供服务层能力，尚未接 APScheduler/Celery
- replay 先返回历史事件，后续模块接入后可继续往规则层投递

