# AI人生回忆录平台

将用户口述、录音与采访内容整理为可追溯的 Memory，并进一步生成可编辑的人生回忆录。完整录音、AI 与回忆录链路属于目标产品设计。

## 当前阶段

**当前阶段（2026-10-15）**：9.6-B 已由用户最终确认 **Completed / Sealed（约定验收范围）**；封板文档提交 `0e39a39b22a72be361833dd0ae42c40f80146b1e` 已推送，exact-commit Backend CI 38691707005 completed/success。进入 **9.6-C 工程设计 / C1合同静态审查PASS、Implementation Not Started**；仅归档合同，不代表真实语音、笔记存储或多来源整理已实现。详见[完整产品路线与C1合同](docs/04_AI设计/Part9.6-C_Continuous-Reminiscence_Engineering-Contract_Draft_V1.0.md)及[独立审查报告](docs/05_开发阶段记录/Part9.6-C1_Independent-Contract-Review_Report_2026-10-15.md)。

最新已验证[Backend CI 38691707005](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/38691707005)绑定exact `0e39a39b22a72be361833dd0ae42c40f80146b1e`：Fast642、普通PG48、B专项PG16.15 **45项／其中竞争11／0skip**，Ruff/format、迁移和清理verified。历史AI Service58、Legacy18未在该CI重跑；工作区Fast920含未提交C3，不与远程642混称。真实Provider、C4/C6、生产及旧UNKNOWN限制保留，保持 **DEVELOPMENT SNAPSHOT ONLY / NOT PRODUCTION READY**。

### B CI 接线历史（补验前快照）

> B CI接线实现最新结论（2026-10-14）：独立定向复审PASS，CI-IR-01～04 CLOSED — STATIC；43项纯mock检查、script Ruff/format和YAML接线检查PASS。新job实际Linux/PostgreSQL/remote CI仍NOT RUN，B-PC-01及E-01保持OPEN；未暂存/提交/推送。后续提交候选为原50路径加workflow/专项脚本/CI合同共53路径，需重新Pre-Commit Audit，三份混合文档仍按hunk排除C3内容。下方待再审记录保留历史，以本段为准。

> B CI定向修复（2026-10-14）：实现初审发现CI-IR-01～03 Blocking Medium及CI-IR-04 Low，已在原专项脚本中修复并扩展至43项纯mock合同/故障注入检查，待独立定向再审。新job真实Linux/PG/remote CI仍NOT RUN，B-PC-01不关闭；下方32项为首次离线检查历史结果。

> 2026-10-14 B CI 接线补充：用户批准六文件实施，workflow已将B用例从原integration入口精确分流至独立PostgreSQL16.15 job；专项Manager/Runner脚本已写入。独立合同审查PASS WITH FINDINGS，32项纯mock合同检查、Ruff/format与YAML接线检查通过；新job真实PG/远程CI尚未运行，实现独立复审待完成。B-PC-01仍OPEN，E-01、57项未全覆盖及未封板边界不变。详情见[CI接线合同](docs/05_开发阶段记录/Part9.6-B_PostgreSQL-CI-Wiring_Implementation-Contract_V1.0.md)。本轮未暂存、提交或推送。

### 当前主线摘要

| Part | 状态与交付边界 |
| --- | --- |
| 9.1–9.5 | 基础 Backend / 数据模型与 API 阶段完成：认证、Family/FamilyMember、Interview/Session/Message、Audio/Transcript/Segment 元数据 |
| 9.5.5 | Memory 前置基础设施/架构决策阶段；B、C1/C2A/C2B、C3.0 — Completed / Sealed；C — Design Frozen / Implementation In Progress；C3 实施 In Progress；C3.1 Implementation Audit = PASS WITH FINDINGS，已完成本地 PostgreSQL 16.15 与回归验证；Implementation Completed（dormant scope），commit / push / exact remote CI PASS；Final Documentation Seal Preparation in progress；C3.2 Next / NOT STARTED |
| Memory + Memoir Slice 1 | 人工 Memory 与确定性 Memoir 草稿已实现；不含 AI 提取、不可变 Revision 或正式审批 |
| 9.6-A | Provider Extension Implementation Completed / COMMITTED LOCALLY；HTTP / PostgreSQL NOT VERIFIED；Real Provider NOT IMPLEMENTED |
| 9.6-B | Completed / Sealed（约定范围）；57项对账归档，E-01 B范围证据CLOSED；封板文档exact 0e39a39 / CI38691707005 success，B45／竞争11通过 |
| 9.6-C / C1 | 完整产品路线与C1合成离线决策内核合同已归档，独立静态审查PASS；候选11新增文件、C01–C58验收未执行；Implementation Not Started，全产品后续工作包未冻结 |

