# 模块 6：用户画像层（User Profile Module）

建议文档名：

```text
docs/modules/60_user_profile_module.md
```

---

## 13. 简单画像与复杂画像分层补充（2026-03-15）

本模块在相关性筛选主链路中的定位补充为：

- 用户画像层继续提供完整 `UserProfile`
- 但需要更明确地区分简单画像与复杂画像
- 规则层主要消费简单画像
- AI 层主要消费由 `ProfileContextSelector` 裁剪出的复杂画像切片

### 13.1 简单画像

适合规则层粗筛的内容包括：

- `identity_tags`
- `degree_level`
- `college`
- `major`
- `grade`
- 当前课程标题
- 当前待办标题

### 13.2 复杂画像

适合 AI 精筛的内容包括：

- `credit_status.program_summary`
- `credit_status.module_progress`
- `credit_status.pending_items`
- `credit_status.attention_signals`
- 毕业进度相关状态

### 13.3 `ProfileContextSelector` 的主链路意义

`ProfileContextSelector` 不只是 token 优化器，还承担架构分层职责：

- 防止规则层直接吞下复杂画像推理
- 防止 AI 默认读取完整画像
- 让复杂画像只在需要精筛时进入主链路

## 1. 业务背景

同一条通知对不同学生的重要性可能完全不同：

- 毕业审核通知对毕业生重要，对低年级学生不重要
- 某门课程的调课通知只对选课学生重要
- 某类学分认定通知只对学分缺口用户重要

因此系统判断的核心前提不是“通知本身”，而是：

**通知与当前用户状态之间的关系。**

用户画像层的业务意义是：

**维护通知判断所需的学生身份、课程、学分、毕业阶段和提醒偏好等核心状态。**

它在整个系统里的位置是：

**外部学生数据 / 用户维护 → 用户画像层 → `UserProfile` → 规则层 / AI 层 / 决策层 / 发文层**

---

## 2. 模块职责

用户画像层只做这些事情：

1. **维护基础身份信息**
2. **维护课程与学分状态**
3. **维护毕业阶段和当前任务状态**
4. **维护提醒偏好**
5. **向其他模块输出稳定的用户画像对象**
6. **根据 facet 需求输出最小相关画像切片**

用户画像层不做这些事情：

- 不采集通知
- 不判断通知是否重要
- 不做最终推送决策
- 不执行消息发送
- 不直接维护规则配置

一句话：

**用户画像层是“用户状态输入源”，不是“通知判断模块”。**

---

## 3. 模块边界

### 3.1 上游依赖

用户画像层上游可能包括：

- 教务系统
- 学工系统
- 手动维护接口
- 用户自定义偏好配置

---

### 3.2 下游依赖

用户画像层向下游输出统一的：

- `UserProfile`

下游默认是：

- 规则层
- AI 层
- 决策层
- 发文层

---

### 3.3 边界约束

用户画像层必须满足：

- 输出结构稳定
- 必须可构建快照
- 用户状态数据与通知分析逻辑解耦
- 支持缺省字段和渐进补全
- 必须可单独运行和测试
- 可以根据 `required_profile_facets` 生成最小 `ProfileContext`
- 不自行决定某条通知需要哪些 facet
- 自动采样流程不得直接进入主通知工作流
- 自动采样必须先经过学校字段兼容层，再落本地 `UserProfile`
- 本地画像字段命名不得依赖某个学校系统的原始字段命名
- 默认采用“离线优先、低频在线验证”的开发方式
- 在线采样不得把学校系统当成实时查询源，只能作为低频同步源
- 在线采样必须受登录冷却、会话复用、端点白名单和请求预算约束
- 一次真实抓取后的原始响应应优先固化为本地 fixture，后续解析与测试默认离线完成

---

## 4. 模块对外接口定义

---

### 4.1 核心数据结构

#### `CourseInfo`

```python
from pydantic import BaseModel
from typing import Optional


class CourseInfo(BaseModel):
    course_id: str
    course_name: str
    teacher: Optional[str] = None
    semester: Optional[str] = None
```

---

#### `NotificationPreference`

