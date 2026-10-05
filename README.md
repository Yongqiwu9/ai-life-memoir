# AI人生回忆录平台

将用户口述、录音与采访内容整理为可追溯的 Memory，并进一步生成可编辑的人生回忆录。完整录音、AI 与回忆录链路属于目标产品设计。

## 当前阶段

| Part | 状态与交付边界 |
| --- | --- |
| 9.1–9.5 | 基础 Backend / 数据模型与 API 阶段完成：认证、Family/FamilyMember、Interview/Session/Message、Audio/Transcript/Segment 元数据 |
| 9.5.5 | Memory 前置基础设施/架构决策阶段；9.5.5-A 已完成产品约束与 ADR 文档整理；9.5.5-B — Completed，本地及远程 CI 验证通过；9.5.5-C — Design Frozen / Implementation Not Started；Next：C1 |
| 9.6 | Memory Extraction — Planned；MemoryCandidate、Memory、提取及人工确认流程尚未实现 |

Part 9.5 完成不代表 Audio upload、Object Storage、STT Provider 或 AI pipeline 已完成。当前代码权限仍为 Owner-only；首版 Family Collaboration、Participant、Consent、来源追踪、修订、删除与净化的实施设计已经冻结，但尚未实现。

当前 ADR 状态：ADR-001、003、004、005、006 为 Accepted；ADR-002、007 为 Proposed；ADR-008、009 仍为 Proposed，其中部分合同已由 9.5.5-C 冻结。Accepted 或 Design Frozen 均不代表对应功能已实施。

Part 9.5.5-B 保留 SQLite 快速测试，并为 PostgreSQL 引入独立的 `TEST_DATABASE_URL` 集成测试。进程环境变量优先；本地还可从 Git 忽略的 `apps/backend/.env.test` 读取该变量。集成测试只接受 PostgreSQL 且数据库名包含 `test` 的地址。测试迁移须显式设置 `TEST_MIGRATION_MODE=1`，并使用相同的测试 URL 校验；缺失时立即失败，不回退到开发 `DATABASE_URL`。普通 Alembic 命令仍按原有 `DATABASE_URL` 运行。GitHub Actions 通过环境变量提供测试 URL 并启用测试迁移模式，真实远程执行已验证通过。

## 项目资料

Part 9.5.5-B — Completed。2026-10-05 在专用 `ai_life_memoir_test`（PostgreSQL 18.6）完成空 public schema → Alembic 单 head `adf9c60d178d`、current/check 及测试后的 current/check。Ruff 和格式检查通过；SQLite fast tests：94 passed / 0 failed / 0 skipped / 2 deselected；PostgreSQL integration tests：2 passed / 0 failed / 0 skipped / 94 deselected。Local PostgreSQL Validation: PASS；Remote GitHub Actions Validation: PASS；Remote CI execution verified: YES。Implementation commit: `07d1f51699b9fbcdaa09b2652be23d3349948921`；[Backend CI run 37283732708](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37283732708)，completed / success。

Current Part: Part 9.5.5-C — Design Frozen / Implementation Not Started。详细设计见 [Part 9.5.5-C Final Implementation Design Freeze](<docs/03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md>)。Next：C1；后续 C1–C8 依据该 SSOT 实施。Part 9.6 — Planned，尚未开始。

- [Part 开发路线图](docs/05_开发阶段记录/Part开发路线图_V2.0.md)
- [系统架构总览](docs/01_架构设计/AI人生回忆录平台_系统架构总览_V1.1.md)
- [Audio/STT 数据模型设计基线](docs/02_数据模型/Part9.5_Audio-STT数据模型设计基线_V1.0.md)
- [ADR-003 Family档案删除策略](<docs/06_技术决策记录/ADR/ADR-003 Family档案删除策略.md>)
- [ADR 目录](docs/06_技术决策记录/ADR/)

代码和文档工作遵循 [Root AGENTS.md](AGENTS.md) 与 [Backend AGENTS.md](apps/backend/AGENTS.md)。templates/ 是代码母版，不参与运行时 import。
