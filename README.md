# AI人生回忆录平台

将用户口述、录音与采访内容整理为可追溯的 Memory，并进一步生成可编辑的人生回忆录。完整录音、AI 与回忆录链路属于目标产品设计。

## 当前阶段

| Part | 状态与交付边界 |
| --- | --- |
| 9.1–9.5 | 基础 Backend / 数据模型与 API 阶段完成：认证、Family/FamilyMember、Interview/Session/Message、Audio/Transcript/Segment 元数据 |
| 9.5.5 | Memory 前置基础设施/架构决策阶段；9.5.5-B — Completed / Sealed；9.5.5-C — Design Frozen / Implementation In Progress；C1/C2A/C2B — Completed / Sealed；C3 — Next / Planned |
| 9.6 | Memory Extraction — Planned；MemoryCandidate、Memory、提取及人工确认流程尚未实现 |

Part 9.5 完成不代表 Audio upload、Object Storage、STT Provider 或 AI pipeline 已完成。C2A 已实现邀请、Membership 与协作管理权限基础；C2B 已完成 Participant 身份关系、本人确认及最小本人权利入口，并在 PostgreSQL 16.15 上通过 remediation commit 对应的 Backend CI。既有 Family 内容、FamilyMember、Interview、Session、Audio、Transcript、Segment、Message API 仍为 Owner-only。Consent、来源追踪、修订、删除与净化尚未实现。

当前 ADR 状态：ADR-001、003、004、005、006 为 Accepted；ADR-002、007 为 Proposed；ADR-008、009 仍为 Proposed，其中部分合同已由 9.5.5-C 冻结。Accepted 或 Design Frozen 均不代表对应功能已实施。

Part 9.5.5-B 保留 SQLite 快速测试，并为 PostgreSQL 引入独立的 `TEST_DATABASE_URL` 集成测试。进程环境变量优先；本地还可从 Git 忽略的 `apps/backend/.env.test` 读取该变量。集成测试只接受 PostgreSQL 且数据库名包含 `test` 的地址。测试迁移须显式设置 `TEST_MIGRATION_MODE=1`，并使用相同的测试 URL 校验；缺失时立即失败，不回退到开发 `DATABASE_URL`。普通 Alembic 命令仍按原有 `DATABASE_URL` 运行。GitHub Actions 通过环境变量提供测试 URL 并启用测试迁移模式，真实远程执行已验证通过。

项目 PostgreSQL 基线为 **PostgreSQL 16.x**，当前本地集成测试与 GitHub Actions 均以 **16.15** 为验收版本。本机安装的其他 major 版本不得作为项目权威验收数据库；PostgreSQL major 升级必须单独完成兼容性验证。

## 项目资料

Part 9.5.5-B — Completed。2026-10-05 在专用 `ai_life_memoir_test`（PostgreSQL 18.6）完成空 public schema → Alembic 单 head `adf9c60d178d`、current/check 及测试后的 current/check。Ruff 和格式检查通过；SQLite fast tests：94 passed / 0 failed / 0 skipped / 2 deselected；PostgreSQL integration tests：2 passed / 0 failed / 0 skipped / 94 deselected。Local PostgreSQL Validation: PASS；Remote GitHub Actions Validation: PASS；Remote CI execution verified: YES。Implementation commit: `07d1f51699b9fbcdaa09b2652be23d3349948921`；[Backend CI run 37283732708](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37283732708)，completed / success。

Current Part: Part 9.5.5-C — Design Frozen / Implementation In Progress。详细设计见 [Part 9.5.5-C Final Implementation Design Freeze](<docs/03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md>)。C1：Policy + Identity Foundation — Completed / Sealed；C2A：Family Collaboration Foundation — Completed / Sealed；C2B：Interview Participant Identity Foundation — Completed / Sealed / Remote CI Passed；C3：Artifact Registry + Provenance — Next / Planned。Part 9.6 — Planned，尚未开始。冻结文档的 Implementation Not Started 是归档时的历史快照。

C1 仅新增 PrivacyPolicyVersion、UserContact、AuthChallenge，扩展现有 User 的 principal_kind/auth_generation，并提供受限的 rights-auth 验证入口。普通账号访问仍按 Owner-only 校验。Policy 期限必须显式使用正整数 seconds，没有生产默认值；未发布完整 Policy 或未验证能力时，新处理门禁拒绝开放，未来撤回/删除安全路径不依赖 active Policy（这些业务流程尚未实现）。

