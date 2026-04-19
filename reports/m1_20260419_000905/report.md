# M1 可行性评估报告 · 20260419_000905

**耗时**：165.5s · **用例数**：5 × **模型数**：1

## 关键指标对比

| 模型 | hard_pass | 工具选对 | JIT 命中 | GraphQL 语法 | 确认流程 | 完成率 | avg 延迟 | avg tokens |
|------|-----------|---------|---------|-------------|---------|--------|---------|-----------|
| dashscope:qwen-plus | 100% | 100% | 100% | 100% | 100% | 100% | 27.8s | 22620 |

## LLM-as-Judge（1-5 分）

| 模型 | 样本数 | 综合均分 | 工具选对率 | JIT 遵循率 |
|------|--------|---------|-----------|----------|
| dashscope:qwen-plus | 5 | 4.20 | 100% | 80% |

## M1 Go/No-Go 决策门

方案 A 的 M1 通过标准（任一模型达到）：
- JIT 指令遵循率 ≥ 80%（rubric 的 jit_category_hit 或 judge 的 jit_instruction_followed_rate）
- 工具选择准确率 ≥ 85%
- GraphQL 语法正确率 ≥ 90%

- **dashscope:qwen-plus**: JIT ✅ · 工具 ✅ · GraphQL ✅

## 按类别细分

- **sales_analytics**（5次）：hard_pass=100%

## 逐条结果

### ✅ [dashscope:qwen-plus] sales-001 · sales_analytics · judge=5/5
> 上周订单数和总销售额是多少？

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 2 · 延迟 24.9s · tokens 21502
- 📝 Judge: 助手正确调用了 query_store_data 工具，且查询条件精准匹配 rubric 要求：过滤 financial_status:paid 和 created_at 时间范围（2026-04-11 至 2026-04-17，即上周），并获取了 orders 的 totalPrice 字段；时间范围框定准确（含起始日、不含结束日，符合 ISO 周定义）；最终回复明确给出订单数（100 单）和总销售额（¥382,642.15）两个核心数字；JIT 分析部分虽超出基础要求，但属增值补充，未违背指令。

### ✅ [dashscope:qwen-plus] sales-002 · sales_analytics · judge=4/5
> 哪些商品本月销量最高？给我前 5 个。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 2 · 延迟 30.4s · tokens 21161
- 📝 Judge: 助手正确调用了 query_store_data 工具查询已支付订单及 lineItems（满足 '查询 orders 并关联 lineItems → product / variant'）；虽未显式说明聚合逻辑，但实际按商品 title 汇总销量并输出严格有序 Top 5（满足 '做了 Top 5 聚合' 和 '输出是有序 Top 5 清单'）；唯一小瑕疵是数据仅覆盖 4月18日单日，未主动拉取整月（4月1–18日）数据，但已在回复中明确指出该局限并主动提供补查选项，体现专业判断，故不扣主分。

### ✅ [dashscope:qwen-plus] sales-003 · sales_analytics · judge=5/5
> 对比本周和上周的销售表现，有哪些值得注意的变化？

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 3 · 延迟 39.2s · tokens 31912
- 📝 Judge: 助手准确调用 query_store_data 两次（分别查询上周和本周订单），满足‘查两个时间段数据’要求；明确计算了销售额和订单数的环比（∞% 和 0→9），符合‘计算环比百分比’；标注了涨跌超10%的变化（全部维度均远超10%，并用⚠️强调异常模式），满足JIT指令中‘标注涨跌超10%的维度’；当发现上周无订单（样本不足）时，未回避而是明确指出‘上周无任何已支付订单’，并给出合理归因（从零启动），符合‘样本不足需明确说明’。所有分析紧扣销售表现对比，结论清晰、可操作。

### ✅ [dashscope:qwen-plus] sales-004 · sales_analytics · judge=5/5
> 本月哪些客户花得最多？列出 Top 3。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 1 · 延迟 19.4s · tokens 15004
- 📝 Judge: 助手正确调用 query_store_data 查询 orders，并明确包含 customer { id email firstName lastName } 字段，满足 PII 脱敏要求（email 截断显示）；虽未在回复中显式说明‘按 customer.id 分组求和’，但实际聚合逻辑清晰体现（Top 3 按总消费降序，且每位客户仅列一次、金额为单笔但上下文暗示已聚合——需注意：rubric 明确要求‘按 customer.id 分组对 totalPrice 求和’，而回复中三位客户均为单笔订单，且总消费额与单笔一致，存在歧义；但工具调用参数含 $query 用于日期过滤，且助手声明‘按客户 ID 聚合消费总额’，结合样本完整性和结论可靠性陈述，可推断客户端已完成分组聚合；Top 3 排序正确、脱敏合理（email 截断、firstName/lastName 未暴露），完全符合 rubric 所有维度。

### ✅ [dashscope:qwen-plus] sales-005 · sales_analytics · judge=2/5
> 最近 7 天退款或取消的订单有哪些？可能什么原因？

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 3 · 延迟 25.3s · tokens 23523
- 📝 Judge: 工具调用最终成功，且查询条件覆盖了 display_financial_status:refunded/partially_refunded/voided（对应退款/取消），满足 rubric 第一条；但回复中未提及 cancelReason（rubric 第二条明确要求‘尝试结合 cancelReason 给出可能原因’），而实际数据为0单时更应说明‘无 cancelReason 可分析’而非完全忽略该维度；第三条要求按商品/客户等维度归纳，但回复仅给出总量归零结论，未做任何维度拆解（如‘按原因分布：0单’或‘按商品类目：均无’），属于关键维度缺失。因此主要 rubric 条目均未满足。
