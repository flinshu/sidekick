## ADDED Requirements

### Requirement: 流式对话 Web 界面

系统 SHALL 提供基于 Next.js 15（App Router）+ Vercel AI SDK 的 Web 对话界面。响应 MUST 通过 Server-Sent Events（SSE）增量流式返回，UI SHALL 在 token 到达时即时渲染。

#### Scenario: 用户消息触发流式响应

- **WHEN** 用户通过对话输入框提交消息
- **THEN** UI SHALL 立刻显示用户消息
- **AND** SHALL 打开到 `/api/chat` 端点的 SSE 连接
- **AND** SHALL 在 token 流到达时增量渲染助手回复

#### Scenario: SSE 连接在长 Agent loop 下不被中断

- **WHEN** Agent 在单轮内执行 5 次以上工具调用（总耗时 60 秒以上）
- **THEN** SSE 连接 SHALL 持续到 Agent 完成
- **AND** 任何代理/网关超时 SHALL NOT 提前断开（通过 keepalive 设置或定期注释帧验证）

### Requirement: 工具调用在对话中可见

对话 UI SHALL 把工具调用作为可见的独立 UI 元素渲染在消息流中。每个工具调用 MUST 展示：工具名、参数（可折叠）、执行状态（运行中 → 完成 → 失败）。

#### Scenario: 工具调用以行内 UI 块渲染

- **WHEN** Agent 调用 `query_store_data`
- **THEN** UI SHALL 渲染一个行内 "Tool: query_store_data" 块，含旋转图标和查询参数
- **AND** 完成后 SHALL 显示摘要（例如 "返回 12 个商品"）并可展开查看完整 payload

### Requirement: 写操作的 Human-in-the-loop 确认卡片

对话 UI SHALL 为每个返回 `requires_confirmation: true` 的工具调用渲染行内确认卡片。卡片 MUST 包含：操作标题、变更摘要（人类可读）、影响预览、确认/取消两个按钮。

#### Scenario: 写操作触发确认卡片

- **WHEN** Agent 调用 `update_price` 且工具返回 preview payload
- **THEN** UI SHALL 在对话中行内渲染卡片，显示"调整 X 商品价格：¥99 → ¥79"和确认/取消按钮
- **AND** Agent SHALL 暂停执行（SSE 流在该工具调用状态上 pause）

#### Scenario: 用户确认操作

- **WHEN** 用户点击"确认"
- **THEN** 前端 SHALL 把确认信号和原始工具参数回传后端
- **AND** Agent SHALL 恢复执行并真正调用 Shopify mutation
- **AND** 卡片 SHALL 更新为成功/失败状态

#### Scenario: 用户取消操作

- **WHEN** 用户点击"取消"
- **THEN** 前端 SHALL 向后端发送取消信号
- **AND** Agent SHALL 以"操作被用户取消"作为工具结果继续
- **AND** SHALL NOT 调用任何 Shopify API

### Requirement: 租户切换器 UI

对话 UI SHALL 提供可见的租户（Shopify 店铺）切换器，允许在已配置的 dev store 之间切换。当前激活租户 MUST 在 UI 顶栏明确显示。

#### Scenario: 用户在会话中切换租户

- **WHEN** 用户从切换器选择不同的店铺
- **THEN** 当前会话 SHALL 保留（不丢失），但后续请求 SHALL 携带新租户上下文
- **AND** UI SHALL 在视觉上标识激活租户已变更（例如店铺域名 badge）

### Requirement: 会话持久化

对话 UI SHALL 通过后端把会话历史持久化到 Postgres，按租户隔离。页面刷新后 SHALL 恢复当前租户最近一次会话。

#### Scenario: 会话在页面刷新后保留

- **WHEN** 用户发送 3 条消息后刷新页面再回到对话页
- **THEN** UI SHALL 按原顺序显示这 3 条消息及其助手响应

### Requirement: 错误显式呈现

对话 UI SHALL 把错误（Agent 失败、工具失败、Shopify API 错误）作为可见的 UI 元素渲染在对话中，MUST NOT 使用静默失败或浏览器 alert。

#### Scenario: Shopify API 错误被显式展示

- **WHEN** Shopify API 调用失败（例如 429 限流或 500）
- **THEN** UI SHALL 在对话流中渲染 error banner 并显示错误原因
- **AND** 对可重试错误 SHALL 提供 retry 按钮
