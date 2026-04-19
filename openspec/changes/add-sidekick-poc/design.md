## Context

《电商智能助手技术选型方案 v4》描述了类 Shopify Sidekick 的完整架构，但多个核心假设只有文献/经验依据，缺少针对"未做模型微调 + 通用 API 模型"这一前提的实证数据。Shopify 在 ICML 2025 论文中通过 GRPO 把工具使用准确率从 ~93% 提升到 ~99%——我们不做微调，起点可能就在 93% 甚至更低。

当前状态：
- `/Users/phper/Code2/saas-ai2/sidekick/` 只有方案文档 `电商智能助手技术选型方案_v4.md` 和 `openspec/` 骨架
- 目录非 git 仓库
- 单人开发（用户作为决策者 + Claude Code 执行全部实现）
- 用户已有 Shopify Partners 账号

约束：
- 不碰 K8s / Helm / Terraform（显式排除）
- 不做模型微调
- 不依赖自研平台 API（用 Shopify Admin API 替代）

## Goals / Non-Goals

**Goals:**

- 用最小工程代价证伪或证实方案 A 的 3 个核心假设：H1（JIT 指令 × 通用模型）、H2（单 Agent × 多工具选择）、H4（LLM 生成 GraphQL 准确率）
- 交付一个可在本机跑起来的端到端对话系统（Web UI → Agent → Shopify 真实 API），覆盖 v4 方案除部署层外的大部分技术选型
- 产出三份决策报告（M1/M2/M3 结束时），每份都能回答"是否继续推进 v4 方案"
- 与 Shopify Sidekick 本身做 benchmark 对照，提供最直观的可行性证据

**Non-Goals:**

- 不追求生产级代码质量（没有完整审计日志、OAuth、加密密钥管理）
- 不做完整 Shopify App（不走 Public App OAuth，只用 Custom App）
- 不做完整的 Mem0 长期记忆（POC 不测跨会话个性化）
- 不做 K8s / Helm / ArgoCD / Terraform 部署
- 不做工具数扩展到 15+ 的压力测试（保持 v4 方案的 6-8 工具）
- 不做性能 / 并发压测（POC 目的是功能可行性，不是容量）

## Decisions

### D1. 技术栈：双栈 Python + TypeScript

**选择**：Python 3.11+（FastAPI + PydanticAI + LiteLLM + Celery）+ TypeScript / Node 20（Next.js 15 + Vercel AI SDK）。

**理由**：
- Python 侧：PydanticAI / LiteLLM / Celery 都是 Python 一等公民；方案 v4 明确用这套
- TS 侧：Vercel AI SDK 提供现成的 SSE 流式 + `useChat` hook + 工具调用 UI，自建成本远高于引入
- 单人开发 + Claude Code 协作下，双栈维护成本可控

**替代方案**：
- 全 TypeScript（Mastra、LangChain.js）—— 生态比 Python 窄，放弃 PydanticAI 的结构化输出验证
- 全 Python（Streamlit 或 Gradio 替代前端）—— UI 灵活度不够，无法验证 HIL 卡片式交互

### D2. 包管理与 Monorepo 工具

**选择**：`uv`（Python）+ `pnpm`（JS）+ 简单 monorepo（不引入 Turborepo/Nx）。

**理由**：
- `uv` 比 poetry 快一个数量级，单人开发体验显著更好
- `pnpm` workspace 原生支持 monorepo，够用
- 引入 Turborepo/Nx 对单人项目是过度工程

**替代方案**：poetry + npm workspaces —— 慢、体验差；Turborepo —— 过度。

### D3. 单 Agent + JIT 的实现位置

**选择**：JIT 指令嵌入在 MCP 工具的返回值里（Shopify 论文原教旨做法），而不是在 Agent 系统提示词中硬编码分支。

**理由**：
- 系统提示词保持稳定 → prompt cache 有效
- 指令局部化 → 分析/内容/运营场景互不干扰
- 工具可以根据查询内容动态附带不同指令（例如 `query_store_data` 查销售时带分析师指令、查商品时带内容创作指令）

**替代方案**：把所有场景指令堆在系统提示词里 —— 会破坏 cache、指令冲突、难调试。

### D4. Shopify API 访问方式

**选择**：Custom App + Admin API access token（dev store 内），不走 Public App OAuth。

**理由**：
- POC 单店铺 token，开箱即用
- 多租户模拟只需 2-3 个 token 即可，不需要完整 OAuth 流程
- Public App OAuth 对 POC 是过度设计

**替代方案**：Public App OAuth —— POC 阶段引入一周工作量，不增加验证价值。

### D5. GraphQL Schema 注入策略

