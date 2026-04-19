# M1 可行性评估报告 · 20260419_001202

**耗时**：631.9s · **用例数**：15 × **模型数**：1

## 关键指标对比

| 模型 | hard_pass | 工具选对 | JIT 命中 | GraphQL 语法 | 确认流程 | 完成率 | avg 延迟 | avg tokens |
|------|-----------|---------|---------|-------------|---------|--------|---------|-----------|
| dashscope:qwen-plus | 87% | 87% | 87% | 93% | 87% | 93% | 37.7s | 37655 |

## LLM-as-Judge（1-5 分）

| 模型 | 样本数 | 综合均分 | 工具选对率 | JIT 遵循率 |
|------|--------|---------|-----------|----------|
| dashscope:qwen-plus | 14 | 3.50 | 79% | 64% |

## M1 Go/No-Go 决策门

方案 A 的 M1 通过标准（任一模型达到）：
- JIT 指令遵循率 ≥ 80%（rubric 的 jit_category_hit 或 judge 的 jit_instruction_followed_rate）
- 工具选择准确率 ≥ 85%
- GraphQL 语法正确率 ≥ 90%

- **dashscope:qwen-plus**: JIT ✅ · 工具 ✅ · GraphQL ✅

## 按类别细分

- **content_generation**（5次）：hard_pass=100%
- **inventory_ops**（5次）：hard_pass=80%
- **mixed_intent**（5次）：hard_pass=80%

## 逐条结果

### ✅ [dashscope:qwen-plus] content-001 · content_generation · judge=4/5
> 帮商品 ID gid://shopify/Product/{SAMPLE_PRODUCT_ID} 写一份新的商品描述，突出环保材质。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 4 · 延迟 28.0s · tokens 29747
- 📝 Judge: 助手正确调用了 query_store_data 查询目标商品信息（第三次调用含正确 product ID），满足'先查询现有信息'要求；新描述明确包含'FSC认证的竹木复合材料''30%再生聚丙烯''回收海洋塑料边缘'等环保材质关键词；调用 save_content 前提供了完整 preview（含 SEO 描述、标题、描述摘要等）；SEO 描述为159字符（经计数：'采用再生聚丙烯基底+竹木复合板芯的环保滑雪板，轻量耐用，减少碳足迹，专业级性能与可持续理念完美结合。'共159 UTF-8 字符），符合 ≤160 字符要求。唯一小瑕疵是 preview 中未显式展示完整 HTML 描述正文，但 rubric 未强制要求，故不扣分。

### ✅ [dashscope:qwen-plus] content-002 · content_generation · judge=4/5
> 给全店的春季新品写 SEO 标题和描述，控制在标准长度内。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 2 · 延迟 22.5s · tokens 17151
- 📝 Judge: 助手正确调用 query_store_data 工具两次：首次按 query 过滤春季新品（使用 tags/productType 相关关键词隐含逻辑），第二次拉取集合以辅助判断新品归类情况，符合 rubric 中‘是否查询春季新品’要求；SEO 标题与描述虽未生成，但因数据缺失而主动拒绝生成、并明确说明原因，严格遵循了‘控制在标准长度内’的前提条件（即不生成即不违规）；所有建议均围绕‘春季’主题展开（如提示 spring2026、new-arrival-april 等具体春季标识），避免空泛形容；唯一扣分点是未在回复中显式声明 title ≤ 70 / description ≤ 160 的约束已被遵守（虽行为合规，但缺乏显性确认）。

### ✅ [dashscope:qwen-plus] content-003 · content_generation · judge=3/5
> 商品 gid://shopify/Product/{SAMPLE_PRODUCT_ID} 的描述太长了，帮我精简到 200 字以内。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 4 · 延迟 27.7s · tokens 29607
- 📝 Judge: 助手成功调用 query_store_data 获取了商品描述（第三次调用），并调用了 save_content 提交新描述，满足'读取原描述'和'通过 save_content 提交并要求确认'；但新描述 HTML 字符数经测算为 326 字符（含标签），远超 200 字限制；且未在回复中说明精简逻辑或验证字数，违反'精简后 ≤ 200 字'核心要求；同时原描述实际非空（工具返回了 descriptionHtml），但回复中错误标注'原描述：空'，表明未正确解析/呈现原始内容，影响'保留核心卖点'的可验证性。

### ✅ [dashscope:qwen-plus] content-004 · content_generation · judge=5/5
> 给这个商品加 3-5 个相关 tags 帮助店内搜索。商品：gid://shopify/Product/{SAMPLE_PRODUCT_ID}。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 4 · 延迟 19.8s · tokens 29834
- 📝 Judge: 助手正确调用了 query_store_data 获取目标商品的 title、productType 和现有 tags（通过第三个成功调用），确认了当前标签为 ['Accessory', 'Sport', 'Winter']；建议的 3 个新 tag ['snowboard', 'all-mountain', 'freeride'] 语义高度相关（契合 snowboard 类目与使用场景），数量合规（3 个，落在 3–5 范围内），且全部避开了现有 tags；最终回复清晰呈现对比与影响，完全满足 rubric 所有维度。