```python
from pydantic import BaseModel


class NotificationPreference(BaseModel):
    channels: list[str] = []
    quiet_hours: list[str] = []
    digest_enabled: bool = True
    muted_categories: list[str] = []
```

---

#### `UserProfile`

```python
from pydantic import BaseModel, Field
from typing import Any, Optional


class UserProfile(BaseModel):
    user_id: str
    student_id: str
    name: Optional[str] = None
    college: Optional[str] = None
    major: Optional[str] = None
    grade: Optional[str] = None
    degree_level: Optional[str] = None
    identity_tags: list[str] = []
    graduation_stage: Optional[str] = None
    enrolled_courses: list[CourseInfo] = []
    credit_status: dict[str, Any] = Field(default_factory=dict)
    current_tasks: list[str] = []
    notification_preference: NotificationPreference = NotificationPreference()
    metadata: dict[str, Any] = Field(default_factory=dict)
```

---

#### `ProfileContext`

```python
from pydantic import BaseModel, Field
from typing import Any


class ProfileContext(BaseModel):
    user_id: str
    facets: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    generated_at: str
```

说明：

- `ProfileContext` 是从完整 `UserProfile` 派生出的最小相关上下文
- AI 层默认消费 `ProfileContext`，而不是直接消费整份 `UserProfile`

---

### 4.2 模块主接口

```python
class UserProfileService:
    async def get_profile(self, user_id: str) -> UserProfile | None:
        ...

    async def upsert_profile(self, profile: UserProfile) -> None:
        ...

    async def build_snapshot(self, user_id: str) -> UserProfile | None:
        ...
```

说明：

- 第一阶段可将 `UserProfile` 直接作为快照对象使用
- 后续如需要，可显式扩展 `UserProfileSnapshot`

---

### 4.3 用户枚举接口

```python
class UserProfileService:
    async def list_active_users(self, limit: int = 1000) -> list[UserProfile]:
        ...
```

说明：

- 用于对多用户执行规则分析或批量决策时枚举目标用户
- 第一阶段“活跃用户”默认定义为 `user_profiles` 中当前存在且可成功构建快照的用户
- 编排层可以直接读取返回结果中的 `user_id`，并在需要时再次调用 `build_snapshot(user_id)`

---

### 4.4 快照语义

`build_snapshot(user_id)` 的第一阶段语义固定为：

- 读取 `user_profiles`、`user_course_enrollments`、`user_preferences` 的当前状态
- 聚合基础身份、课程、学分、毕业阶段、当前任务和提醒偏好
- 输出一个可直接给规则层 / AI 层 / 决策层消费的稳定 `UserProfile`
- 只做状态聚合，不做“该通知是否与用户相关”的业务判断

---

### 4.5 画像切片接口

```python
class ProfileContextSelector:
    async def select(self, profile: UserProfile, required_facets: list[str], context: dict | None = None) -> ProfileContext:
        ...
```

说明：

- `required_facets` 必须来自共享协议中的 `profile_facet` 枚举
- `ProfileContextSelector` 负责把完整快照裁剪为最小相关上下文
- 该组件不负责判断 facet 是否合理，只负责执行选择与结构化输出

---

### 4.6 手动维护接口

```http
PUT /api/v1/users/{user_id}/profile
Content-Type: application/json
```

作用：

- 手动更新用户画像
- 便于本地联调和初期数据维护

---

## 5. 模块内部架构

建议用户画像层拆成两部分：

本地画像域：

1. `ProfileRepository`
2. `CourseSyncAdapter`
3. `CreditStatusManager`
4. `GraduationStatusManager`
5. `PreferenceManager`
6. `SnapshotBuilder`
7. `ProfileContextSelector`

自动采样扩展：

8. `ProfileSamplingService`
9. `ProfileCompatibilityLayer`
10. `ProfileSyncOrchestrator`

如果启用真实在线采样，还必须配套以下保护组件：

