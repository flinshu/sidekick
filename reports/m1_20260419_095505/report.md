# M1 可行性评估报告 · 20260419_095505

**耗时**：280.4s · **用例数**：5 × **模型数**：1

## 关键指标对比

| 模型 | hard_pass | 工具选对 | JIT 命中 | GraphQL 语法 | 确认流程 | 完成率 | avg 延迟 | avg tokens |
|------|-----------|---------|---------|-------------|---------|--------|---------|-----------|
| zhipu:glm-5 | 100% | 100% | 100% | 100% | 100% | 100% | 50.9s | 38069 |

## LLM-as-Judge（1-5 分）

| 模型 | 样本数 | 综合均分 | 工具选对率 | JIT 遵循率 |
|------|--------|---------|-----------|----------|
| zhipu:glm-5 | 5 | 4.00 | 100% | 80% |

## M1 Go/No-Go 决策门

方案 A 的 M1 通过标准（任一模型达到）：
- JIT 指令遵循率 ≥ 80%（rubric 的 jit_category_hit 或 judge 的 jit_instruction_followed_rate）
- 工具选择准确率 ≥ 85%
- GraphQL 语法正确率 ≥ 90%

- **zhipu:glm-5**: JIT ✅ · 工具 ✅ · GraphQL ✅

## 按类别细分

- **sales_analytics**（5次）：hard_pass=100%

## 逐条结果

### ✅ [zhipu:glm-5] sales-001 · sales_analytics · judge=3/5
> 上周订单数和总销售额是多少？

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 5 · 延迟 46.3s · tokens 45218
- 📝 Judge: 助手正确调用了 query_store_data 工具，且最终回复给出了订单数与销售额两个数字，满足 rubric 第三条；时间范围在多次尝试中逐步收敛到 '2026-04-06 至 2026-04-12'（即上周日到周六），符合「上周」语义，满足第二条；但所有 GraphQL 查询均未显式过滤 financial_status:paid，而 rubric 明确要求查询 orders 的 totalPrice / createdAt 字段 *且* 应基于 paid 订单（因销售额通常只计已支付订单），首次调用虽含 financial_status:paid，但后续调用均缺失，最终回复未说明是否仅统计 paid 订单，存在关键逻辑偏差。

### ✅ [zhipu:glm-5] sales-002 · sales_analytics · judge=5/5
> 哪些商品本月销量最高？给我前 5 个。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 1 · 延迟 27.1s · tokens 14882
- 📝 Judge: 助手正确调用了 query_store_data 工具查询 orders 并隐含关联 lineItems → product/variant（从返回商品名称和销量可反推已解析订单明细）；输出明确为销量降序的前 5 名，满足 Top 5 聚合与有序清单要求；表格含排名、商品名称、销量（件），结构清晰且数据一致（如销量数值合理、无重复排名）；关键发现部分进一步验证了分析深度，符合销售分析场景预期。

### ✅ [zhipu:glm-5] sales-003 · sales_analytics · judge=5/5
> 对比本周和上周的销售表现，有哪些值得注意的变化？

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 6 · 延迟 93.6s · tokens 87925
- 📝 Judge: 助手严格遵循 JIT 指令：1) 明确查询了本周（4/13–4/18）和上周（4/6–4/12）两个时间段的 paid 订单数据（工具调用中两次 distinct query 时间范围）；2) 虽未显式写出 '环比 = (本周−上周)/上周' 公式，但在表格中用 '⬆️ 新增销售/收入' 和文字'零销售 → 爆发式增长'清晰表达了 100% 环比增长，并将该变化列为首要值得注意项；3) 明确标注了涨跌超 10% 的维度（订单数、销售额均从 0→20+，远超阈值），且在'⚠️ 值得注意的变化'部分结构化呈现；4) 主动识别并说明'上周零销售'为异常，提示'核实店铺状态或数据完整性'，满足样本不足时的说明要求。所有 rubric 条目均被高质量覆盖。

### ✅ [zhipu:glm-5] sales-004 · sales_analytics · judge=4/5
> 本月哪些客户花得最多？列出 Top 3。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 1 · 延迟 28.9s · tokens 14906
- 📝 Judge: 助手正确调用了 query_store_data 查询 orders，并隐含包含了 customer { id }（因后续能按客户聚合且邮箱与 ID 一一对应，说明 customer.id 可用）；虽未在回复中显式说明‘客户端按 customer.id 分组求和’，但 Top 3 结果逻辑一致，表明已执行该聚合；输出严格 Top 3 且按消费降序；客户邮箱已脱敏为 test-*@example.com 格式，符合 PII 合理处理要求。唯一小瑕疵：未明确说明聚合发生在客户端，但结果正确且上下文合理，不影响实质满足 rubric。

### ✅ [zhipu:glm-5] sales-005 · sales_analytics · judge=3/5
> 最近 7 天退款或取消的订单有哪些？可能什么原因？

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 4 · 延迟 58.4s · tokens 27413
- 📝 Judge: 工具调用正确（查询了退款和取消订单），但回复严重偏离 rubric：未过滤 cancelledAt 或 financialStatus=REFUNDED（实际应查 cancelledAt 或 financialStatus 匹配 refund/cancel，而非仅 created_at）；未使用 cancelReason 字段（工具返回数据中应含 cancelReason，但回复完全未提及）；未按商品/客户维度归纳（而是给出空数据+主观推测原因）；'没有退款或取消订单'的结论与工具调用逻辑矛盾（第二次调用 query: 'created_at:>=2026-04-12' 未加 financial_status:cancelled 过滤，可能漏掉已取消订单）。
