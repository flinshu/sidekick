# M1 可行性评估报告 · 20260419_093907

**耗时**：98.7s · **用例数**：3 × **模型数**：1

## 关键指标对比

| 模型 | hard_pass | 工具选对 | JIT 命中 | GraphQL 语法 | 确认流程 | 完成率 | avg 延迟 | avg tokens |
|------|-----------|---------|---------|-------------|---------|--------|---------|-----------|
| dashscope:qwen-plus | 33% | 67% | 67% | 100% | 100% | 67% | 29.8s | 45518 |

## LLM-as-Judge（1-5 分）

| 模型 | 样本数 | 综合均分 | 工具选对率 | JIT 遵循率 |
|------|--------|---------|-----------|----------|
| dashscope:qwen-plus | 2 | 2.50 | 0% | 50% |

## M1 Go/No-Go 决策门

方案 A 的 M1 通过标准（任一模型达到）：
- JIT 指令遵循率 ≥ 80%（rubric 的 jit_category_hit 或 judge 的 jit_instruction_followed_rate）
- 工具选择准确率 ≥ 85%
- GraphQL 语法正确率 ≥ 90%

- **dashscope:qwen-plus**: JIT ⚠️ (67%) · 工具 ⚠️ (67%) · GraphQL ✅

## 按类别细分

- **inventory_ops**（1次）：hard_pass=0%
- **mixed_intent**（2次）：hard_pass=50%

## 逐条结果

### ❌ [dashscope:qwen-plus] inv-005 · inventory_ops · judge=2/5
> 仓库 A 和仓库 B 的库存差异在哪些商品上最大？

✗ 工具选对 · ✗ 调用数达标 · ✗ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 0 · 延迟 9.2s · tokens 5753
- ⚠️ 缺失工具：['query_store_data']，实际调用：[]
- ⚠️ JIT 场景未命中期望：['inventory_ops']，实际：[]
- 📝 Judge: rubric 要求必须查询 inventoryLevels 并按 location 分组、计算差值并排序、给出跨仓调拨建议；但助手未调用任何工具（如 inventoryLevels 查询），也未执行任何计算或排序，更未提供调拨建议；相反，它将问题退回给用户索要 Location ID，属于未履行核心分析职责；虽对 Shopify 数据模型理解正确，但完全未满足 rubric 的三项强制性操作要求。

### ❌ [dashscope:qwen-plus] mix-001 · mixed_intent
> 上周销量下滑的商品有哪些？给这些商品各写一个促销文案。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✗ 完成
调用次数 10 · 延迟 57.6s · tokens 96939
- ⚠️ 未完成：error=max_iterations (10) 超出，hit_max_iterations=True

### ✅ [dashscope:qwen-plus] mix-005 · mixed_intent · judge=3/5
> 帮我看看 T 恤类目这周的销售表现，如果销量低于 10 件就启动 8 折促销。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 3 · 延迟 22.6s · tokens 33861
- 📝 Judge: 工具调用未聚焦于 'T 恤'（含常见变体如 'T-shirt', 'tshirt'），而是错误地查询了更宽泛的 apparel/clothing/tops/shirts 类目，违背 rubric 中'按 productType=T 恤 查询'的要求；虽正确识别销量为0 < 10 并提出创建促销需确认，体现了条件触发逻辑，但因根本未查到 T 恤商品，无法验证是否真实销量低于10——可能因查询范围错误导致假阴性；未体现对 'T 恤' 多种拼写/空格/大小写（如 'T Shirt'、't shirt'）的鲁棒匹配，也未在无结果时回退检查 query_store_data 是否返回空或报错。
