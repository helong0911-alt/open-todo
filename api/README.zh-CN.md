# Open-Todo API

> [English](./README.md) | [返回项目根目录](../README.zh-CN.md)

Open-Todo 的 FastAPI API 服务——AI 原生任务基础设施，支持动态 Schema、JIT 自愈、事务性发件箱（Webhook + 邮件）、MCP Streamable HTTP 传输协议和双层认证。

---

## 环境要求

- Python 3.11+
- pip

## 安装

```bash
pip install -r requirements.txt
```

## 运行

### 开发服务器

```bash
uvicorn api.app.main:app --host 0.0.0.0 --port 9000 --reload
```

服务启动在 `http://localhost:9000`。交互式 API 文档在 `/docs`（Swagger）和 `/redoc`。

### Docker

从项目根目录：

1. 创建你的环境变量文件：
   ```bash
   cp .env.example .env
   # 编辑 .env，设置你的 SMTP_PASSWORD 等信息
   nano .env
   ```
   > **注意**：首次初始化的默认管理员账号为 `admin` / `admin123`。部署成功后请务必第一时间登录并修改密码！

2. 启动服务：
   ```bash
   docker compose up --build api
   ```

`api` 服务监听 9000 端口。SQLite 数据库持久化在 Docker 卷 `/app/data/otd.db`。

### 导入检查

快速验证所有模块是否正确解析：

```bash
python -c "from api.app.main import app; print('OK')"
```

## 运行测试

```bash
python -m pytest api/ -v                                  # 全部测试
python -m pytest api/tests/test_todos.py -v               # 单个文件
python -m pytest api/tests/test_todos.py::test_create_todo -v  # 单个函数
```

---

## 模块结构

```
api/
├── app/
│   ├── main.py               # FastAPI 入口，生命周期（数据库初始化 + Worker）
│   ├── api/                   # 路由模块
│   │   ├── auth.py            # POST /auth/captcha, /login, /register, /logout; GET /auth/verify
│   │   ├── api_keys.py        # POST /keys/create, /list, /update, /delete（会话认证）
│   │   ├── projects.py        # GET /projects, POST /projects/create
│   │   ├── schemas.py         # POST /projects/schema/get, /projects/schema/update
│   │   ├── todos.py           # POST /todos/list, /create, /update, /move, /delete, /bulk-create
│   │   ├── webhooks.py        # POST /webhooks/create, /list, /tasks
│   │   ├── automation.py      # POST /automation/webhook/logs, /webhook/retry
│   │   ├── mcp.py             # POST /mcp（Streamable HTTP）；旧版 GET /mcp/tools, POST /mcp/tools/call
│   │   └── notifications.py   # POST /notifications/rules/create, /list, /update, /delete
│   ├── core/                  # 基础设施
│   │   ├── config.py          # 全部环境变量、常量（数据库 URL、SMTP、邮件、API 元数据）
│   │   ├── database.py        # SQLite 引擎、会话工厂、PRAGMA foreign_keys=ON
│   │   ├── auth.py            # 双层认证：get_current_user（API 密钥）、get_session_user（会话令牌）
│   │   ├── healer.py          # JIT 自愈引擎（Schema 演进、类型默认值补丁）
│   │   ├── validator.py       # 动态 Schema 验证引擎（6 种字段类型）
│   │   ├── email.py           # 邮件入队层 + SMTP 投递（Jinja2 模板）
│   │   └── captcha.py         # 基于数据库的图形验证码（生成 + 验证）
│   ├── models/
│   │   └── models.py          # 全部 ORM 模型（11 张表）
│   ├── worker/
│   │   ├── base.py            # BaseOutboxWorker 抽象基类（轮询、退避、生命周期）
│   │   ├── outbox.py          # Webhook 投递 Worker（httpx、指数退避）
│   │   └── email_worker.py    # 邮件投递 Worker（aiosmtplib、优先级队列）
│   └── templates/email/       # Jinja2 HTML 邮件模板
│       ├── verification.html      # 邮箱验证链接
│       ├── task_notification.html  # Todo CRUD 通知
│       └── webhook_failure.html   # Webhook 投递失败告警
├── Dockerfile
└── requirements.txt
```

## ORM 模型（11 张表）

| 模型 | 表名 | 说明 |
|------|------|------|
| `User` | `user` | 邮箱+密码认证，`is_active` 标志，验证令牌 |
| `ApiKey` | `api_key` | `sk-otd-*` 密钥，支持启用/禁用/软删除生命周期 |
| `SessionToken` | `session_token` | `ses-*` Web 登录会话令牌 |
| `Project` | `project` | 用户拥有的项目，含名称和描述 |
| `ProjectSchema` | `project_schema` | 动态字段定义 + 单调递增 `schemaVersion` |
| `Todo` | `todo` | 自引用树（WBS），JSON 内容，OCC `version`，`schemaVersion` |
| `WebhookRule` | `webhook_rule` | 项目级事件规则（Create/Update/Delete + 目标字段） |
| `WebhookTask` | `webhook_task` | Webhook 投递事务性发件箱 |
| `NotificationRule` | `notification_rule` | 用户级邮件通知订阅（按事件类型） |
| `EmailTask` | `email_task` | 邮件投递事务性发件箱（优先级队列） |
| `CaptchaChallenge` | `captcha_challenge` | 一次性图形验证码（5 分钟有效期） |

## API 端点

