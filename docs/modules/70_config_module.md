# 模块 7：配置层（Config Module）

建议文档名：

```text
docs/modules/70_config_module.md
```

---

## AI Runtime Priority Update

AI runtime 配置的当前约束如下：

- 默认以 ConfigService.get_ai_runtime_config() 返回的 AIRuntimeConfig 为基线配置。
- 当 `config_backend="sqlite"` 时，AI runtime 配置从 SQLite 的 `ai_runtime_configs` 表读取，而不是继续回退到本地 runtime json 文件。
- Settings / env 只用于本地调试 override，并且只允许在 container.py 装配阶段合并一次；下游 service 不再自行读取 env 或做第二轮配置猜测。
- `provider` override 不会隐式级联覆盖 `model_name`；只有显式提供 `AI_MODEL_NAME`、`KIMI_MODEL` 或 `settings.ai_model_name` 时，才会覆盖配置层已有模型名。
- AIRuntimeConfig.enabled 必须真实影响运行时行为：关闭时 AI 不发起模型请求，主链路继续运行，并在 call log 中记录 skipped。
- AIRuntimeConfig.max_retries 只控制模型调用阶段的重试次数，不扩散到 prompt 构建、结果校验或业务层 fallback。
- 这意味着配置层除了提供字段，还要保证这些字段能被容器装配成最终生效的 resolved runtime config。


## 1. 业务背景

整个系统有大量需要持续调整的内容：

- 来源配置
- 规则配置
- 通知类别配置
- AI 运行配置
- 推送策略配置
- 发文渠道配置
- 阈值和版本

如果这些内容散落在代码里，会出现这些问题：

- 变更成本高
- 联调困难
- 无法版本化
- 多模块难以统一语义
- 无法支撑后续持续优化

因此配置层的业务意义是：

**作为系统统一配置入口，为各模块提供稳定、版本化、可审计的配置对象。**

它在整个系统里的位置是：

**管理后台 / 本地配置 / 运维变更 → 配置层 → 各模块读取配置**

---

## 2. 模块职责

配置层只做这些事情：

1. **管理来源配置**
2. **管理规则配置**
3. **管理通知类别配置**
4. **管理 AI 运行配置**
5. **管理推送策略和阈值**
6. **管理发文渠道配置**
7. **管理配置版本和变更记录**

配置层不做这些事情：

- 不执行规则
- 不采集通知
- 不做最终推送
- 不直接发送消息
- 不做用户画像判断

一句话：

**配置层是“系统参数与策略源”，不是“业务执行层”。**

---

## 3. 模块边界

### 3.1 上游依赖

配置层上游可能包括：

- 管理后台
- 本地配置文件
- 运营 / 开发手动维护

---

## 4. 模块对外接口定义

---

## 5. 模块内部架构

建议配置层拆成 7 个子模块：

1. `SourceConfigManager`
2. `RuleConfigManager`
3. `CategoryConfigManager`
4. `PushPolicyManager`
5. `ConfigVersionManager`
6. `ConfigCache`
7. `ConfigAuditRepository`

---

## 6. 子模块详细设计

---

## 7. 数据存储设计

配置层至少依赖：

### 7.1 `source_configs`

来源配置。

### 7.2 `rule_configs`

规则配置。

### 7.3 `notification_category_configs`

通知类别配置。

### 7.4 `ai_runtime_configs`

AI 运行配置。

说明：

- SQLite 后端下，AI runtime 的当前生效版本由 `config_change_logs` 驱动，实际配置快照存放在 `ai_runtime_configs`。

### 7.5 `push_policy_configs`

推送策略配置。

### 7.6 `config_change_logs`

配置变更审计日志。

---

## 8. Mock 设计

---

## 9. 测试要求

---

## 10. 开发约束

### 10.1 必须做

- 配置统一入口
- 支持版本化
- 支持审计
- 支持数据库和本地文件双实现

### 10.2 不要做

- 不要把业务逻辑塞进配置层执行
- 不要让各模块维护私有规则副本
- 不要修改配置后没有版本记录

### 10.3 推荐工程目录

```text
backend/app/services/config/
  __init__.py
  service.py
  source_config_manager.py
  rule_config_manager.py
  category_config_manager.py
  push_policy_manager.py
  version_manager.py
  cache.py
  repositories/
    config_audit_repository.py
  tests/
    test_rule_config_manager.py
    test_push_policy_manager.py
    test_version_manager.py
```

---

## 11. 模块交付物

配置层模块完成时，应该交付：

1. 代码实现
2. 模块 README
3. mock 配置文件
4. 单元测试
5. 配置发布与读取接口
6. 审计日志实现

---

## 12. 本模块一句话定义

**配置层模块的核心业务，是为系统各模块提供统一、稳定、版本化、可审计的配置对象与配置读取能力。**

---