**选择**：M1 阶段用"手工 curated subset"——选出 top 20 核心类型（Product、Variant、Order、Customer、InventoryLevel、Collection、PriceRule、DiscountCode 等）完整注入系统提示词。M2 再试 RAG 检索式注入或两阶段查询。

**理由**：
- Shopify 完整 schema introspection 有数 MB，直接注入会吃掉大部分 context
- 手工 subset 在 M1 足够验证"LLM 能否生成正确 GraphQL"
- 注入策略本身就是需要验证的工程问题，M1 先确立 baseline，M2 再优化

**替代方案**：
- 完整 schema 直接注入 —— 上下文爆炸
- RAG 检索 schema 片段 —— 先跑 baseline 再优化，不要在 M1 就加 RAG 变量
- 两阶段查询（先问类型，再问字段） —— 增加 LLM 调用次数，M2 可试

### D6. 工具数量与边界

**选择**：固定 6 个工具——1 个 GraphQL 读 + 5 个写（update_price、update_inventory、save_content、create_promotion、create_automation），与 v4 方案一致。写操作优先用 Shopify GraphQL Mutation，因为 Shopify 的 Mutation 比 REST 更新更频繁。

**理由**：
- 保持 v4 方案原设计，验证的是"6-8 工具 + 单 Agent"假设
- 不超出验证边界，避免引入太多变量

**替代方案**：纯 REST 写操作 —— Shopify 的 REST Admin API 被官方标记为 legacy，GraphQL Mutation 是未来方向。

### D7. 多模型对比方式

**选择**：LiteLLM 路由 + YAML 配置。M1 至少跑 Claude Sonnet（主力）+ GPT-4o + Qwen-Max 三组对比。按任务类型配置偏好模型（意图识别用小模型、分析用大模型）。

**理由**：
- v4 方案明确"模型无关"，LiteLLM 是标准做法
- 三模型覆盖三大生态（Anthropic/OpenAI/阿里），能验证模型无关性是否真的成立

**替代方案**：只跑一个模型 —— 无法验证"模型无关"这条核心设计原则。

### D8. 前端技术选型

**选择**：Next.js 15 App Router + Vercel AI SDK（`useChat` + `streamText`）+ shadcn/ui。

**理由**：
- Vercel AI SDK 把 SSE 流式、工具调用渲染、HIL 状态管理都内置了
- App Router 是 Next.js 15 默认，Server Components 适合认证/状态获取
- shadcn/ui 提供现成的卡片组件，HIL 确认卡片开发成本极低

**替代方案**：纯 React + 手写 EventSource —— 重复造轮子。

### D9. 数据与存储

**选择**：
- Sidekick 内部数据：Postgres（Agent 状态 checkpoint、会话历史、评估数据）—— 用 Aurora PG 的本地替代即普通 Postgres
- 缓存与会话：Redis（ElastiCache 的本地替代）
- 向量搜索：Qdrant（语义缓存的 embedding 索引；M1 可不启用，M2 M3 才用）
- 全部 Docker Compose 本地起

**理由**：与生产方案同构（只改连接串即可切云），但 POC 无运维负担。

### D10. 评估与可观测性

**选择**：Langfuse 自托管（Docker）做追踪；RAGAS + DeepEval 做评估；pytest 里集成评估脚本做 CI。

**理由**：
- Langfuse 开源可自托管，POC 阶段零成本
- RAGAS + DeepEval 是 v4 方案指定，不换
- pytest 集成是 Python 生态自然选择

**替代方案**：LangSmith —— 免费层有限，付费不便宜，自托管更优。

### D11. Human-in-the-loop 交互形式

**选择**：在对话流里内联插入一张"写操作确认卡片"（标题 + 操作摘要 + 影响预览 + 确认/取消按钮），而不是弹出独立对话框。Agent 在工具调用前先 pause，用户确认后 resume。

**理由**：
- Shopify Sidekick 本身就是这种形态，体验经过验证
- Vercel AI SDK 的 tool call UI 原生支持这种模式（`toolInvocation` 状态）
- 不破坏对话流，保持上下文连续

**替代方案**：弹窗式 —— 打断体验，Shopify 明确避开。

### D12. 语义缓存策略

**选择**：M2 阶段先实现最简版本——用 sentence-transformers 本地生成 embedding，Redis 存 key = 问题 embedding hash，value = 回答 + metadata；命中条件 = 余弦相似度 > 0.95。M3 调优阈值、按租户分 namespace、多级缓存。

**理由**：
- 先跑通最简版本拿到真实命中率数据，再决定是否值得优化到 v4 方案声称的 40-68% 省钱
- 复杂缓存策略（LLM 重写 query、按意图分类缓存）留给 M3