9.6-B范围依据[正式对账](docs/05_开发阶段记录/Part9.6-B_B01-B57_Acceptance-Reconciliation_2026-10-15.md)及[E-01独立关闭意见](docs/05_开发阶段记录/Part9.6-B_E01_Coverage-Closure_Independent-Review_2026-10-15.md)保留；B38同旧Memory恢复后置C4，B46静态inventory，B48执行＋约束证明，不宣称57项全层验证。下一步为C1文档归档审计及另行实施批准；本轮不暂存/提交/推送。此前合同/报告的“封板准备”“未归档”保留其历史时点，最新状态以本节为准；历史C3/BM-01与旧v3 UNKNOWN不变。

Part 9.5 完成不代表 Audio upload、Object Storage、STT Provider 或 AI pipeline 已完成。C2A 已实现邀请、Membership 与协作管理权限基础；C2B 已完成 Participant 身份关系、本人确认及最小本人权利入口，并在 PostgreSQL 16.15 上通过 remediation commit 对应的 Backend CI。既有 Family 内容、FamilyMember、Interview、Session、Audio、Transcript、Segment、Message API 仍为 Owner-only。9.6-B 已有离线 Candidate/Revision/审批 profile；完整生产 Consent、C3 来源链路、C5 Artifact 审批接线、删除与净化仍未实现。

当前 ADR 状态：ADR-001、003、004、005、006 为 Accepted；ADR-002、007 为 Proposed；ADR-008、009 仍为 Proposed，其中部分合同已由 9.5.5-C 冻结。Accepted 或 Design Frozen 均不代表对应功能已实施。

Part 9.5.5-B 保留 SQLite 快速测试，并为 PostgreSQL 引入独立的 `TEST_DATABASE_URL` 集成测试。进程环境变量优先；本地还可从 Git 忽略的 `apps/backend/.env.test` 读取该变量。集成测试只接受 PostgreSQL 且数据库名包含 `test` 的地址。测试迁移须显式设置 `TEST_MIGRATION_MODE=1`，并使用相同的测试 URL 校验；缺失时立即失败，不回退到开发 `DATABASE_URL`。普通 Alembic 命令仍按原有 `DATABASE_URL` 运行。GitHub Actions 通过环境变量提供测试 URL 并启用测试迁移模式，真实远程执行已验证通过。

项目 PostgreSQL 基线为 **PostgreSQL 16.x**，当前本地集成测试与 GitHub Actions 均以 **16.15** 为验收版本。本机安装的其他 major 版本不得作为项目权威验收数据库；PostgreSQL major 升级必须单独完成兼容性验证。

## 项目资料

Part 9.5.5-B — Completed。2026-10-05 在专用 `ai_life_memoir_test`（PostgreSQL 18.6）完成空 public schema → Alembic 单 head `adf9c60d178d`、current/check 及测试后的 current/check。Ruff 和格式检查通过；SQLite fast tests：94 passed / 0 failed / 0 skipped / 2 deselected；PostgreSQL integration tests：2 passed / 0 failed / 0 skipped / 94 deselected。Local PostgreSQL Validation: PASS；Remote GitHub Actions Validation: PASS；Remote CI execution verified: YES。Implementation commit: `07d1f51699b9fbcdaa09b2652be23d3349948921`；[Backend CI run 37283732708](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37283732708)，completed / success。

Current Part: Part 9.5.5-C3.1 — SourceArtifact Registry Schema / Models，Implementation Audit = PASS WITH FINDINGS；本地验证 PASS；Staged Audit / Exact Commit Audit / Push / Remote Backend CI 均 PASS。Implementation Completed（dormant scope）；Final Documentation Seal Preparation in progress，封板提交及其自身 CI 尚未完成。Part 9.5.5-C 与 C3 整体为 Implementation In Progress；C1/C2A/C2B、C3.0 均为 Completed / Sealed。合同见 [C3 Implementation Contract Addendum](docs/03_业务流程/Part9.5.5-C3_Implementation-Contract-Addendum_V1.0.md) 与 [父级 Design Freeze](docs/03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md)。下一步 C3.2 Content Artifact Integration；Part 9.6 — Planned / NOT STARTED。父级冻结文档保留历史快照。

