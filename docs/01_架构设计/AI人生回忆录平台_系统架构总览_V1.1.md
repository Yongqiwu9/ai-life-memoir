# AI人生回忆录平台 — 系统架构总览 V1.1

> Part 9.5.5-C 的详细冻结设计见：[Family Collaboration / Participant / Consent Design Freeze V1.0](../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md)。
> 当前状态：9.5.5-B Completed / Sealed；9.5.5-C DESIGN FROZEN / IMPLEMENTATION IN PROGRESS；C1 Completed / Sealed；C2 Next / Not Started；9.6 Planned。阶段来源为 [README](../../README.md) 和 [路线图](../05_开发阶段记录/Part开发路线图_V2.0.md)。
> 下文保留 Part 9.5 / 9.5.5-A 架构快照，包括当时的阶段、ADR 状态及未决项；已在 C 冻结的权限、身份、Consent、来源、修订和删除决策以该 SSOT 及更新后的 ADR 为准。ADR-004/005/006 已 Accepted，但 FamilyMembership、Consent、Deletion Pipeline、Sanitization 均尚未实现。

## 1. 平台目标

将用户口述、录音、访谈内容整理为结构化 Memory，并进一步生成可编辑的人生回忆录（Memoir）。
平台面向家庭与个人，核心链路为 Target Design（包含尚未实现的处理环节）：

```text
User → Family → FamilyMember → Interview → InterviewSession
        → AudioRecording → Transcript → TranscriptSegment
        → InterviewMessage → Memory → Memoir
```

## 2. Backend 架构

C1 当前增量：现有 User 增加 account / rights_only / system 能力类型与 auth_generation；仅新建 PrivacyPolicyVersion、UserContact、AuthChallenge。rights-auth challenge、verify 与 rights/me 提供认证基础，不建立 Speaker、Participant、Consent 或 Family 访问权。account 与 rights JWT 分离校验，旧无类型 token 须重新登录。PrivacyPolicyVersion 发布后内容不可变；缺值、缺能力证据或完整性失败时，新处理保持关闭。撤回/删除仅预留独立安全路径分类，没有实现流程。

C1 已由 implementation commit `35ec7e33a060b07e4834091b04c2caeb852b707c` 实施，并由 Backend CI run `37412935434` 远程验证成功。该封板只证明上述基础范围：rights_only authentication 不等于 Speaker identity、Consent、Source ownership 或 Family collaboration permission。

生产认证渠道的加密、密钥管理、投递与限流仍待经过验证的 Provider adapter；默认拒绝开放。测试替身使用内存 opaque vault，不能作为生产密码学实现。新增 migration 仅在专用测试库验证，没有运行生产迁移。下文既有快照不用于判断 C1 是否已实施。

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

Current Implementation 为 Owner-only isolation，当前用户一律来自 JWT，禁止信任 request body 中的 user_id。首版支持 Family Collaboration 是已确认 Product Decision，目标 User → FamilyMembership → Family 的权限方案仍为 Proposed；不能把 Owner-only 描述为最终产品权限模型。

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

### 4.1 Current Implementation：访谈数据模型与 API

```text
Interview → InterviewSession → InterviewMessage（客户端 user/text）
InterviewSession → AudioRecording（元数据）→ Transcript（元数据）→ TranscriptSegment
```

Audio upload、Object Storage、STT Provider 和 AI pipeline 尚未实现。当前仅有服务端 create_transcript_message 辅助函数把 Segment 写为 audio_transcript Message，没有自动录音/STT 作业调用链；普通客户端不能伪造该来源的 Message。

### 4.2 Target Design：未来 AI 数据流

```text
Source Message / Segment → AI Extraction → MemoryCandidate → Human Review → Memory
Memory → RAG/Embedding → Vector DB
Memory → Memoir Generation → Memoir
```

AI 输出的是候选内容，须人工确认后成为 Memory；来源追踪必须保留。确认者权限、修改后的审批和重跑版本策略见 ADR-008 的 Open Questions。

## 5. 模块边界

- `apps/backend/`：业务 API、数据、权限（Part 9.1–9.5 基础 Backend / 数据模型/API 阶段完成）
- `apps/elder-app/`：老人端 UniApp（前端，未开发）
- `apps/writer-admin/`：React 管理/写作后台（未开发）
- `services/ai-service/`：独立 AI 服务（未来）
- `packages/`：共享类型/工具
- `templates/`：代码母版，禁止 runtime import
- `database/`：seed/fixture
- `infra/`：部署基础设施
- `docs/`：项目知识库（本目录）

