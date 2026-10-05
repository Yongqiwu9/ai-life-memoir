# AI人生回忆录平台_开发日志_V1.0

## 1. 项目简介

AI人生回忆录平台用于长期采集个人经历，通过家庭关系、访谈、录音、语音识别、AI分析，最终生成结构化人生回忆录。

核心链路：

User → Family → FamilyMember → Interview → InterviewSession →
AudioRecording → Transcript → TranscriptSegment → InterviewMessage → AI
Extraction → Memory → Memoir

------------------------------------------------------------------------

## 2. 开发阶段记录

### Part 9.1 Backend基础设施

完成：

-   Backend工程结构
-   FastAPI基础架构
-   数据库基础
-   Alembic迁移体系

### Part 9.2 Authentication / User

完成：

-   用户模型
-   JWT认证体系
-   用户安全边界

### Part 9.3 Family + FamilyMember

提交：

668d1e0 feat: implement family and family member

完成：

-   Family
-   FamilyMember
-   CRUD
-   Service
-   API
-   Owner Isolation

### Part 9.4 Interview

提交：

79bb296 feat: implement interview module

完成：

-   Interview
-   InterviewSession
-   InterviewMessage

已建立的数据关系：

User → Family → FamilyMember → Interview → InterviewSession → InterviewMessage

### Part 9.5 Audio/STT

提交：

e30f043 feat: implement audio and stt data infrastructure

完成：

-   AudioRecording
-   Transcript
-   TranscriptSegment

已建立的数据关系：

AudioRecording → Transcript → TranscriptSegment → InterviewMessage

说明：这是 Audio/STT 元数据与来源关系，不代表已实现 Audio upload、真实 STT Provider 或自动转写 Pipeline。

### Part 9.5.5-A Memory 前置产品决策与 ADR 冻结

提交：

616e478 docs: freeze pre-memory architecture decisions

完成：

-   产品约束与 ADR-001～ADR-009 状态整理
-   Family Archive 删除、协作、讲述者、Consent、状态机、Candidate 与第三方处理边界记录

### Part 9.5.5-B PostgreSQL Integration Test + CI Baseline

状态：

Completed，2026-10-05 本地 PostgreSQL 与真实远程 GitHub Actions 验证均通过。

已实现：

-   保留 SQLite 快速测试
-   独立 PostgreSQL integration marker、Alembic/pytest 共用的 `TEST_DATABASE_URL` 加载与测试库名称安全检查
-   本地从 Git 忽略的 `apps/backend/.env.test` 加载测试 URL；测试迁移需显式启用 `TEST_MIGRATION_MODE=1`，缺少测试 URL 时不回退到开发库
-   迁移后 schema、UUID、访谈链、Audio/STT 元数据链、Message source、CASCADE / SET NULL 测试
-   GitHub Actions Backend CI：Ruff、SQLite tests、PostgreSQL fresh upgrade、Alembic check、integration tests

本地验证：

-   Ruff check / format check 通过
-   SQLite/快速测试：94 passed、2 deselected，其中包含 8 项纯配置安全测试
-   配置安全测试覆盖进程环境优先、本地 `.env.test` 加载、缺少或非测试 URL 拒绝、密码不进入错误信息、测试模式无开发库回退及正常 Alembic 模式保留
-   专用 `ai_life_memoir_test`，PostgreSQL 18.6，实际数据库名称验证通过；只操作测试库 public schema，未连接或修改开发数据库
-   空 public schema → 四个既有 migration → 唯一 head `adf9c60d178d`；upgrade/current/check 全部通过，集成测试后的 current/check 仍通过
-   实际 PostgreSQL 核心表、UUID、FK 关系链、MessageSource text/audio_transcript、CASCADE 与 SET NULL 验证通过；这是数据基础设施验证，不代表录音/STT 功能完成
-   SQLite fast tests：94 passed / 0 failed / 0 skipped / 2 deselected；PostgreSQL integration tests：2 passed / 0 failed / 0 skipped / 94 deselected
-   非阻塞警告：Starlette TestClient/httpx 弃用提示、pytest 缓存目录写入权限提示；测试退出码均为 0。无需为本轮验证修改业务代码
-   本地验证完成时 GitHub Actions workflow 已实现，远程执行当时尚未验证；后续成功结果见最终封板记录

最终封板记录（2026-10-05）：

-   Part 9.5.5-B status: Completed
-   Implementation commit: `07d1f51699b9fbcdaa09b2652be23d3349948921`，`test: add PostgreSQL integration and CI baseline`
-   Local PostgreSQL validation: PASS；Alembic fresh migration validation: PASS
-   Fast tests: PASS（94 passed / 0 failed / 0 skipped / 2 deselected）
-   PostgreSQL integration tests: PASS（2 passed / 0 failed / 0 skipped / 94 deselected）
-   GitHub Actions: Backend CI；[run 37283732708](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37283732708)，对应上述 implementation commit，master，completed / success
-   Remote CI execution verified: YES；Remote CI result: PASS。Python 3.12 / PostgreSQL 16 的远程流程包含 Ruff/format、fast tests、fresh upgrade、current/check、integration 及测试后的 current/check，均成功
-   历史交接记录：验收完成时下一项为 Part 9.5.5-C；其后已完成设计冻结，当前状态见下节
-   Part 9.5 Audio/STT 仍仅为 data/API infrastructure；真实 Audio upload、STT Provider 与生产 STT pipeline 尚未完成

### Part 9.5.5-C Family Collaboration + Participant + Consent Design Freeze

状态：

Design Frozen / Implementation Not Started。

已完成：

-   冻结 Family Collaboration、Participant、Consent、Source Provenance、Revision、Deletion、Sanitization 与 Privacy Policy 的实施设计
-   明确统一 User 身份体系、本人授权、用途隔离、历史恢复、删除传播、净化验收与 fail-safe 边界
-   形成后续 C1–C8 实施的单一设计依据：[Part 9.5.5-C Final Implementation Design Freeze](<../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md>)
-   ADR-001、003、004、005、006 为 Accepted；ADR-002、007 为 Proposed；ADR-008、009 仍为 Proposed，其中部分合同已冻结

实施边界：

-   本阶段完成的是设计封板，尚未实现 Model、Migration、Schema、Service/API、权限切换或测试
-   当前生产代码仍执行 Owner-only isolation
-   Next：C1；后续 C1–C8 依据 SSOT 实施
-   Part 9.6 Memory Extraction 保持 Planned，尚未开始

未完成：

-   Family Collaboration、Participant、Consent 的 C1–C8 实施
-   已冻结隐私状态机的代码落地、Message / Segment sequence 并发修复
-   MemoryCandidate、Memory Extraction
-   真实 Audio upload、STT Provider、AI Pipeline

下一阶段：

Part 9.5.5-C1，依据 Design Freeze SSOT 开始实施。

------------------------------------------------------------------------

## 3. 当前状态

已完成：

-   后端基础
-   用户体系
-   家庭体系
-   访谈体系
-   音频/STT数据模型

当前周期：

Part 9.5.5-C — Design Frozen / Implementation Not Started。Part 9.5.5-B 的 Local validation: PASS、Remote CI: VERIFIED / PASS 作为历史验收记录保留。

下一阶段：

Part 9.5.5-C1。后续 C1–C8 依据 Design Freeze SSOT 实施；Part 9.6 保持 Planned。