C3.0 合同证据：Addendum commit `345f852d36f94752ddea99fba1f889d9d632ded0`，对应 [Backend CI run 37762742776](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37762742776)；Final Contract Re-Audit PASS，BM-01～04 CLOSED。封板 commit `5f09d6c7e4c57672a85cca548cda150bc3c39c30` 自身的 [Backend CI run 37765330926](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37765330926) 已 completed / success，exact SHA 匹配，C3.0 封板条件已满足。两个 CI 均验证 pre-C3 Backend 基线，不代表 C3 功能完成。

C3.1 新增 dormant SourceArtifact ORM 原型：具名结构约束、候选键、FK 与 SQL NULL-only locator；不注册到生产 metadata，无 C3-A/C3-B migration 或部署。2026-10-09 在专用 PostgreSQL 16.15 测试库完成本地验证：SourceArtifact PostgreSQL 原型 8 passed；完整 integration 48 passed / 180 deselected；SQLite fast 180 passed / 48 deselected（含原型 7 passed）；均为 0 failed / 0 errors / 0 skipped。Ruff/format PASS；Alembic heads/current/check PASS，单 head `d4f8a1c2b3e6`。Implementation Audit = PASS WITH FINDINGS；Staged Audit / Exact Commit Audit / Push / Remote Backend CI 均 PASS；尚未完成独立文档封板及其自身 CI。没有 runtime Registry 注册、内容 artifact_id 接入、最终 PostgreSQL guards、backfill、DAG、Speaker Binding、Contribution 或 Consent / Access Gate。

C3.1 implementation commit：`aa711f9b2b18ad522226b1d99afac47ea0a0dc3e`；[Backend CI run 37939418187](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37939418187)，workflow `.github/workflows/backend-ci.yml`，event push，branch master，head SHA 与 implementation commit 精确匹配，completed / success。远程 SQLite 180 passed / 48 deselected，PostgreSQL integration 48 passed / 180 deselected，均 0 failed / 0 skipped；PostgreSQL 16.15；Ruff、format（128 files）、Alembic heads / fresh upgrade / current / check / post-integration current/check PASS，单 head `d4f8a1c2b3e6`。

C3.1 仅在批准的 dormant SourceArtifact ORM foundation 范围内 Implementation Completed，不代表生产部署或完整 C3 完成。Production metadata registration、runtime Registry、content artifact_id integration、historical backfill、DerivedSource DAG、SourceSpeakerBinding、ArtifactContribution、final PostgreSQL source guards、Consent / Access Gate 和 production deletion pipeline 均 NOT IMPLEMENTED；C3-A/C3-B 均 NOT CREATED。C2B、C3.0 保持 Completed / Sealed，既有 Owner-only 内容 API 权限不变。DF-01：Deferred Medium，单语句 Family multi-path DELETE 可触发 SQLSTATE 23503，归属 C6 deletion flow / later C3 guards；L-01：Low，Starlette/httpx 弃用警告，归属 Backend dependency maintenance。

Final Documentation Seal：Preparation in progress。独立文档封板 commit 及其自身 exact-SHA Backend CI 尚未完成；仅在该提交推送且其 exact-SHA CI completed / success 后最终封板才生效。当前不声明 C3.1 Sealed，不预填未来 seal SHA 或 CI Run ID。C3.2 Content Artifact Integration — Next / NOT STARTED；Part 9.6 — Planned / NOT STARTED。

C3.1 FK 验证仅证明测试用终态 fixture 中逐项 Session / Interview / Family 删除的 SET NULL 与稳定 scope 保留；不授权普通 live-state 删除。PostgreSQL 16.15 的单条 Family 多路径 cascade 已复现 SQLSTATE 23503，此机械限制仍需在后续合法删除流程设计中处理；本阶段未实施该流程或最终反向保护。

C1 仅新增 PrivacyPolicyVersion、UserContact、AuthChallenge，扩展现有 User 的 principal_kind/auth_generation，并提供受限的 rights-auth 验证入口。普通账号访问仍按 Owner-only 校验。Policy 期限必须显式使用正整数 seconds，没有生产默认值；未发布完整 Policy 或未验证能力时，新处理门禁拒绝开放，未来撤回/删除安全路径不依赖 active Policy（这些业务流程尚未实现）。

rights token 与 account token 分别校验类型、scope、主体能力及当前 generation；rights token 额外校验 aud/iss 和验证记录。旧的无类型/无 generation 账号 JWT 需要重新登录。既有注册/密码登录接口保持原形。旧邮箱不自动生成 verified Contact，也不自动合并身份。

