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

实现：

User ↓ Family ↓ Member ↓ Interview ↓ Session ↓ Message

### Part 9.5 Audio/STT

提交：

e30f043 feat: implement audio and stt data infrastructure

完成：

-   AudioRecording
-   Transcript
-   TranscriptSegment

实现：

Audio ↓ STT ↓ Transcript ↓ Segment ↓ Message

### Part 9.5.5-A Memory 前置产品决策与 ADR 冻结

提交：

616e478 docs: freeze pre-memory architecture decisions

完成：

-   产品约束与 ADR-001～ADR-009 状态整理
-   Family Archive 删除、协作、讲述者、Consent、状态机、Candidate 与第三方处理边界记录

### Part 9.5.5-B PostgreSQL Integration Test + CI Baseline

状态：

Completed (Local Validation)，2026-10-05 完成本地 PostgreSQL 验证；远程 GitHub Actions 执行尚未验证。

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
-   GitHub Actions workflow 已实现；remote execution not yet verified

未完成：

-   Family Collaboration、Participant、Consent
-   状态机收敛、Message / Segment sequence 并发修复
-   MemoryCandidate、Memory Extraction
-   真实 Audio upload、STT Provider、AI Pipeline

下一阶段：

Part 9.5.5-C Family Collaboration + Participant + Consent

------------------------------------------------------------------------

## 3. 当前状态

已完成：

-   后端基础
-   用户体系
-   家庭体系
-   访谈体系
-   音频/STT数据模型

当前周期：

Part 9.5.5-B — Completed (Local Validation)。GitHub Actions CI workflow implemented; remote execution not yet verified。

下一阶段：

Part 9.5.5-C Family Collaboration + Participant + Consent
