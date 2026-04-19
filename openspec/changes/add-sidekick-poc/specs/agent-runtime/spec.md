## ADDED Requirements

### Requirement: 单 Agent 运行时与多模型路由

系统 SHALL 提供一个用 PydanticAI 构建的单 Agent 运行时，每轮对话通过统一入口调用。运行时 MUST NOT 把 Agent 实现绑定到具体模型供应商；模型选择 SHALL 在请求时通过 LiteLLM 路由配置解析。

#### Scenario: 使用默认模型调用 Agent

- **WHEN** 对话请求分发到运行时且未显式指定模型
- **THEN** 运行时 SHALL 从 YAML 路由配置解析默认模型（例如 analysis 任务类型用 Claude Sonnet）
- **AND** Agent 定义 SHALL 在实例化时不硬编码模型名

#### Scenario: 通过配置切换模型

- **WHEN** YAML 路由配置中 analysis 任务类型的首选模型从 Claude Sonnet 改为 GPT-4o
- **THEN** 下一次 analysis 类型的对话请求 SHALL 路由到 GPT-4o
- **AND** 不需要任何代码改动

#### Scenario: 模型故障时自动 fallback

- **WHEN** 首选模型 API 返回 5xx 错误或超时
- **THEN** LiteLLM SHALL 自动切到配置的备用模型
- **AND** fallback 事件 SHALL 写入 Langfuse 追踪并附带失败原因

### Requirement: 通过工具返回值注入 JIT 指令

系统 SHALL 支持 JIT（Just-in-Time）指令注入：MCP 工具在返回数据时同时返回场景指令字符串。系统提示词 MUST 保持稳定（以保留 prompt cache 命中），场景相关指引 MUST 仅通过工具返回值传递。

#### Scenario: 销售查询附带分析师 JIT 指令

- **WHEN** `query_store_data` 工具针对销售类查询返回数据
- **THEN** 工具返回值 SHALL 包含 `jit_instruction` 字段，内容为分析师模式指引（例如"对比周环比，标注涨跌超 10% 的商品"）
- **AND** Agent 在后续生成中 SHALL 把该指令纳入推理上下文

#### Scenario: 商品详情查询附带内容创作者 JIT 指令

- **WHEN** `query_store_data` 工具返回商品详情数据
- **THEN** 返回值 SHALL 包含内容创作者指引的 `jit_instruction`（例如"SEO 描述控制 160 字符"）
- **AND** Agent 下一段输出 SHALL 满足 160 字符限制

#### Scenario: 跨轮次系统提示词保持稳定

- **WHEN** 多轮对话依次触发不同工具
- **THEN** 系统提示词 SHALL 在所有轮次保持字节级一致（用 SHA-256 校验提示词前缀）
- **AND** Langfuse 追踪记录的 prompt cache 指标 SHALL 显示重复前缀的命中

### Requirement: 带迭代上限的 Agentic Loop

运行时 SHALL 执行 Agentic Loop（LLM → 工具调用 → 工具结果 → LLM → ...）直到 Agent 标记完成或达到最大迭代次数。最大迭代次数 MUST 可配置，默认值为 10。

#### Scenario: 在上限内正常完成

- **WHEN** Agent 在 3 次工具调用后自然产出最终响应
- **THEN** Loop SHALL 终止并返回最终响应
- **AND** 迭代次数（4：3 次工具 + 1 次最终生成）SHALL 写入追踪记录

#### Scenario: 触发上限时强制终止

- **WHEN** Agent 在同一轮请求第 11 次工具调用
- **THEN** Loop SHALL 以 "max iterations exceeded" 错误终止
- **AND** 部分响应 SHALL 返回给用户并附带 incomplete 标志

### Requirement: 通过 PydanticAI 进行结构化输出验证

所有用于程序化用途的 Agent 输出（分析报告、生成内容、工具参数等）SHALL 用 PydanticAI 输出 schema 进行验证。验证失败 MUST 触发自动重试（最多 3 次）后才向上抛错。

#### Scenario: 输出符合 schema

- **WHEN** Agent 返回符合 `SalesReport` schema 的输出
- **THEN** 运行时 SHALL 返回解析后的 Pydantic 模型给调用方

#### Scenario: 输出无效时自动重试

- **WHEN** Agent 首次输出未通过 Pydantic 校验
- **THEN** 运行时 SHALL 自动重试，并在提示词中追加错误信息（例如 "Previous output failed validation: <error>"）
- **AND** SHALL 在累计 3 次内成功或失败

### Requirement: 通过 Celery 执行长任务

运行时 SHALL 把预计耗时超过 30 秒的长任务（例如批量内容生成）通过 Redis broker 转发到 Celery worker 执行。Celery worker MUST 与同步调用共享同一份 Agent 代码与配置。

#### Scenario: 短任务同步执行

- **WHEN** 对话请求预计在 30 秒内完成（例如简单数据查询）
- **THEN** 运行时 SHALL 在 FastAPI 请求处理中同步执行

#### Scenario: 长任务派发到 Celery

- **WHEN** 对话请求被标记为 batch-generation 或预计超过 30 秒
- **THEN** 运行时 SHALL 入队 Celery 任务并立即向客户端返回任务 ID
- **AND** 客户端 SHALL 能通过另一个端点轮询任务状态
