## ADDED Requirements

### Requirement: Agent 响应的语义缓存层

系统 SHALL 实现语义缓存层：在调用 Agent 之前，先检查同租户范围内是否存在语义相似的历史问题及其响应。命中则 SHALL 直接返回缓存响应。

#### Scenario: 完全匹配命中

- **WHEN** 某租户曾问过"上周销量"并得到响应
- **AND** 该租户再次问"上周销量"
- **THEN** 缓存 SHALL 返回历史响应
- **AND** SHALL NOT 触发任何 LLM 调用
- **AND** 命中事件 SHALL 作为指标记录

#### Scenario: 高于阈值的语义相似命中

- **WHEN** 某租户曾问"上周销量"并得到响应
- **AND** 该租户再问"上个星期的销售情况"
- **AND** 两个问题 embedding 的余弦相似度 ≥ 0.95
- **THEN** 缓存 SHALL 返回原响应

#### Scenario: 相似度低于阈值时未命中

- **WHEN** 某租户曾问"上周销量"
- **AND** 再问"这个月的退货率"
- **AND** 相似度 < 0.95
- **THEN** 缓存 SHALL 返回 miss
- **AND** Agent SHALL 正常被调用

### Requirement: 本地 Embedding 模型

缓存键的 embedding SHALL 由本地 sentence-transformer 模型生成（不允许调外部 API）。具体模型 MUST 可配置；默认 SHALL 使用支持中英双语的多语言模型。

#### Scenario: Embedding 在本地生成

- **WHEN** 处理一个新的用户问题
- **THEN** 其 embedding SHALL 在本地用配置的模型计算
- **AND** SHALL NOT 调用任何外部 embedding API（例如 OpenAI embeddings）

### Requirement: 按租户分 namespace 的缓存

缓存条目 MUST 按租户 namespace 隔离。查询 SHALL 只考虑当前租户上下文的条目。

#### Scenario: 阻止跨租户命中

- **WHEN** 租户 A 缓存了问题 Q 的响应 R
- **AND** 租户 B 提问同样的 Q
- **THEN** 租户 B SHALL 经历 cache miss
- **AND** SHALL 收到由 Agent 新生成的响应

### Requirement: 缓存命中率指标

系统 SHALL 记录每租户和聚合的缓存命中率指标。指标 SHALL 包括：总查询数、命中数、未命中数、滚动 1 小时和 24 小时窗口的命中率百分比。

#### Scenario: 命中率通过指标端点暴露

- **WHEN** 操作员查询 `/api/metrics/cache`
- **THEN** 端点 SHALL 返回 JSON，包含 `total_queries`、`hits`、`misses`、`hit_rate_1h`、`hit_rate_24h`

### Requirement: 写操作触发缓存失效

当某租户通过 Shopify 工具成功执行写操作（例如 `update_price`、`save_content`）后，该租户的缓存 SHALL 使语义相关的条目失效，避免提供陈旧数据。

#### Scenario: 价格更新失效与价格相关的缓存

- **WHEN** 租户 A 成功调用 `update_price`
- **THEN** 租户 A 中包含"价格"/"price"/"售价"等 token 的缓存条目 SHALL 失效
- **AND** 失效动作 SHALL 写入日志

### Requirement: 缓存条目 TTL

每个缓存条目 SHALL 有 TTL。默认 TTL：分析类响应 24 小时，含动态数据（库存、订单状态）的响应 1 小时。TTL MUST 可配置。

#### Scenario: 过期条目不被服务

- **WHEN** 某缓存条目创建于 25 小时前，TTL 为 24 小时
- **AND** 有查询匹配该条目
- **THEN** 缓存 SHALL 返回 miss 并淘汰该过期条目
