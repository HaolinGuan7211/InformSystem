# AGENTS.md

## 适用范围

本文件适用于整个仓库 `D:\InformSystem`。

它的目标是帮助后续协作 agent、独立 Codex 线程和开发者快速理解这个仓库该怎么工作，尤其是在模块并行开发时避免接口漂移。

## 先读什么

任何 agent 在动手前，默认按下面顺序阅读：

1. `docs/system/00_system_overview.md`
2. `docs/system/01_shared_schemas.md`
3. `docs/system/02_workflow_orchestration.md`
4. `docs/system/05_database_schema.md`
5. `docs/system/04_mock_and_integration_conventions.md`
6. 自己负责的模块文档 `docs/modules/X0_*.md`
7. 自己的上游模块文档
8. 自己的下游模块文档

如果只是实现某个模块，也不要跳过 `01` 和 `02`。

## 当前项目原则

- 项目采用 `Contract-First + Mock-Driven Development`
- 当前是模块化单体原型，不是最终生产部署形态
- 文档目标架构是 `PostgreSQL + Redis + Celery + Docker Compose`
- 当前代码实现允许使用本地 `SQLite` 作为原型和测试存储

## 共享契约优先级

如果多个文档之间发生冲突，优先级如下：

1. `docs/system/01_shared_schemas.md`
2. `docs/system/02_workflow_orchestration.md`
3. `docs/system/05_database_schema.md`
4. `docs/modules/X0_*.md`

规则：

- 共享对象字段和枚举冲突，以 `docs/system/01_shared_schemas.md` 为准
- 主流程责任归属冲突，以 `docs/system/02_workflow_orchestration.md` 为准
- 表结构和自然幂等键冲突，以 `docs/system/05_database_schema.md` 为准

## 模块边界红线

- 接入层只做采集、标准化、接入去重和原始事件存储
- 规则层只做单个 `(SourceEvent, UserProfile)` 的结构化分析
- 事件与用户的配对责任属于编排层，不属于规则层
- AI 层是补充理解层，不是最终裁决层
- 决策层是唯一的最终动作裁定入口
- 发文层只执行触达，不重新判断业务动作
- 用户画像层提供稳定画像快照，不做通知判断
- 配置层提供统一配置，不执行业务规则
- 反馈层记录事实和样本，不直接改线上裁决

## 改动共享对象时怎么做

如果你需要新增、删除或重命名跨模块字段：

1. 先更新 `docs/system/01_shared_schemas.md`
2. 再更新 `docs/system/05_database_schema.md` 中对应字段
3. 再更新相关模块文档
4. 最后更新 mock 和代码

不要只改代码或只改某一个模块文档。

## 改动主链路时怎么做

如果你觉得某个责任归属应该改变，例如：

- 谁负责用户枚举
- 谁负责 AI 触发
- replay 到底从哪里重新开始

先更新 `docs/system/02_workflow_orchestration.md`，再修改模块设计和代码。

不要在模块内部偷偷改主流程。

## Mock 规则

- 权威跨模块样例在 `mocks/shared/golden_flows/`
- 模块自己的输入输出 mock 放在 `mocks/<module>/`
- 新增 mock 时，优先复用已有 golden flow 语义
- 如果 golden flow 不够，再补新的 flow，不要随便改已有 flow 的共享字段

## 代码实现约束

- 优先复用 `backend/app/shared/` 中的共享模型
- 不要把平台细节泄漏到共享对象里
- 不要把重要查询字段全塞进 `metadata` 或 `jsonb`
- 保持模块目录边界清晰，避免横向耦合
- 新增 API 时，优先放入对应模块的 route，并与模块文档对齐

## 本地运行

安装依赖：

```bash
pip install -e .[dev]
```

启动服务：

```bash
uvicorn backend.app.main:app --reload
```

运行测试：

```bash
pytest
```

## Git 与本地文件

默认不要提交：

- `__pycache__/`
- `.pytest_cache/`
- `backend/data/`
- `*.db`
- `*.egg-info/`
- `tmp/`
- `docs/module_reports/`
- `docs/thread_prompts/`

提交前建议确认：

- `git status`
- 共享契约是否同步更新
- mock 是否同步更新
- 测试是否覆盖主要变更

## 工作线程沟通目录

如果需要与独立 Codex 线程沟通，使用这两个占位目录：

- `docs/thread_prompts/`
- `docs/module_reports/`

这两个目录当前只保留空壳说明文件；需要时可临时新建 prompt 或报告文件。

## 一句话原则

先守住契约，再推进实现；先守住模块边界，再考虑局部方便。
