# 模块 7：配置层（Config Module）

建议文档名：

```text
docs/modules/70_config_module.md
```

---

## 1. 业务背景

整个系统有大量需要持续调整的内容：

- 来源配置
- 规则配置
- 通知类别配置
- 推送策略配置
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
4. **管理推送策略和阈值**
5. **管理配置版本和变更记录**

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

### 3.2 下游依赖

配置层向下游输出：

- `SourceConfig`
- `RuleConfig`
- `NotificationCategoryConfig`
- `PushPolicyConfig`

下游默认是：

- 接入层
- 规则层
- 决策层
- 发文层

---

### 3.3 边界约束

配置层必须满足：

- 配置读取稳定、版本明确
- 配置变更可审计
- 配置对象语义统一
- 不把模块特有默认值藏在黑盒逻辑里
- 支持数据库和本地文件双实现

---

## 4. 模块对外接口定义

---

### 4.1 核心数据结构

#### `RuleConfig`

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
```

---

#### `NotificationCategoryConfig`

```python
from pydantic import BaseModel


class NotificationCategoryConfig(BaseModel):
    category_id: str
    category_name: str
    parent_category: str | None = None
    keywords: list[str] = []
    enabled: bool = True
```

---

#### `PushPolicyConfig`

```python
from pydantic import BaseModel, Field
from typing import Any


class PushPolicyConfig(BaseModel):
    policy_id: str
    policy_name: str
    enabled: bool = True
    action: str
    conditions: dict[str, Any] = Field(default_factory=dict)
    channels: list[str] = []
    version: str
```

---

### 4.2 模块主接口

```python
class ConfigService:
    async def get_source_config(self, source_id: str) -> dict | None:
        ...

    async def list_enabled_sources(self) -> list[dict]:
        ...

    async def get_rule_configs(self, scene: str | None = None) -> list[RuleConfig]:
        ...

    async def get_push_policies(self) -> list[PushPolicyConfig]:
        ...
```

---

### 4.3 配置发布接口

```python
class ConfigService:
    async def publish_config(self, config_type: str, payload: dict, operator: str) -> str:
        ...
```

说明：

- 用于发布新版本配置
- 返回新版本号或配置版本 ID

---

### 4.4 回滚接口

```python
class ConfigService:
    async def rollback(self, config_type: str, version: str, operator: str) -> None:
        ...
```

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

### 6.1 SourceConfigManager

#### 业务背景

来源配置会直接影响接入层行为。

#### 职责

- 管理来源配置
- 管理启停和优先级
- 输出统一 `SourceConfig`

#### 接口

```python
class SourceConfigManager:
    async def get_by_source_id(self, source_id: str) -> dict | None:
        ...
```

---

### 6.2 RuleConfigManager

#### 业务背景

规则层必须读取统一规则，而不是各自维护副本。

#### 职责

- 管理规则配置
- 管理启停状态
- 管理规则版本

#### 接口

```python
class RuleConfigManager:
    async def list_active_rules(self, scene: str | None = None) -> list[RuleConfig]:
        ...
```

---

### 6.3 CategoryConfigManager

#### 业务背景

通知类别需要统一定义，否则不同模块会用不同名称描述同一类通知。

#### 职责

- 维护类别层级
- 维护类别关键词
- 提供类别字典

#### 接口

```python
class CategoryConfigManager:
    async def list_categories(self) -> list[NotificationCategoryConfig]:
        ...
```

---

### 6.4 PushPolicyManager

#### 业务背景

是否立即提醒、是否汇总、走哪个渠道，本质上都属于策略配置。

#### 职责

- 管理推送动作配置
- 管理优先级阈值
- 管理渠道和时间窗口策略

#### 接口

```python
class PushPolicyManager:
    async def list_active_policies(self) -> list[PushPolicyConfig]:
        ...
```

---

### 6.5 ConfigVersionManager

#### 业务背景

配置变更必须有版本记录，否则无法回溯线上行为。

#### 职责

- 分配版本号
- 记录发布和回滚
- 提供版本查询

#### 接口

```python
class ConfigVersionManager:
    async def create_version(self, config_type: str, operator: str) -> str:
        ...
```

---

### 6.6 ConfigCache

#### 业务背景

配置频繁读、低频写，缓存可以降低主存储压力。

#### 职责

- 缓存当前活跃配置
- 提供失效刷新能力
- 减少重复读取

#### 接口

```python
class ConfigCache:
    async def get(self, key: str):
        ...

    async def invalidate(self, key: str) -> None:
        ...
```

---

### 6.7 ConfigAuditRepository

#### 业务背景

配置变更需要审计，便于定位线上行为变化原因。

#### 职责

- 存储配置变更记录
- 支持按类型 / 版本查询
- 支持审计导出

#### 接口

```python
class ConfigAuditRepository:
    async def save_change(self, config_type: str, version: str, payload: dict, operator: str) -> None:
        ...
```

---

## 7. 数据存储设计

配置层至少依赖：

### 7.1 `source_configs`

来源配置。

### 7.2 `rule_configs`

规则配置。

### 7.3 `notification_category_configs`

通知类别配置。

### 7.4 `push_policy_configs`

推送策略配置。

### 7.5 `config_change_logs`

配置变更审计日志。

---

## 8. Mock 设计

---

### 8.1 Mock 上游输入

#### 规则配置发布请求

```json
{
  "config_type": "rule_configs",
  "payload": {
    "rule_id": "rule_grad_001",
    "rule_name": "毕业材料提交通知识别",
    "scene": "rule_engine",
    "enabled": true,
    "priority": 100,
    "conditions": {
      "keywords": ["毕业生", "提交", "材料"]
    },
    "outputs": {
      "category": "graduation_material_submission"
    },
    "version": "v1"
  },
  "operator": "admin"
}
```

---

### 8.2 Mock 下游输出

#### `PushPolicyConfig`

```json
{
  "policy_id": "policy_push_now_001",
  "policy_name": "高风险即时提醒策略",
  "enabled": true,
  "action": "push_now",
  "conditions": {
    "min_priority_score": 90,
    "risk_level": ["high", "critical"]
  },
  "channels": ["app_push"],
  "version": "policy_v1"
}
```

---

## 9. 测试要求

---

### 9.1 单元测试

至少包括：

1. 来源配置读取测试
2. 规则配置读取测试
3. 推送策略读取测试
4. 版本发布测试
5. 回滚测试
6. 缓存失效测试

---

### 9.2 集成测试

至少包括：

1. 配置发布后下游读取测试
2. 本地文件和数据库双实现测试
3. 审计日志测试
4. 多模块并发读取配置测试

---

### 9.3 验收标准

- 各模块可以通过统一接口读取配置
- 配置变更可审计、可回滚
- 配置语义在模块间一致
- 支持本地 mock 配置驱动联调

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

