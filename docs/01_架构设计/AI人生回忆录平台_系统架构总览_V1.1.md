# AI人生回忆录平台 — 系统架构总览 V1.1

## 1. 平台目标

将用户口述、录音、访谈内容整理为结构化 Memory，并进一步生成可编辑的人生回忆录（Memoir）。
平台面向家庭与个人，核心链路为：

```text
User → Family → FamilyMember → Interview → InterviewSession
        → AudioRecording → Transcript → TranscriptSegment
        → InterviewMessage → Memory → Memoir
```

## 2. Backend 架构

Backend 是单体 FastAPI 业务系统，技术基线：

- Python 3.12+
- FastAPI + SQLAlchemy 2.x + Pydantic v2
- PostgreSQL（含未来 pgvector）+ Redis（未来）
- Alembic 迁移，JWT 认证

分层严格为：

```text
Router → Service → CRUD → Model
Schema = API 输入/输出
Dependency = 认证/权限
```

- Router：只处理 HTTP、路径参数、依赖注入与响应。
- Service：业务规则、事务边界、Owner Isolation。
- CRUD：纯数据库访问。
- Model：SQLAlchemy 2.x typed mapping，UUID 主键、timezone-aware UTC。

所有用户资源必须 owner isolation，当前用户一律来自 JWT，禁止信任 request body 中的 user_id。

## 3. AI Service 未来职责

AI Service 独立于 Backend（`services/ai-service/`），未来负责：

- LLM / Prompt / Agent
- RAG / Embedding / Vector Database
- STT（或经由独立 Provider）
- Memory Extraction / 人生故事提取
- Fact Checker
- Memoir 生成

Backend 负责业务数据与权限；AI Service 负责智能内容生成。
统一数据流：`Client → Backend API → Database`，`Backend → AI Service → LLM/RAG/Embedding`。

## 4. 数据流

### 4.1 访谈数据流（当前已完成）

```text
Interview → InterviewSession → AudioRecording
                                └─ STT → Transcript → TranscriptSegment
InterviewSession → InterviewMessage（text / audio_transcript）
```

### 4.2 未来 AI 数据流

```text
InterviewMessage → AI Extraction → Memory Candidate → Memory
Memory → RAG/Embedding → Vector DB
Memory → Memoir Generation → Memoir
```

## 5. 模块边界

- `apps/backend/`：业务 API、数据、权限（Part 9.1–9.5 已完成）
- `apps/elder-app/`：老人端 UniApp（前端，未开发）
- `apps/writer-admin/`：React 管理/写作后台（未开发）
- `services/ai-service/`：独立 AI 服务（未来）
- `packages/`：共享类型/工具
- `templates/`：代码母版，禁止 runtime import
- `database/`：seed/fixture
- `infra/`：部署基础设施
- `docs/`：项目知识库（本目录）

## 6. 当前已完成 Part

| Part | 内容 | 状态 |
| --- | --- | --- |
| 9.1 | Backend Infrastructure | 完成 |
| 9.2 | User + JWT Authentication | 完成 |
| 9.3 | Family + FamilyMember | 完成 |
| 9.4 | Interview / InterviewSession / InterviewMessage | 完成 |
| 9.5 | AudioRecording / Transcript / TranscriptSegment | 完成 |

当前数据模型已形成：

```text
User
 └── Family
      └── FamilyMember
            └── Interview
                  └── InterviewSession
                        ├── AudioRecording
                        │       └── Transcript
                        │              └── TranscriptSegment
                        └── InterviewMessage
                              └── (0..N) TranscriptSegment
```

Message 是 AI Pipeline 的事件载体，不是 Transcript 的简单复制。
