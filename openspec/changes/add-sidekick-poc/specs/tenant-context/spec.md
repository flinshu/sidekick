## ADDED Requirements

### Requirement: 请求级租户上下文

后端处理对话请求时 SHALL 携带显式的租户上下文，标识请求所属的 Shopify 店铺。租户上下文 MUST 可解析为：店铺 domain、Shopify Admin API token、租户级配置（locale、模型偏好等）。

#### Scenario: 从请求头提取租户上下文

- **WHEN** 对话请求携带头 `X-Shop-Domain: shop-alpha.myshopify.com`
- **THEN** 后端 SHALL 在请求生命周期内构造租户上下文对象
- **AND** 所有下游调用（Agent 运行时、工具、缓存查询）SHALL 能访问该上下文

#### Scenario: 缺失租户上下文时拒绝请求

- **WHEN** 对话请求未带租户头或带了未注册的 shop domain
- **THEN** 后端 SHALL 返回 400 并附带清晰错误信息
- **AND** SHALL NOT 调用 Agent

### Requirement: 租户配置注册表

系统 SHALL 维护一份租户配置注册表，映射 shop domain → token + 可选覆盖项。POC 阶段，注册表 MAY 为已检入的 YAML 文件或基于 `.env`，MUST NOT 依赖生产级密钥管理。

#### Scenario: 启动时加载注册表

- **WHEN** 后端启动
- **THEN** 租户注册表 SHALL 从 `config/tenants.yaml`（或等价配置）加载
- **AND** 可用租户列表 SHALL 通过 `/api/tenants` 端点暴露给 UI 切换器

#### Scenario: 注册表支持 2-3 个 dev store

- **WHEN** POC 配置列出 3 个 dev store
- **THEN** 每个 SHALL 有独立的 token 并可通过切换器访问

### Requirement: 数据层的租户隔离

所有租户范围的数据（会话、缓存条目、评估记录、Agent 状态 checkpoint）SHALL 包含 `tenant_id` 字段或命名空间。读取这些数据的查询 MUST 始终按当前租户上下文过滤。跨租户数据泄漏视为严重缺陷。

#### Scenario: 会话历史按租户过滤

- **WHEN** UI 请求租户 A 的会话列表
- **THEN** 后端 SHALL 只返回 `tenant_id = A` 的会话
- **AND** SHALL NOT 返回租户 B 的会话，即使两者有相同的用户标识

#### Scenario: 语义缓存按租户分 namespace

- **WHEN** 租户 A 和租户 B 问同一个问题"上周销量"
- **THEN** 语义缓存 SHALL 把两者视为独立条目（按 `tenant_id` 分 namespace）
- **AND** 租户 A 的缓存命中 SHALL NOT 服务租户 B 的请求

### Requirement: 跨租户访问尝试的日志

任何尝试访问当前租户以外数据的行为（例如通过篡改 API 参数）SHALL 作为安全事件记录并被拒绝。

#### Scenario: 篡改租户 ID 被拒绝

- **WHEN** 请求携带 `X-Shop-Domain: shop-alpha.myshopify.com` 但请求的 `conv-123` 实际属于 `shop-beta.myshopify.com`
- **THEN** 后端 SHALL 返回 403 Forbidden
- **AND** SHALL 记录该事件并附带声明的租户与资源实际所属的租户
