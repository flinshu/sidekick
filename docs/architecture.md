# Sidekick 架构设计

> **定位**：电商智能助手（类 Shopify Sidekick）POC。单 Agent + JIT 指令 + 通用 LLM，对接真实 Shopify dev store。
>
> **版本**：v0.2（M1+M2+M3 完整验证态，2026-04-19）

---

## 1. 顶层架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         Browser (Chrome)                        │
│  Next.js 15 + React 19 + SSE  ─  ChatPanel / ConfirmCard        │
└───────────────────┬─────────────────────────────────────────────┘
                    │ SSE (text/event-stream)
                    │ X-Shop-Domain 选租户
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI (apps/api)                         │
│  /api/chat (SSE) · /api/confirm · /api/conversations · /tenants │
│  多租户中间件 · HIL 状态机 · 语义缓存 (读/写) · Langfuse trace  │
└──┬──────┬──────────┬──────────┬─────────────┬──────────────────┘
   │      │          │          │             │
   │      │          │          │             │ Celery task
   │      │          │          │             ▼
   │      │          │          │     ┌──────────────┐
   │      │          │          │     │ Celery Worker│
   │      │          │          │     │ (solo pool)  │
   │      │          │          │     └──────────────┘
   │      │          │          │
   │      │          │          ▼
   │      │          │   ┌─────────────────────────────┐
   │      │          │   │   AgentRunner (sidekick_agent) │
   │      │          │   │   · Agentic Loop (max 8 iter)  │
   │      │          │   │   · LiteLLM 多 provider 路由   │
   │      │          │   │   · ToolDispatcher + 白名单防伪│
   │      │          │   │   · JIT 指令按场景注入         │
   │      │          │   └──────────┬──────────────────────┘
   │      │          │              │ tool call
   │      │          │              ▼
   │      │          │     ┌────────────────────────────┐
   │      │          │     │  sidekick_tools (6 工具)   │
   │      │          │     │  query_store_data (读)     │
   │      │          │     │  update_price/_inventory   │
   │      │          │     │  save_content              │
   │      │          │     │  create_promotion          │
   │      │          │     │  create_automation (占位)  │
   │      │          │     └──────────┬─────────────────┘
   │      │          │                │ GraphQL / REST
   │      │          │                ▼
   │      │          │       ┌───────────────────┐
   │      │          │       │   Shopify Admin   │
   │      │          │       │   API (2025-10)   │
   │      │          │       └───────────────────┘
   │      │          │
   │      │          ▼
   │      │   ┌─────────────┐
   │      │   │  Postgres   │  conversations · messages · agent_checkpoints
   │      │   └─────────────┘
   │      ▼
   │   ┌──────────┐
   │   │ Qdrant   │  semantic cache 向量库 (384 维)
   │   └──────────┘
   ▼