**替代方案**：直接用 GPTCache/MemGPT —— 黑盒程度高，调试复杂。

### D13. Milestone 决策门

**M1 通过标准**：
- JIT 指令遵循率 ≥ 80%（至少 Claude Sonnet 基线）
- 工具选择准确率 ≥ 85%
- GraphQL 查询语法正确率 ≥ 90%，字段选择合理性 ≥ 80%
- 三模型对比报告有定量数据，不是"感觉还行"

**M1 失败后的分支**：
- 遵循率 70-80%：尝试 few-shot examples、JIT 指令措辞优化，可补 3-5 天
- 遵循率 < 70%：停下来评估是否转方案 B（多 Agent）或引入微调

**M2 通过标准**：端到端对话跑通、HIL UI 能用、多租户切换不串数据、Langfuse 追踪完整。

**M3 通过标准**：CI 能自动跑评估、语义缓存命中率有真实数据（不要求达到 40%，但要有一个已知数值作为后续优化起点）。

## Risks / Trade-offs

- **[风险] 通用模型 JIT 指令遵循率远低于 Shopify 微调模型** → Mitigation: M1 第一步就测，失败立即停损；准备 few-shot examples 作为补救；保留转方案 B 的退路
- **[风险] Shopify Admin API schema 注入 context 过大** → Mitigation: M1 用手工 curated subset 限制大小；测 prompt cache 命中率；超标则切 RAG 检索式注入
- **[风险] Shopify dev store 数据不够真实导致评估失真** → Mitigation: 用 Shopify 官方 dummy data app 塞代表性数据（≥ 50 商品、≥ 100 订单、≥ 5 collection）；测试用例覆盖典型场景
- **[风险] 单人 + AI 协作下代码质量漂移** → Mitigation: 每个 milestone 结束做一次 code review；保留 evaluation-suite 作为回归保险
- **[风险] 语义缓存实测命中率远低于 40-68%（v4 声称）** → Mitigation: 这正是要验证的假设，不算风险是结论；M3 报告如实写出真实数字
- **[风险] Claude Code 在跨语言 (Python + TS) 场景下容易产生微小不一致** → Mitigation: 共享 schema（JSON Schema 或 Pydantic → TypeScript 生成）；前后端通信用明确的 DTO
- **[风险] 测试用例数量少（20 条）可能代表性不足** → Mitigation: M1 报告显式说明样本局限；M3 扩展到 100+ 条（用户模拟生成）
- **[风险] 时间估算乐观（6 周单人完成）** → Mitigation: Milestone 级 go/no-go 门；M1 跑完如果到了 2 周就必须重评范围
- **[风险] Shopify API rate limit 阻塞测试** → Mitigation: POC 流量小，dev store 限额够用；若触发限额则改为录制 response 回放

## Migration Plan

这是首次建立项目，无历史代码要迁移。

部署路径（全本地）：
1. Git init → 建立项目骨架
2. Docker Compose 起本地服务（Postgres、Redis、Qdrant、Langfuse）
3. Python 和 Node 环境（uv、pnpm）
4. 配置 .env（Shopify token、模型 API key、数据库连接）
5. M1 → M2 → M3 递进开发

回滚策略：每个 milestone 有独立分支或 tag；失败 milestone 的产出物保留供反思，不直接删除。

## Open Questions

1. **OQ1**: 是否将"前端嵌入 JS SDK"（v4 方案里提到的"一行 script 接入商家后台"）纳入 POC？—— 建议不纳入，POC 以 standalone Next.js 页面形式运行即可验证核心
2. **OQ2**: 多租户 token 存储方式——明文 .env 还是加密入 Postgres？—— POC 建议 .env 明文（2-3 个 dev store 够用），M3 再加密
3. **OQ3**: 语义缓存的 embedding 模型选哪个——OpenAI text-embedding-3-small（省事）还是本地 sentence-transformers（离线、免费）？—— 建议本地 sentence-transformers（`BAAI/bge-small-zh` 或 `all-MiniLM-L6-v2`），完全本地化
4. **OQ4**: 用户模拟测试（M3）的"模拟商家"用哪个模型扮演？—— 建议用 Claude Opus 或 GPT-5.4（能力更强的扮演"刁钻商家"更有压力），且不和被测 Agent 同模型（避免同构偏差）
5. **OQ5**: 最终可行性报告呈现形式——Markdown 文档还是 Notebook + 图表？—— 建议 Markdown 主报告 + Jupyter Notebook 附录（含图表和原始数据），方便发给 stakeholder
