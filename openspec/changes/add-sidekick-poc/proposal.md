## Why

《电商智能助手技术选型方案 v4》提出了类 Shopify Sidekick 的完整架构（单 Agent + JIT 指令 + 多模型路由 + GraphQL/REST 工具 + 多租户 + 评估体系），但其中多个关键假设没有实证数据——最大的是"通用模型（未做 GRPO 微调）能否稳定执行 JIT 指令"。在投入生产级建设之前，需要一个 POC 以最小成本回答"这套技术选型是否成立"。

本次变更交付一个单人可运行的 POC 项目骨架，用 Shopify dev store 作为真实数据源，分三个 milestone 逐步验证核心假设。不做 K8s / 生产级基础设施。

## What Changes

- 在 `/Users/phper/Code2/saas-ai2/sidekick/` 初始化 monorepo 项目骨架（`apps/{web,api,worker}` + `packages/{agent,tools,evals}`）
- 引入双栈：Python 3.11+（FastAPI + PydanticAI + LiteLLM + Celery）+ Node 20 / TypeScript（Next.js 15 + Vercel AI SDK）
- M1 交付：CLI 可执行的单 Agent + JIT 指令 + 6 个 Shopify 工具 + 20 条测试用例 × 3 模型对比报告
- M2 交付：Next.js 对话 Web 端 + SSE 流式 + Human-in-the-loop 写操作确认 UI + 多租户（2-3 个 Shopify dev store）+ LiteLLM 多模型路由 + Celery 异步 + Redis 语义缓存骨架 + Langfuse 追踪
- M3 交付：CI 自动化 RAGAS + DeepEval + LLM-as-Judge；语义缓存命中率实测数据；用户模拟回归；最终可行性报告
- 用 Docker Compose 管理本地服务（Postgres、Redis、Qdrant、Langfuse）
- 基准对照：同组测试问题在 Shopify Sidekick 本身跑一遍做 benchmark
- 每个 milestone 结束设 go/no-go checkpoint：M1 不通过则停下来重评方案 A

## Capabilities

### New Capabilities

- `agent-runtime`: 单 Agent 核心运行时——PydanticAI 定义、LiteLLM 多模型路由、JIT 指令注入机制、Agentic Loop 控制
- `shopify-tools`: Shopify Admin API 工具集——1 个 GraphQL 读工具（query_store_data）+ 5 个 REST/GraphQL 写工具（价格/库存/描述/促销/折扣）+ Schema 子集注入策略
- `chat-interface`: Web 对话界面——Next.js 15 App Router + Vercel AI SDK + SSE 流式 + Human-in-the-loop 写操作确认卡片
- `tenant-context`: 多租户上下文——按 shop domain 切换 Shopify store token + 请求级隔离（demo 支持 2-3 个 dev store）
- `response-cache`: 语义缓存层——Redis 存储 + embedding 相似度匹配 + 命中率指标采集
- `evaluation-suite`: 评估与可观测性——RAGAS 检索质量 + DeepEval 安全护栏 + LLM-as-Judge + Langfuse 追踪 + 用户模拟回归

### Modified Capabilities

无（当前 `openspec/specs/` 为空，这是项目首次引入能力）。

## Impact

- **新仓库结构**：当前工作目录非 git 仓库，需 `git init`。Monorepo 一次性创建多目录（apps/web、apps/api、apps/worker、packages/agent、packages/tools、packages/evals、infra、tests/cases、docs）
- **外部依赖**：需要 Shopify Partners 账号 + dev store（用户已有）、Custom App 的 Admin API access token、至少一个模型 API key（Anthropic/OpenAI/阿里百炼）
- **本地运行环境**：依赖 Docker Desktop 跑 Postgres/Redis/Qdrant/Langfuse；Python 3.11+（uv 管理）；Node 20 LTS（pnpm 管理）
- **成本**：M1 阶段模型 API 调用 ~$50；完整 POC 跑下来 ~$200-500（多模型对比 + 自动化评估跑多次）
- **显式不做**：K8s、Helm、ArgoCD、Terraform、生产级安全（OAuth、审计日志、加密密钥管理）、Mem0 长期记忆（留给后续）
- **决策门**：每个 milestone Done 时产出报告供决策。M1 失败（JIT 遵循率 < 70% 或工具选择准确率 < 85%）将触发方案重评，可能改为方案 B（多 Agent）或考虑引入微调
