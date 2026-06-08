# AloFootMind 前端

基于 Vue 3 + TypeScript + Vite 的足球分析前端应用。

## 功能特性

- **比赛列表**：浏览所有比赛，支持分页
- **比赛详情**：查看比分、阵容、关键事件、统计数据，触发赛后分析
- **赛后分析**：触发 AI 战术分析，SSE 流式实时显示 Agent 执行过程
- **赛前分析**：球队对阵分析与预测，生成战前情报报告
- **智能问答**：基于 RAG 的语义搜索问答，支持多轮对话与流式回答中断
- **聊天历史**：最多 10 条会话，支持重命名、删除，新聊天自动创建会话
- **用户认证**：注册/登录/邮箱验证/密码重置，未登录时弹窗引导
- **多语言**：中文/英文切换，所有 UI 文本通过 i18n 管理
- **通用确认对话框**：可复用的 ConfirmDialog 组件（用于删除/清空确认）

## 技术栈

- **框架**：Vue 3.5 + TypeScript
- **构建工具**：Vite 8
- **路由**：Vue Router 4
- **状态管理**：Pinia（auth、chat sessions）
- **UI 样式**：TailwindCSS 3
- **国际化**：vue-i18n
- **Markdown 渲染**：markdown-it
- **SSE 流式传输**：自定义 composable

## 环境要求

- Node.js 20+
- npm 或 pnpm

## 快速开始

### 1. 安装依赖

```bash
npm install
```

### 2. 开发模式

```bash
npm run dev
```

访问 `http://localhost:5173`

### 3. 生产构建

```bash
npm run build
```

构建产物输出到 `dist/` 目录

## 项目结构

```
frontend/
├── src/
│   ├── api/
│   │   └── index.ts          # API 客户端封装
│   ├── components/
│   │   ├── AgentViewer.vue   # Agent 执行过程可视化
│   │   ├── AppLayout.vue     # 应用布局（含侧边栏导航与聊天会话列表）
│   │   ├── AuthModal.vue     # 未登录提示模态框
│   │   ├── ConfirmDialog.vue # 通用确认对话框
│   │   └── ReportViewer.vue  # Markdown 报告渲染
│   ├── composables/
│   │   ├── useMarkdown.ts    # Markdown 渲染
│   │   └── useSseStream.ts   # SSE 流式传输 hook（支持 AbortController 中断）
│   ├── i18n/
│   │   ├── en.ts             # 英文翻译
│   │   └── zh.ts             # 中文翻译
│   ├── stores/
│   │   ├── auth.ts           # 用户认证状态（Token 刷新、自动持久化）
│   │   └── chat.ts           # 聊天会话状态（CRUD、列表排序）
│   ├── router/
│   │   └── index.ts          # 路由配置（含 /chat/:id 会话路由）
│   ├── style.css             # 全局样式
│   ├── App.vue               # 根组件
│   └── main.ts               # 入口文件
├── public/
├── index.html
├── vite.config.ts
├── tsconfig.json
└── package.json
```

## 页面说明

### 比赛列表 (`/matches`)
- 显示所有比赛列表
- 支持分页加载
- 点击进入比赛详情

### 比赛详情 (`/matches/:id`)
- 比赛比分、时间、球场信息
- 双方阵容
- 关键事件（进球、红黄牌）
- 统计数据（射门、传球、犯规）
- 触发赛后分析按钮
- Agent 执行过程实时展示
- 分析报告 Markdown 渲染

### 赛前分析 (`/pre-match`)
- 选择两支球队进行赛前分析
- 实时显示 Agent 执行过程
- 展示分析报告

### 智能问答 (`/chat` 与 `/chat/:id`)
- 基于比赛数据的语义搜索，RAG 驱动精准回答
- 多轮对话，支持 SSE 流式传输
- 发送第一条消息时自动创建会话并跳转到 `/chat/:id`
- 流式回答过程中可随时点击「中断」停止生成
- 已保存的历史会话自动加载到侧边栏，支持重命名/删除

### 登录 (`/login`)
- 邮箱 + 密码登录
- 未登录用户访问需要认证的页面时自动弹出 AuthModal

### 注册 (`/register`)
- 邮箱注册，发送 6 位数字验证码
- 验证通过后方可登录

### 密码重置 (`/forgot-password`)
- 通过邮箱发送重置验证码
- 输入验证码后设置新密码

## API 配置

API 基础路径在 `src/api/index.ts` 中配置：

```typescript
const BASE_URL = ''
```

当前配置为相对路径（请求走当前域名），适用于前后端同域部署。如需代理到本地后端开发环境，在 `vite.config.ts` 中配置 `server.proxy`：

```typescript
server: {
  proxy: {
    '/api': 'http://localhost:8000'
  }
}
```

## 国际化

默认语言：中文

切换语言在 `src/i18n/index.ts` 中配置，支持：
- `zh` - 中文
- `en` - 英文

添加新翻译：
1. 在 `src/i18n/zh.ts` 添加中文键值
2. 在 `src/i18n/en.ts` 添加英文键值
3. 在组件中使用 `t('key')` 调用

## 开发

### 代码检查

```bash
npm run lint
```

### 类型检查

```bash
npm run type-check
```

## Docker 部署

### 构建前端镜像

```bash
docker build -t alofootmind-frontend .
```

### 使用 Docker Compose 运行

```bash
cd ..
docker compose --profile full up -d
```

前端通过 Nginx 服务在 `http://localhost`，API 请求代理到后端 `http://localhost:8000`。

## 常见问题

### API 请求失败
- 确认后端服务运行在 `http://localhost:8000`
- 检查 CORS 配置是否包含前端 URL
- 查看浏览器控制台网络请求状态

### SSE 流式连接断开
- 检查后端 SSE 端点是否正常
- 确认网络连接稳定
- 查看浏览器控制台 SSE 错误信息

### 样式不生效
- 确认 TailwindCSS 配置正确
- 检查 `style.css` 是否被引入
- 清除浏览器缓存重试

## 许可证

MIT