- `LoginCooldownGuard`：限制同一学校账号在冷却窗口内的真实登录次数
- `SessionReuseStore`：同一采样任务内复用同一会话，禁止重复认证
- `AllowedEndpointPolicy`：仅允许访问已登记的学校端点白名单
- `FixtureCaptureStore`：一次真实抓取后固化原始响应，后续默认离线调试

其中：

- `ProfileSamplingService` 负责认证、会话建立、学校侧原始数据采样
- `ProfileCompatibilityLayer` 负责把学校字段映射为本地画像字段
- `ProfileSyncOrchestrator` 负责执行“采样 -> 兼容映射 -> 合并 -> 落库 -> 快照”
- `SnapshotBuilder` 继续只消费本地画像数据，不直接访问学校系统
- `ProfileContextSelector` 负责从完整快照中按 facet 输出最小业务上下文

---

## 6. 子模块详细设计

---

### 6.1 ProfileRepository

#### 业务背景

用户基础身份是整个画像的主锚点。

#### 职责

- 存储基础用户资料
- 支持按 `user_id` 查询
- 支持创建和更新

#### 接口

```python
class ProfileRepository:
    async def save(self, profile: UserProfile) -> None:
        ...

    async def get_by_user_id(self, user_id: str) -> UserProfile | None:
        ...
```

---

### 6.2 CourseSyncAdapter

#### 业务背景

课程相关通知依赖“本学期修读课程”这一动态信息。

#### 职责

- 对接外部课程数据源
- 同步课程清单
- 输出统一课程信息结构

#### 接口

```python
class CourseSyncAdapter:
    async def sync_courses(self, user_id: str) -> list[CourseInfo]:
        ...
```

---

### 6.3 CreditStatusManager

#### 业务背景

学分缺口、培养计划完成情况会直接影响通知价值判断。

#### 职责

- 维护学分状态
- 输出面向规则层的结构化字段
- 支持标记缺口和异常状态
- 产出 `attention_signals` 这类高价值派生信号

#### 接口

```python
class CreditStatusManager:
    async def get_credit_status(self, user_id: str) -> dict:
        ...
```

#### 第一阶段结构约束

`credit_status` 的内部结构必须对齐共享协议，至少包含：

- `program_summary`
- `module_progress`
- `pending_items`
- `attention_signals`
- `source_snapshot`

约束说明：

- `module_progress` 中的子模块是后续规则和 AI 的默认消费粒度
- “全量培养方案课程明细”不应直接塞进 `enrolled_courses`
- 学校侧字段如 `PYFADM`、`KZH`、`FKZH` 只能停留在 `metadata`

---

### 6.4 GraduationStatusManager

#### 业务背景

毕业审核、学位申请、离校手续等场景都依赖毕业阶段状态。

#### 职责

- 维护毕业阶段
- 维护毕业相关待办状态
- 输出统一毕业状态字段

#### 接口

```python
class GraduationStatusManager:
    async def get_graduation_stage(self, user_id: str) -> str | None:
        ...
```

---

### 6.5 PreferenceManager

#### 业务背景

提醒策略必须考虑用户偏好和静默时间。

#### 职责

- 管理渠道偏好
- 管理静默时间
- 管理 digest 设置和类别屏蔽

#### 接口

```python
class PreferenceManager:
    async def get_preference(self, user_id: str) -> NotificationPreference:
        ...
```

---

### 6.6 SnapshotBuilder

#### 业务背景

分析链路需要读取的是“某一时刻的稳定画像视图”，而不是临时拼装数据。

#### 职责

- 聚合基础资料、课程、学分、毕业阶段、偏好
- 生成统一 `UserProfile`
- 保证分析时读取一致

#### 接口

```python
class SnapshotBuilder:
    async def build(self, user_id: str) -> UserProfile | None:
        ...
```

---

### 6.7 ProfileContextSelector

#### 业务背景

随着学业完成数据变细，完整 `UserProfile` 已经不适合默认直接进入 AI。

#### 职责

- 根据 `required_profile_facets` 从完整快照中提取最小相关上下文
- 控制 AI 默认可见的课程、模块缺口和偏好范围
- 为下游提供稳定的 `ProfileContext`

#### 接口