### 认证与会话管理

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `POST` | `/auth/captcha` | 否 | 生成验证码图片（一次性，5 分钟有效期） |
| `POST` | `/auth/register` | 否 | 邮箱+密码+验证码注册；入队验证邮件 |
| `POST` | `/auth/login` | 否 | 邮箱+密码+验证码登录；返回会话令牌 |
| `GET` | `/auth/verify` | 否 | 通过 `?token=xxx` 查询参数验证邮箱 |
| `POST` | `/auth/logout` | 否 | 注销会话令牌 |

### API 密钥管理（会话令牌认证）

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `POST` | `/keys/create` | 会话 | 创建新 API 密钥（完整值仅显示一次） |
| `POST` | `/keys/list` | 会话 | 列出所有密钥（脱敏值） |
| `POST` | `/keys/update` | 会话 | 重命名或启用/禁用密钥 |
| `POST` | `/keys/delete` | 会话 | 软删除密钥（不可逆） |

### 项目

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `GET` | `/projects` | API 密钥 | 列出用户的项目 |
| `POST` | `/projects/create` | API 密钥 | 创建项目 |

### Schema

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `POST` | `/projects/schema/get` | API 密钥 | 获取项目字段 Schema（不存在则自动创建） |
| `POST` | `/projects/schema/update` | API 密钥 | 替换项目字段 Schema（递增 `schemaVersion`） |

### 任务（Todo）

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `POST` | `/todos/list` | API 密钥 | 列出项目的任务（扁平数组，内存中 JIT 自愈） |
| `POST` | `/todos/create` | API 密钥 | 创建任务（Schema 验证、Webhook 发件箱、邮件通知） |
| `POST` | `/todos/update` | API 密钥 | 更新任务（OCC、深度差异、JIT 自愈写回、Webhook） |
| `POST` | `/todos/move` | API 密钥 | 重新挂载任务（循环引用检测、OCC） |
| `POST` | `/todos/delete` | API 密钥 | 递归级联删除（逐节点 Webhook 发件箱） |
| `POST` | `/todos/bulk-create` | API 密钥 | 单事务批量创建多个任务 |

### Webhook

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `POST` | `/webhooks/create` | API 密钥 | 创建 Webhook 规则 |
| `POST` | `/webhooks/list` | API 密钥 | 列出项目的 Webhook 规则 |
| `POST` | `/webhooks/tasks` | API 密钥 | 列出项目的发件箱任务 |

### 自动化

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `POST` | `/automation/webhook/logs` | API 密钥 | 查询投递历史（可选 `todoId` 过滤） |
| `POST` | `/automation/webhook/retry` | API 密钥 | 重试失败/待处理的投递 |

### 邮件通知

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `POST` | `/notifications/rules/create` | API 密钥 | 创建通知规则（TaskCreate/TaskUpdate/TaskDelete/WebhookFailure） |
| `POST` | `/notifications/rules/list` | API 密钥 | 列出用户的所有规则 |
| `POST` | `/notifications/rules/update` | API 密钥 | 启用/禁用规则 |
| `POST` | `/notifications/rules/delete` | API 密钥 | 硬删除规则 |

### MCP（Model Context Protocol）

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `POST` | `/mcp` | 视方法而定 | 标准 MCP Streamable HTTP（JSON-RPC 2.0：initialize、tools/list、tools/call、ping） |
| `GET` | `/mcp` | — | 返回 405（不提供服务端发起的 SSE） |
| `GET` | `/mcp/tools` | 否 | 旧版工具发现 |
| `POST` | `/mcp/tools/call` | API 密钥 | 旧版工具调用 |

### 健康检查

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `GET` | `/` | 否 | 健康检查（返回服务名 + 版本） |

## 核心设计决策

- **仅 POST 变更**：无 PATCH、PUT、DELETE。ID 始终在请求体中，绝不在 URL 路径参数中。
- **全 camelCase**：JSON 字段、Webhook 载荷、数据库别名。
- **双层认证**：API 密钥（`sk-otd-*`，`X-API-KEY` 请求头）用于程序化访问；会话令牌（`ses-*`，`X-SESSION-TOKEN` 请求头）用于 Web 会话。
- **事务性发件箱**：Webhook 任务和邮件任务与数据变更在同一事务中原子写入。
- **JIT 自愈**：无迁移的 Schema 演进——缺失字段在读取时内存补丁，写入时持久化。
- **乐观并发控制**：更新时提供 `version`，不匹配返回 409 Conflict。
- **动态验证**：内容根据项目 Schema 校验，错误信息引用 `fieldDescription` 以便 AI 自我纠正。
- **MCP Streamable HTTP**：标准 JSON-RPC 2.0 传输协议在 `POST /mcp`，提供 10 个 AI 可用工具。
- **SQLite 默认**：零配置，每次连接自动执行 `PRAGMA foreign_keys=ON`。

## 依赖

| 包 | 版本 | 用途 |
|----|------|------|
| `fastapi` | `>=0.104.0` | Web 框架 |
| `uvicorn[standard]` | `>=0.24.0` | ASGI 服务器 |
| `sqlmodel` | `>=0.0.14` | ORM（SQLAlchemy + Pydantic） |
| `pydantic` | `>=2.5.0` | 数据验证 |
| `httpx` | `>=0.25.0` | 异步 HTTP 客户端（Webhook 投递） |
| `python-dotenv` | `>=1.0.0` | 环境变量加载 |
| `aiosmtplib` | `>=3.0.0` | 异步 SMTP 客户端（邮件投递） |
| `jinja2` | `>=3.1.0` | 邮件模板渲染 |
| `captcha` | `>=0.6.0` | 图形验证码生成 |
| `bcrypt` | `>=4.0.0` | 密码哈希 |

---

> [返回项目根目录](../README.zh-CN.md)
