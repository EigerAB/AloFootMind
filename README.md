# AloFootMind — 多智能体足球赛事分析系统

基于 LangGraph 多智能体 + RAG 的足球赛事分析平台，使用 StatsBomb Open Data 作为数据来源。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3.5 + TypeScript + Vite + TailwindCSS + Vue Router + Pinia + vue-i18n |
| 后端 | Python 3.12 + FastAPI |
| 存储 | PostgreSQL 16 + Redis + Milvus 2.4 |
| AI | LangGraph + LangChain + DeepSeek + BAAI/bge-m3 |
| 认证 | JWT（access + refresh）+ bcrypt + 邮箱验证 |

## 快速启动

### 1. 启动基础设施

```bash
docker-compose up -d
```

### 2. 配置环境变量

```bash
cp backend/.env.example backend/.env
# 编辑 .env，填入 API keys、数据库连接和 StatsBomb 数据路径
```

### 3. 安装后端依赖

```bash
cd backend
# 推荐使用 uv（已根据 pyproject.toml + uv.lock 锁定依赖）
uv sync
```

### 4. 初始化数据库 & 导入数据

```bash
# 初始化 PostgreSQL 表结构和 Milvus Collections
uv run python -c "import asyncio; from app.db.postgres import init_db; asyncio.run(init_db())"

# 导入 StatsBomb 数据（以英超为例，competition_id=2）
uv run python scripts/ingest.py --competition_id 2
```

### 5. 启动后端

```bash
uv run uvicorn app.main:app --reload --port 8000
```

### 6. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端默认运行在 http://localhost:5173，后端 API 在 http://localhost:8000

## 核心功能

- **赛后复盘**：选择一场比赛，触发 AI 战术分析，实时查看 Agent 执行进度（SSE 流式推送）
- **对阵情报**：选择两支球队，生成基于历史数据的战前情报报告
- **智能问答**：自然语言查询足球数据，RAG 驱动精准回答，支持多轮对话
- **用户认证**：注册/登录/邮箱验证/密码重置，JWT 双 Token 机制
- **聊天历史**：最多保存 10 条会话，支持重命名、删除和中断流式回答
- **多语言**：中文/英文切换

## 应用层实现

三个应用层（post_match / pre_match / aichat）本质上是对上述 ETL 语料和 RAG 检索层的不同组合方式。

### 赛后复盘（post_match）

**触发方式**：用户选择一场已导入的比赛，`POST /api/post-match` 创建后台任务，返回 `task_id`，前端通过 SSE 实时消费 Agent 执行日志。

![赛后复盘](/source/post_match_list.png)

**Sub-graph 链路**：

```
fetch_match_data
  └── SQL: matches JOIN teams JOIN events_aggregated，获取比赛元数据 + key_events_json
          │
          ▼
rag_retrieval（当场比赛维度）
  ├── tactical_level: retrieve(match_id=current_id, top_k=8)
  └── player_level:  retrieve(player_ids=extract_key_players(key_events, 5), top_k=10)
          │
          ▼
tactical_analysis
  └── DeepSeek LLM，prompt 注入比赛统计数据 + RAG 上下文（最多 20 条）
      输出结构化 Markdown 报告（比赛概述/战术阵型/关键战术时刻/球员亮点/战术总结）
          │
          ▼
report_generation
  └── 持久化到 analysis_reports 表（report_type='post_match'）
```

**RAG 策略**：只检索当场比赛，不引入历史对比——目的是基于客观事件数据分析本场战术，避免跨场干扰。`extract_key_players()` 按事件权重（Goal×3, Assist×2, Red Card×2, Key Pass×1.5, Yellow Card×1）提取 Top-5 关键球员 ID，定向检索其球员画像。

### 赛前情报（pre_match）

**触发方式**：用户选择主客队，`POST /api/pre-match` 创建后台任务，链路与 post_match 类似，但 RAG 检索维度更广。
![赛前情报](/source/pre_match_1.png)
![赛前情报](/source/pre_match_2.png)

**Sub-graph 链路**：

