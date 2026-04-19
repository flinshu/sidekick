# Sidekick POC

电商智能助手（类 Shopify Sidekick）的可行性验证项目。

**当前状态**：✅ M1 + M2 + M3 已完成（OpenSpec ~70/77 任务）。
- [🏛 架构设计](docs/architecture.md)：整体架构图 + 技术栈 + 数据流 + 安全边界
- [📋 M1 报告](docs/m1_final_report.md)：双 provider 都通过决策门
- [📋 M3 终报](docs/m3_final_report.md)：方案 A 7 个核心假设全部实证
- [🗂 v4 方案原文](docs/电商智能助手技术选型方案_v4.md)
- [📐 OpenSpec change](openspec/changes/add-sidekick-poc/)

## 目标

验证《电商智能助手技术选型方案 v4》中"方案 A：单 Agent + JIT 指令 + 通用模型"这套技术选型的可行性。用 Shopify dev store 作为真实数据源，不做模型微调，不做 K8s 部署。

## Milestones

| Milestone | Done 定义 |
|-----------|-----------|
| M1 核心可行性（约 1 周） | 20 条测试用例 × 3 模型跑完，输出定量报告：JIT 指令遵循率、工具选择准确率、GraphQL 生成准确率 |
| M2 工程骨架（约 3 周） | Next.js 对话 Web + SSE + HIL 确认 UI + 多租户 + LiteLLM 路由 + Celery + Redis 语义缓存 + Langfuse 追踪 |
| M3 评估 + 可靠性（约 2 周） | RAGAS + DeepEval 自动化（CI）+ 语义缓存命中率实测 + 用户模拟回归 + 最终可行性报告 |

每个 milestone 结束设 Go/No-Go checkpoint。

## 仓库结构

```
apps/
├─ api/           FastAPI 后端 + Agent 运行时 + CLI（M1 已用）
├─ web/           Next.js 15 前端（M2）
└─ worker/        Celery worker（M2）
packages/
├─ agent/         Agent 定义 + JIT 指令管理
├─ tools/         Shopify MCP 工具集
└─ evals/         RAGAS / DeepEval / LLM Judge / 报告生成
infra/
└─ docker-compose.yml   本地服务（Postgres / Redis / Qdrant / Langfuse）
tests/
└─ cases/         20 条测试用例
scripts/          运维脚本（Shopify ping 等）
config/           YAML 配置（LiteLLM 路由、tenants 等）
docs/             设计文档
reports/          评估输出（M1/M2/M3 报告）
openspec/         OpenSpec 规范与 changes
```

## 快速启动

### 环境要求

- macOS / Linux
- Python 3.11+（uv 自动管理）
- Node 20 LTS + pnpm 10+
- Docker Desktop

### 初始化

```bash
# 1. 拷贝环境变量模板，填入 Shopify token + 模型 API key
cp .env.example .env
$EDITOR .env

# 2. 启动本地服务
docker compose -f infra/docker-compose.yml up -d

# 3. 初始化 Python 依赖
cd apps/api && uv sync

# 4. 验证 Shopify 连通性
uv run python ../../scripts/shopify_ping.py
```

### M1：命令行跟 Agent 对话

```bash
cd apps/api
uv run python -m app.cli chat
```

### M1：跑测试用例 × 多模型对比

```bash
cd /Users/phper/Code2/saas-ai2/sidekick
# 全套 20 用例 × 双 provider
uv run python -m sidekick_evals.runner \
  --models=dashscope:qwen-plus,zhipu:glm-5 \
  --judge-model=dashscope/qwen-plus
```

### M2：起前后端联调

```bash
# Terminal 1: API
uv run uvicorn app.main:app --app-dir apps/api --port 8001 --reload

# Terminal 2: Celery worker（macOS 必须 solo pool）
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES \
  uv run celery -A worker.celery_app worker -l info --pool=solo

# Terminal 3: Web
cd apps/web && pnpm dev
# → http://localhost:3000
```

### M3：用户模拟回归

```bash
uv run python -m sidekick_evals.sim_runner \
  --personas newbie,power,adversarial \
  --target-model dashscope:qwen-plus \
  --driver-model zhipu:glm-5 \
  --runs-per-persona 3 \
  --max-turns 5
```

### CI（GitHub Actions）

`.github/workflows/eval.yml`：
- 每次 push 自动跑 unit tests
- workflow_dispatch 手动触发完整评估（带 baseline 阈值）

## 准备工作（必须）

### 1. Shopify Partners 账号 + Dev Store

1. 登录 https://partners.shopify.com
2. 新建 Development Store（免费，无限制）
3. 在 store 后台 → Apps → Develop apps → Create an app
4. 配置 Admin API access scopes：`read_products` `write_products` `read_orders` `read_inventory` `write_inventory` `read_price_rules` `write_price_rules` `read_discounts` `write_discounts`
5. Install app → 复制 Admin API access token
6. 填入 `.env` 的 `SHOPIFY_ADMIN_TOKEN` 和 `SHOPIFY_SHOP_DOMAIN`

### 2. 模型 API Key

至少配置一个：

| 变量 | 说明 |
|------|------|
| `ANTHROPIC_API_KEY` | Claude Sonnet/Opus/Haiku（推荐 M1 首选） |
| `OPENAI_API_KEY` | GPT-4o / 4o-mini |
| `DASHSCOPE_API_KEY` | 阿里百炼 Qwen-Max / Qwen-Turbo |

### 3. Dev Store 灌测试数据

Shopify 提供 Dummy Data app 可一键灌入商品/订单/客户：
- 在 dev store 后台 Apps store 搜索 "Simple Sample Data" 或 "Dummy Products"
- 安装后生成至少 50 商品 / 100 订单 / 5 collection

## 当前进度

参见 [openspec/changes/add-sidekick-poc/tasks.md](openspec/changes/add-sidekick-poc/tasks.md) 中的 checkbox 状态。
