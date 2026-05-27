# AloFootMind — 多智能体足球赛事分析系统

基于 LangGraph 多智能体 + RAG 的足球赛事分析平台，使用 StatsBomb Open Data 作为数据来源。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue3 + TypeScript + TailwindCSS + Fetch SSE + markdown-it |
| 后端 | Python + FastAPI |
| 存储 | PostgreSQL + Redis + Milvus |
| AI | LangGraph + LangChain + DeepSeek + GPT-4o + BAAI/bge-m3 |

## 快速启动

### 1. 启动基础设施

```bash
docker-compose up -d
```

### 2. 配置环境变量

```bash
cp backend/.env.example backend/.env
# 编辑 .env，填入 API keys 和 StatsBomb 数据路径
```

### 3. 安装后端依赖

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. 初始化数据库 & 导入数据

```bash
# 初始化 PostgreSQL 表结构和 Milvus Collections
python -m app.db.init

# 导入 StatsBomb 数据（以英超为例，competition_id=2）
python scripts/ingest.py --competition_id 2
```

### 5. 启动后端

```bash
uvicorn app.main:app --reload --port 8000
```

### 6. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端默认运行在 http://localhost:5173，后端 API 在 http://localhost:8000

## 核心功能

- **赛后复盘**：选择一场比赛，触发 AI 战术分析，实时查看 Agent 执行进度
- **对阵情报**：选择两支球队，生成基于历史数据的战前情报报告
- **智能问答**：自然语言查询足球数据，RAG 驱动精准回答

## 项目结构

```
AloFootMind/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI 路由
│   │   ├── agents/       # LangGraph Agent 定义
│   │   ├── etl/          # 数据管道
│   │   ├── db/           # 数据库模型与连接
│   │   └── services/     # RAG、存储等服务
│   ├── scripts/
│   │   └── ingest.py     # ETL CLI
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── views/        # 页面组件
│       ├── components/   # 通用组件
│       ├── composables/  # Vue3 组合式函数
│       └── api/          # API 客户端
└── docker-compose.yml
```