```python
class ProfileContextSelector:
    async def select(self, profile: UserProfile, required_facets: list[str], context: dict | None = None) -> ProfileContext:
        ...
```

#### 开发约束

- 默认不输出未被请求的 facet
- 默认不把 82 条全量课程明细直接放入 AI 输入
- 允许在 `metadata` 中记录切片来源、版本和降级说明

---

## 7. 数据存储设计

用户画像层至少依赖：

### 7.1 `user_profiles`

用于存储用户基础资料。

### 7.2 `user_course_enrollments`

用于存储课程信息。

### 7.3 `user_preferences`

用于存储提醒偏好和静默策略。

### 7.4 四类状态输入方案

- 课程状态：进入 `user_course_enrollments`，由 `CourseSyncAdapter` 输出 `enrolled_courses`
- 学分状态：进入 `user_profiles.credit_status_json`，在快照中映射为 `credit_status`
- 毕业阶段与当前待办：进入 `user_profiles.graduation_stage` 和 `current_tasks_json`
- 偏好状态：进入 `user_preferences`，在快照中映射为 `notification_preference`

补充约束：

- `credit_status_json` 是“学业完成状态”的主落点，不是任意大杂烩 JSON
- 用户自定义关注项如需持久化，优先进入偏好 / 订阅配置域，不默认混入 `credit_status`

---

## 8. Mock 设计

---

### 8.1 Mock 上游输入

#### 手动画像输入

```json
{
  "user_id": "stu_001",
  "student_id": "20260001",
  "college": "计算机学院",
  "major": "软件工程",
  "grade": "2022",
  "degree_level": "undergraduate",
  "identity_tags": ["毕业生"],
  "graduation_stage": "graduation_review"
}
```

---

### 8.2 Mock 下游输出

#### `UserProfile`

```json
{
  "user_id": "stu_001",
  "student_id": "20260001",
  "name": "张三",
  "college": "计算机学院",
  "major": "软件工程",
  "grade": "2022",
  "degree_level": "undergraduate",
  "identity_tags": ["毕业生"],
  "graduation_stage": "graduation_review",
  "enrolled_courses": [],
  "credit_status": {
    "program_summary": {
      "program_name": "2022级软件工程主修培养方案",
      "required_total_credits": 160.0,
      "completed_total_credits": 154.0,
      "outstanding_total_credits": 6.0,
      "exempted_total_credits": 0.0,
      "plan_version": "2022"
    },
    "module_progress": [
      {
        "module_id": "mod_practice",
        "module_name": "实践模块",
        "parent_module_id": null,
        "parent_module_name": null,
        "module_level": "parent",
        "required_credits": 16.0,
        "completed_credits": 12.0,
        "outstanding_credits": 4.0,
        "required_course_count": null,
        "completed_course_count": null,
        "outstanding_course_count": null,
        "completion_status": "in_progress",
        "attention_tags": ["credit_gap"],
        "metadata": {}
      }
    ],
    "pending_items": [
      {
        "item_id": "pending_practice_001",
        "item_type": "module_credit_gap",
        "title": "实践模块仍需补足 4 学分",
        "module_id": "mod_practice",
        "module_name": "实践模块",
        "credits": 4.0,
        "status": "pending",
        "priority_hint": "high",
        "metadata": {}
      }
    ],
    "attention_signals": [
      {
        "signal_type": "credit_gap",
        "signal_key": "practice_credit_gap",
        "signal_value": "4.0",
        "severity": "high",
        "evidence": ["实践模块未完成"]
      }
    ],
    "source_snapshot": {
      "school_code": "szu",
      "source_system": "ehall_academic_completion",
      "synced_at": "2026-03-13T10:19:00+08:00",
      "source_version": "xywccx_v1",
      "freshness_status": "fresh",
      "metadata": {}
    }
  },
  "current_tasks": ["毕业资格审核"],
  "notification_preference": {
    "channels": ["app_push"],
    "quiet_hours": ["23:00-07:00"],
    "digest_enabled": true,
    "muted_categories": []
  },
  "metadata": {}
}
```

---

## 9. 测试要求

---