## 6. 当前阶段与交付边界

| Part | 内容 | 状态 |
| --- | --- | --- |
| 9.1 | Backend Infrastructure | 基础实现完成 |
| 9.2 | User + JWT Authentication | 基础实现完成 |
| 9.3 | Family + FamilyMember | 数据模型/API 完成；当前 Owner-only |
| 9.4 | Interview / InterviewSession / InterviewMessage | 数据模型/API 完成；目标状态机 Proposed |
| 9.5 | AudioRecording / Transcript / TranscriptSegment | 元数据模型/API 完成；真实上传/STT 未实现 |
| 9.5.5 | Memory 前置基础设施/架构决策 | 进行中；9.5.5-A 文档交付供人工审查 |
| 9.6 | Memory Extraction | Planned；模型、提取及确认流程尚未实现 |

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
                        └── InterviewMessage（每条最多回链 1 个 TranscriptSegment）
```

一个 TranscriptSegment 可以被 0..N 个 Message 引用，见 ADR-001。Message 是未来 AI Pipeline 的事件载体；当前具备来源字段和 Segment 回链，不代表 AI Pipeline 已实现。

## 7. Memory 前置决策边界

本轮 Part 9.5.5-A 只整理文档。Accepted 表示对应决策范围已确认，不表示代码实现或全链删除已验收。

| ADR | Status | 决策范围 |
| --- | --- | --- |
| [ADR-001 Segment-Message关系](<../06_技术决策记录/ADR/ADR-001 Segment-Message关系.md>) | Accepted（既有） | Segment 可关联 0..N 个 Message，每个 Message 最多回链一个 Segment |
| [ADR-002 User账号删除策略](<../06_技术决策记录/ADR/ADR-002 User账号删除策略.md>) | Proposed | 账号处置、Owner 转移和保留规则未定；记录现有 User→Family CASCADE 风险 |
| [ADR-003 Family档案删除策略](<../06_技术决策记录/ADR/ADR-003 Family档案删除策略.md>) | Accepted | Owner 可删除整个 Family Archive，包括协作者贡献；不能否决 Speaker 本人有效撤回/删除 |
| [ADR-004 Family协作权限模型](<../06_技术决策记录/ADR/ADR-004 Family协作权限模型.md>) | Proposed | 协作方向已确认，角色能力和编辑审批粒度未定 |
| [ADR-005 Interview参与者与讲述者模型](<../06_技术决策记录/ADR/ADR-005 Interview参与者与讲述者模型.md>) | Proposed | 一个 subject、多个 speaker 的概念已确认，身份关联和最小参与者基数未定 |
| [ADR-006 Consent授权撤回与删除策略](<../06_技术决策记录/ADR/ADR-006 Consent授权撤回与删除策略.md>) | Proposed | 本人同意、撤回与删除原则已确认，结构、核验和派生处理流程未定 |
| [ADR-007 Interview-Session状态机](<../06_技术决策记录/ADR/ADR-007 Interview-Session状态机.md>) | Proposed | 当前代码与目标状态枚举冲突；目标转换和历史迁移未冻结 |
| [ADR-008 MemoryCandidate确认流程](<../06_技术决策记录/ADR/ADR-008 MemoryCandidate确认流程.md>) | Proposed | 候选→人工审阅→Memory 的目标链；确认权和版本策略未定 |
| [ADR-009 AI-STT第三方数据处理边界](<../06_技术决策记录/ADR/ADR-009 AI-STT第三方数据处理边界.md>) | Proposed | 遵守 Backend/AI Service 边界；Provider、留存、训练和删除传播未定 |

Product Decision 已确认默认入口为“回忆我自己”，继续使用统一 Family / FamilyMember / Interview 模型，不另建个人档案系统。FamilyMember 是回忆档案人物，不能直接等同 User、FamilyMembership 或 speaker；User 与“我自己”的人物关联方式仍需明确。

Owner 删除整个 Family Archive 与 Speaker 本人来源数据撤回/删除是独立生命周期。删除内容立即退出正常产品访问路径，Owner 不提供普通用户恢复入口；备份最终清除周期、法律留存和不可逆物理删除时间均保留为 Open Questions，不在本轮确定。
