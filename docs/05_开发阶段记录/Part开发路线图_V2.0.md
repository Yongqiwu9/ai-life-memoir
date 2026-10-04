# AI人生回忆录平台 — Part 开发路线图 V2.0

## Part 9 — Backend Core

| Part | 内容 | 状态 | 关键交付 |
| --- | --- | --- | --- |
| 9.1 | Backend Infrastructure | 完成 | FastAPI、SQLAlchemy、Settings、Logging、Exception、Alembic、pytest、ruff |
| 9.2 | User + JWT Authentication | 完成 | User 模型、bcrypt、JWT、注册/登录/当前用户 |
| 9.3 | Family + FamilyMember | 完成 | 家庭与成员 CRUD、owner isolation |
| 9.4 | Interview | 完成 | Interview / InterviewSession / InterviewMessage、完整所有权链 |
| 9.5 | Audio/STT 数据基础设施 | 完成 | AudioRecording / Transcript / TranscriptSegment、Message source/segment 扩展 |
| 9.6 | Memory Extraction | 规划中 | Memory Candidate / Memory、提取与确认流程 |
| 9.7 | AI Agent | 规划中 | 访谈追问、assistant 消息生成 |
| 9.8 | Memoir Generation | 规划中 | Memory → Memoir 组装与编辑 |

## 后续阶段（概览）

- Part 10：老人端 UniApp（elder-app）
- Part 11：管理/写作后台（writer-admin）
- Part 12：AI Service 独立化、RAG/Embedding
- Part 13：部署与运维（infra）

## 阶段原则

1. 每个 Part 只做最小增量，禁止提前实现后续模块。
2. 所有用户资源必须 owner isolation。
3. 数据库变更必须走 Alembic，保持单一 head。
4. 每个 Part 完成必须通过 pytest / ruff / alembic check / PostgreSQL smoke。
5. 每个 Part 独立 commit，保留历史审计轨迹。