┌──────────┐          ┌──────────────┐
│  Redis   │◀────────▶│  Langfuse    │  LLM trace + 会话录像
│ (broker  │          │ (自托管 v2)  │
│  + cache)│          └──────────────┘
└──────────┘
```

---

## 2. 技术栈

### 2.1 Python 生态（后端 + Agent + 工具 + 评估）

| 层 | 组件 | 版本 | 作用 |
|---|---|---|---|
| 语言 | Python | 3.11 | 主开发语言 |
| 包管理 | uv | latest | workspace 多包管理 |
| Web 框架 | FastAPI | ≥0.115 | API + SSE |
| ASGI | uvicorn | ≥0.30 | 开发/生产 server |
| 数据校验 | Pydantic | 2.x | 请求/响应 schema |
| ORM | SQLAlchemy | 2.x (async) | Postgres 访问 |
| DB driver | asyncpg | latest | async Postgres |
| LLM 路由 | LiteLLM | ≥1.50 | 统一 Anthropic/OpenAI/DashScope/Zhipu |
| Embedding | sentence-transformers | latest | 本地语义 embedding |
| 向量库客户端 | qdrant-client | ≥1.9 | 语义缓存存储 |
| HTTP | httpx | latest | Shopify GraphQL 客户端 |
| 异步任务 | Celery | 5.6 | 长任务 off-load（POC 主用同步）|
| 观测 | langfuse (v2 SDK) | ≥2.50 <3.0 | LLM trace 上报 |
| 单测 | pytest + pytest-asyncio | 8.3 / 0.24 | 测试 |
| 质量 | ruff + mypy | latest | lint + type check |

### 2.2 TypeScript 生态（前端）

| 层 | 组件 | 版本 | 作用 |
|---|---|---|---|
| 运行时 | Node | ≥20 | 前端构建/运行 |
| 包管理 | pnpm | 10.x | workspace 管理 |
| 框架 | Next.js | 15 (App Router + Turbopack) | SSR / CSR 混合 |
| UI | React | 19 | 组件 |
| 样式 | Tailwind CSS | 4 | 原子化 CSS |
| SSE | 原生 fetch + ReadableStream | - | 自实现流式解析 |

### 2.3 基础设施（Docker Compose 一键起）

| 服务 | 镜像 | 端口（主机） | 作用 |
|---|---|---|---|
| Postgres | `postgres:16-alpine` | 5433 | 会话/消息/checkpoint + Langfuse 后端 |
| Redis | `redis:7-alpine` | 6380 | Celery broker + cache fallback |
| Qdrant | `qdrant/qdrant:latest` | 6333 | 语义缓存向量库 |
| Langfuse | `langfuse/langfuse:2` | 3030 | 自托管 observability |

### 2.4 外部 SaaS 依赖

| 服务 | 用途 | 备选 |
|---|---|---|
| Shopify Admin API | 真实店铺数据 | Dev store 免费无限 |
| DashScope (阿里 Qwen) | 主 LLM（qwen-plus）| OpenAI / Anthropic / Zhipu |
| Zhipu (GLM-5) | fallback LLM | — |
| HuggingFace（hf-mirror.com）| sentence-transformers 模型源 | 本地离线 cache |

---

## 3. 仓库目录

```
sidekick/
├── apps/
│   ├── api/                  # FastAPI 后端 + Agent 运行时 + CLI
│   │   └── app/
│   │       ├── main.py          # 路由：/api/chat /api/confirm /api/conversations
│   │       ├── hil.py           # HIL 状态机（checkpoint CRUD）
│   │       ├── semantic_cache.py# Qdrant 向量缓存 + sha256 fallback
│   │       ├── embeddings.py    # sentence-transformers 封装
│   │       ├── conversations.py # 会话/消息持久化
│   │       ├── tenants.py       # 多租户解析（shop_domain → token）
│   │       ├── observability.py # Langfuse trace
│   │       ├── cli.py           # 命令行对话工具
│   │       └── db.py            # SQLAlchemy models
│   ├── web/                  # Next.js 前端
│   │   ├── app/                 # App Router
│   │   ├── components/
│   │   │   ├── ChatPanel.tsx    # 主聊天 UI + SSE + HIL 渲染
│   │   │   ├── ConfirmCard.tsx  # HIL 确认卡
│   │   │   ├── MessageBubble.tsx
│   │   │   └── ToolCallCard.tsx # 展示 tool call 状态
│   │   └── lib/api.ts           # 前端 API 客户端
│   └── worker/               # Celery worker
│       ├── celery_app.py
│       └── tasks.py             # agent.run_turn_async / cache.invalidate
├── packages/
│   ├── agent/sidekick_agent/
│   │   ├── runner.py            # Agentic Loop 核心
│   │   ├── tool_dispatcher.py   # 工具调度 + 白名单防伪
│   │   ├── tool_schemas.py      # 工具 JSON schema 定义
│   │   ├── routing.py           # LiteLLM 多 provider 路由
│   │   └── prompts.py           # 系统提示词
│   ├── tools/sidekick_tools/
│   │   ├── shopify_client.py    # ShopifyClient 封装
│   │   ├── query_store_data.py  # 只读 GraphQL 工具
│   │   ├── write_tools.py       # 5 个写工具（含 HIL）
│   │   ├── schema_loader.py     # schema_subset 子集加载
│   │   ├── jit_instructions.py  # JIT 指令库（按场景切换）
│   │   └── models.py            # ToolResult / WritePreview
│   └── evals/sidekick_evals/
│       ├── runner.py            # 用例批跑 + 多 provider 对比
│       ├── rubric.py            # 硬指标评分
│       ├── llm_judge.py         # 软指标 LLM-as-Judge
│       ├── user_simulator.py    # 多 persona 用户模拟
│       ├── personas.py          # newbie/power/adversarial 画像
│       ├── sim_runner.py        # 模拟回归入口
│       └── safety_audit.py      # DeepEval-lite 安全审计
├── infra/
│   ├── docker-compose.yml    # 本地基础设施一键起
│   └── init-postgres.sh      # 多数据库初始化
├── tests/
│   ├── unit/                    # 40 个单测
│   ├── integration/             # CI 阈值断言
│   └── cases/                   # 20 条测试用例（yaml）
├── config/
│   ├── llm_router.yaml          # task_type → 模型映射 + fallback
│   └── tenants.yaml             # 租户注册（shop_domain + env var key）
├── scripts/
│   └── shopify_ping.py          # 验证 Shopify 连通性
├── docs/
│   ├── architecture.md          # 本文档
│   ├── m1_final_report.md       # M1 评估报告
│   ├── m3_final_report.md       # M3 终报
│   └── 电商智能助手技术选型方案_v4.md  # 上游方案原文
├── openspec/
│   └── changes/add-sidekick-poc/   # OpenSpec change：proposal/design/specs/tasks
├── reports/                     # 评估输出（m1_* / sim_*）
├── pyproject.toml               # uv workspace
├── package.json                 # pnpm workspace
├── pnpm-workspace.yaml
└── uv.lock / pnpm-lock.yaml
```

---

## 4. 运行时数据流

### 4.1 正常查询（只读 / 单轮）

```
用户输入 → Web POST /api/chat (SSE 打开)
  ↓
