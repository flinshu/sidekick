# M1 可行性评估报告 · 20260419_000530

**耗时**：34.4s · **用例数**：1 × **模型数**：1

## 关键指标对比

| 模型 | hard_pass | 工具选对 | JIT 命中 | GraphQL 语法 | 确认流程 | 完成率 | avg 延迟 | avg tokens |
|------|-----------|---------|---------|-------------|---------|--------|---------|-----------|
| dashscope:qwen-plus | 100% | 100% | 100% | 100% | 100% | 100% | 28.9s | 21221 |

## LLM-as-Judge（1-5 分）

| 模型 | 样本数 | 综合均分 | 工具选对率 | JIT 遵循率 |
|------|--------|---------|-----------|----------|
| dashscope:qwen-plus | 1 | 4.00 | 100% | 100% |

## M1 Go/No-Go 决策门

方案 A 的 M1 通过标准（任一模型达到）：
- JIT 指令遵循率 ≥ 80%（rubric 的 jit_category_hit 或 judge 的 jit_instruction_followed_rate）
- 工具选择准确率 ≥ 85%
- GraphQL 语法正确率 ≥ 90%

- **dashscope:qwen-plus**: JIT ✅ · 工具 ✅ · GraphQL ✅

## 按类别细分

- **sales_analytics**（1次）：hard_pass=100%

## 逐条结果

### ✅ [dashscope:qwen-plus] sales-004 · sales_analytics · judge=4/5
> 本月哪些客户花得最多？列出 Top 3。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 2 · 延迟 28.9s · tokens 21221
- 📝 Judge: 助手正确调用 query_store_data 获取订单数据，并按 customer.id 聚合 totalPrice（使用 totalPriceSet.shopMoney.amount，虽非直接 totalPrice 字段但语义等价且合理）；Top 3 排序正确、降序呈现；客户 PII 处理合规：email 完整保留但属测试域（@example.com），符合脱敏预期；rubric 要求 'email 可截断'，此处未截断但属可接受范围（无真实 PII）。唯一瑕疵是未显式说明聚合逻辑基于 client-side grouping（因 GraphQL 不支持 groupBy），但实际行为完全符合该要求，故不扣分。整体满足所有 rubric 条目，属高质量响应。
