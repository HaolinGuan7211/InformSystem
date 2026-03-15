# 模块 3：AI 处理层（AI Processing Module）

建议文档名：

```text
docs/modules/30_ai_processing_module.md
```

---

## 13. 相关性精筛职责补充（2026-03-15）

本模块在相关性筛选主链路中的定位补充为：

- AI 层不是仅做摘要和字段抽取
- AI 层需要承担第二阶段相关性精筛职责
- 尤其要处理规则层留下来的 `unknown` 候选通知

### 13.1 AI 精筛输入

AI 默认消费：

- `SourceEvent`
- `RuleAnalysisResult`
- `ProfileContext`

在当前阶段个人工具架构下，AI 模块内部还需要再细分为：

- Stage 1：`SourceEvent + RuleAnalysisResult + LightProfileTags`
- Stage 2：`SourceEvent + RuleAnalysisResult + ProfileContext`

其中 Stage 1 只负责判断“是否值得加载重画像继续精筛”，而 Stage 2 才输出最终 `AIAnalysisResult`。

其中 `ProfileContext` 应优先承载复杂画像切片，例如：

- `academic_completion`
- `graduation_progress`
- `activity_based_credit_gap`
- `online_platform_credit_gap`

### 13.2 AI 精筛输出

`AIAnalysisResult.relevance_hint` 在本次调整后应优先使用标准值：

- `relevant`
- `irrelevant`
- `uncertain`

决策层需要显式消费该字段，而不能只把 AI 当作摘要补充器。

### 13.3 AI 的负向判断

AI 层需要为候选通知提供真正的负向筛选能力。

也就是说：

- 规则层留下的候选通知
- 在 AI 看完复杂内容和复杂画像切片后
- 可以被判定为不应触达

这类负向判断应进入决策层，而不是只停留在 AI 摘要文本里。

## Runtime Semantics Update

当前实现对 AIRuntimeConfig 的运行时语义补充如下：

- 配置优先级：默认以 ConfigService 读取到的 AIRuntimeConfig 为准，Settings / env 只作为本地调试 override，并且只允许在 container.py 装配阶段合并一次；AI service 和 gateway 只消费这份 resolved config。
- enabled=false：AIProcessingService.analyze() 是严格入口，会直接拒绝运行；analyze_or_fallback() 会返回 None，不会触发任何 gateway 调用，并写入 ai_call_logs.status = "skipped"。
- enabled=false 时，workflow 会在 AI 前先短路，不再构建 AI 专用 `ProfileContext`。
- max_retries：只作用于模型调用阶段，只对 ModelGatewayError 生效；prompt 构建错误、结果校验错误、schema/字段错误、模型输出 JSON 解析或语义错误都不会重试。
- 审计语义：正常完成写 success，重试耗尽或非重试型失败写 failed，运行时关闭写 skipped。
- 上游契约保持不变：AI 仍然只消费 SourceEvent + RuleAnalysisResult + ProfileContext，不会回退为完整 UserProfile 输入。


## 1. 业务背景

校园通知中存在大量半结构化和非结构化文本，仅靠规则很难稳定处理这些场景：

- 表达隐晦的动作要求
- 模糊的目标人群描述
- 分散在正文中的截止时间
- 长文本通知摘要
- 模糊类别归类

但系统第一阶段的原则不是“AI 全权裁决”，而是：

**规则优先，AI 辅助。**

因此 AI 层的业务意义是：

**在规则层之后，对复杂语义做补充理解和字段抽取，为决策层提供额外参考。**

它在整个系统里的位置是：

**`SourceEvent + RuleAnalysisResult + ProfileContext` → AI 层 → `AIAnalysisResult` → 决策层**

---

## 2. 模块职责

AI 处理层只做这些事情：

1. **做复杂语义理解**
2. **抽取关键字段**
3. **生成简要摘要**
4. **辅助类别判定**
5. **只消费最小相关画像上下文**
6. **输出结构化 AI 分析结果**

AI 处理层不做这些事情：

- 不替代接入层做采集
- 不替代规则层做基础初筛
- 不直接做最终推送决策
- 不直接触发消息发送
- 不直接维护用户画像和系统配置

一句话：

**AI 处理层是“语义理解补充模块”，不是“唯一判断模块”。**

---

## 3. 模块边界

### 3.1 上游依赖

AI 层上游默认包括：

- `SourceEvent`
- `RuleAnalysisResult`
- `ProfileContext`
- 配置层提供的模型配置、提示词模板和阈值配置

---

## 4. 模块对外接口定义

---

## 5. 模块内部架构

建议 AI 层拆成 7 个子模块：

1. `PromptBuilder`
2. `ModelGateway`
3. `FieldExtractor`
4. `SummaryGenerator`
5. `ResultValidator`
6. `AICache`
7. `AIAnalysisRepository`

---

## 6. 子模块详细设计

---

## 7. 数据存储设计

AI 层至少依赖两类表：

### 7.1 `ai_analysis_results`

用于存储结构化 AI 分析结果。

### 7.2 `ai_call_logs`

用于记录模型调用日志、耗时、错误和供应商信息。

---

## 8. Mock 设计

本模块必须支持无真实模型条件下的独立联调。

---

## 9. 测试要求

---

## 10. 开发约束

### 10.1 必须做

- 保留模型名和 Prompt 版本
- 输出结构化 `AIAnalysisResult`
- 支持结果校验与降级
- 兼容 `ProfileContext` 作为标准上游输入
- 支持 mock 模型联调

### 10.2 不要做

- 不要让 AI 直接做最终推送动作
- 不要把未经校验的原始模型文本直接交给决策层
- 不要把规则层可以稳定完成的工作全部迁移给 AI
- 不要默认把完整 `UserProfile` 原样喂给模型

### 10.3 推荐工程目录

```text
backend/app/services/ai_processing/
  __init__.py
  service.py
  prompt_builder.py
  model_gateway.py
  field_extractor.py
  summary_generator.py
  result_validator.py
  cache.py
  repositories/
    ai_analysis_repository.py
  tests/
    test_prompt_builder.py
    test_result_validator.py
    test_mock_gateway.py
```

---

## 11. 模块交付物

AI 处理层模块完成时，应该交付：

1. 代码实现
2. 模块 README
3. Prompt 模板
4. mock 输入输出文件
5. 单元测试
6. 模型网关抽象
7. 结果存储实现

---

## 12. 本模块一句话定义

**AI 处理层模块的核心业务，是在规则层之后补充复杂语义理解与字段抽取，为决策层提供可控、可审计的辅助分析结果。**

---