生产加密 Provider、验证消息投递、生产密钥管理/轮换及生产分布式限流适配器均尚未实现：默认 rights-auth 返回能力不可用，不能视为 production-ready rights authentication。测试用 opaque memory vault 不是生产加密。

C1 implementation commit：`35ec7e33a060b07e4834091b04c2caeb852b707c`，`feat: implement policy and identity foundation`。Local Validation：PASS；Remote Validation：PASS；[Backend CI run 37412935434](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37412935434)，master，completed / success。C1 的详细验收记录见[开发日志](docs/00_项目管理/AI人生回忆录平台_开发日志_V1.0.md)。未执行生产数据库迁移。

C2A 已由 implementation commit `a33f6eb6160a2e0eb5276b0c08d9a5d9c2534cfd`（`feat: implement family collaboration foundation`）实施并封板。正式范围包括 `CommandIdempotencyRecord`、`FamilyInvitation`、`FamilyMembership`、Owner/active Collaborator 协作管理门禁、`invitation_acceptance` 身份核验与 context-bound `verification_proof`、邀请/成员 API，以及 migration `b7e2c4d891a0`。Local Validation：PASS；Remote Validation：PASS；[Backend CI run 37492358055](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37492358055)，master，completed / success。最新验证：Ruff/format PASS；Fast 163 passed / 29 deselected；PostgreSQL integration 29 passed / 163 deselected；Alembic head/current/check 及 post-integration current/check PASS；并发与安全验证 PASS。

C2B 已由 implementation commit `1038313cd57f6a76f5c6c27213912284e5af38fa` 和 remediation commit `fbb79b6a8af06b3d50e1d4923eb56169128efcde` 实施并封板；migration 为 `d4f8a1c2b3e6`，down revision 为 `b7e2c4d891a0`。Remediation commit 对应的 [Backend CI run 37627066699](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37627066699) 在 master 上 completed / success：PostgreSQL 16.15，Fast 173 passed / 40 deselected，PostgreSQL integration 40 passed / 173 deselected，Ruff、format、Alembic heads / fresh upgrade / current / check / post-integration current/check 均通过。

C2B 已实现 `InterviewParticipant`、speaker-only V1 role、稳定 `interview_scope_id`、Participant proposal、`participant_confirmation`、context-bound 本人身份核验、account / rights_only 本人最小访问、本人确认/停用、成年声明、幂等复用、verified `UserContact` 绑定及数据库约束和危险 downgrade 保护。Participant verified 不等于 Consent；Participant relationship 和 FamilyMembership 均不授予 Family archive 内容访问权。既有内容 API 继续保持 Owner-only，除明确新增的 Participant 最小本人 rights path 外。Consent、生产 Source/Provenance 链路（除前述 dormant ORM foundation 外）、RevisionProposal、Deletion Pipeline、Privacy Ledger、Outbox、Sanitization 与 MemoryCandidate 仍未实现；人工 Memory / 确定性 Memoir Slice 1 已实现，正式版本审批仍待 9.6-B。Part 9.5.5-C 仍为 Implementation In Progress。

- [Part 开发路线图](docs/05_开发阶段记录/Part开发路线图_V2.0.md)
- [系统架构总览](docs/01_架构设计/AI人生回忆录平台_系统架构总览_V1.1.md)
- [Audio/STT 数据模型设计基线](docs/02_数据模型/Part9.5_Audio-STT数据模型设计基线_V1.0.md)
- [ADR-003 Family档案删除策略](<docs/06_技术决策记录/ADR/ADR-003 Family档案删除策略.md>)
- [ADR 目录](docs/06_技术决策记录/ADR/)

代码和文档工作遵循 [Root AGENTS.md](AGENTS.md) 与 [Backend AGENTS.md](apps/backend/AGENTS.md)。templates/ 是代码母版，不参与运行时 import。


## Part 9.6-A Provider Extension — 当前状态（2026-10-12）

- **Status：Implementation Completed**
- **Independent Review：PASS**
- **Scope：Offline Provider Extension**
- **Limitations：**
  - HTTP/ASGI NOT VERIFIED
  - PostgreSQL NOT VERIFIED
  - Real AI Provider NOT IMPLEMENTED
- **Release：DEVELOPMENT SNAPSHOT ONLY**
- **下一阶段：Part 9.6-B Candidate + Revision + Human Review**

