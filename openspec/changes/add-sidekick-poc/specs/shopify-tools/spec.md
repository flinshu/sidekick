## ADDED Requirements

### Requirement: 统一的 GraphQL 读工具（query_store_data）

系统 SHALL 暴露一个名为 `query_store_data` 的 MCP 工具，接收 GraphQL 查询字符串和变量，对 Shopify Admin GraphQL API 执行后返回结果，并附带场景对应的 JIT 指令。

#### Scenario: 销售查询返回带分析师 JIT 指令

- **WHEN** Agent 用查询 `orders { edges { node { totalPrice createdAt } } }` 调用 `query_store_data`
- **THEN** 工具 SHALL 对 `/admin/api/2025-04/graphql.json` 执行查询并返回结果
- **AND** 返回值 SHALL 包含分析师模式指引的 `jit_instruction` 字段

#### Scenario: 商品查询返回带内容创作者 JIT 指令

- **WHEN** Agent 用查询 `products { edges { node { title descriptionHtml } } }` 调用 `query_store_data`
- **THEN** 工具 SHALL 返回商品数据
- **AND** 返回值 SHALL 包含内容创作者指引的 `jit_instruction` 字段

#### Scenario: GraphQL 语法错误被本地拦截

- **WHEN** Agent 提供语法错误的查询
- **THEN** 工具 SHALL 返回错误对象并附带解析错误信息
- **AND** SHALL NOT 调用 Shopify API

### Requirement: 注入 curated GraphQL Schema 子集

系统 SHALL 在启动时把人工筛选的 Shopify Admin GraphQL schema 子集注入 Agent 的系统提示词。该子集 MUST 至少覆盖以下类型：`Product`、`ProductVariant`、`Order`、`LineItem`、`Customer`、`InventoryLevel`、`InventoryItem`、`Collection`、`PriceRule`、`DiscountCode`。

#### Scenario: 启动时加载 schema 子集

- **WHEN** Agent 运行时启动
- **THEN** curated schema 子集 SHALL 从已检入的文件读取（例如 `packages/tools/shopify_schema_subset.graphql`）
- **AND** SHALL 嵌入到系统提示词中

#### Scenario: schema 子集大小受控

- **WHEN** curated 子集被加载
- **THEN** 其总 token 数（用当前模型的 tokenizer 计算）SHALL NOT 超过 15,000
- **AND** 超出时构建 SHALL 失败并给出明确错误，便于裁剪

### Requirement: 5 个 Shopify 写操作工具

系统 SHALL 暴露 5 个写工具，每个封装具体的 Shopify mutation 或 REST 接口。每个写工具 MUST 返回 `requires_confirmation: true` 标志，让 Agent 在真正调用 Shopify 之前先走 Human-in-the-loop 流程。

5 个工具：
- `update_price` — 更新商品 variant 价格（GraphQL: `productVariantUpdate`）
- `update_inventory` — 调整库存数量（GraphQL: `inventoryAdjustQuantities`）
- `save_content` — 更新商品描述/SEO（GraphQL: `productUpdate`）
- `create_promotion` — 创建价格规则 + 折扣码（GraphQL: `priceRuleCreate` + `discountCodeCreate`）
- `create_automation` — 创建草稿态 Shopify Flow（REST: Flow API，可选；M1 可 stub）

#### Scenario: 写工具先返回确认 payload 不直接执行

- **WHEN** Agent 用 variant ID 和新价格调用 `update_price`
- **THEN** 工具 SHALL 返回结构化 preview，包括当前价格、新价格、variant 名称、`requires_confirmation: true`
- **AND** SHALL NOT 在第一次调用时打 Shopify API

#### Scenario: 用户确认后真正执行写操作

- **WHEN** Human-in-the-loop 流程返回用户确认及原始工具参数
- **THEN** 工具 SHALL 执行 Shopify mutation/REST 调用
- **AND** SHALL 返回 Shopify API 响应（包含 variant 新状态）

#### Scenario: 用户拒绝则中止写操作

- **WHEN** 用户拒绝确认
- **THEN** SHALL NOT 调用任何 Shopify API
- **AND** 对话 SHALL 继续，并告知用户操作已取消

### Requirement: 通过 Custom App Token 访问 Shopify API

系统 SHALL 用每个租户（每个 Shopify dev store）独立的 Custom App Admin API access token 进行鉴权。Token MUST NOT 硬编码在源码中；SHALL 通过环境变量或租户配置注入。

#### Scenario: 单租户开发时从环境变量读 token

- **WHEN** POC 以单 dev store 运行，通过 `SHOPIFY_SHOP_DOMAIN` 和 `SHOPIFY_ADMIN_TOKEN` 环境变量配置
- **THEN** 所有 Shopify API 调用 SHALL 使用该 token

#### Scenario: 按租户上下文选择 token

- **WHEN** 多租户配置中 `shop-alpha.myshopify.com` 映射到 token A，`shop-beta.myshopify.com` 映射到 token B
- **AND** 请求带租户上下文 `shop-alpha.myshopify.com`
- **THEN** 该请求的 Shopify API 调用 SHALL 使用 token A

### Requirement: 遵守 Shopify API rate limit

系统 SHALL 在每次响应中读取 Shopify 的 leaky bucket 状态（REST 用 `X-Shopify-Shop-Api-Call-Limit` 头，GraphQL 用 `extensions.cost` 字段）。当可用余量低于 10% 时，MUST 在下次调用前引入延迟。

#### Scenario: 接近上限时退避

- **WHEN** GraphQL 响应显示 `cost.throttleStatus.currentlyAvailable < 100`（总额度 1000）
- **THEN** 下一次 Shopify API 调用 SHALL 延迟到 bucket 恢复
- **AND** 延迟时长 SHALL 写入日志
