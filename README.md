# InformSystem

`InformSystem` 是一个面向个人使用的校园通知筛选工具。

它的目标不是单纯收集通知，而是把校园里的大量信息进一步分成：

- 需要你尽快处理的
- 值得保留关注的
- 大概率与你无关的

当前系统已经具备一条完整可运行的链路：接入通知、维护个人画像、结合规则与 AI 判断相关性、给出动作结果，并保留分析记录。

## 它现在能做什么

### 过滤校园通知

系统会对通知做多层判断，尽量把真正重要的内容留下来，把明显无关的内容压下去。

当前输出的动作包括：

- `push_now`
- `push_high`
- `digest`
- `archive`
- `ignore`

### 结合你的个人信息做判断

系统可以利用个人画像来判断通知是否真的值得你关注。

当前可用的画像信息包括：

- 学号、姓名、学院、专业、年级
- 身份标签与毕业阶段
- 当前课程与当前任务
- 学业完成状态、模块缺口、毕业进度
- 通知偏好

### 支持真实通知导入与本地运行

系统支持：

- 手工导入通知
- 重放已有通知并重新判断
- 低频接入部分真实校园通知来源

它适合做个人日常使用和低频验证，不适合高频抓取学校站点。

### 保留判断结果，方便回看

系统会保存：

- 原始通知事件
- 规则分析结果
- AI 分析结果
- 决策结果
- 投递记录
- 反馈样本

这样你不仅能看到结果，也能回头检查系统为什么这样判断。

## 适合怎样使用

当前这套系统最适合单用户场景，也就是把它当成你自己的校园通知助手：

- 帮你从大量通知里找出真正需要看的内容
- 减少外学院公示、内部事务、教职工通知这类噪音
- 对开放机会、课程、讲座、学业相关通知做进一步筛选

## 当前边界

这套系统已经能用，但仍有几个现实边界：

- 不建议高频抓取学校站点
- 判断质量依赖个人画像的完整度
- 公共信息、开放机会、基础设施通知这类边界样本仍在持续调优
- 当前更适合个人使用，不是正式的大规模消息平台

## 快速开始

### 安装依赖

```bash
pip install -e .[dev]
```

### 启动服务

```bash
uvicorn backend.app.main:app --reload
```

### 运行测试

```bash
pytest
```

## 推荐用法

### 本地跑完整链路

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_system_demo.ps1 -Mode local
```

### 导入并判断一批通知

```powershell
python scripts\probe_szu_board_for_user.py --max-items 10 --request-delay-seconds 1.2
```

这个脚本会：

- 导入一批通知
- 使用本地画像跑完整判断链路
- 输出汇总结果和本地数据文件

## 关键文档

- [00_system_overview.md](D:/InformSystem/docs/system/00_system_overview.md)
- [01_shared_schemas.md](D:/InformSystem/docs/system/01_shared_schemas.md)
- [02_workflow_orchestration.md](D:/InformSystem/docs/system/02_workflow_orchestration.md)
- [05_database_schema.md](D:/InformSystem/docs/system/05_database_schema.md)