```
fetch_team_history
  └── SQL: 查询两队最近 10 场交锋记录（h2h_matches），含阵型、比分、射门数
          │
          ▼
rag_retrieval（三维度检索）
  ├── match_level:   retrieve(match_ids=[h2h_latest_id], top_k=2)
  │                  ← 仅取最近一场 H2H 的比赛摘要
  ├── tactical_level: retrieve(match_ids=[h2h_latest_id, home_last_id, away_last_id], top_k=8)
  │                  ← H2H + 主队非H2H最近一场 + 客队非H2H最近一场
  └── player_level:  retrieve(player_ids=dedup(h2h_players + home_players + away_players), top_k=10)
                     ← 三场比赛关键球员合并去重
          │
          ▼
matchup_analysis
  └── DeepSeek LLM，基于 H2H 历史 + RAG 上下文生成赛前情报报告
```

**降级策略**：若两队无历史交锋记录，`match_level` 检索跳过，`tactical_level` 降级为仅主客队各自最近一场。

### AI 问答（aichat）

**与前两者的核心区别**：aichat 不走主图（`run_analysis`），直接由 `POST /api/chat` endpoint 调用 `build_qa_graph()`，全程流式 SSE 返回，无 `task_id` 中转。

![AI 问答](/source/chat_1.png)
![AI 问答](/source/chat_2.png)
![AI 问答](/source/chat_3.png)
![AI 问答](/source/chat_4.png)

**完整请求链路**：

```
POST /api/chat  {query, session_id?, conversation_history?, qa_meta?}
  │
  ├── 1. 会话恢复：若有 session_id，从 chat_sessions 加载 messages + qa_meta
  │
  ├── 2. qa_graph.ainvoke(state, timeout=30s)
  │       query_rewrite → relevance_gate → [classify → query_classify → rag_retrieval] | END
  │       返回: {_route, rag_context, qa_meta}
  │
  ├── 3. StreamingResponse(_generate())
  │       classify      → stream_answer(query, rag_context, history)      [RAG 增强，流式]
  │       direct_answer → stream_direct_answer(query, history)            [纯对话，流式]
  │       boundary_answer → stream_boundary_answer(query, history)        [边界提示，流式]
  │       每个 token: yield "data: {token}\n\n"
  │
  └── 4. 会话持久化（流结束后）
          UPDATE/INSERT chat_sessions SET messages=..., qa_meta=..., updated_at=NOW()
          event: done  {sources, qa_meta, session_id}
```

**会话管理**：`chat_sessions` 表最多保留每用户 10 条会话（超限时 insert 前抛 429），会话名称默认取首条用户消息的前 30 字符。前端侧边栏展示最近 10 条会话，支持重命名、删除、中断（`POST /api/chat/sessions/{id}/cancel` 写入 system role 的 cancelled 标记）。

---

## 项目结构

```
AloFootMind/
├── backend/              # FastAPI 后端
│   ├── app/
│   │   ├── api/          # FastAPI 路由（比赛、分析、认证、聊天）
│   │   ├── agents/       # LangGraph 多智能体定义（赛前/赛后/问答子图）
│   │   ├── core/         # 配置（Pydantic Settings）
│   │   ├── db/           # 数据库模型、连接、迁移
│   │   ├── etl/          # StatsBomb 数据解析与三层 RAG 语料生成
│   │   └── services/     # RAG 检索、嵌入、LLM 客户端
│   ├── scripts/
│   │   ├── ingest.py     # ETL CLI（全量/增量导入）
│   │   └── seed_mock.py  # Mock 数据种子
│   ├── alembic/          # 数据库迁移
│   ├── .env.example
│   ├── pyproject.toml
│   └── uv.lock
├── frontend/             # Vue 3 前端
│   └── src/
│       ├── api/          # API 客户端（含自动刷新 Token）
│       ├── components/   # 通用组件（布局、模态框、确认对话框）
│       ├── composables/  # Vue3 组合式函数（SSE、Markdown）
│       ├── i18n/         # 国际化（zh / en）
│       ├── router/       # 路由配置
│       ├── stores/       # Pinia 状态管理（auth、chat）
│       ├── views/        # 页面组件
│       └── main.ts       # 入口文件
├── openspec/             # OpenSpec 变更管理
│   └── changes/
│       └── archive/      # 已归档的变更
└── docker-compose.yml    # 基础设施编排（Postgres + Redis + Milvus）
```
