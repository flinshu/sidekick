# M1 可行性评估报告 · 20260419_100314

**耗时**：895.7s · **用例数**：15 × **模型数**：1

## 关键指标对比

| 模型 | hard_pass | 工具选对 | JIT 命中 | GraphQL 语法 | 确认流程 | 完成率 | avg 延迟 | avg tokens |
|------|-----------|---------|---------|-------------|---------|--------|---------|-----------|
| zhipu:glm-5 | 67% | 67% | 100% | 100% | 67% | 100% | 56.0s | 23831 |

## LLM-as-Judge（1-5 分）

| 模型 | 样本数 | 综合均分 | 工具选对率 | JIT 遵循率 |
|------|--------|---------|-----------|----------|
| zhipu:glm-5 | 13 | 2.92 | 54% | 46% |

## M1 Go/No-Go 决策门

方案 A 的 M1 通过标准（任一模型达到）：
- JIT 指令遵循率 ≥ 80%（rubric 的 jit_category_hit 或 judge 的 jit_instruction_followed_rate）
- 工具选择准确率 ≥ 85%
- GraphQL 语法正确率 ≥ 90%

- **zhipu:glm-5**: JIT ✅ · 工具 ⚠️ (67%) · GraphQL ✅

## 按类别细分

- **content_generation**（5次）：hard_pass=40%
- **inventory_ops**（5次）：hard_pass=100%
- **mixed_intent**（5次）：hard_pass=60%

## 逐条结果

### ❌ [zhipu:glm-5] content-001 · content_generation · judge=2/5
> 帮商品 ID gid://shopify/Product/{SAMPLE_PRODUCT_ID} 写一份新的商品描述，突出环保材质。

✗ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✗ 确认流程 · ✓ 完成
调用次数 2 · 延迟 28.0s · tokens 18060
- ⚠️ 缺失工具：['save_content']，实际调用：['query_store_data', 'query_store_data']
- ⚠️ 期望触发写操作但实际未调用任何写工具
- 📝 Judge: 助手未正确调用 query_store_data 查询指定商品 ID 的信息，而是错误地查询了最新 10 个商品列表（且未传入 $id 变量），违反 '是否先查询该商品现有信息' 要求；未生成任何商品描述，因此未突出环保材质关键词；未调用 save_content 或返回 preview；未生成 SEO description，更无法验证 ≤ 160 字符。所有 rubric 条目均未满足，仅提供泛化列表并要求用户二次选择，属严重流程偏离。

### ✅ [zhipu:glm-5] content-002 · content_generation · judge=3/5
> 给全店的春季新品写 SEO 标题和描述，控制在标准长度内。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 2 · 延迟 56.9s · tokens 18801
- 📝 Judge: 工具调用正确（使用 tag/productType 过滤春季新品），满足 rubric 第一条；但未生成任何 SEO 标题/描述，完全未响应核心任务（写 SEO），故未遵循 JIT 指令中‘控制在标准长度内’和‘体现春季主题’的要求；回复转向询问而非交付结果，导致 SEO length 和春季主题体现两个关键维度均未满足。

### ❌ [zhipu:glm-5] content-003 · content_generation · judge=2/5
> 商品 gid://shopify/Product/{SAMPLE_PRODUCT_ID} 的描述太长了，帮我精简到 200 字以内。

✗ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✗ 确认流程 · ✓ 完成
调用次数 2 · 延迟 52.4s · tokens 17851
- ⚠️ 缺失工具：['save_content']，实际调用：['query_store_data', 'query_store_data']
- ⚠️ 期望触发写操作但实际未调用任何写工具
- 📝 Judge: 工具调用错误：首次 query_store_data 尝试使用含变量 $id 的 GraphQL 查询但失败（ok: false），未重试或修正；第二次却退化为查询最新10个商品列表，而非目标商品详情，导致无法读取原描述——违反rubric首条。未精简任何描述，故无法验证字数、卖点保留、save_content提交等后续要求。回复将占位符误判为真实ID，且未主动提取/展示目标商品原始description字段，仅列举无关商品，完全偏离任务目标。

### ❌ [zhipu:glm-5] content-004 · content_generation · judge=2/5
> 给这个商品加 3-5 个相关 tags 帮助店内搜索。商品：gid://shopify/Product/{SAMPLE_PRODUCT_ID}。

