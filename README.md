# AloFootMind — 多智能体足球赛事分析系统

基于 LangGraph 多智能体 + RAG 的足球赛事分析平台，使用 StatsBomb Open Data 作为数据来源。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3.5 + TypeScript + Vite + TailwindCSS + Vue Router + Pinia + vue-i18n |
| 后端 | Python 3.12 + FastAPI + SQLAlchemy（异步） |
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
