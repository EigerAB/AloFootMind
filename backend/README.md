# AloFootMind 后端

基于 FastAPI 的足球分析后端，采用 LangGraph 多智能体系统进行 AI 分析。

## 功能特性

- **赛后分析**：使用多智能体系统进行战术分析
- **赛前情报**：球队对阵分析和预测
- **RAG 驱动的问答**：基于比赛数据和报告的语义搜索
- **StatsBomb 数据集成**：StatsBomb Open Data 的 ETL 管道
- **向量搜索**：基于 Milvus 的语义检索

## 技术栈

- **框架**：FastAPI 0.115+
- **数据库**：PostgreSQL 16 + SQLAlchemy（异步）
- **缓存**：Redis + hiredis
- **向量数据库**：Milvus 2.4
- **大模型**：OpenAI (GPT-4o) / DeepSeek (deepseek-chat)
- **嵌入模型**：BAAI/bge-m3 (FlagEmbedding)

## 环境要求

- Python 3.12+
- Docker & Docker Compose（用于基础设施）
- StatsBomb Open Data（数据导入时可选）

## 快速开始

### 1. 环境变量配置

复制 `.env.example` 到 `.env` 并配置：

```bash
cp .env.example .env
```

必需的环境变量：
```env
DB_URL=postgresql+asyncpg://user:pass@localhost:5432/alofootmind
REDIS_URL=redis://localhost:6379/0
MILVUS_HOST=localhost
MILVUS_PORT=19530
DEEPSEEK_API_KEY=your_deepseek_key
OPENAI_API_KEY=your_openai_key
STATSBOMB_DATA_PATH=/path/to/statsbomb/open-data
CORS_ORIGINS=http://localhost:5173,http://localhost
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 初始化数据库

```bash
# 使用 Docker Compose（推荐）
docker compose up -d postgres redis milvus

# 或手动运行迁移
alembic upgrade head
```

### 4. 启动服务器

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

或使用 Docker：
```bash
docker compose -f ../docker-compose.yml --profile full up -d backend
```

## API 接口

### 联赛
- `GET /api/competitions` - 列出所有联赛
- `GET /api/competitions/{competition_id}/teams` - 搜索联赛中的球队

### 比赛
- `GET /api/matches` - 列出比赛（支持分页）
- `GET /api/matches/{match_id}` - 获取比赛详情
- `POST /api/matches/{match_id}/analysis` - 触发赛后分析
- `GET /api/matches/{match_id}/report` - 获取分析报告

### 分析
- `POST /api/analysis/pre-match` - 触发赛前分析
- `GET /api/tasks/{task_id}/status` - 获取任务状态
- `GET /api/tasks/{task_id}/stream` - SSE 任务更新流
- `GET /api/tasks/{task_id}/result` - 获取任务结果
- `POST /api/chat` - RAG 驱动的问答

### 健康检查
- `GET /health` - 健康检查（Postgres、Redis、Milvus）

## 数据导入

### 完整 StatsBomb 数据导入
```bash
# 导入所有联赛
python scripts/ingest.py

# 导入指定联赛
python scripts/ingest.py --competition_id 2

# 试运行（不写入）
python scripts/ingest.py --dry-run
```

### 单个赛季导入
```bash
python scripts/ingest.py --competition_id 2 --season_id 44
```

### Mock 数据（用于测试）
```bash
python scripts/seed_mock.py
```

或使用 Makefile：
```bash
cd ..
make seed-mock
```

## 项目结构

```
backend/
├── app/
│   ├── api/
│   │   └── routes/          # API 路由
│   ├── agents/
│   │   ├── subgraphs/       # LangGraph 子图（赛前/赛后/问答）
│   │   ├── graph.py         # 主多智能体图
│   │   ├── state.py         # 共享状态定义
│   │   └── utils.py         # 智能体工具函数
│   ├── db/
│   │   ├── models.py        # SQLAlchemy 模型
│   │   ├── postgres.py      # PostgreSQL 连接
│   │   ├── redis_client.py  # Redis 客户端
│   │   └── milvus_client.py # Milvus 客户端
│   ├── etl/
│   │   ├── parser.py        # StatsBomb JSON 解析器
│   │   └── pipeline.py      # ETL 管道
│   ├── services/
│   │   ├── embedder.py      # BGE 嵌入
│   │   └── rag_service.py   # RAG 检索
│   └── core/
│       └── config.py        # 配置（Pydantic）
├── scripts/
│   ├── ingest.py            # ETL CLI
│   └── seed_mock.py         # Mock 数据种子
├── alembic/                 # 数据库迁移
├── requirements.txt
└── Dockerfile
```

## 开发

### 运行测试
```bash
pytest
```

### 代码检查
```bash
ruff check .
```

### 类型检查
```bash
mypy app --ignore-missing-imports
```

### 数据库迁移
```bash
# 创建迁移
alembic revision --autogenerate -m "描述"

# 应用迁移
alembic upgrade head

# 回滚
alembic downgrade -1
```

## Docker 部署

### 构建后端镜像
```bash
docker build -t alofootmind-backend .
```

### 使用 Docker Compose 运行
```bash
cd ..
docker compose --profile full up -d
```

## 常见问题

### 连接问题
- 确保 PostgreSQL、Redis 和 Milvus 正在运行
- 检查 `.env` 中的 `DB_URL`、`REDIS_URL`、`MILVUS_HOST`
- 验证 `CORS_ORIGINS` 包含你的前端 URL

### Milvus 集合错误
- 运行 `python -m app.db.milvus_init` 初始化集合
- 检查 Milvus 是否可访问：`docker compose logs milvus`

### LLM API 错误
- 验证 `DEEPSEEK_API_KEY` 和 `OPENAI_API_KEY` 有效
- 检查 `.env` 中的 `DEEPSEEK_BASE`（默认：https://api.deepseek.com/v1）

## 许可证

MIT
