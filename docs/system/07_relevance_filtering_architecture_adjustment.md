# 07_relevance_filtering_architecture_adjustment.md

## 1. 文档目的

本文件用于收口 2026-03-15 对“通知相关性筛选架构”的专项调整。

本次调整要解决的问题不是某个模块实现细节，而是主链路中这几个职责出现了偏移：

- 规则层承担了过多“复杂画像 + 复杂语义”的判断
- AI 层更多在做摘要和补充说明，没有真正承担第二阶段精筛职责
- 决策层对 `unknown` 的文案和动作口径不一致，容易出现“已归档但 reason_summary 仍写成与你可能相关”
- 用户画像层已经具备复杂画像能力，但主链路还没有把“简单画像用于粗筛、复杂画像用于精筛”明确冻结

本文件的目标是把相关性筛选主链路调整为：

**规则层做硬条件粗筛，AI 层做候选通知精筛，决策层做最终动作裁定。**

---

## 2. 为什么要调整

当前原型已经证明系统可以跑通真实通知实验，但也暴露出三个结构性问题：

1. `rule_relevance_status = unknown` 的通知很多，说明规则层对复杂内容没有足够把握。
2. `reason_summary` 对大量 `archive` 结果仍然写成“与你可能相关”，说明“候选通知”和“最终相关通知”在文案上没有被区分。
3. 用户画像层已经拿到了更复杂的学业完成数据，但规则层并不适合直接承担这些复杂画像的细粒度语义判断。

如果继续维持“规则层做大部分判断，AI 只做补充”，系统会出现：

- 规则层持续膨胀，越来越难维护
- AI 接入真实模型后也难以真正改善筛选质量
- 用户看到大量“可能相关但没推”的解释文案，产品语义混乱

---

## 3. 新的主链路结论

本次调整后，相关性筛选主链路固定为：

1. 接入层生成 `SourceEvent`
2. 编排层枚举目标用户并构建完整 `UserProfile`
3. 规则层基于通知文本和用户简单画像做第一阶段粗筛
4. 规则层输出：
   - `relevance_status`
   - `should_invoke_ai`
   - `required_profile_facets`
5. 对于规则层明确判为 `irrelevant` 的通知，主链路可直接结束，不再进入 AI 精筛
6. 对于规则层判为 `relevant` 或 `unknown` 且 `should_invoke_ai = true` 的候选通知：
   - 编排层调用 `ProfileContextSelector`
   - 用户画像层输出最小相关 `ProfileContext`
   - AI 层对候选通知做第二阶段精筛
7. AI 层输出结构化语义判断，重点包括：
   - `summary`
   - `normalized_category`
   - `relevance_hint`
   - `urgency_hint`
   - `risk_hint`
   - `confidence`
8. 决策层统一消费：
   - `RuleAnalysisResult`
   - `AIAnalysisResult`
   - `UserProfile`
   - 策略配置
9. 决策层输出 `DecisionResult`
10. 发文层仅执行触达

---

## 4. 规则层调整原则

### 4.1 新定位

规则层的定位调整为：

**基于简单标签、显式文本命中和硬约束做初步筛选，而不是完成复杂画像理解。**

### 4.2 规则层优先处理的内容

规则层优先处理这些“硬条件”：

- `identity_tags`
- `degree_level`
- `college`
- `major`
- `grade`
- 显式课程名命中
- 显式当前待办命中
- 明确的动作词、截止时间、附件、来源权威度

### 4.3 规则层不再扩张的方向

以下能力不应继续向规则层扩张：

- 基于复杂学分缺口的细粒度业务推理
- 基于培养方案模块完成情况的复杂相关性判断
- 依赖长文本上下文、隐含语义、弱提示信息的复杂受众推断
- 用大量 if-else 或配置堆叠去近似替代 AI 精筛

### 4.4 `relevance_status` 的粗筛语义

在本次调整后，规则层的 `relevance_status` 语义收口为：

- `irrelevant`
  - 表示存在明确硬失配
  - 例如明确学院不匹配、明确身份不匹配、规则层已能高置信度排除
- `relevant`
  - 表示存在明确硬命中
  - 例如明确毕业生通知且身份标签命中、明确课程通知且当前课程命中
- `unknown`
  - 表示规则层认为“值得进入 AI 精筛的候选通知”
  - `unknown` 不等价于“已经与你相关”
  - `unknown` 更接近“candidate”

结论：

**规则层输出 `unknown` 时，产品和决策语义都不得直接把它翻译成“与你可能相关”的最终结论。**

---

## 5. AI 层调整原则

### 5.1 新定位

AI 层的定位调整为：

**对规则层留下来的候选通知，结合复杂通知内容与复杂画像切片做第二阶段精筛。**

### 5.2 AI 层重点承担的事情

AI 层应重点承担：

