# M1 可行性评估报告 · 20260418_235352

**耗时**：174.4s · **用例数**：5 × **模型数**：1

## 关键指标对比

| 模型 | hard_pass | 工具选对 | JIT 命中 | GraphQL 语法 | 确认流程 | 完成率 | avg 延迟 | avg tokens |
|------|-----------|---------|---------|-------------|---------|--------|---------|-----------|
| dashscope:qwen-plus | 100% | 100% | 100% | 100% | 100% | 100% | 30.0s | 23496 |

## LLM-as-Judge（1-5 分）

| 模型 | 样本数 | 综合均分 | 工具选对率 | JIT 遵循率 |
|------|--------|---------|-----------|----------|
| dashscope:qwen-plus | 5 | 4.00 | 80% | 80% |

## M1 Go/No-Go 决策门

方案 A 的 M1 通过标准（任一模型达到）：
- JIT 指令遵循率 ≥ 80%（rubric 的 jit_category_hit 或 judge 的 jit_instruction_followed_rate）
- 工具选择准确率 ≥ 85%
- GraphQL 语法正确率 ≥ 90%

- **dashscope:qwen-plus**: JIT ✅ · 工具 ✅ · GraphQL ✅

## 按类别细分

- **sales_analytics**（5次）：hard_pass=100%

## 逐条结果

### ✅ [dashscope:qwen-plus] sales-001 · sales_analytics · judge=4/5
> 上周订单数和总销售额是多少？

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 3 · 延迟 21.3s · tokens 25488
- 📝 Judge: 工具调用正确：最终成功调用了 query_store_data，且 query 参数中使用了 created_at 过滤「上周」（2026-04-11 至 2026-04-17），并获取了 orders 和 totalPrice 字段，满足 rubric 前两条。最终回复也准确给出了订单数（85）和总销售额（¥249,876.45），满足第三条。但 JIT 指令明确要求「计算环比」，而助手在回复中声明「由于缺少前一周数据无法计算环比」，未主动补查或尝试推导，属于未遵循 JIT 指令第 1、2 条；此外 rubric 未要求分析平均值、最高/最低单等衍生指标，属冗余输出，轻微偏离「只给两个数字」的核心要求。

### ✅ [dashscope:qwen-plus] sales-002 · sales_analytics · judge=5/5
> 哪些商品本月销量最高？给我前 5 个。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 2 · 延迟 29.0s · tokens 20006
- 📝 Judge: 助手正确选择了 query_store_data 工具来拉取本月已支付订单的 lineItems（满足 '查询 orders 并关联 lineItems → product/variant'）；从 127 条 lineItems 中准确聚合出 Top 5 商品并按总销量降序排列（满足 '做了 Top 5 聚合' 和 '输出是有序 Top 5 清单'）；回复中明确标注销量数值、排序标识（1️⃣–5️⃣）及业务上下文，完全符合 rubric 所有维度。

### ✅ [dashscope:qwen-plus] sales-003 · sales_analytics · judge=5/5
> 对比本周和上周的销售表现，有哪些值得注意的变化？

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 6 · 延迟 38.5s · tokens 22560
- 📝 Judge: 助手严格遵循 JIT 指令：1) 正确查询了本周（2026-04-14 起）和上周（2026-04-07–13）两段数据；2) 明确计算并标注了‘周环比增长无限大（0 → 72 单）’，符合‘标注涨跌超 10% 的维度’要求；3) 对上周 0 单这一异常样本，未回避或猜测，而是明确说明‘不是数据遗漏，而是真实业务现象’，并给出合理归因，满足‘样本不足时明确说明’；4) 所有分析均基于实际拉取的数据，逻辑闭环、结论可验证。

### ✅ [dashscope:qwen-plus] sales-004 · sales_analytics · judge=2/5
> 上个月哪些客户花得最多？列出 Top 3。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 4 · 延迟 40.8s · tokens 30198
- 📝 Judge: 助手未按 rubric 要求查询 customers 表并使用 amountSpent 字段，而是错误地查询 orders 表并按时间排序（两次均用 PROCESSED_AT/CREATED_AT），完全偏离了‘客户消费总额’分析目标；Top 3 应基于每个客户的累计 amountSpent 排序，而非订单时间；虽对 PII 无暴露（因无结果），但根本未尝试聚合客户维度数据，属于工具选择与分析逻辑双重错误。

### ✅ [dashscope:qwen-plus] sales-005 · sales_analytics · judge=4/5
> 最近 7 天退款或取消的订单有哪些？可能什么原因？

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 2 · 延迟 20.5s · tokens 19226
- 📝 Judge: 助手正确选择了 query_store_data 工具并构造了包含 cancelledAt 和 displayFinancialStatus 的查询，满足 rubric 中‘过滤 cancelledAt 或 financialStatus=REFUNDED’的要求；虽未返回 cancelReason（因无数据），但明确指出‘数据样本为 0’，合理解释了无法分析原因的客观限制，符合 rubric 第二条精神；回复未堆砌原始订单列表，而是归纳为‘0 单’‘¥0.00’‘履约健康’等业务结论，并给出可操作的排查建议，满足第三条‘按维度归纳’要求；唯一小瑕疵是未显式提及 cancelReason 字段缺失本身，但该字段在空结果下无信息价值，故不构成实质性缺陷。
