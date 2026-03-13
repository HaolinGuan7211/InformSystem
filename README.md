# InformSystem

校园通知智能筛选系统。

这个仓库当前包含两部分内容：

- 一套完整的 contract-first 系统文档，用来约束模块边界、共享对象和联调方式
- 一套可运行的后端原型实现，覆盖接入、规则、AI、决策、发文、画像、配置和反馈八个模块

项目目标不是简单聚合通知，而是围绕学生个人状态，从多源校园通知中筛出真正相关、真正需要行动、真正值得打扰的内容。

## 仓库重点

- 系统总纲：`00_system_overview.md`
- 共享协议：`01_shared_schemas.md`
- 主链路编排：`02_workflow_orchestration.md`
- Mock 与联调约定：`04_mock_and_integration_conventions.md`
- 数据库契约：`05_database_schema.md`
- 模块详细设计：`docs/modules/`
- 模块线程提示词：`docs/thread_prompts/`
- 跨模块 golden flow：`mocks/shared/golden_flows/`

## 当前模块

- `Ingestion`
- `Rule Engine`
- `AI Processing`
- `Decision Engine`
- `Delivery`
- `User Profile`
- `Config`
- `Feedback`

## 当前实现定位

当前仓库是第一阶段的模块化单体原型：

- API 框架：`FastAPI`
- 本地开发持久化：`SQLite`
- 文档目标架构：`PostgreSQL + Redis + Celery + Docker Compose`

说明：

- 文档中的系统目标架构是后续正式落地方向
- 当前代码实现优先服务于模块边界收口、mock 联调和本地可运行闭环

## 目录结构

```text
backend/
  app/
    api/
    core/
    shared/
    services/
      ingestion/
      rule_engine/
      ai_processing/
      decision_engine/
      delivery/
      user_profile/
      config/
      feedback/
docs/
  modules/
  thread_prompts/
mocks/
  ingestion/
  rule_engine/
  ai_processing/
  decision_engine/
  delivery/
  user_profile/
  config/
  feedback/
  shared/golden_flows/
scripts/
```

## 文档阅读顺序

如果你要理解系统或接手某个模块，建议按这个顺序看：

1. `00_system_overview.md`
2. `01_shared_schemas.md`
3. `02_workflow_orchestration.md`
4. `05_database_schema.md`
5. `04_mock_and_integration_conventions.md`
6. `docs/modules/<模块文档>`
7. `docs/thread_prompts/<对应线程提示词>`

## 本地运行

```bash
pip install -e .[dev]
uvicorn backend.app.main:app --reload
```

启动后可访问：

- `GET /health`
- `POST /api/v1/webhooks/{source_id}`
- `POST /api/v1/ingestion/manual`
- `POST /api/v1/ingestion/replay/{event_id}`
- `GET /api/v1/users/active`
- `GET /api/v1/users/{user_id}/profile`
- `PUT /api/v1/users/{user_id}/profile`
- `POST /api/v1/feedback`
- `POST /api/v1/feedback/delivery-outcomes`
- `GET /api/v1/feedback/optimization-samples`

## 本地 demo

```bash
python scripts/demo_ingestion.py
```

## 测试

运行全量测试：

```bash
pytest
```

如果只想跑某个模块：

```bash
pytest backend/app/services/ingestion/tests
pytest backend/app/services/rule_engine/tests
pytest backend/app/services/decision_engine/tests
```

## Mock 与联调

仓库采用 `Contract-First + Mock-Driven Development`。

关键约定：

- 模块各自维护自己的输入输出 mock
- `mocks/shared/golden_flows/` 下的样例是跨模块联调权威样例
- 如果共享对象变更，先改 `01_shared_schemas.md`，再改模块文档和 mock

## 当前开发约束

- 不要跨模块偷改共享对象语义
- 不要把最终决策逻辑塞进非决策层
- 不要把用户枚举逻辑塞进规则层
- 不要让 AI 成为主链路单点依赖
- 不要把本地数据库、缓存和构建产物提交到仓库

## Git 说明

本仓库已经初始化 Git。

默认不提交的内容包括：

- `__pycache__/`
- `.pytest_cache/`
- `backend/data/`
- `*.db`
- `*.egg-info/`

## 下一步建议

- 继续把文档契约逐步收敛为代码中的统一 shared models
- 将当前 SQLite 原型逐步迁移到文档约定的 PostgreSQL / Redis / Celery 方案
- 以 golden flow 为基础补更多跨模块集成测试

