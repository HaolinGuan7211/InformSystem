# 模块 6 线程提示词

以下内容可直接复制给独立 Codex 线程。

你当前负责 `D:\InformSystem` 的模块 6：用户画像层（User Profile）。

你的工作目标：

- 基于系统总纲和契约文档，完成用户画像层的设计收口，并在需要时推进实现。
- 你的模块负责维护用户状态输入，不负责做通知相关性判断。
- 重点是稳定输出 `UserProfile` 快照，并支撑编排层做用户枚举。

请按以下顺序阅读文档：

1. `D:\InformSystem\00_system_overview.md`
2. `D:\InformSystem\01_shared_schemas.md`
3. `D:\InformSystem\02_workflow_orchestration.md`
4. `D:\InformSystem\05_database_schema.md`
5. `D:\InformSystem\04_mock_and_integration_conventions.md`
6. `D:\InformSystem\docs\modules\60_user_profile_module.md`
7. `D:\InformSystem\docs\modules\20_rule_engine_module.md`
8. `D:\InformSystem\docs\modules\40_decision_engine_module.md`
9. `D:\InformSystem\docs\modules\50_delivery_module.md`

你在主链路中的位置：

- 你负责 `list_active_users()` 和 `build_snapshot(user_id)`
- 编排层调用你枚举用户并构建画像
- 规则层只消费 `UserProfile`，不应该自己拼用户数据

你的上游参考：

- 外部学生资料
- 课程数据
- 学分状态数据
- 用户偏好数据

你的下游参考：

- 编排层
- 规则层
- AI 层
- 决策层
- 发文层

你必须重点保证：

- `UserProfile`、`CourseInfo`、`NotificationPreference` 严格对齐 `01_shared_schemas.md`
- 支持快照思维，不让下游分析依赖临时拼接的动态数据
- 支持缺省字段和渐进补全
- `user_profiles`、`user_course_enrollments`、`user_preferences` 表设计对齐 `05_database_schema.md`
- 提供可供联调的用户画像 mock 和 golden flow 对齐样例

你绝对不要做：

- 不要在画像层做通知相关性判断
- 不要直接返回“这个通知与用户相关”的结论
- 不要让字段命名直接绑定某个上游系统的脏数据格式
- 不要绕过编排层自己驱动规则层

如果发现冲突，按下面规则处理：

- 如果你觉得规则层需要用户枚举能力，先停下；这属于编排层责任
- 如果你要新增画像字段，先确认是否属于共享对象，再决定是否更新 `01_shared_schemas.md`
- 如果你发现状态字段过于业务化，优先归入 `metadata` 或单独字段设计讨论

本线程建议交付：

- 用户画像对象和快照语义收口
- 用户枚举和快照构建接口
- 课程、学分、毕业阶段、偏好四类状态输入方案
- mock 用户样例
- 如果被要求实现，再提交 repository、snapshot builder、测试和维护接口

