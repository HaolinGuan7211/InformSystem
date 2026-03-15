# Delivery

模块 5 负责把 `DecisionResult` 转成真实触达动作，并把执行过程落到 `delivery_logs` / `delivery_digest_jobs`。

## 已实现内容

- `DeliveryPlanner` 把决策结果收口成按渠道拆分的 `DeliveryTask`
- `MessageRenderer` 统一生成即时提醒和 digest 汇总文案
- `GatewayManager` + mock 渠道网关屏蔽外部发送细节
- `RetryManager` 负责失败重试，并保留中间失败日志
- `DigestComposer` 负责 digest 入队、窗口聚合与 flush
- `DeliveryLogRepository` / `DigestJobRepository` 持久化投递日志和 digest 队列
- `DeliveryService` 提供单条、批量、digest flush 三个执行入口

## 当前边界

- 发文层只执行 `push_now`、`push_high`、`digest`；`archive` / `ignore` 会被直接跳过
- 发文层不回头重算渠道；默认只消费 `DecisionResult.delivery_channels`
- `scheduled` 类型当前先落 `pending` 日志，待编排层在到点后重新调用 `dispatch`
- 缺失渠道或缺少网关适配器时，会落失败日志而不是直接抛异常吞掉审计
- 渠道实现先使用 mock 网关，后续可以在 `GatewayManager` 中替换为真实 SDK 适配器