✗ 工具选对 · ✗ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✗ 确认流程 · ✓ 完成
调用次数 1 · 延迟 17.9s · tokens 11102
- ⚠️ 缺失工具：['save_content']，实际调用：['query_store_data']
- ⚠️ 期望触发写操作但实际未调用任何写工具
- 📝 Judge: 工具调用失败，但助手未尝试 fallback 查询（如用 handle 或 title 检索），也未从占位符中提取任何可用信息；rubric 要求必须查询 title/productType/existing tags 来生成 tags，而助手完全未获取到任何商品元数据，导致无法执行核心任务；虽礼貌指出问题并请求补充信息，但未体现任何基于已有线索的推理或最小可行响应（如示例 tag 模板），故在 rubric 关键维度上严重缺失。

### ✅ [zhipu:glm-5] content-005 · content_generation · judge=2/5
> 给 T 恤类目的 5 个商品批量写一套统一风格的描述。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 3 · 延迟 32.2s · tokens 24211
- 📝 Judge: 助手未满足 rubric 中的三个核心要求：1) 未查询到 T 恤类目商品（虽尝试了 'T恤' 和 'T-Shirt' 查询，但最终结论是‘没有’，未验证是否因标签/字段不匹配导致漏查，也未 fallback 到更鲁棒的查询如 tags 或 title 包含 'T恤'）；2) 未生成任何商品描述，因此完全缺失‘统一风格和结构’的体现；3) 更无从谈起‘针对每个商品保留差异化卖点’。回复转向替代方案属合理交互，但本质未完成原始任务。

### ✅ [zhipu:glm-5] inv-001 · inventory_ops
> 哪些商品库存已经低于安全线（假设 7 天销量）？

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 2 · 延迟 122.7s · tokens 21587

### ✅ [zhipu:glm-5] inv-002 · inventory_ops
> 需要补货的 SKU 有哪些？建议补多少？

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 3 · 延迟 93.3s · tokens 27831

### ✅ [zhipu:glm-5] inv-003 · inventory_ops · judge=5/5
> 库存里有哪些积压 30 天以上没卖动的商品？

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 2 · 延迟 45.1s · tokens 17998
- 📝 Judge: 助手准确结合库存（total_inventory > 0）与近30天订单数据（created_at >= 2026-03-20, paid）识别零销售积压商品，满足‘结合库存+订单识别长期积压’；明确给出下架/促销建议（如‘促销清仓或下架’‘打折测试’），满足第二条；通过‘⚠️ 积压严重/明显’及不同折扣力度、处置优先级区分严重程度，并隐含品类一致性（均为 snowboard），满足第三条。回复结构清晰、可操作性强，无冗余或遗漏。

### ✅ [zhipu:glm-5] inv-004 · inventory_ops · judge=3/5
> 把 The Minimal Snowboard 的库存增加 5 件。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 2 · 延迟 45.3s · tokens 17741
- 📝 Judge: 助手正确调用了 query_store_data 查商品及 variant/inventoryItem，也调用了 update_inventory（delta=+5），符合前两条 rubric。但最终回复中已执行了库存更新（工具调用记录显示 update_inventory 成功），却仍以「确认」形式呈现，违反 rubric 第三条‘没直接执行，需用户确认’——即应仅生成 preview 并阻断执行，而非先调用 update_inventory 再让用户确认。这是关键流程错误。

### ✅ [zhipu:glm-5] inv-005 · inventory_ops · judge=2/5
> 仓库 A 和仓库 B 的库存差异在哪些商品上最大？

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 3 · 延迟 34.6s · tokens 20711
- 📝 Judge: 助手未正确选择工具：rubric 明确要求查询 inventoryLevels 并按 location 分组、计算两仓库差值并排序，但所有调用均未涉及 inventoryLevels 字段或 location-level inventory 查询；第二次调用甚至失败，且未重试或构造含 locations + inventoryLevels 的合法 GraphQL 查询；最终回复错误断定‘只有一个仓库’，而用户问题预设了仓库 A/B 存在，说明工具调用未能获取真实位置库存数据；虽回复结构清晰且提供了备选分析路径（JIT instruction followed），但核心任务（识别差异最大商品及调拨建议）完全未执行。

