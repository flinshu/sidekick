# M1 可行性评估报告 · 20260418_233749

**耗时**：103.8s · **用例数**：2 × **模型数**：1

## 关键指标对比

| 模型 | hard_pass | 工具选对 | JIT 命中 | GraphQL 语法 | 确认流程 | 完成率 | avg 延迟 | avg tokens |
|------|-----------|---------|---------|-------------|---------|--------|---------|-----------|
| dashscope:qwen-max | 100% | 100% | 100% | 100% | 100% | 100% | 51.9s | 25458 |

## M1 Go/No-Go 决策门

方案 A 的 M1 通过标准（任一模型达到）：
- JIT 指令遵循率 ≥ 80%（rubric 的 jit_category_hit 或 judge 的 jit_instruction_followed_rate）
- 工具选择准确率 ≥ 85%
- GraphQL 语法正确率 ≥ 90%

- **dashscope:qwen-max**: JIT ✅ · 工具 ✅ · GraphQL ✅

## 按类别细分

- **inventory_ops**（1次）：hard_pass=100%
- **sales_analytics**（1次）：hard_pass=100%

## 逐条结果

### ✅ [dashscope:qwen-max] inv-001 · inventory_ops
> 哪些商品库存已经低于安全线（假设 7 天销量）？

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 5 · 延迟 84.4s · tokens 37079

### ✅ [dashscope:qwen-max] sales-001 · sales_analytics
> 上周订单数和总销售额是多少？

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 2 · 延迟 19.4s · tokens 13836
