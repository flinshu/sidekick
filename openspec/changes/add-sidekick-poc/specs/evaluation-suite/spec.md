## ADDED Requirements

### Requirement: 至少 20 个场景的测试用例库

系统 SHALL 维护至少 20 条测试用例，覆盖 4 类：销售分析（≥5）、库存运营（≥5）、内容生成（≥5）、混合意图工作流（≥5）。每条测试用例 MUST 包含：用户问题、期望的工具调用序列、期望的 JIT 指令类别、响应评分 rubric。

#### Scenario: 测试用例可作为 pytest fixture 加载

- **WHEN** 运行 `pytest tests/cases/`
- **THEN** 每条测试用例 SHALL 被加载并作为独立测试执行
- **AND** 每个测试 SHALL 产出 pass/fail 结果以及评分指标

#### Scenario: 混合意图用例覆盖多步工作流

- **WHEN** 运行混合意图测试用例（例如"上周下滑的商品 + 给它们写促销文案"）
- **THEN** 测试 SHALL 验证 Agent 按正确顺序调用分析和内容两类工具
- **AND** SHALL 验证 JIT 指令在两个阶段间的切换

### Requirement: 多模型对比执行

评估套件 SHALL 支持把同一组测试用例针对多个模型（至少 Claude Sonnet、GPT-4o、Qwen-Max）批量执行并产出并排对比报告。

#### Scenario: 单条命令运行所有模型

- **WHEN** 操作员运行 `pytest tests/cases/ --models=claude-sonnet,gpt-4o,qwen-max`
- **THEN** 每条测试用例 SHALL 被每个模型各执行一次
- **AND** 对比报告 SHALL 按模型聚合得分

#### Scenario: 报告含定量指标

- **WHEN** 对比执行完成
- **THEN** 报告 SHALL 对每个模型给出：JIT 指令遵循率、工具选择准确率、GraphQL 语法正确率、GraphQL 字段合理性、LLM-as-Judge 综合质量分

### Requirement: RAGAS 检索质量评估

评估套件 SHALL 集成 RAGAS 指标（faithfulness、answer relevancy、context precision、context recall），用于涉及 RAG 检索的测试用例。RAGAS SHALL 作为 CI 的一部分运行。

#### Scenario: RAGAS 指标按 RAG 用例计算

- **WHEN** 测试用例标记为 rag-enabled 并被执行
- **THEN** 套件 SHALL 用检索到的上下文和生成的回答计算 RAGAS 指标
- **AND** SHALL 把得分与测试结果一并记录

### Requirement: DeepEval 安全护栏

评估套件 SHALL 在所有测试用例上运行 DeepEval 的幻觉、毒性、偏见、回避（evasion）四项指标。回避检测（reward hacking 模式：模型在可做的任务上选择回避）SHALL 作为一等指标。

#### Scenario: 模型在可做的任务上回避被识别

- **WHEN** 测试用例代表一个模型实际能处理的任务（例如标准商品描述生成）
- **AND** 模型回复"我无法处理"或类似话术
- **THEN** DeepEval SHALL 标记为 evasion
- **AND** 该测试 SHALL 失败，无视其他指标

### Requirement: LLM-as-Judge 质量打分

评估套件 SHALL 用一个 LLM（与被测 Agent 当次使用的模型不同）作为 Judge，按 1-5 分 rubric 对响应质量打分。Judge SHALL 收到：用户问题、Agent 响应、rubric 标准。

#### Scenario: Judge 模型与 Agent 模型不同

- **WHEN** 被测 Agent 用 Claude Sonnet
- **THEN** LLM-as-Judge 默认 SHALL 用其他模型（例如 GPT-4o 或 Qwen-Max）
- **AND** SHALL NOT 用 Claude Sonnet 评估同一次运行

#### Scenario: 人评与 LLM Judge 校准

- **WHEN** M1 首次运行完成
- **THEN** 人工 SHALL 抽样手动评 20 条响应
- **AND** 人评分数与 LLM Judge 分数的相关系数 SHALL 被计算
- **AND** 相关系数 < 0.6 时 MUST 优化 LLM Judge rubric 后再继续

### Requirement: 所有 Agent 执行都接 Langfuse 追踪

所有 Agent 调用（含评估运行）SHALL 上报到 Langfuse。Trace MUST 包含：模型、prompt、工具调用、工具结果、JIT 指令、token 用量、延迟、成本估算、租户 ID。

#### Scenario: Trace 完整捕获 Agentic Loop

- **WHEN** Agent 执行涉及 3 次工具调用 + 1 次最终响应
- **THEN** Langfuse trace SHALL 显示 4 个 LLM span 和 3 个 tool-execution span，并具有正确父子关系
- **AND** 总延迟和成本 SHALL 在 trace 根节点聚合

#### Scenario: Trace 可按租户过滤

- **WHEN** 操作员在 Langfuse 按租户 ID 过滤
- **THEN** 只有该租户的 trace SHALL 被返回

### Requirement: CI 集成评估

评估套件 SHALL 在 main 分支每次 push 时或通过 workflow_dispatch 手动触发运行。失败 SHALL 阻止 PR 合并。CI 运行 SHALL 产出包含完整对比报告的 artifact。

#### Scenario: CI 运行产出对比报告 artifact

- **WHEN** CI workflow 完成一次评估运行
- **THEN** SHALL 把 markdown 对比报告作为 workflow artifact 上传
- **AND** 摘要 SHALL 在对应 PR 上以评论形式发布

### Requirement: 用户模拟回归测试

评估套件 SHALL 包含用户模拟回归：由 LLM 扮演商家（新手/高级用户/刁钻测试者）与 Agent 进行多轮对话。回归 SHALL 在每次 milestone 发布前运行。

#### Scenario: "刁钻商家"模拟通过 baseline

- **WHEN** LLM 扮演刁钻商家进行 10 轮对话，故意用矛盾或模糊请求干扰 Agent
- **THEN** Agent SHALL NOT 产生幻觉式工具调用，SHALL NOT 突破 JIT 指令边界
- **AND** DeepEval 的 evasion 指标 SHALL 维持在阈值之下

### Requirement: 最终可行性报告生成

每个 milestone（M1/M2/M3）结束时，评估套件 SHALL 产出书面可行性报告，总结：milestone 的 go/no-go 标准是否达成、定量证据、显著失败、对下一阶段的建议。

#### Scenario: M1 报告明确回答 go/no-go

- **WHEN** M1 评估完成
- **THEN** 报告 SHALL 显式声明对 3 个关键阈值（JIT 遵循 ≥80%、工具选择 ≥85%、GraphQL 语法 ≥90%）的 PASS/FAIL
- **AND** SHALL 包含每个模型的原始得分、至少 5 段示例对话、与 Shopify Sidekick 在同问题上的对照