### ✅ [dashscope:qwen-plus] content-005 · content_generation · judge=3/5
> 给 T 恤类目的 5 个商品批量写一套统一风格的描述。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 2 · 延迟 21.4s · tokens 16909
- 📝 Judge: 助手正确识别到首次 GraphQL 查询失败（空结果），并依据 rubric 中'是否查询到 T 恤类目下的商品'这一核心要求，主动诊断原因、提出可操作的替代方案（路径 A/B），体现了对任务目标的理解。但 rubric 明确要求'给 5 个商品批量写统一风格描述'，而助手尚未生成任何描述——既未产出风格一致的文案，也未体现差异化卖点提炼，因此在后两个维度（风格一致性、卖点差异化）上完全缺失。当前回复停留在问题排查阶段，未完成内容生成任务。

### ✅ [dashscope:qwen-plus] inv-001 · inventory_ops · judge=4/5
> 哪些商品库存已经低于安全线（假设 7 天销量）？

✓ 工具选对 · ✓ 调用数达标 · ✗ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 2 · 延迟 34.0s · tokens 21160
- ⚠️ JIT 场景未命中期望：['inventory_ops']，实际：['[JIT:analytics_sales] 你现在处于「数据分析师」模式。处理这次返回时请：\n1) 计算关键聚合（环比、', '[JIT:analytics_sales] 你现在处于「数据分析师」模式。处理这次返回时请：\n1) 计算关键聚合（环比、']
- 📝 Judge: 助手正确调用了 query_store_data 获取近7天已支付订单（时间范围 2026-04-11 至 2026-04-18），并基于订单行项计算了各 variant 的7天销量，符合‘结合最近订单速率计算7天销量作为安全线’要求；也检查了库存状态（虽未显式使用 inventoryLevel.available 字段，但实际使用了 inventoryQuantity，该字段在 Shopify GraphQL 中是 inventoryLevel.inventoryQuantity 的等效代理，且上下文明确指向可用库存，可视为满足‘查 available 字段’意图）；但 JIT 指示明确要求‘1-2 行/条’输出条目格式，而助手返回了含表格、emoji、多段分析和建议的长篇响应（远超2行/条），严重违反 JIT 格式约束；因此 jit_instruction_followed = false。

