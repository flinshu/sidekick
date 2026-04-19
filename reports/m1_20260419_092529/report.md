# M1 可行性评估报告 · 20260419_092529

**耗时**：125.5s · **用例数**：3 × **模型数**：1

## 关键指标对比

| 模型 | hard_pass | 工具选对 | JIT 命中 | GraphQL 语法 | 确认流程 | 完成率 | avg 延迟 | avg tokens |
|------|-----------|---------|---------|-------------|---------|--------|---------|-----------|
| dashscope:qwen-plus | 33% | 100% | 100% | 67% | 67% | 33% | 39.9s | 72553 |

## LLM-as-Judge（1-5 分）

| 模型 | 样本数 | 综合均分 | 工具选对率 | JIT 遵循率 |
|------|--------|---------|-----------|----------|
| dashscope:qwen-plus | 1 | 2.00 | 0% | 0% |

## M1 Go/No-Go 决策门

方案 A 的 M1 通过标准（任一模型达到）：
- JIT 指令遵循率 ≥ 80%（rubric 的 jit_category_hit 或 judge 的 jit_instruction_followed_rate）
- 工具选择准确率 ≥ 85%
- GraphQL 语法正确率 ≥ 90%

- **dashscope:qwen-plus**: JIT ✅ · 工具 ✅ · GraphQL ⚠️ (67%)

## 按类别细分

- **inventory_ops**（1次）：hard_pass=0%
- **mixed_intent**（2次）：hard_pass=50%

## 逐条结果

### ❌ [dashscope:qwen-plus] inv-004 · inventory_ops
> 把 The Minimal Snowboard 的库存增加 5 件。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✗ 确认流程 · ✗ 完成
调用次数 10 · 延迟 39.9s · tokens 70552
- ⚠️ 写操作没有触发 preview/确认流程
- ⚠️ 未完成：error=max_iterations (10) 超出，hit_max_iterations=True

### ❌ [dashscope:qwen-plus] mix-001 · mixed_intent
> 上周销量下滑的商品有哪些？给这些商品各写一个促销文案。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✗ GraphQL 语法 · ✓ 确认流程 · ✗ 完成
调用次数 4 · 延迟 32.1s · tokens 31656
- ⚠️ query_store_data 参数不是合法 JSON: {"query": "query GetProductDetails($ids: [ID!]!) { nodes(ids: $ids) { ... on Pro
- ⚠️ 未完成：error=所有模型都失败，hit_max_iterations=False

### ✅ [dashscope:qwen-plus] mix-003 · mixed_intent · judge=2/5
> 哪些客户最近 30 天没下单但之前花费超过 100 美元？给他们发个召回折扣。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 8 · 延迟 47.7s · tokens 115450
- 📝 Judge: 助手未正确识别并执行核心分析逻辑：未先查询最近30天无订单的客户（仅两次调用orders但时间范围错误，如2026-03-20明显为未来日期，且未与customers结果做差集）；未按amountSpent > 100过滤客户（所有customer查询均未带where条件，仅排序或全量拉取）；折扣码WELCOMEBACK20虽体现召回意图，但缺乏针对'高价值流失客户'的定向限制（如仅限amountSpent > 100且lastOrder < 30d的客户），违反召回精准性要求；PII（email/firstName/lastName）在工具调用中被直接拉取但最终回复中完全未呈现或脱敏，既未聚合统计也未说明处理方式，违反PII合理性要求。