依据项目 Owner 确认的实施完成与独立审查 PASS 状态同步；本轮不复跑测试或审查，不增加 HTTP、PostgreSQL 或真实 Provider 验证结论。详细范围与历史记录见 [Provider Extension Contract V1.0](docs/04_AI设计/Part9.6-A_Provider-Extension_Implementation-Contract_V1.0.md)。本次只同步文档，未执行 Git 写操作。

## Part 9.6-A Provider Extension 合同草案归档（2026-10-12）

> 以下保留合同起草与归档时的历史状态；其中 Draft / Pending / NOT STARTED 已由上方当前状态取代。

- 完整合同草案见：[Scope Freeze + Implementation Contract V1.0](docs/04_AI设计/Part9.6-A_Provider-Extension_Implementation-Contract_V1.0.md)，作为本子阶段详细草案的唯一来源。
- Product Scope：**CONFIRMED**；Contract：**DRAFT — PENDING INDEPENDENT REVIEW**；Implementation：**NOT STARTED**。归档不构成实施批准。
- 近期步骤：独立合同审查与批准 → 另行授权的离线 Provider Extension 实施；9.6-B 仍为 Candidate + Revision + Human Review，9.6-C 仍为获批后的真实 Provider 接入。
- 本次只归档文档；未运行测试、操作数据库或执行 Git 暂存、提交、推送。既有 9.6-A 实现及其验证边界保持原有记录。


## Part 9.6-B — 完整设计草案归档（2026-10-12，历史主线快照）

详细 SSOT：[Candidate + Immutable Revision + Human Review — Implementation Contract V1.0](docs/04_AI设计/Part9.6-B_Candidate-Revision-Human-Review_Implementation-Contract_V1.0.md)。

| 项目 | 最新状态 |
| --- | --- |
| 9.6-A Provider Extension | 本地已提交 master @ `6c12e96e4f83ada7cb7c7dd60fec4283269f8700`；本次未核验 push/远端 CI |
| 9.6-B 产品决定 | CONFIRMED：单条原始文字提取、重跑新批次、不可变 Revision、Owner 明确审批、Memoir 精确版本引用 |
| 9.6-B 工程合同 | REVISED DRAFT — PENDING TARGETED RE-REVIEW |
| 9.6-B Implementation | NOT STARTED / NOT AUTHORIZED |
| Next | 定向合同再审 → 用户批准修订后的精确实施范围；归档不构成 Design Freeze 或代码批准 |
| 9.6-C | FUTURE / NOT STARTED；真实 Provider 与 Consent 门禁另行批准 |

本节保存当时草案与提交准备状态；当前状态见文首“当前阶段”，历史验证记录保留其日期与范围。详细草案包含单一 RevisionProposal 审批权威的离线 profile、表与 FK、状态机、API 切换、敏感 HMAC、Legacy 迁移、57 项验收及 42 个拟实施源码文件；真实 C3/C4/C6 不因此完成。HTTP/ASGI、PostgreSQL、真实 Provider 和生产验收边界按各次验证范围记录。

本次 Documentation Only：未修改 runtime、migration、tests、workflow 或配置，未运行应用/测试、操作数据库/Docker 或暂存、提交、推送；既有未提交内容保留。

## Part 9.6-B — 合同审查最小修订（2026-10-12，历史状态）

正式独立合同审查：**PASS WITH FINDINGS（Medium 2 / Low 1）**。详细修订与历史审查 hash 保存在 [合同 §15.3](docs/04_AI设计/Part9.6-B_Candidate-Revision-Human-Review_Implementation-Contract_V1.0.md#153-正式独立合同审查与本次修订2026-10-12)。

- B-CR-01：明确旧 Interview / FamilyMember / Family DELETE 的引用预检、Service 回滚、三个 CRUD 单目标删除及窄错误边界；拟范围增补6个既有文件，**42=20新增＋22修改**。
- B-CR-02：只验收离线 Stub 的 TimeoutError 安全分类；不声称五秒实际 deadline、中断或取消已实现。
- B-CR-03：版本仅按已有目标/Proposal命令要求；新建例外、旧禁用入口兼容明确。
- 补充提交不确定后的只读查询：pending/终态/unknown分别返回，不因暂缺记录重执行。未来验收现为**57项**。

产品决定 P01–P11不变。**REVISED DRAFT — PENDING TARGETED RE-REVIEW；IMPLEMENTATION NOT STARTED / NOT AUTHORIZED。** 42文件范围须再审及用户明确批准；本轮仅修订文档，未写代码/测试/migration或操作数据库/Git。