- 理解复杂长文本和隐含动作要求
- 理解弱表达、跨段落、非模板化描述
- 结合复杂画像切片判断通知是否真的与该用户有关
- 对 `unknown` 候选通知给出更明确的正向或负向判断

### 5.3 AI 的输入原则

AI 默认不直接消费完整 `UserProfile`，而是消费：

- `SourceEvent`
- `RuleAnalysisResult`
- `ProfileContext`

其中：

- 简单画像 facet 由规则层决定是否需要
- 复杂画像 facet 由 `required_profile_facets` 驱动选择
- `ProfileContext` 应优先承载：
  - `academic_completion`
  - `graduation_progress`
  - `activity_based_credit_gap`
  - `online_platform_credit_gap`
  - 必要的 `current_courses`

### 5.4 `relevance_hint` 的精筛语义

从本次调整起，`AIAnalysisResult.relevance_hint` 应按以下规范使用：

- `relevant`
- `irrelevant`
- `uncertain`

允许保留附加解释，但决策层消费时必须先按这三个标准值解释，而不是把任意自然语言都当自由文案。

---

## 6. 决策层调整原则

### 6.1 新定位

决策层继续是唯一最终裁决入口，但它必须显式承担“合并规则粗筛与 AI 精筛”的责任。

### 6.2 决策层最重要的新约束

决策层必须显式消费 AI 的负向判断。

至少应满足这些合并语义：

- 规则层 `irrelevant`
  - 直接 `ignore`
  - 不依赖 AI 翻盘
- 规则层 `unknown` 且 AI `relevance_hint = irrelevant`
  - 默认 `archive` 或 `ignore`
- 规则层 `unknown` 且 AI `relevance_hint = relevant`
  - 进入正常优先级与动作裁定
- 规则层 `relevant` 且 AI `relevance_hint = irrelevant`
  - 原则上只允许在“规则命中不是硬受众约束、而是粗候选命中”时做保守降级
  - 不允许让 AI 推翻明确的硬身份命中

### 6.3 `reason_summary` 语义必须与最终动作一致

`reason_summary` 是最终决策摘要，不是规则层中间态描述。

因此：

- `archive` 的通知不应直接写成“与你可能相关”
- `ignore` 的通知不应出现正向相关措辞
- `unknown` 作为中间态不得原样泄漏成最终用户语义

推荐改写方向：

- 规则层硬失配：
  - “规则层判定该通知与当前用户无关，结束当前处理链路。”
- 粗筛命中但 AI 未确认：
  - “规则粗筛命中候选范围，但未达到精筛触达阈值，已归档观察。”
- AI 确认相关：
  - “规则粗筛与 AI 精筛均判定该通知与你相关，且存在明确动作要求。”

---

## 7. 用户画像层调整原则

### 7.1 新定位

用户画像层保持“状态输入源”定位，但要更明确地区分：

- 简单画像
- 复杂画像

### 7.2 简单画像

适合规则层粗筛的画像内容：

- `identity_tags`
- `degree_level`
- `college`
- `major`
- `grade`
- 当前课程名
- 当前待办标题

### 7.3 复杂画像

适合 AI 精筛的画像内容：

- 学业完成模块缺口
- `attention_signals`
- `pending_items`
- 毕业进度明细
- 活动学分 / 网课平台学分缺口
- 更细粒度的课程上下文或模块上下文

### 7.4 `ProfileContextSelector` 的新作用

`ProfileContextSelector` 不只是“节省 token”，还承担主链路分层责任：

- 规则层不直接处理复杂画像细节
- AI 层只看被显式请求的复杂画像切片
- 决策层仍保留消费完整画像和结构化画像信号的能力

---

## 8. 对现有共享对象的解释补充

本次调整不新增跨模块字段，先通过现有对象收口语义：

- `RuleAnalysisResult.relevance_status`
  - 解释为第一阶段粗筛结论
- `RuleAnalysisResult.should_invoke_ai`
  - 解释为“该候选通知是否需要 AI 精筛”
- `RuleAnalysisResult.required_profile_facets`
  - 解释为“精筛真正需要的画像切片”
- `AIAnalysisResult.relevance_hint`
  - 解释为第二阶段精筛相关性结论
- `DecisionResult.reason_summary`
  - 解释为最终动作摘要，不是中间态翻译

---

## 9. 迁移建议

这次调整建议按下面顺序落地：

1. 先改文档和契约解释
2. 再改决策层对 `relevance_hint` 的消费逻辑
3. 再收紧规则层，让它少做复杂画像推理
4. 再增强 AI prompt 和结果校验，让 AI 真正承担第二阶段精筛职责
5. 最后再根据实验样本调整脚本中的统计口径与展示文案

---

## 10. 一句话定义

**本次架构调整的核心，是把通知筛选主链路改成“规则层做硬条件粗筛，AI 层做候选通知精筛，决策层输出与最终动作一致的裁定语义”。**
