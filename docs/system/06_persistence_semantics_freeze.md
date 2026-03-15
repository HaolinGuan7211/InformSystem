# 06_persistence_semantics_freeze.md

# 持久化语义冻结补充（2026-03-15）

## 1. 文档目的

本文件用于冻结当前阶段与持久化语义直接相关的跨模块约束，重点覆盖：

- `decision_results`
- `delivery_logs`
- `optimization_samples`
- 决策层、发文层、反馈层之间的事实写入与读取边界

这不是新的总纲，也不是替代 `05_database_schema.md` 的完整 schema 文档，而是：

**针对持久化语义漂移问题的专项冻结补充。**

---

## 2. 适用范围与优先级

本文件主要适用于以下模块：

- 模块 4：Decision Engine
- 模块 5：Delivery
- 模块 8：Feedback

优先级规则：

1. `01_shared_schemas.md`
2. `02_workflow_orchestration.md`
3. `05_database_schema.md`
4. 本文件
5. `docs/modules/40_*.md` / `50_*.md` / `80_*.md`

说明：

- 本文件不改变 `01/02/05` 的大原则，只把其中与持久化语义相关、容易在并行实现中漂移的部分写细
- 如果本文件和模块文档冲突，以本文件为准

---

## 3. 问题背景

当前仓库已经形成了可运行的全链路原型，但在持久化层出现了三类典型漂移：

1. `decision_results` 实际更像“最新快照表”，而不是 append-only 事实表
2. `delivery_logs` 虽然物理上是一张表，但存在两套 repository 语义
3. 反馈层的样本回填建立在“latest 查询 + 重复 delivery log repo”的假设上，容易把查询便利演变成第二套持久化语义

这些问题在原型期不一定立即阻塞运行，但会直接影响：

- replay
- 审计
- 决策历史追踪
- 投递事实回溯
- 样本质量
- 后续策略对比与误判分析

---

## 4. 冻结结论

### 4.1 `decision_results`

- `decision_results` 是 append-only 事实表
- 每一次决策生成都必须追加一行新的 `decision_results`
- 自然幂等键 `event_id + user_id + policy_version` 只用于识别“同类决策”，不用于覆盖写
- “最新决策”属于读取视图，不属于写入策略
- 不允许通过 `ON CONFLICT ... DO UPDATE` 或唯一键覆盖来实现“取最新”

### 4.2 `delivery_logs`

- `delivery_logs` 是系统唯一的投递事实表
- `pending / failed / sent / skipped` 都是事实日志，不是临时状态缓存
- 同一 `task_id` 下允许存在多条投递历史
- `latest by task`、`latest by event and user` 等能力都是读取视图，不改变 append-only 本质

### 4.3 canonical repository

- `delivery_logs` 的 canonical repository 归属发文层
- 决策层拥有 `decision_results` 的 canonical repository
- 反馈层不再维护第二套 delivery log 写入语义

### 4.4 feedback 回流边界

- 工作流内由发文层刚刚生成的 `DeliveryLog`，反馈层不应再次写入 `delivery_logs`
- 该场景下，反馈层只消费事实并组装样本
- 只有“外部回执补录 / 人工补录”场景，反馈层才可通过同一套 canonical delivery log abstraction 追加新事实

### 4.5 `optimization_samples`

- `optimization_samples` 是派生样本表，不是线上事实表
- 不允许用 `optimization_samples` 替代 `decision_results` 或 `delivery_logs`
- 样本组装中的 latest 查询，必须建立在 append-only 事实表之上

---

## 5. 对各模块的职责约束

### 5.1 模块 4：Decision Engine

- 负责写入 `decision_results`
- `save()` 必须纯追加写
- 可提供 latest 读取接口，但 latest 只能由排序派生
- 可按需要补充版本查询 / 历史查询接口

### 5.2 模块 5：Delivery

- 负责写入 `delivery_logs`
- 持有 canonical delivery log repository
- 需要提供反馈层可复用的标准读取接口
- 不负责样本组装

### 5.3 模块 8：Feedback

- 负责写入 `user_feedback`
- 负责写入 `optimization_samples`
- 通过 canonical repository 读取 delivery facts
- 不再维护独立的 delivery log 写入语义

---

## 6. 施工顺序

本专项必须按下面顺序推进：

1. 主线程冻结本文件
2. 模块 4 先处理 `decision_results`
3. 模块 5 处理 `delivery_logs` canonical repository
4. 模块 8 最后适配 feedback 回流与样本回填
5. 主线程做集成验收

并行规则：

- 40 和 50 可以并行
- 80 必须等待 50 的 canonical repository 接口稳定后再落代码

---

## 7. 最小验收标准

### 7.1 决策事实

- 同一 `event_id + user_id + policy_version` 多次保存后，数据库中保留多条决策事实
- latest 查询仍能稳定返回最新一条

### 7.2 投递事实

- workflow 跑完后，`delivery_logs` 由发文层写入一次即可
- feedback 不会再重复写入工作流内的同一条 delivery fact

### 7.3 反馈样本

- `SampleAssembler` 仍能回填最新 decision 与最新 delivery fact
- `optimization_samples` 仍能正常导出

---

## 8. 不要这样做

- 不要用 upsert 伪装 append-only
- 不要为方便读取新建第二套“latest state 表”
- 不要让 feedback 模块继续保留自己的 delivery log 持久化语义
- 不要为了这次专项顺手改共享 schema 字段
- 不要在未冻结语义时多线程同时改 `database.py`、`container.py`、workflow 主链路

---

## 9. 本文档一句话定义

**本文件的作用，是冻结决策事实、投递事实和反馈样本之间的持久化边界，避免并行施工时各模块对“事实表、最新视图、样本表”长成三套不同语义。**

