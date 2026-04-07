# Open-Todo Web

> [English](./README.md) | [返回项目根目录](../README.zh-CN.md)

Open-Todo 的 Vue 3 Web 应用——暗色主题 WBS 树表格界面，支持动态字段渲染、Schema 编辑、验证码登录/注册、API 密钥管理、邮箱验证和 Webhook 自动化仪表板。

---

## 环境要求

- Node.js 20+
- npm

## 安装

```bash
npm install
```

## 运行

### 开发服务器

```bash
npm run dev
```

开发服务器启动在 `http://localhost:3000`。`/api/*` 请求会代理到 `http://localhost:9000`（API 服务需要先启动）。

### 生产构建

```bash
npm run build
```

先运行 `vue-tsc` 类型检查，再执行 `vite build` 生产打包。输出到 `dist/` 目录。

### 仅类型检查

```bash
npx vue-tsc -b
```

### Docker

从项目根目录：

```bash
docker compose up --build web
```

`web` 服务构建 Vue 应用后通过 Nginx 在 3000 端口提供服务。Nginx 将 `/api/*` 请求代理到 `api` 服务。

---

## 模块结构

```
web/
├── src/
│   ├── main.ts                    # Vue 应用启动（Pinia、Naive UI、Router）
│   ├── App.vue                    # 根组件（认证覆盖层 + 导航框架）
│   ├── style.css                  # Tailwind 指令 + 基础样式
│   ├── api/
│   │   └── index.ts               # Axios 客户端、全部 API 函数、X-API-KEY + X-SESSION-TOKEN 拦截器
│   ├── components/
│   │   ├── TodoTreeRow.vue        # 单行 WBS 树表格（展开、缩进、操作按钮）
│   │   └── DynamicFieldRenderer.vue  # 按类型渲染字段值（标签、链接、头像等）
│   ├── composables/
│   │   ├── useProject.ts          # 共享项目 + Schema 状态（单例 ref 模式）
│   │   └── useTodos.ts            # 共享任务树状态 + CRUD 操作
│   ├── router/
│   │   └── index.ts               # Vue Router（5 个路由，懒加载视图）
│   ├── types/
│   │   └── index.ts               # 与 API 响应对应的 TypeScript 接口定义
│   ├── utils/
│   │   └── treeBuilder.ts         # 扁平列表 <-> 嵌套树转换
│   └── views/
│       ├── ProjectListView.vue    # 项目列表 + 创建表单
│       ├── ProjectDetailView.vue  # WBS 树表格 + Schema 编辑器弹窗 + 任务增删改
│       ├── AutomationView.vue     # Webhook 规则 + 投递审计日志 + 重试
│       ├── KeyManagementView.vue  # API 密钥增删改查（创建、重命名、启用/禁用、删除）
│       └── EmailVerifyView.vue    # 邮箱验证页面（公开页面，无需登录）
├── index.html
├── vite.config.ts                 # Vite 配置（3000 端口，/api 代理到 :9000）
├── tsconfig.json                  # TypeScript strict 模式，@/* 路径别名
├── tailwind.config.js             # Tailwind 配置，class-based 暗色模式
├── postcss.config.js              # PostCSS + Tailwind + Autoprefixer
├── Dockerfile                     # 多阶段构建：Node 构建 + Nginx 部署
└── package.json
```

## 路由

| 路径 | 名称 | 视图 | 认证 | 说明 |
|------|------|------|------|------|
| `/` | `projects` | `ProjectListView` | 会话 | 浏览项目、创建新项目 |
| `/project/:id` | `project-detail` | `ProjectDetailView` | 会话 | WBS 树表格、Schema 编辑器、任务增删改 |
| `/project/:id/automation` | `automation` | `AutomationView` | 会话 | Webhook 规则、投递日志、重试 |
| `/keys` | `key-management` | `KeyManagementView` | 会话 | API 密钥创建、重命名、启用/禁用、删除 |
| `/verify` | `email-verify` | `EmailVerifyView` | 公开 | 通过 `?token=xxx` 验证邮箱 |

## 核心架构

- **组合式 API**：所有组件使用 `<script setup lang="ts">`。
- **单例状态**：Composable 使用模块作用域 `ref()` 实现共享状态（未使用 Pinia store，尽管 Pinia 已安装）。
- **双层认证**：Web 端使用会话令牌（`X-SESSION-TOKEN` 请求头，存储在 `localStorage`）进行所有 API 调用。API 密钥（`X-API-KEY` 请求头）也会附加到程序化端点。两个请求头均通过 Axios 请求拦截器注入。
- **仅 POST 变更**：所有变更通过 POST 请求发送 camelCase JSON 体。
- **动态渲染**：`DynamicFieldRenderer` 根据字段类型自动选择 UI（枚举→`NTag`、链接→超链接、负责人→`NAvatar`、日期→格式化字符串、数字→等宽字体）。
- **树构建**：API 返回的扁平任务列表在客户端通过 `treeBuilder.ts` 转换为嵌套树。展开状态在数据刷新时保留。
- **轮询**：`ProjectDetailView` 每 10 秒自动刷新任务数据。
- **暗色主题**：默认暗色主题（`<html class="dark">`），gray-950 背景，gray-900 卡片，blue-400 强调色。全局应用 Naive UI `darkTheme`。
- **验证码**：登录和注册均需在提交前完成图形验证码验证。

## 视图详情

### ProjectListView
浏览所有用户项目。可折叠的新项目创建表单。点击进入 WBS 树。显示项目名称、描述、目录、Git URL、自动化链接和截断的项目 ID。

### ProjectDetailView
完整的 WBS 树表格，动态列标题来自 Schema 字段。支持展开/折叠、任务增删改查（创建根/子任务、编辑、确认删除）、完成状态切换、Schema 编辑器弹窗（字段类型下拉和枚举值管理）。10 秒自动轮询。

### AutomationView
Webhook 规则管理：创建规则（事件类型、目标字段、Webhook URL）。审计日志时间线，显示状态标签、重试次数、错误信息，以及失败投递的一键重试。

### KeyManagementView
创建、重命名、启用/禁用和软删除 API 密钥。完整密钥值仅在创建时显示一次（带复制按钮和警告）。列表中显示脱敏值。第一个创建的密钥自动存储在 localStorage 中用于 API 访问。

### EmailVerifyView
公开页面（无需登录）。从 URL 读取 `?token=xxx`，调用 `GET /auth/verify`，显示成功（绿色勾号 + 邮箱）或错误状态，带有"去登录"按钮。

## 依赖

### 运行时
- `vue@^3.5.0`
- `vue-router@^4.4.0`
- `pinia@^2.2.0`
- `naive-ui@^2.39.0`
- `axios@^1.7.0`

### 开发
- `vite@^6.0.0`
- `vue-tsc@^2.1.0`
- `typescript@~5.6.0`
- `tailwindcss@^3.4.0`
- `@vitejs/plugin-vue@^5.1.0`
- `postcss@^8.4.47`
- `autoprefixer@^10.4.20`

---

> [返回项目根目录](../README.zh-CN.md)
