# User Profile Module

模块 6 负责维护稳定的 `UserProfile` 快照，并向编排层提供用户枚举能力。

## 已实现内容

- `SQLiteUserProfileRepository` 覆盖 `user_profiles`、`user_course_enrollments`、`user_preferences`
- `SnapshotBuilder` 聚合基础资料、课程、学分、毕业状态和提醒偏好
- `UserProfileService` 提供 `get_profile`、`upsert_profile`、`build_snapshot`、`list_active_users`
- FastAPI 手动维护接口：
  - `PUT /api/v1/users/{user_id}/profile`
  - `GET /api/v1/users/{user_id}/profile`
  - `GET /api/v1/users/active`

## 当前约束

- 第一阶段把 `user_profiles` 中当前存在的用户视为“活跃用户”
- `list_active_users()` 返回完整快照列表，编排层可直接读取 `user_id` 后逐个重建快照
- 画像层只维护状态输入，不输出通知相关性结论
- 缺省字段按共享协议自动补成 `null`、`[]`、`{}`

## 主要样例

- 上游输入：
  - `mocks/user_profile/upstream_inputs/graduation_material_submission__input__manual_profile_request.json`
  - `mocks/user_profile/upstream_inputs/course_schedule_change__input__manual_profile_request.json`
- 输出样例：
  - `mocks/user_profile/downstream_outputs/graduation_material_submission__output__user_profile.json`
  - `mocks/user_profile/downstream_outputs/course_schedule_change__output__user_profile.json`
- Golden flow 对齐：
  - `mocks/shared/golden_flows/flow_001_graduation_material_submission/02_user_profile.json`