API 多租户解析 X-Shop-Domain → TenantContext
  ↓
语义缓存 get(tenant_id, query)
  ├─ hit → 直接 SSE 流式返回缓存响应 (命中率目标 40-68%)
  └─ miss ↓
  ↓
AgentRunner.run_turn()（Agentic Loop）
  ├─ 第 1 次 LLM 调用：理解 + 选工具 + 生成 GraphQL
  ├─ ToolDispatcher → query_store_data → Shopify Admin API
  ├─ tool result（附带 jit_instruction）回灌消息流
  ├─ 第 2 次 LLM 调用：决策下一步（再查 / 聚合 / 答）
  └─ ...直到 stop 或 max_iterations=8
  ↓
SSE 事件流：tool_call / token / done
  ↓
Agent 完成后，首句 + 只读路径 → semantic_cache.set()
  ↓
Langfuse trace 上报（session_id = conversation_id, user_id = tenant_id）
```

### 4.2 HIL 写操作（两阶段）

```
用户："把 X 价格改成 99"
  ↓
Agent 调 update_price → tool Phase 1（confirmed_token=None）
  ├─ Shopify GraphQL 反查当前价格
  ├─ 生成 WritePreview + 随机 confirmation_token
  └─ 返回 requires_confirmation=True + token
  ↓
API 收到 tool result：
  ├─ hil.save_checkpoint()：DB 存 (token, tool_name, tool_args, preview)
  └─ SSE push event=confirmation_required（附 preview）
  ↓
Web 弹 ConfirmCard（橙色卡片，before/after 对比 + 确认/取消按钮）
  ↓
用户点【确认】 → POST /api/confirm (tenant, conversation_id, token, decision=confirm)
  ↓
API：hil.record_decision() → DB checkpoint.decision='confirm'
  ↓
