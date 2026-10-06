# AI人生回忆录平台 — Part 开发路线图 V2.0

## Part 9 — Backend Core

| Part | 内容 | 状态 | 关键交付 |
| --- | --- | --- | --- |
| 9.1 | Backend Infrastructure | 基础实现完成 | FastAPI、SQLAlchemy、Settings、Logging、Exception、Alembic、pytest、ruff |
| 9.2 | User + JWT Authentication | 基础实现完成 | User 模型、bcrypt、JWT、注册/登录/当前用户 |
| 9.3 | Family + FamilyMember | 数据模型/API 完成 | 家庭与档案人物 CRUD、当前 Owner-only isolation |
| 9.4 | Interview | 数据模型/API 完成 | Interview / InterviewSession / InterviewMessage、当前所有权查询链；状态机仍待决策与落地 |
| 9.5 | Audio/STT 数据基础设施 | 数据模型/API 完成 | AudioRecording / Transcript / TranscriptSegment 元数据、Message source/segment 扩展 |
| 9.5.5 | Memory 前置基础设施/架构决策 | C Design Frozen；Implementation In Progress | B Completed / Sealed；C1 Completed / Sealed；C2 Next / Not Started |
| 9.6 | Memory Extraction | Planned（规划中） | MemoryCandidate / Memory、提取与人工确认流程，尚未实现 |
| 9.7 | AI Agent | 规划中 | 访谈追问、assistant 消息生成 |
| 9.8 | Memoir Generation | 规划中 | Memory → Memoir 组装与编辑 |

Part 9.1–9.5 的完成范围是基础 Backend、数据模型与 API。Part 9.5 不代表 Audio upload、Object Storage、STT Provider 或 AI pipeline 已完成；当前尚无真实录音到转写的自动处理链路。

Part 9.5.5-A 是文档决策整理任务，未创建模型、状态转换、迁移、CI 或 AI/STT 功能。当前 ADR-001、003、004、005、006 为 Accepted；ADR-002、007 为 Proposed；ADR-008、009 仍为 Proposed，其中部分合同由 9.5.5-C 冻结。ADR 状态与 Design Frozen 均不代表功能已经实现，也不代表 Part 9.6 已开始开发。

Part 9.5.5-B 保留现有 SQLite 快速测试，增加标记为 `integration` 的 PostgreSQL 测试、共用的 `TEST_DATABASE_URL` 加载与校验、以及 GitHub Actions Backend CI。进程环境变量优先，本地可读取 Git 忽略的 `apps/backend/.env.test`。测试迁移必须显式设置 `TEST_MIGRATION_MODE=1`；缺少安全的测试 URL 时立即失败，不回退到开发库。普通 Alembic 迁移仍使用原有 `DATABASE_URL`。CI 使用临时 PostgreSQL service，并通过环境变量提供测试 URL 和测试迁移模式。本地真实 PostgreSQL 和远程 GitHub Actions 均验证通过。

2026-10-05 Part 9.5.5-B 最终验收完成：专用 PostgreSQL 18.6 测试库空 public schema 成功迁移至唯一 head `adf9c60d178d`，current/check 及集成测试后的 current/check 均通过。Ruff/format 通过；SQLite fast tests：94 passed / 0 failed / 0 skipped / 2 deselected；PostgreSQL integration tests：2 passed / 0 failed / 0 skipped / 94 deselected。Local validation: PASS；Remote CI: VERIFIED / PASS。Implementation commit: `07d1f51699b9fbcdaa09b2652be23d3349948921`；[Backend CI run 37283732708](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37283732708)，master，completed / success。

Current Part: Part 9.5.5-C — Design Frozen / Implementation In Progress。详细设计以 [Part 9.5.5-C Final Implementation Design Freeze](<../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md>) 为 SSOT。C1 Policy + Identity Foundation — Completed / Sealed，Local PASS / Remote CI PASS；C2 — Next / Not Started。Part 9.6 — Planned。

### Part 9.5.5-C 实施子阶段

| 子阶段 | 范围 | 状态 |
| --- | --- | --- |
| C1 | Policy + Identity Foundation | Completed / Sealed |
| C2 | FamilyMembership + Invitation + Participant | Next / Not Started |
| C3 | Artifact Registry + Provenance | Planned |
| C4 | Consent + Source Binding + Access Gate | Planned |
| C5 | RevisionProposal | Planned |
| C6 | Deletion + Ledger + Outbox | Planned |
| C7 | Restore + Expiry + Sanitization | Planned |
| C8 | PostgreSQL Integration + Security Final Audit | Planned |

C1 evidence：implementation commit `35ec7e33a060b07e4834091b04c2caeb852b707c`；[Backend CI run 37412935434](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37412935434)，completed / success。

决策明细见 [Part 9.5.5-C Final Implementation Design Freeze](<../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md>)；ADR 总览见[系统架构总览的 ADR 状态表](../01_架构设计/AI人生回忆录平台_系统架构总览_V1.1.md#7-memory-前置决策边界)。

## 后续阶段（概览）

- Part 10：老人端 UniApp（elder-app）
- Part 11：管理/写作后台（writer-admin）
- Part 12：AI Service 独立化、RAG/Embedding
- Part 13：部署与运维（infra）

## 阶段原则

1. 每个 Part 只做最小增量，禁止提前实现后续模块。
2. 当前实现执行 Owner-only isolation；首版 Family Collaboration 的实施设计已经冻结，尚未在代码中实现。
3. 数据库变更必须走 Alembic，保持单一 head。
4. 每个 Part 完成必须通过 pytest / ruff / alembic check / PostgreSQL smoke。
5. 每个 Part 独立 commit，保留历史审计轨迹。

Part 9.5.5-C Design Freeze 文档保留设计封板时的历史快照。C1 本轮仅实现 PrivacyPolicyVersion、User 扩展、UserContact、AuthChallenge 与最小 rights-auth 基础；不含 Participant、Consent、协作、来源、删除或净化业务。生产加密/投递/限流能力未接入时，验证入口保持关闭；生产 retention 值尚未冻结。