### 9.1 单元测试

至少包括：

1. 用户资料读写测试
2. 偏好读取测试
3. 缺省字段兼容测试
4. 课程同步测试
5. 快照构建测试
6. `credit_status` 结构冻结测试
7. `ProfileContextSelector` 切片测试
8. 毕业阶段状态测试

---

### 9.2 集成测试

至少包括：

1. `user_id → UserProfile` 完整链路测试
2. 手动维护接口测试
3. 画像变更后下游读取测试
4. `required_profile_facets -> ProfileContext` 生成测试
5. 批量枚举用户测试

---

### 9.3 验收标准

- 下游模块能稳定读取 `UserProfile`
- 画像可渐进补全，不要求一次完备
- 画像更新不会破坏历史分析链路
- 偏好字段可供决策层和发文层直接使用

---

## 10. 开发约束

### 10.1 必须做

- 输出统一 `UserProfile`
- 支持基础身份、课程、学分、毕业状态和偏好
- 支持快照构建
- 提供 `ProfileContextSelector`
- 支持手动维护能力
- 如果实现自动采样，必须保留“学校采样层 -> 兼容层 -> 本地画像层”的分层边界
- 自动采样结果必须支持缺省字段、渐进补全和与现有画像合并
- 自动采样必须提供离线 fixture 驱动能力，不能把真实学校系统当成默认开发环境

### 10.2 在线采样安全约束

- 一个采样任务最多只允许一次真实登录
- 同一采样任务内所有页面和接口必须复用同一个 session
- 未经人工确认，不得执行真实在线采样
- 在线采样必须设置登录冷却时间；默认建议同一学校账号 2 小时内最多 1 次真实登录
- 在线采样必须设置请求预算；超过预算后必须硬停止，不得自动重试
- 在线采样只能访问已登记的端点白名单，不得在学校系统中临时扫目录、猜路径或探测未知入口
- 出现验证码、滑块、异常跳转、频繁重定向、403、404、412 或账号异常提示时，必须立即停止，不得继续尝试
- 真实抓取拿到一次响应后，应立即转入离线解析、映射和测试，不得为调试重复登录
- 浏览器人工登录态接管优先级高于脚本直登；除非已明确验证安全窗口，否则不要默认脚本直登
- 自动采样流程不得在主通知编排链路中隐式触发，必须由独立同步任务显式执行

### 10.3 不要做

- 不要在画像层写通知判断逻辑
- 不要把下游规则写回画像模型
- 不要让字段命名依赖某个上游系统原始命名
- 不要把全量培养方案课程明细直接塞进 `enrolled_courses`
- 不要为了调试反复单独执行认证脚本
- 不要把多个学校系统入口放在同一轮真实探测里批量尝试
- 不要在未固化 fixture 前持续对真实系统做解析调试

### 10.4 推荐工程目录

```text
backend/app/services/user_profile/
  __init__.py
  service.py
  snapshot_builder.py
  course_sync_adapter.py
  credit_status_manager.py
  graduation_status_manager.py
  preference_manager.py
  repositories/
    profile_repository.py
  tests/
    test_snapshot_builder.py
    test_preference_manager.py
    test_profile_service.py

backend/app/services/profile_sampling/
  auth/
    base.py
    browser_session_provider.py
    offline_auth_provider.py
    szu_http_cas_provider.py
  samplers/
    base.py
    szu/
      board_identity_sampler.py
      personal_info_sampler.py
      hint_payload_sampler.py
  models.py
  service.py

backend/app/services/profile_compat/
  mappers/
    base.py
    szu_mapper.py
  merge.py
  models.py
  service.py

backend/app/workflows/
  profile_sync_orchestrator.py
```

---

## 11. 模块交付物

用户画像层模块完成时，应该交付：

1. 代码实现
2. 模块 README
3. mock 输入输出文件
4. 单元测试
5. 数据存储实现
6. 手动维护接口

---

## 12. 本模块一句话定义

**用户画像层模块的核心业务，是维护通知判断所需的用户状态信息，并向下游输出稳定统一的用户画像对象。**

---