rights token 与 account token 分别校验类型、scope、主体能力及当前 generation；rights token 额外校验 aud/iss 和验证记录。旧的无类型/无 generation 账号 JWT 需要重新登录。既有注册/密码登录接口保持原形。旧邮箱不自动生成 verified Contact，也不自动合并身份。

生产加密 Provider、验证消息投递、生产密钥管理/轮换及生产分布式限流适配器均尚未实现：默认 rights-auth 返回能力不可用，不能视为 production-ready rights authentication。测试用 opaque memory vault 不是生产加密。

C1 implementation commit：`35ec7e33a060b07e4834091b04c2caeb852b707c`，`feat: implement policy and identity foundation`。Local Validation：PASS；Remote Validation：PASS；[Backend CI run 37412935434](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37412935434)，master，completed / success。C1 的详细验收记录见[开发日志](docs/00_项目管理/AI人生回忆录平台_开发日志_V1.0.md)。未执行生产数据库迁移。

C2A 已由 implementation commit `a33f6eb6160a2e0eb5276b0c08d9a5d9c2534cfd`（`feat: implement family collaboration foundation`）实施并封板。正式范围包括 `CommandIdempotencyRecord`、`FamilyInvitation`、`FamilyMembership`、Owner/active Collaborator 协作管理门禁、`invitation_acceptance` 身份核验与 context-bound `verification_proof`、邀请/成员 API，以及 migration `b7e2c4d891a0`。Local Validation：PASS；Remote Validation：PASS；[Backend CI run 37492358055](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37492358055)，master，completed / success。最新验证：Ruff/format PASS；Fast 163 passed / 29 deselected；PostgreSQL integration 29 passed / 163 deselected；Alembic head/current/check 及 post-integration current/check PASS；并发与安全验证 PASS。

C2B 已由 implementation commit `1038313cd57f6a76f5c6c27213912284e5af38fa` 和 remediation commit `fbb79b6a8af06b3d50e1d4923eb56169128efcde` 实施并封板；migration 为 `d4f8a1c2b3e6`，down revision 为 `b7e2c4d891a0`。Remediation commit 对应的 [Backend CI run 37627066699](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37627066699) 在 master 上 completed / success：PostgreSQL 16.15，Fast 173 passed / 40 deselected，PostgreSQL integration 40 passed / 173 deselected，Ruff、format、Alembic heads / fresh upgrade / current / check / post-integration current/check 均通过。

C2B 已实现 `InterviewParticipant`、speaker-only V1 role、稳定 `interview_scope_id`、Participant proposal、`participant_confirmation`、context-bound 本人身份核验、account / rights_only 本人最小访问、本人确认/停用、成年声明、幂等复用、verified `UserContact` 绑定及数据库约束和危险 downgrade 保护。Participant verified 不等于 Consent；Participant relationship 和 FamilyMembership 均不授予 Family archive 内容访问权。既有内容 API 继续保持 Owner-only，除明确新增的 Participant 最小本人 rights path 外。Consent、Source/Provenance、RevisionProposal、Deletion Pipeline、Privacy Ledger、Outbox、Sanitization、MemoryCandidate、Memory 和 Memoir 仍未实现；Part 9.5.5-C 仍为 Implementation In Progress。

- [Part 开发路线图](docs/05_开发阶段记录/Part开发路线图_V2.0.md)
- [系统架构总览](docs/01_架构设计/AI人生回忆录平台_系统架构总览_V1.1.md)
- [Audio/STT 数据模型设计基线](docs/02_数据模型/Part9.5_Audio-STT数据模型设计基线_V1.0.md)
- [ADR-003 Family档案删除策略](<docs/06_技术决策记录/ADR/ADR-003 Family档案删除策略.md>)
- [ADR 目录](docs/06_技术决策记录/ADR/)

代码和文档工作遵循 [Root AGENTS.md](AGENTS.md) 与 [Backend AGENTS.md](apps/backend/AGENTS.md)。templates/ 是代码母版，不参与运行时 import。
