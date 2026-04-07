# Open-Todo (OTD)

> [English](./README.md)

**AI 原生任务基础设施 — 技术白皮书**

---

## 🚀 项目愿景与核心架构

Open-Todo 不是又一个任务管理工具。它是从底层为程序化消费而设计的**工业级任务基础设施**——服务于 AI Agent、自动化流水线和人类开发者。

三大基础支柱定义了整体架构：

### 无限层级 WBS（工作分解结构）

任务通过邻接表自引用（`Todo.parentId` -> `Todo.todoId`）形成**无界树**。没有深度限制。一个项目可以从顶层史诗级任务一直建模到跨越任意嵌套层级的原子子任务。

- **重新挂载**: `move_todo` 将节点（及其整个子树）迁移到新的父节点。基于 BFS 的循环引用检测防止树结构损坏。
- **级联删除**: `delete_todo` 执行 BFS 后代收集并移除整个子树。每个被删除的节点都会写入独立的发件箱记录用于 Webhook 通知——杜绝静默数据丢失。

### 动态 Schema 引擎

每个项目在运行时通过 `fieldsDefinition` 定义自己的数据模型——一个字段描述符数组，支持 6 种类型：

| 字段类型 | 存储 | 默认值（JIT 自愈） |
|---------|------|-------------------|
| `text` | 字符串 | `""` |
| `number` | 数字 | `0` |
| `date` | 字符串 (ISO) | `""` |
| `enum` | 字符串 | `enumValues` 的第一个条目 |
| `link` | 字符串 (URL) | `""` |
| `assignee` | 字符串 | `""` |

每次 `create_todo` 和 `update_todo` 都会在持久化前验证提交的 `content` 是否符合项目 Schema。无效字段名或类型不匹配将被 `422` 拒绝。

这意味着 CRM 流水线、Sprint 看板和招聘追踪器可以在同一个 OTD 实例中共存，拥有完全不同的字段结构——无需迁移，无需改代码。

### 仅 POST 变更契约

**没有 PATCH。没有 PUT。没有 DELETE。** 所有变更操作使用 `POST`。所有标识符通过 JSON 请求体传递，绝不放在 URL 路径参数中。这消除了 HTTP 动词歧义，使 AI Agent 的载荷构造完全确定性化。

即使是带过滤条件的读取端点（如 `/todos/list`）也使用 POST 来接受结构化查询体。只有简单的无参数读取使用 GET。

---

## 🛡️ 数据演进哲学：JIT Healing（即时自愈）

Schema 变更不可避免。在传统系统中，添加或删除字段意味着运行迁移脚本、回填数据或接受不一致。Open-Todo 采取了不同的策略：**JIT Healing（即时自愈）**。

### 问题所在

当项目 Schema 变更时（例如新增了一个 `priority` 枚举字段），已有的 Todo 没有该字段的值。读取它们会产生不完整的数据。传统解决方案：

- **迁移脚本**: 停机、批处理、脆弱。
- **全面允许 Null**: 将复杂度推给每个消费者。
- **Schema 版本化 + 转换器**: 沉重的基础设施。

### OTD 的解决方案

每个 Todo 在创建/更新时标记其 `schemaVersion`。项目 Schema 维护一个单调递增的 `schemaVersion`，每次 Schema 更新时自动递增。

当读取一个 Todo 且其 `schemaVersion` < 项目当前 `schemaVersion` 时，OTD 应用 **JIT Healing**：

1. **读取时（list/get）**: 使用类型适配的默认值（见上表）**在内存中**补丁缺失字段。数据库不被触碰。消费者看到的是完整的对象。

2. **写入时（update）**: 先对内容进行自愈，然后将用户的变更合并在自愈结果之上，最终连同当前 `schemaVersion` 一起持久化。旧数据作为下一次写入的副作用被**物理升级**。

### 特性

