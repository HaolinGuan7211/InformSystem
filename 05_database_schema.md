# 05_database_schema.md

# 校园通知智能筛选系统数据库 Schema 草案

## 1. 文档目的

本文档用于定义第一阶段数据库层面的公共约束，包括：

- 核心表清单
- 关键字段
- 主键与唯一键
- 跨模块表关系
- 追加写还是更新写的策略

本文件是跨模块持久化契约，不等价于最终 SQL DDL。

---

## 2. 适用范围

第一阶段目标数据库为：

- PostgreSQL：主数据库
- Redis：缓存、Broker、去重与幂等辅助
- MinIO / S3：附件对象存储

说明：

- 本文档以 PostgreSQL 表结构为主
- SQLite 仅可作为本地原型或测试替代，不作为权威 schema

---

## 3. 全局数据库约定

### 3.1 表与列命名

- 表名统一使用复数下划线形式，例如 `raw_events`
- 列名统一使用 `snake_case`
- 外键统一使用 `*_id`

### 3.2 主键约定

- 第一阶段主键统一使用应用层生成的字符串 ID
- 不要求数据库侧生成自增主键作为业务主键

### 3.3 时间列约定

- 所有时间列统一使用 `timestamptz`
- 建议保留 `created_at` 和 `updated_at`

### 3.4 JSON 列约定

- 结构化但变动较快的扩展字段使用 `jsonb`
- 不允许把本应单独建字段的关键查询字段全部塞进 `jsonb`

### 3.5 写入策略约定

以下表以“追加写”为主：

- `raw_events`
- `rule_analysis_results`
- `ai_analysis_results`
- `ai_call_logs`
- `decision_results`
- `delivery_logs`
- `user_feedback`
- `optimization_samples`
- `config_change_logs`

以下表允许“更新写”：

- `source_configs`
- `user_profiles`
- `user_course_enrollments`
- `user_preferences`
- `rule_configs`
- `push_policy_configs`
- `notification_category_configs`
- `ai_runtime_configs`

---

## 4. 核心关系概览

主链路关系建议如下：

- `source_configs` 1 -> n `raw_events`
- `raw_events` 1 -> n `rule_analysis_results`
- `user_profiles` 1 -> n `rule_analysis_results`
- `raw_events` 1 -> n `ai_analysis_results`
- `user_profiles` 1 -> n `ai_analysis_results`
- `raw_events` 1 -> n `decision_results`
- `user_profiles` 1 -> n `decision_results`
- `decision_results` 1 -> n `delivery_logs`
- `raw_events` 1 -> n `user_feedback`
- `user_profiles` 1 -> n `user_feedback`
- `raw_events` 1 -> n `optimization_samples`

说明：

- 第一阶段允许部分关系通过业务键关联，而不是强制所有表都加数据库级外键
- 但表字段命名必须允许这种关联关系稳定存在

---

## 5. 核心表设计

---

### 5.1 `source_configs`

用途：

- 存储信源配置

关键字段建议：

- `source_id` `text` PK
- `source_name` `text`
- `source_type` `text`
- `connector_type` `text`
- `enabled` `boolean`
- `auth_config` `jsonb`
- `parse_config` `jsonb`
- `polling_schedule` `text`
- `authority_level` `text`
- `priority` `int`
- `version` `text`
- `created_at` `timestamptz`
- `updated_at` `timestamptz`

约束建议：

- 主键：`source_id`
- 索引：`enabled`, `source_type`

写入策略：

- upsert

---

### 5.2 `raw_events`

用途：

- 存储标准化后的原始事件

关键字段建议：

- `event_id` `text` PK
- `source_id` `text`
- `source_type` `text`
- `source_name` `text`
- `channel_type` `text`
- `title` `text null`
- `content_text` `text`
- `content_html` `text null`
- `author` `text null`
- `published_at` `timestamptz null`
- `collected_at` `timestamptz`
- `url` `text null`
- `attachments_json` `jsonb`
- `metadata_json` `jsonb`
- `canonical_notice_id` `text null`
- `content_hash` `text null`
- `unique_source_key` `text null`
- `created_at` `timestamptz`