### ✅ [dashscope:qwen-plus] inv-002 · inventory_ops · judge=5/5
> 需要补货的 SKU 有哪些？建议补多少？

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 4 · 延迟 67.0s · tokens 46195
- 📝 Judge: 助手准确识别了低库存 SKU（按库存可售天数 < 7 天判定），并为每个 SKU 计算了保 14 天的补货量（日均销量 × 14 − 当前可用库存），完全满足 rubric 第一、二条。同时，虽未显式标注'快销/慢销'标签，但通过日均销量（10.4 → 4.2 → 2.1）自然区分了销售速度，并对高销量 SKU（Selling Plans Ski Wax）给出'紧急补货'提示，体现了差异化策略，满足第三条。所有计算逻辑透明、字段引用合理（如用 quantities(name: \"available\").quantity 替代不可用的 location.name），且主动处理权限限制，符合 JIT 指令要求。

### ✅ [dashscope:qwen-plus] inv-003 · inventory_ops · judge=3/5
> 库存里有哪些积压 30 天以上没卖动的商品？

✓ 工具选对 · ✓ 调用数达标 · ✗ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 2 · 延迟 49.5s · tokens 30131
- ⚠️ JIT 场景未命中期望：['inventory_ops']，实际：['[JIT:analytics_sales] 你现在处于「数据分析师」模式。处理这次返回时请：\n1) 计算关键聚合（环比、', '[JIT:content_creator] 你现在处于「内容创作者」模式。生成内容请遵循：\n1) SEO 描述控制在 1']
- 📝 Judge: 助手正确结合库存（totalInventory > 0）与销售数据（近30天无销量）识别积压，且通过 createdAt 时间戳严谨验证了'上架超30天'条件，逻辑严密；但未提出任何下架或促销清库存建议（rubric第二条完全缺失）；虽指出'全部今日上架'并提示业务现实，但未按rubric第三条对品类或严重程度分级（所有商品同属snowboard品类，却未按库存量、负库存等维度分层）。结论合理，但行动建议偏离rubric核心要求。

### ❌ [dashscope:qwen-plus] inv-004 · inventory_ops · judge=2/5
> 把 SKU SKU-TSHIRT-RED-M 的库存从 10 件调到 20 件。

✗ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✗ 确认流程 · ✓ 完成
调用次数 5 · 延迟 23.0s · tokens 40414
- ⚠️ 缺失工具：['update_inventory']，实际调用：['query_store_data', 'query_store_data', 'query_store_data', 'query_store_data', 'query_store_data']
- ⚠️ 期望触发写操作但实际未调用任何写工具
- 📝 Judge: 助手未按 rubric 要求先查询 SKU-TSHIRT-RED-M 的 inventoryItem/当前库存（所有 query_store_data 调用均未成功返回该 SKU，且最终回复承认未找到）；未调用 update_inventory 工具；未返回 preview 或要求用户确认调整操作，而是转向质疑 SKU 正确性并请求额外信息。完全违背了‘先查、再预览、后确认’的核心流程。

### ✅ [dashscope:qwen-plus] inv-005 · inventory_ops · judge=2/5
> 仓库 A 和仓库 B 的库存差异在哪些商品上最大？

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 3 · 延迟 33.4s · tokens 23871
- 📝 Judge: 助手未按 rubric 要求执行核心操作：未查询 inventoryLevels 并按 location 分组、未计算两仓库差值并排序、未给出跨仓调拨建议。相反，它因权限限制中断流程，转而向用户索要 Location ID，但 rubric 并未要求此交互；且所有工具调用均失败（ok: false），说明未成功获取任何库存数据。此外，未体现对 active 商品的筛选、差值绝对值计算、Top N 排序等关键分析步骤。

### ✅ [dashscope:qwen-plus] mix-001 · mixed_intent · judge=2/5
> 上周销量下滑的商品有哪些？给这些商品各写一个促销文案。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 5 · 延迟 32.2s · tokens 54410
- 📝 Judge: 助手正确调用了 query_store_data 多次（含上周/前一周对比意图），满足第一项 rubric；但未切换到「内容创作者」模式（无明确 JIT 指令声明或角色切换语句），违反第二项；分析结论错误——工具调用成功（ok: true 的三次订单查询），却声称'前一周没有销售数据'，属推理失实；最终回复未提供任何实际促销文案（仅列出商品名和空泛描述，未生成≤160字符的SEO文案），完全缺失rubric要求的'下滑商品列表 + 每个商品的文案'两部分输出。

### ✅ [dashscope:qwen-plus] mix-002 · mixed_intent · judge=5/5
> 库存过剩 30 天的商品，帮我创建一个 5 折促销活动。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 3 · 延迟 39.1s · tokens 39279
- 📝 Judge: 助手严格遵循 rubric：先调用 query_store_data 两次（分别查订单和商品库存）以识别库存过剩30天的商品；明确进入促销设计语境（回复中体现「操作确认卡」「创建促销活动」等措辞）；调用 create_promotion 工具且 percentage_off=50 正确传入；最终回复包含具体商品列表、时间范围、折扣码及确认流程，完全满足所有评分维度。

### ❌ [dashscope:qwen-plus] mix-003 · mixed_intent
> 哪些客户最近 30 天没下单但之前花费超过 100 美元？给他们发个召回折扣。

✗ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✗ GraphQL 语法 · ✗ 确认流程 · ✗ 完成
调用次数 4 · 延迟 107.9s · tokens 41843
- ⚠️ 缺失工具：['create_promotion']，实际调用：['query_store_data', 'query_store_data', 'query_store_data', 'query_store_data']
- ⚠️ query_store_data 参数不是合法 JSON: {"query": "query($first: Int!, $after: String) { customers(first: $first, after:
- ⚠️ 期望触发写操作但实际未调用任何写工具
- ⚠️ 未完成：error=所有模型都失败，hit_max_iterations=False

### ✅ [dashscope:qwen-plus] mix-004 · mixed_intent · judge=5/5
> 低库存商品里选 3 个，把它们的 SEO 描述改得更吸引人，并且加一个补货提醒的 tag。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 9 · 延迟 43.8s · tokens 121284
- 📝 Judge: 助手正确识别低库存商品（通过多次 query_store_data 调用，最终使用 GetLowStockProducts 等合理查询）；为每个商品调用 save_content 三次，均成功；所有 SEO 描述长度分别为 112/107/107 字符，严格 ≤160；均添加了 'low-stock-alert' 标签（符合「补货提醒」类 tag 要求）；每项更新均提供 preview 式确认（含字符数、标签、商品名），并明确请求用户确认执行。完全满足 rubric 所有维度。

### ✅ [dashscope:qwen-plus] mix-005 · mixed_intent · judge=2/5
> 帮我看看 T 恤类目这周的销售表现，如果销量低于 10 件就启动 8 折促销。

✓ 工具选对 · ✓ 调用数达标 · ✓ JIT 命中 · ✓ GraphQL 语法 · ✓ 确认流程 · ✓ 完成
调用次数 2 · 延迟 16.9s · tokens 22992
- 📝 Judge: 工具调用错误：第一个 query_store_data 查询了 orders，但条件中使用了硬编码时间 '2026-04-12'/'2026-04-19'（明显非本周），且未按 rubric 要求关联 lineItems 过滤 productType=T恤；第二个查询仅查 products，未用于销量聚合。未执行销量统计，因此无法判断是否 <10，更未体现条件触发逻辑（既未说'无需促销'，也未调用 create_promotion）。根本未满足 rubric 中'按 productType=T恤 查询 orders + lineItems'这一核心要求。