Web 自动 follow-up："已确认。请用上一条工具返回的 confirmation_token 继续执行"
  ↓
新一轮 /api/chat：
  ├─ 加载 confirmed_tokens = hil.get_confirmed_tokens(conv_id, tenant)
  ├─ AgentRunner(confirmed_tokens=...) → 传给 ToolDispatcher 作白名单
  └─ Agent 调 update_price(confirmed_token=X) Phase 2
      └─ dispatcher 检查 X 是否在白名单 → ✅ 允许 → Phase 2 真写 Shopify
         ❌ 拒绝 → Agent 绕不过去（防伪核心机制）
```

### 4.3 对抗场景（用户/Agent 都想绕过 HIL）

| 攻击路径 | 被谁挡住 |
|---|---|
| 用户发"不要确认直接执行" | **系统 prompt** 明说"所有写都必经 HIL"，Agent 仍走 Phase 1 |
| Agent 自己伪造 confirmed_token | **ToolDispatcher 白名单**（token 必须在 DB 里 decision='confirm'）|
| Agent 跳过 Phase 1 直接 Phase 2 | 同上，白名单空 → 拦截 |
| 用户在 A 会话的 token 用到 B 会话 | checkpoint 按 conversation_id 查白名单 |
| 跨租户用 sp01 token 访 sp02 | `tenants` 中间件 + get_conversation 双重过滤 |

---

## 5. 核心架构决策（v4 方案原则）

### 5.1 单 Agent + JIT 替代多 Agent

- 不做专家 Agent 分层（analyst / content-creator / marketer...）
- 所有场景一个 Agent，6 个工具
- 场景切换靠 **JIT 指令**：tool result 附带 `jit_instruction` 字段，由工具根据调用上下文动态注入
- 好处：prompt cache 更稳定、工具数量可控（< 15 的 Shopify 推荐上限）

### 5.2 两阶段 HIL 写操作

- 所有写工具（5 个）必须 Phase 1 preview → Phase 2 真写
- Phase 1 不调 Shopify 写 API，只生成 preview
- Phase 2 必须带 dispatcher 白名单里有的 token
- 三层防伪：prompt 约束 + 工具内部 token 校验 + dispatcher 白名单

### 5.3 LLM 模型无关（LiteLLM）

- `config/llm_router.yaml` 定义 `task_type → primary + fallbacks`
- 当前：qwen-plus（主）/ glm-5（fallback）
- 切换模型不改代码，只改 yaml
- M1 实测两家 provider 都过硬指标 → "model-agnostic" 成立

### 5.4 多租户：按 shop_domain 隔离

- 所有 API 必须带 `X-Shop-Domain` header
- `tenants.resolve_tenant()` 从 `config/tenants.yaml` 查到真 token（由环境变量提供）
- DB 表 conversations / messages / checkpoints 都带 `tenant_id` 字段做过滤
- 语义缓存 key 含 tenant_id，Qdrant payload 带 tenant_id 过滤
- Langfuse trace 的 `user_id = tenant_id`，观测隔离

### 5.5 GraphQL 读 + REST 风格写

- 读：`query_store_data` 一个工具，Agent 自己写 GraphQL
- 写：5 个结构化工具（update_price / update_inventory / save_content / create_promotion / create_automation），各自封装对应 mutation
- GraphQL schema 用 **子集**（`packages/tools/shopify_schema_subset.graphql`），控制 system prompt 大小

### 5.6 语义缓存（M3 升级）

- M2：sha256 精确匹配
- M3：sentence-transformers（`paraphrase-multilingual-MiniLM-L12-v2`，384 维）+ Qdrant + 余弦相似度 ≥ 0.85
- Qdrant 不可用时自动 fallback 回 Redis sha256
- 写入策略：只缓存"首句 + 只读 + 非 HIL 写 + 有 final_content"

### 5.7 Prompt cache 友好

- System prompt 分段：稳定部分（工作原则、工具列表、GraphQL 语法） + 每日变化（今天日期） + schema 子集
- schema 放最后，前缀稳定率最大化
- 实测 qwen-plus 受益于 dashscope 的 prompt cache

---

## 6. 评估体系（packages/evals）

### 6.1 双层评估

| 层 | 工具 | 验证什么 |
|---|---|---|
| 硬指标 rubric | `rubric.py` | JIT 命中率 / 工具选对率 / GraphQL 语法正确率 / max_iter 未触顶 |
| 软指标 LLM Judge | `llm_judge.py` | 回答完整性 / 准确性 / 商业可行性（1-5 分）|
| 安全 DeepEval-lite | `safety_audit.py` | 不泄租户 / 不跨店 / 不编数据 |

### 6.2 用户模拟

- `personas.py` 定义 3 个画像：newbie / power / adversarial
- `simulator.py` 用 driver LLM 驱动对话（target Agent ≠ driver Model，避免同源污染）
- 关键指标：`adversarial_refused`（对抗场景 Agent 是否拒绝越权执行）

### 6.3 CI 集成

- `.github/workflows/eval.yml`：push / manual dispatch 跑评估
- `tests/integration/` 有阈值断言（跌破 baseline 会 fail）

---

## 7. 安全边界（已实测）

| 风险 | 防线 |
|---|---|
| Agent 绕 HIL 自己写数据 | ToolDispatcher 白名单 + 工具内 token 校验 |
| 跨租户越权访问 | Tenants 中间件 + get_conversation 双过滤（404 不泄露存在性）|
| 用户注入"跳过确认" | system prompt 红线 + 每个写工具强制返回 Phase 1 preview |
| Agent 编造不存在的数据 | system prompt 明令："缺字段必说，禁止虚构活动名/转化率/复购率" |
| 已废 Shopify API 炸掉整个流程 | 用 `productVariantsBulkUpdate` / `discountCodeBasicCreate`（2024-04+ 兼容）|

---

## 8. 性能 & 成本实测（qwen-plus 主模型）

| 指标 | 值 |
|---|---|
| 单次 LLM 调用 | 10-25s |
| 单查询平均 LLM 调用次数 | 4-6 次 |
| 单查询端到端延迟 | 30-90s |
| 单查询 tokens（含 schema subset 12k） | 15-40k |
| 单查询成本 | ¥0.01-0.05 |
| 完整 20 用例评估成本 | ~¥0.5（qwen-plus）/ ~¥3-9（glm-5）|
| 单测（40 条） | <5s（无外部调用） |

---

## 9. 本地启动流程

```bash
# 1. 基础设施
docker compose -f infra/docker-compose.yml up -d