约束建议：

- 主键：`event_id`
- 唯一索引：`unique_source_key`（允许 null）
- 普通索引：`source_id`, `url`, `content_hash`, `collected_at`

写入策略：

- append-only

---

### 5.3 `user_profiles`

用途：

- 存储用户基础身份与状态

关键字段建议：

- `user_id` `text` PK
- `student_id` `text`
- `name` `text null`
- `college` `text null`
- `major` `text null`
- `grade` `text null`
- `degree_level` `text null`
- `identity_tags_json` `jsonb`
- `graduation_stage` `text null`
- `credit_status_json` `jsonb`
- `current_tasks_json` `jsonb`
- `metadata_json` `jsonb`
- `created_at` `timestamptz`
- `updated_at` `timestamptz`

约束建议：

- 主键：`user_id`
- 唯一索引：`student_id`
- 普通索引：`college`, `grade`, `graduation_stage`

写入策略：

- upsert

结构约束补充：

- `credit_status_json` 必须对齐 `01_shared_schemas.md` 中冻结的内部结构，至少包含：
  - `program_summary`
  - `module_progress`
  - `pending_items`
  - `attention_signals`
  - `source_snapshot`
- 学校侧原始字段如 `PYFADM`、`KZH`、`FKZH` 不得提升为 `user_profiles` 的一级列，只能停留在 `credit_status_json[*].metadata` 或 `metadata_json`
- `enrolled_courses` 对应的当前课程快照仍存于 `user_course_enrollments`，不得把全量培养方案课程明细混写进 `user_course_enrollments`

---

### 5.4 `user_course_enrollments`

用途：

- 存储课程快照

关键字段建议：

- `user_id` `text`
- `course_id` `text`
- `course_name` `text`
- `teacher` `text null`
- `semester` `text null`
- `created_at` `timestamptz`
- `updated_at` `timestamptz`

约束建议：

- 复合唯一键：`user_id + course_id + semester`
- 索引：`user_id`, `semester`

写入策略：

- upsert

---

### 5.5 `user_preferences`

用途：

- 存储通知偏好

关键字段建议：

- `user_id` `text` PK
- `channels_json` `jsonb`
- `quiet_hours_json` `jsonb`
- `digest_enabled` `boolean`
- `muted_categories_json` `jsonb`
- `created_at` `timestamptz`
- `updated_at` `timestamptz`

写入策略：

- upsert

---

### 5.6 `rule_configs`

用途：

- 存储规则配置

关键字段建议：

- `rule_id` `text`
- `version` `text`
- `rule_name` `text`
- `scene` `text`
- `enabled` `boolean`
- `priority` `int`
- `conditions_json` `jsonb`
- `outputs_json` `jsonb`
- `created_at` `timestamptz`
- `updated_at` `timestamptz`

约束建议：

- 复合唯一键：`rule_id + version`
- 索引：`scene`, `enabled`, `priority`

写入策略：

- append new version, active flag switch

---

### 5.7 `rule_analysis_results`

用途：

- 存储规则分析结果

关键字段建议：

- `analysis_id` `text` PK
- `event_id` `text`
- `user_id` `text`
- `rule_version` `text`
- `candidate_categories_json` `jsonb`
- `matched_rules_json` `jsonb`
- `extracted_signals_json` `jsonb`
- `required_profile_facets_json` `jsonb`
- `relevance_status` `text`
- `relevance_score` `numeric`
- `action_required` `boolean null`
- `deadline_at` `timestamptz null`
- `urgency_level` `text`
- `risk_level` `text`
- `should_invoke_ai` `boolean`
- `should_continue` `boolean`
- `explanation_json` `jsonb`
- `metadata_json` `jsonb`
- `generated_at` `timestamptz`

约束建议：

- 主键：`analysis_id`
- 自然唯一键：`event_id + user_id + rule_version`
- 索引：`event_id`, `user_id`, `relevance_status`, `should_invoke_ai`

写入策略：

