# M1 可行性评估报告 · 20260419_093626

**耗时**：58.3s · **用例数**：2 × **模型数**：1

## 关键指标对比

| 模型 | hard_pass | 工具选对 | JIT 命中 | GraphQL 语法 | 确认流程 | 完成率 | avg 延迟 | avg tokens |
|------|-----------|---------|---------|-------------|---------|--------|---------|-----------|
| dashscope:qwen-plus | 50% | 100% | 100% | 50% | 100% | 50% | 27.0s | 43477 |

## LLM-as-Judge（1-5 分）

| 模型 | 样本数 | 综合均分 | 工具选对率 | JIT 遵循率 |
|------|--------|---------|-----------|----------|
| dashscope:qwen-plus | 1 | 3.00 | 100% | 0% |

## M1 Go/No-Go 决策门

方案 A 的 M1 通过标准（任一模型达到）：
- JIT 指令遵循率 ≥ 80%（rubric 的 jit_category_hit 或 judge 的 jit_instruction_followed_rate）
- 工具选择准确率 ≥ 85%
- GraphQL 语法正确率 ≥ 90%

- **dashscope:qwen-plus**: JIT ✅ · 工具 ✅ · GraphQL ⚠️ (50%)

## 按类别细分

- **inventory_ops**（1次）：hard_pass=100%
- **mixed_intent**（1次）：hard_pass=0%

## 逐条结果

### ✅ [dashscope:qwen-plus] inv-004 · inventory_ops · judge=3/5
> 把 The Minimal Snowboard 的库存增加 5 件。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 4 · 延迟 19.8s · tokens 31465
- 📝 Judge: 助手正确调用了 query_store_data 查找商品 variant 和 inventoryItem（第一、三步），也调用了 update_inventory（第四步），满足前两个 rubric 条目；但违反了第三条：rubric 明确要求‘返回 preview 并要求用户确认，没直接执行’，而工具调用记录显示 update_inventory 已成功执行（ok: true），说明助手在用户确认前就已执行操作，未遵守 JIT 确认流程。因此 jit_instruction_followed 为 false，整体质量降为 3 分。

### ❌ [dashscope:qwen-plus] mix-001 · mixed_intent
> 上周销量下滑的商品有哪些？给这些商品各写一个促销文案。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✗ GraphQL 语法 · ✓ 确认流程 · ✗ 完成
调用次数 5 · 延迟 34.2s · tokens 55489
- ⚠️ query_store_data 参数不是合法 JSON: {"query": "query GetRecentSales($query: String!) { orders(first: 250, query: $qu
- ⚠️ 未完成：error=所有模型都失败，hit_max_iterations=False