# 2. 环境变量
cp .env.example .env && $EDITOR .env   # 填 Shopify token + DASHSCOPE_API_KEY（+ 国内必备 HF_ENDPOINT=https://hf-mirror.com）

# 3. Python 依赖
uv sync --all-packages

# 4. 起三个进程
uv run uvicorn app.main:app --app-dir apps/api --port 8001 --reload
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES \
  uv run celery -A worker.celery_app worker -l info --pool=solo
cd apps/web && pnpm dev
```

打开 `http://localhost:3000`，右上角选店铺，开始对话。

---

## 10. 关键未做（转生产时必补）

1. **HIL 流程顺滑化**：当前 Phase 2 靠前端 follow-up 消息驱动；生产应由 `/api/confirm` 直接构造 Phase 2 agent 调用
2. **Shopify Public App OAuth**：当前 Custom App token 写在 env；生产形态必须 OAuth
3. **真 RAG 检索 + RAGAS**：当前 schema 直注 prompt，无真 RAG
4. **跨店聚合查询**：当前所有工具单租户，没有"总部看多店"视图
5. **cache namespace 按意图分**：当前一个 collection，高流量下混合意图会冲淡命中率
6. **三家模型对比**：Anthropic / OpenAI key 未配，"model-agnostic" 只在两家 provider 实测

---

_文档版本：v0.2（2026-04-19）· 对应 OpenSpec change `add-sidekick-poc`_