- append-only

结构约束补充：

- `required_profile_facets_json` 中的值必须来自共享协议中的 `profile_facet` 枚举
- `required_profile_facets_json` 用于驱动后续 `ProfileContextSelector` 生成最小相关画像上下文，不得被替换进 `metadata_json`

---

### 5.8 `ai_analysis_results`

用途：

- 存储 AI 分析结果

关键字段建议：

- `ai_result_id` `text` PK
- `event_id` `text`
- `user_id` `text`
- `model_name` `text`
- `prompt_version` `text`
- `summary` `text null`
- `normalized_category` `text null`
- `action_items_json` `jsonb`
- `extracted_fields_json` `jsonb`
- `relevance_hint` `text null`
- `urgency_hint` `text null`
- `risk_hint` `text null`
- `confidence` `numeric`
- `needs_human_review` `boolean`
- `raw_response_ref` `text null`
- `metadata_json` `jsonb`
- `generated_at` `timestamptz`

约束建议：

- 主键：`ai_result_id`
- 自然唯一键：`event_id + user_id + model_name + prompt_version`
- 索引：`event_id`, `user_id`, `needs_human_review`

写入策略：

- append-only

---

### 5.9 `ai_call_logs`

用途：

- 存储模型调用日志

关键字段建议：

- `call_id` `text` PK
- `event_id` `text`
- `user_id` `text`
- `model_name` `text`
- `prompt_version` `text`
- `status` `text`
- `latency_ms` `int null`
- `error_message` `text null`
- `raw_request_ref` `text null`
- `raw_response_ref` `text null`
- `created_at` `timestamptz`

写入策略：

- append-only

---

### 5.10 `push_policy_configs`

用途：

- 存储推送策略配置

关键字段建议：

- `policy_id` `text`
- `version` `text`
- `policy_name` `text`
- `enabled` `boolean`
- `action` `text`
- `conditions_json` `jsonb`
- `channels_json` `jsonb`
- `created_at` `timestamptz`
- `updated_at` `timestamptz`

约束建议：

- 复合唯一键：`policy_id + version`
- 索引：`enabled`, `action`

---

### 5.11 `notification_category_configs`

用途：

- 存储通知类别配置

关键字段建议：

- `category_id` `text` PK
- `category_name` `text`
- `parent_category` `text null`
- `keywords_json` `jsonb`
- `enabled` `boolean`
- `created_at` `timestamptz`
- `updated_at` `timestamptz`

---

### 5.12 `ai_runtime_configs`

用途：

- 存储 AI runtime 配置快照

关键字段建议：

- `config_id` `text`
- `version` `text`
- `enabled` `boolean`
- `provider` `text`
- `model_name` `text`
- `prompt_version` `text`
- `template_path` `text`
- `endpoint` `text null`
- `api_key` `text null`
- `timeout_seconds` `numeric`
- `max_retries` `int`
- `metadata_json` `jsonb`
- `created_at` `timestamptz`
- `updated_at` `timestamptz`

约束建议：

- 复合唯一键：`config_id + version`
- 索引：`config_id`, `version`

写入策略：

- append new version, active version driven by `config_change_logs`

---

### 5.13 `decision_results`

用途：

- 存储最终决策结果

关键字段建议：

- `decision_id` `text` PK
- `event_id` `text`
- `user_id` `text`
- `relevance_status` `text`
- `priority_score` `numeric`
- `priority_level` `text`
- `decision_action` `text`
- `delivery_timing` `text`
- `delivery_channels_json` `jsonb`
- `action_required` `boolean null`
- `deadline_at` `timestamptz null`
- `reason_summary` `text`
- `explanations_json` `jsonb`
- `evidences_json` `jsonb`
- `policy_version` `text`
- `metadata_json` `jsonb`
- `generated_at` `timestamptz`

约束建议：

- 主键：`decision_id`
- 自然唯一键：`event_id + user_id + policy_version`
- 索引：`event_id`, `user_id`, `decision_action`, `priority_level`

写入策略：

- append-only

---

### 5.14 `delivery_logs`

