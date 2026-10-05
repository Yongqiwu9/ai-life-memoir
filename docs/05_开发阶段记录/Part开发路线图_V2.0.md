# AI人生回忆录平台 — Part 开发路线图 V2.0

## Part 9 — Backend Core

| Part | 内容 | 状态 | 关键交付 |
| --- | --- | --- | --- |
| 9.1 | Backend Infrastructure | 基础实现完成 | FastAPI、SQLAlchemy、Settings、Logging、Exception、Alembic、pytest、ruff |
| 9.2 | User + JWT Authentication | 基础实现完成 | User 模型、bcrypt、JWT、注册/登录/当前用户 |
| 9.3 | Family + FamilyMember | 数据模型/API 完成 | 家庭与档案人物 CRUD、当前 Owner-only isolation |
| 9.4 | Interview | 数据模型/API 完成 | Interview / InterviewSession / InterviewMessage、当前所有权查询链；状态机仍待决策与落地 |
| 9.5 | Audio/STT 数据基础设施 | 数据模型/API 完成 | AudioRecording / Transcript / TranscriptSegment 元数据、Message source/segment 扩展 |
| 9.5.5 | Memory 前置基础设施/架构决策 | 进行中 | 9.5.5-A 整理已确认产品约束、ADR 状态与 Open Questions；本轮文档供人工审查 |
| 9.6 | Memory Extraction | Planned（规划中） | MemoryCandidate / Memory、提取与人工确认流程，尚未实现 |
| 9.7 | AI Agent | 规划中 | 访谈追问、assistant 消息生成 |
| 9.8 | Memoir Generation | 规划中 | Memory → Memoir 组装与编辑 |

Part 9.1–9.5 的完成范围是基础 Backend、数据模型与 API。Part 9.5 不代表 Audio upload、Object Storage、STT Provider 或 AI pipeline 已完成；当前尚无真实录音到转写的自动处理链路。

Part 9.5.5-A 是文档决策整理任务，未创建模型、状态转换、迁移、CI 或 AI/STT 功能。ADR-003 的 Accepted 仅覆盖 Owner 删除整个 Family Archive 的产品权限；ADR-002、004–009 仍为 Proposed，不能据此认定所有 Memory 前置决策已冻结或 Part 9.6 已开始开发。

决策明细和未决问题见[系统架构总览的 ADR 状态表](../01_架构设计/AI人生回忆录平台_系统架构总览_V1.1.md#7-memory-前置决策边界)。

## 后续阶段（概览）

- Part 10：老人端 UniApp（elder-app）
- Part 11：管理/写作后台（writer-admin）
- Part 12：AI Service 独立化、RAG/Embedding
- Part 13：部署与运维（infra）

## 阶段原则

1. 每个 Part 只做最小增量，禁止提前实现后续模块。
2. 当前实现执行 Owner-only isolation；首版 Family Collaboration 的目标权限方案见 [ADR-004](<../06_技术决策记录/ADR/ADR-004 Family协作权限模型.md>)，尚未在代码中实现。
3. 数据库变更必须走 Alembic，保持单一 head。
4. 每个 Part 完成必须通过 pytest / ruff / alembic check / PostgreSQL smoke。
5. 每个 Part 独立 commit，保留历史审计轨迹。

本轮 Part 9.5.5-A 仅修改文档，停止在人工审查前，不自动暂存或提交；不执行会改变数据库状态的验证命令。