### ✅ [zhipu:glm-5] mix-001 · mixed_intent · judge=2/5
> 上周销量下滑的商品有哪些？给这些商品各写一个促销文案。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 4 · 延迟 98.7s · tokens 45951
- 📝 Judge: 助手未按 rubric 要求先调用 query_store_data 分析‘上周销量下滑’——工具调用中无任何环比/同比销量对比逻辑，也未过滤出‘下滑商品’；反而直接假设了5个‘库存积压商品’并生成文案，完全偏离用户意图。未切换到‘内容创作者’模式的明确 JIT 指令（如声明角色或风格约束），且文案中混入虚构库存数（如‘85件库存’）和不存在的商品名（如‘The Multi-location Snowboard’），说明未基于真实查询结果生成。最终输出缺失‘下滑商品列表’这一关键分析部分，仅呈现虚构文案，两部分结构不成立。

### ❌ [zhipu:glm-5] mix-002 · mixed_intent · judge=3/5
> 库存过剩 30 天的商品，帮我创建一个 5 折促销活动。

✗ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✗ 确认流程 · ✓ 完成
调用次数 2 · 延迟 44.6s · tokens 20756
- ⚠️ 缺失工具：['create_promotion']，实际调用：['query_store_data', 'query_store_data']
- ⚠️ 期望触发写操作但实际未调用任何写工具
- 📝 Judge: 助手正确调用了 query_store_data 工具两次以识别库存积压商品，满足‘先查库存+订单数据’要求；但未切换到‘促销设计’模式（回复中无任何促销策略分析、目标设定或活动结构说明）；未调用 create_promotion 工具，仅停留在询问确认阶段，未触发确认流程；虽在文案中提及‘5 折’，但未将 percentage_off=50 实际传入工具调用，违反 rubric 第四条。因此 JIT 指令未被遵循，关键动作缺失。

### ❌ [zhipu:glm-5] mix-003 · mixed_intent · judge=2/5
> 哪些客户最近 30 天没下单但之前花费超过 100 美元？给他们发个召回折扣。

✗ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✗ 确认流程 · ✓ 完成
调用次数 4 · 延迟 62.0s · tokens 41655
- ⚠️ 缺失工具：['create_promotion']，实际调用：['query_store_data', 'query_store_data', 'query_store_data', 'query_store_data']
- ⚠️ 期望触发写操作但实际未调用任何写工具
- 📝 Judge: 工具调用未正确识别流失客户：未执行「先查客户 + 订单数据识别最近30天没下单但历史花费>100美元」的核心逻辑。第一次查询因语法错误失败，后续查询虽获取了部分订单和客户数据，但未做客户ID集合差集（如：所有amountSpent > 100的客户 - 最近30天下单客户），导致错误断言‘无流失客户’；折扣码设计完全缺失（rubric要求体现‘召回’用途）；PII呈现不合理——直接提及‘3个客户（消费金额$0）’隐含可推断个体，且未脱敏/聚合；未生成任何折扣码或召回策略，违反核心意图。

### ✅ [zhipu:glm-5] mix-004 · mixed_intent · judge=5/5
> 低库存商品里选 3 个，把它们的 SEO 描述改得更吸引人，并且加一个补货提醒的 tag。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 5 · 延迟 63.1s · tokens 28214
- 📝 Judge: 助手正确识别低库存商品（通过 inventory 排序查询），为每个商品调用 save_content；所有 SEO 描述均 ≤ 160 字符（最长句 152 字）；每个商品均新增「补货提醒」tag（含保留原 tag 的情况）；每次写操作均提供清晰 preview（原/新描述与标签对比）并要求用户确认，完全满足 rubric 所有维度。

### ✅ [zhipu:glm-5] mix-005 · mixed_intent · judge=5/5
> 帮我看看 T 恤类目这周的销售表现，如果销量低于 10 件就启动 8 折促销。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 4 · 延迟 43.2s · tokens 24994
- 📝 Judge: 助手准确识别了用户意图是分析T恤类目本周销量并条件触发促销；通过多次query_store_data调用（含product_type/tag/title多维度匹配）确认无T恤商品，从而得出销量为0的结论；明确指出销量<10且因无商品而无法创建促销，符合'条件触发'逻辑；未误触发create_promotion，也未在销量≥10时错误执行动作；所有判断均基于数据事实，响应清晰闭环。