用途：

- 存储投递日志

关键字段建议：

- `log_id` `text` PK
- `task_id` `text`
- `decision_id` `text`
- `event_id` `text`
- `user_id` `text`
- `channel` `text`
- `status` `text`
- `retry_count` `int`
- `provider_message_id` `text null`
- `error_message` `text null`
- `delivered_at` `timestamptz null`
- `metadata_json` `jsonb`
- `created_at` `timestamptz`

约束建议：

- 主键：`log_id`
- 索引：`decision_id`, `event_id`, `user_id`, `status`, `channel`

写入策略：

- append-only

---

### 5.15 `delivery_digest_jobs`

用途：

- 存储待汇总发送或已汇总的任务

关键字段建议：

- `job_id` `text` PK
- `user_id` `text`
- `window_key` `text`
- `status` `text`
- `task_refs_json` `jsonb`
- `scheduled_at` `timestamptz`
- `sent_at` `timestamptz null`
- `created_at` `timestamptz`

约束建议：

- 唯一键：`user_id + window_key`

---

### 5.16 `user_feedback`

用途：

- 存储用户反馈记录

关键字段建议：

- `feedback_id` `text` PK
- `user_id` `text`
- `event_id` `text`
- `decision_id` `text null`
- `delivery_log_id` `text null`
- `feedback_type` `text`
- `rating` `int null`
- `comment` `text null`
- `metadata_json` `jsonb`
- `created_at` `timestamptz`

约束建议：

- 主键：`feedback_id`
- 索引：`user_id`, `event_id`, `feedback_type`, `created_at`

写入策略：

- append-only

---

### 5.17 `optimization_samples`

用途：

- 存储规则优化和 AI 优化样本

关键字段建议：

- `sample_id` `text` PK
- `event_id` `text`
- `user_id` `text`
- `rule_analysis_id` `text null`
- `ai_result_id` `text null`
- `decision_id` `text null`
- `delivery_log_id` `text null`
- `outcome_label` `text`
- `source` `text`
- `metadata_json` `jsonb`
- `generated_at` `timestamptz`

约束建议：

- 主键：`sample_id`
- 索引：`event_id`, `user_id`, `outcome_label`, `source`

---

### 5.18 `config_change_logs`

用途：

- 存储配置发布和回滚审计

关键字段建议：

- `change_id` `text` PK
- `config_type` `text`
- `version` `text`
- `operator` `text`
- `action` `text`
- `payload_json` `jsonb`
- `created_at` `timestamptz`

约束建议：

- 索引：`config_type`, `version`, `created_at`

---

## 6. 外键策略建议

第一阶段推荐：

- 应用层保证主链路键的一致性
- 关键主表可以逐步加数据库外键
- 对高吞吐日志表可暂时弱化数据库外键，避免过度耦合迁移成本

最低建议：

- `raw_events.source_id -> source_configs.source_id`
- `rule_analysis_results.event_id -> raw_events.event_id`
- `rule_analysis_results.user_id -> user_profiles.user_id`
- `decision_results.event_id -> raw_events.event_id`
- `decision_results.user_id -> user_profiles.user_id`
- `delivery_logs.decision_id -> decision_results.decision_id`

---

## 7. 与共享协议的对应关系

表字段设计必须与 `01_shared_schemas.md` 保持一致：

- 共享对象已有标准字段的，不得只放进 `jsonb`
- 标准枚举值必须保持一致
- `metadata` 对应列统一使用 `metadata_json`

---

## 8. 独立线程工作约束

如果独立线程需要新增持久化字段，应遵循以下规则：

1. 先确认该字段是否属于共享对象
2. 若属于共享对象，先更新 `01_shared_schemas.md`
3. 再在本文件补充列设计
4. 最后回写对应模块文档

模块线程不得绕过本文件，私自定义与共享对象不一致的数据库列。

---

## 9. 本文档一句话定义

**数据库 schema 文档的核心作用，是冻结跨模块持久化关系与关键字段设计，避免并行开发时表结构各自长成不同样子。**

---
