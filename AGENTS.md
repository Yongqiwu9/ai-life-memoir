# AI人生回忆录平台 — Root AGENTS.md

## 1. Project

AI人生回忆录平台（AI Life Memoir Platform）。

目标：
将用户口述、录音、采访内容整理为结构化 Memory，并进一步生成可编辑的人生回忆录。

## 2. Monorepo

必须遵循：

- templates/：代码母版，不参与运行时 import
- apps/backend/：FastAPI 主业务系统
- apps/elder-app/：老人端 UniApp
- apps/writer-admin/：React 管理/写作后台
- services/ai-service/：独立 AI 服务
- packages/：跨应用共享类型/工具
- database/：seed / fixture
- infra/：部署基础设施
- scripts/：自动化脚本
- docs/：项目知识库

不要重新建立平铺的 backend/、frontend/、ai-service/ 根目录。

## 3. Architecture Rules

客户端不得直接访问 PostgreSQL、Redis 或 AI Provider。

统一：

Client -> Backend API -> Database

Backend -> AI Service -> LLM/RAG/Embedding

## 4. Backend

技术基线：
- Python 3.12+
- FastAPI
- SQLAlchemy 2.x
- Pydantic v2
- Alembic
- PostgreSQL
- pgvector
- Redis
- JWT

分层：

Router -> Service -> CRUD -> Model

Schema 负责 API 输入/输出。

禁止：
- Router 中直接编写复杂 SQL
- CRUD 层处理业务规则
- 客户端提交 user_id 后直接信任
- 生产代码写死密钥
- 跨层循环依赖

## 5. AI Service

AI Service 独立于 Backend。

Backend 负责业务数据和权限。
AI Service 负责：
- LLM
- Prompt
- Agent
- RAG
- Embedding
- AI 内容生成/提取

## 6. Templates

新增重复模块时优先使用 templates/。

模板是母版，不是运行时代码。

不要让应用 import templates/ 下的 Python 文件。

## 7. Security

- 所有用户资源必须进行 owner isolation
- JWT 是生产认证基础
- 不信任客户端 user_id
- Secrets 只能来自环境变量或 Secret Manager
- 日志禁止输出密码、token、API key

## 8. Database

- 数据库结构变更必须通过 Alembic
- 不允许手工修改生产数据库结构
- 时间统一使用 timezone-aware UTC
- 主键优先 UUID
- 用户数据必须具备明确 owner 关系

## 9. API

默认 API 前缀：

/api/v1

标准 CRUD：

POST   /resources
GET    /resources
GET    /resources/{id}
PATCH  /resources/{id}
DELETE /resources/{id}

列表默认：
page=1
page_size=20

## 10. Codex Workflow

执行顺序：

1. 阅读相关 AGENTS.md
2. 阅读相关 docs
3. 查找已有模板
4. 查找已有实现
5. 只修改必要文件
6. 运行 lint/test
7. 检查 git diff
8. 汇报修改内容和验证结果

禁止在没有检查现有代码的情况下重新生成整个项目。

## 11. Scope

如果任务只要求修改一个模块，不要顺便重构整个 Monorepo。

如果发现架构问题：
- 先说明
- 提供最小修改方案
- 不擅自扩大修改范围