- **零停机**: 无迁移步骤。Schema 变更即时生效。
- **透明**: 消费者始终看到完整的、符合 Schema 的对象。
- **保守**: 自愈仅填充缺失字段，绝不覆盖已有值。
- **惰性物理升级**: 数据仅在下次被写入时就地升级，避免不必要的 I/O。

---

## 🤖 AI 操控与 MCP 接入指南

Open-Todo 实现了标准的 **MCP Streamable HTTP 传输协议**（[2025-03-26 规范](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports#streamable-http)）——Claude Code、OpenCode、Cursor、VS Code Copilot 等 MCP 客户端所使用的标准 JSON-RPC 2.0 协议。

### 协议机制

**主端点**（标准 MCP Streamable HTTP）：

| 端点 | 方法 | 认证 | 用途 |
|------|------|------|------|
| `/mcp` | POST | 视方法而定 | JSON-RPC 2.0 分发——`initialize`、`tools/list`、`tools/call`、`ping` |
| `/mcp` | GET | — | 返回 405（不提供服务端发起的 SSE 流） |

- `initialize`、`ping` 和 `tools/list` **无需认证**。
- `tools/call` 需要 `X-API-KEY` 请求头。
- 工具调用错误通过 JSON-RPC 结果中的 `isError: true` 返回，而非 HTTP 错误码。这防止 AI 客户端将 HTTP 层错误与业务层错误混淆。

**旧版端点**（保留向后兼容）：

| 端点 | 方法 | 认证 | 用途 |
|------|------|------|------|
| `/mcp/tools` | GET | 无 | 工具发现 |
| `/mcp/tools/call` | POST | `X-API-KEY` | 工具调用 |

### 可用工具（14 个）

| # | 工具 | 说明 |
|---|------|------|
| 1 | `list_projects` | 列出用户拥有的所有项目 |
| 2 | `create_project` | 创建新项目 |
| 3 | `update_project` | 更新项目元数据（名称、描述、目录、Git URL） |
| 4 | `get_project_schema` | 获取项目的动态字段 Schema |
| 5 | `update_project_schema` | 替换项目的字段 Schema |
| 6 | `list_todos` | 列出项目的所有 Todo，省略 `projectId` 时返回所有项目的 Todo |
| 7 | `create_todo` | 创建 Todo，内容经过 Schema 验证 |
| 8 | `update_todo` | 更新内容/状态，支持 OCC 和深度差异比较 |
| 9 | `move_todo` | 在项目内重新挂载 Todo |
| 10 | `delete_todo` | 递归删除 Todo 及其所有后代 |
| 11 | `bulk_create_todos` | 在单个事务中批量创建多个 Todo |
| 12 | `list_members` | 列出项目中注册的所有成员（Agent） |
| 13 | `add_member` | 将 Agent 添加为项目成员 |
| 14 | `remove_member` | 从项目中移除成员（Agent） |

> **注意**: Webhook 规则、Webhook 投递日志和邮件通知规则通过 Web 后台管理，不作为 MCP 工具暴露。

### AI Agent 认证

Open-Todo 使用前缀为 `sk-otd-` 的 API 密钥进行所有程序化访问。密钥通过 `X-API-KEY` HTTP 头传递。

**获取密钥**:
1. 通过 Web UI 或 `POST /auth/register` 注册账户。
2. 通过收件箱中的链接验证邮箱。
3. 登录后在密钥管理页面创建 API 密钥。完整密钥**仅显示一次**。

### MCP 客户端配置

#### Claude Code（CLI `claude`）

在项目的 `.mcp.json` 中：

```json
{
  "mcpServers": {
    "open-todo": {
      "type": "url",
      "url": "http://localhost:9000/mcp",
      "headers": {
        "X-API-KEY": "sk-otd-your-api-key-here"
      }
    }
  }
}
```

或使用环境变量实现静默认证：

```json
{
  "mcpServers": {
    "open-todo": {
      "type": "url",
      "url": "http://localhost:9000/mcp",
      "headers": {
        "X-API-KEY": "${OTD_API_KEY}"
      }
    }
  }
}
```

启动前在 Shell 中设置 `export OTD_API_KEY=sk-otd-...`。

#### VS Code（Claude Desktop / Copilot）

在 `.vscode/mcp.json` 中：

```json
{
  "servers": {
    "open-todo": {
      "type": "url",
      "url": "http://localhost:9000/mcp",
      "headers": {
        "X-API-KEY": "${OTD_API_KEY}"
      }
    }
  }
}
```

#### OpenCode

在项目的 `opencode.json` 或 `~/.opencode/config.json` 中：

```json
{
  "mcp": {
    "open-todo": {
      "type": "remote",
      "url": "http://localhost:9000/mcp",
      "headers": {
        "X-API-KEY": "{env:OTD_API_KEY}"
      }
    }
  }
}
```

> **注意**: OpenCode 使用 `{env:VAR_NAME}` 语法进行环境变量插值，而非 `${VAR_NAME}`。

#### Cursor / Continue

添加到你的 MCP 配置文件（如 `.cursor/mcp.json` 或等效位置）：

```json
{
  "mcpServers": {
    "open-todo": {
      "type": "url",
      "url": "http://localhost:9000/mcp",
      "headers": {
        "X-API-KEY": "${OTD_API_KEY}"
      }
    }
  }
}
```

**要点**:
- 环境变量语法因客户端而异：OpenCode 使用 `{env:VAR_NAME}`，Claude Code / VS Code / Cursor 使用 `${VAR_NAME}`。
- 实际密钥永远不会出现在纳入版本控制的配置文件中。
- `/mcp` 端点处理完整的 MCP 协议——客户端**无需**追加 `/tools` 或 `/tools/call`。
- 工具发现（`tools/list`）无需认证，因此客户端可以在配置任何密钥之前枚举可用工具。

### 人类专属 vs. AI 可访问的边界

OTD 执行明确的安全边界：

| 域 | 端点 | 认证 | 访问权限 |
|----|------|------|---------|
| 认证与注册 | `/auth/*` | 会话令牌 | 仅人类 |
| API 密钥管理 | `/keys/*` | 会话令牌 | 仅人类 |
| Webhook 规则与日志 | `/webhooks/*`、`/automation/*` | 会话令牌 | 仅人类 |
| 邮件通知规则 | `/notifications/*` | 会话令牌 | 仅人类 |
| 全部 10 个 MCP 工具 | `POST /mcp` | API 密钥 (`X-API-KEY`) | AI Agent |
| REST API（CRUD） | `/projects/*`、`/todos/*` 等 | API 密钥 (`X-API-KEY`) | AI + 人类 |

这意味着 AI Agent **不能**注册账户、创建 API 密钥、配置 Webhook 目标地址或管理通知规则。这些特权操作需要人类通过会话令牌登录。

---

## 📡 可靠性模型与自动化

### 事务性发件箱模式

Webhook 投递**绝非发后即忘**。当 Todo 被创建、更新或删除时，对应的 `WebhookTask` 发件箱记录在**与数据变更相同的数据库事务中**插入。如果提交成功，Webhook 任务就存在。如果失败，数据变更和 Webhook 任务都不会持久化。这保证了通知的**恰好一次意图**。

**Worker 机制**:
- 每 **5 秒**轮询一次，每轮批处理上限 **100 个任务**。
- HTTP 投递超时：**15 秒**。
- **5 次重试**，指数退避间隔：2、4、8、16 分钟。
- 任务状态：`pending` -> `success` | `failed`。
- 最终失败时（5 次重试全部耗尽）：入队 `WebhookFailure` 邮件告警。

### 多模态通知

OTD 支持两种互补的通知渠道：

**1. 被动推送 — Webhooks**

项目级规则定义哪些事件（`todo.created`、`todo.updated`、`todo.deleted`）触发 HTTP POST 回调到外部 URL。载荷包含完整的 `before`/`after` 深度差异快照。

**2. 主动报告 — 邮件通知**

用户级规则选择性订阅 4 种事件类型的邮件告警：

| 事件类型 | 优先级 | 说明 |
|---------|--------|------|
| `TaskCreate` | 普通 | 有 Todo 被创建 |
| `TaskUpdate` | 普通 | 有 Todo 被更新 |
| `TaskDelete` | 普通 | 有 Todo 被删除 |
| `WebhookFailure` | 高 | Webhook 投递在最大重试后永久失败 |

邮件投递使用独立的 `EmailTask` 发件箱，具有相同的事务性保证、优先级队列（高 > 普通 > 低）和重试机制。三个 Jinja2 HTML 模板驱动邮件渲染。

第 5 种事件类型 `Verification` 在注册时始终以高优先级发送，不受通知规则控制。

**开关**: 邮件投递默认禁用。在 `.env` 中设置 `MAIL_ENABLED=true` 并配置 SMTP 凭证以激活。

---

## 🔐 身份中心与凭证管理

### 双层认证

OTD 将人类认证和机器认证分离：

| 层级 | 请求头 | 前缀 | 用途 |
|------|--------|------|------|
| 会话令牌 | `X-SESSION-TOKEN` | `ses-` | Web 登录、密钥管理、Webhook 配置 |
| API 密钥 | `X-API-KEY` | `sk-otd-` | 程序化访问、MCP 工具、REST API |

### 多密钥架构

每个用户可以创建**多个 API 密钥**，各自拥有独立的生命周期。这使得：

- **Agent 隔离**: 给每个 AI Agent（Claude、GPT、Cursor）分配独立的密钥。
- **密钥轮换**: 创建新密钥，更新 Agent 配置，禁用旧密钥——零停机。
- **审计追踪**: 密钥级别的访问跟踪。

**密钥生命周期**:

```
创建 (sk-otd-... 仅显示一次)
  -> 激活 (is_enabled=true, is_deleted=false)
  -> 禁用 (is_enabled=false, is_deleted=false)   [可逆]
  -> 软删除 (is_enabled=false, is_deleted=true)  [不可逆]
```

列出密钥时，API 返回**脱敏值**：前 12 个字符 + `...` + 后 4 个字符。完整密钥仅在创建时显示。

### 注册流程

1. `POST /auth/register` 传入 `email`、`password` 和 `captchaId`/`captchaCode`。
2. 发送验证邮件（如果 `MAIL_ENABLED=true`）。
3. 用户点击邮件中的链接 -> `GET /auth/verify?token=xxx` 激活账户。
4. 未验证用户登录将被 `403` 阻止。

---

## 🏗️ 快速开始

### Docker Compose（推荐）

```bash
git clone <repo-url> && cd open-todo
cp .env.example .env   # 如需邮件功能请编辑 SMTP 设置
docker compose up --build
```

- **API**: http://localhost:9000
- **Web**: http://localhost:3030
- **API 文档**: http://localhost:9000/docs

### 本地开发

**API**:
```bash
pip install -r api/requirements.txt
uvicorn api.app.main:app --host 0.0.0.0 --port 9000 --reload
```

**Web**:
```bash
cd web
npm install
npm run dev   # 代理 /api -> localhost:9000
```

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `sqlite:///./otd.db` | 数据库连接字符串 |
| `SMTP_HOST` | — | SMTP 服务器主机名 |
| `SMTP_PORT` | `587` | SMTP 服务器端口 |
| `SMTP_USERNAME` | — | SMTP 登录用户名 |
| `SMTP_PASSWORD` | — | SMTP 登录密码 |
| `SMTP_USE_TLS` | `true` | 启用 STARTTLS |
| `MAIL_FROM_ADDRESS` | — | 发件人邮箱地址 |
| `MAIL_FROM_NAME` | — | 发件人显示名称 |
| `MAIL_ENABLED` | `false` | 启用邮件投递 |
| `APP_BASE_URL` | `http://localhost:9000` | API 基础 URL |
| `WEB_BASE_URL` | `http://localhost:3030` | Web 基础 URL（用于邮件链接） |

---

## 🔄 CI/CD

Open-Todo 使用 GitHub Actions 进行持续集成与部署。工作流定义在 `.github/workflows/deploy.yml`。

### 流水线概览

```
Pull Request（任意分支）              Push 到 main
        │                                │
        ▼                                ▼
  ┌───────────┐                    ┌───────────┐
  │ api-test  │                    │ api-test  │
  │ web-test  │                    │ web-test  │
  └───────────┘                    └─────┬─────┘
        │                                │
     (结束)                              ▼
                                   ┌───────────┐
                                   │  deploy   │
                                   └───────────┘
```

- **Pull Request** — 仅触发 Lint & 测试（不部署）。
- **Push 到 main** — 先执行 Lint & 测试，通过后 SSH 部署到服务器。

### 各任务说明

| 任务 | 目录 | 步骤 |
|------|------|------|
| `api-test` | `api/` | 安装 Python 3.11 依赖、导入检查、`pytest` |
| `web-test` | `web/` | 安装 Node 20 依赖、`vue-tsc` 类型检查、`npm run build` |
| `deploy` | — | SSH 登录服务器、自动执行 `git clone`/`pull`、注入 Secrets 到 `.env`、执行 `docker compose up -d --build` |

### 必需的 GitHub Secrets

部署任务运行前，需在 **Settings > Secrets and variables > Actions** 中配置以下密钥：

| Secret | 说明 | 必填 |
|--------|------|------|
| `DEPLOY_HOST` | 服务器 IP 或域名 | 是 |
| `DEPLOY_USER` | SSH 用户名（该用户必须在 `docker` 用户组中） | 是 |
| `DEPLOY_SSH_KEY` | SSH 私钥（完整 PEM 内容） | 是 |
| `DEPLOY_PATH` | 项目在服务器上的绝对路径 | 是 |
| `DEPLOY_PORT` | SSH 端口（默认 22） | 否 |
| `DATABASE_URL` | 生产环境数据库 URL | 否 |
| `MAIL_ENABLED` | 设为 "true" 启用 SMTP | 否 |
| `SMTP_*` | `SMTP_HOST`、`SMTP_PORT`、`SMTP_USERNAME`、`SMTP_PASSWORD`、`SMTP_USE_TLS` | 否 |
| `PIP_INDEX_URL`| 自定义 Pip 源（如清华源 `https://pypi.tuna.tsinghua.edu.cn/simple/`）加速 Docker 构建 | 否 |

### 服务器准备

在目标服务器上确保：

1. 已安装 **Docker** 和 **Docker Compose**。
2. 配置在 `DEPLOY_USER` 中的用户已被加入 `docker` 用户组：
   ```bash
   sudo usermod -aG docker <your-deploy-user>
   ```

> **注意**：部署脚本会自动检测 `DEPLOY_PATH`。如果目录为空，它会自动帮你克隆代码；它也会在执行 Docker 之前安全地将 Secrets 注入到 `.env` 文件中。另外，首次启动时系统初始化的默认管理员账号为 `admin` / `admin123`。部署成功后请务必**第一时间登录并修改密码**！

#### 替代方案：非 Docker 部署（系统原生部署）
如果您不想使用 Docker，请确保目标服务器上已安装 Python 3.11+ 和 Node 20+。您需要修改 `.github/workflows/deploy.yml`，移除 Docker 相关命令，并恢复手动的构建步骤（例如：使用 `venv` 安装 `pip` 依赖、运行 `npm run build` 构建前端，并使用 `pm2` 或 `systemd` 重启服务）。

### 本地运行 CI 检查

推送前可在本地复现 CI 检查：

```bash
# API
pip install -r api/requirements.txt
python -c "from api.app.main import app; print('OK')"
python -m pytest api/ -v

# Web
cd web
npm install
npx vue-tsc -b
npm run build
```

---

## 🧩 技术栈

| 层级 | 技术 |
|------|------|
| API | Python 3.11+、FastAPI、SQLModel、Pydantic v2、httpx |
| Web | Vue 3、TypeScript (strict)、Vite、Tailwind CSS、Naive UI |
| 数据库 | SQLite（默认）、JSON 列存储动态内容 |
| 部署 | Docker Compose（API `:9000`、Web `:3030`） |

---

## 📁 项目结构

```
open-todo/
├── api/                      # API 服务
│   ├── app/
│   │   ├── main.py           # FastAPI 入口 + 生命周期（Worker）
│   │   ├── api/              # 路由模块
│   │   │   ├── auth.py       # 注册、登录、验证、验证码
│   │   │   ├── api_keys.py   # 多密钥增删改查（会话认证）
│   │   │   ├── projects.py   # 项目增删改查
│   │   │   ├── schemas.py    # 动态 Schema 获取/更新
│   │   │   ├── todos.py      # Todo 增删改查 + JIT 自愈 + 发件箱
│   │   │   ├── webhooks.py   # Webhook 规则增删改查
│   │   │   ├── automation.py # Webhook 日志 + 重试
│   │   │   ├── mcp.py        # MCP 工具定义（10 个工具）
│   │   │   └── notifications.py  # 邮件通知规则
│   │   ├── core/             # 基础设施
│   │   │   ├── config.py     # 环境变量、常量
│   │   │   ├── database.py   # 引擎、会话、外键 Pragma
│   │   │   ├── auth.py       # get_current_user / get_session_user
│   │   │   ├── healer.py     # JIT 自愈引擎
│   │   │   ├── validator.py  # Schema 验证
│   │   │   ├── email.py      # 邮件入队 + SMTP 发送
│   │   │   └── captcha.py    # 基于数据库的验证码
│   │   ├── models/
│   │   │   └── models.py     # 全部 SQLModel ORM 定义
│   │   ├── worker/
│   │   │   ├── base.py       # BaseOutboxWorker 抽象基类
│   │   │   ├── outbox.py     # Webhook 投递 Worker
│   │   │   └── email_worker.py  # 邮件投递 Worker
│   │   └── templates/email/  # Jinja2 邮件模板
│   ├── Dockerfile
│   └── requirements.txt
├── web/                      # Web 应用
│   ├── src/
│   │   ├── api/              # Axios HTTP 客户端
│   │   ├── components/       # TodoTreeRow、DynamicFieldRenderer
│   │   ├── composables/      # 单例状态（useProject、useTodos）
│   │   ├── views/            # 所有页面视图
│   │   ├── types/            # TypeScript 接口定义
│   │   └── router/           # Vue Router 配置
│   ├── nginx.conf        # Nginx 代理及 SPA 路由配置文件
│   ├── Dockerfile
│   └── package.json
├── skills/                   # AI Skill 定义文件
│   └── open-todo/            # Open-Todo 相关 Skill
│       ├── open-todo-projects.md # 项目管理器 Skill
│       ├── open-todo-schemas.md  # Schema 设计器 Skill
│       ├── open-todo-tasks.md    # 任务管理器 Skill
│       ├── SKILL.md              # Skill 清单与集成指南
│       └── README.md             # Skill 编写指南
├── docker-compose.yml
├── AGENTS.md                 # AI Agent 编码规范
└── .env.example              # 环境变量模板
```

> **API 详情**: 见 [api/README.zh-CN.md](./api/README.zh-CN.md)
> **Web 详情**: 见 [web/README.zh-CN.md](./web/README.zh-CN.md)

---

## 📜 许可证

[Apache License 2.0](./LICENSE)
