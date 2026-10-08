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

Part 9.5.5-C — Design Frozen / Implementation In Progress。C1 Policy + Identity Foundation、C2A Family Collaboration Foundation、C2B Interview Participant Identity Foundation — Completed / Sealed。Part 9.5.5-B — Completed / Sealed，其 Local validation: PASS、Remote CI: VERIFIED / PASS 作为历史验收记录保留。

下一阶段：

Part 9.5.5-C3.0 Implementation Contract — Completed / Audited / Published；Final Seal 待本次文档封板提交自身的 exact Backend CI 成功。C3 实际实施 NOT STARTED；下一阶段 C3.1 Registry Schema / Models — Next / Planned / NOT STARTED，须等待 C3.0 Final Seal 生效。Part 9.6 保持 Planned / NOT STARTED。

## 4. Part 9.5.5-C1 Policy + Identity Foundation 本地实施记录

日期：2026-10-05。起始 HEAD：`ade0f0ca2dbecab474d315a853b2e7721e9e9609`，master；本轮不暂存、不提交、不推送。

- 仅新增 PrivacyPolicyVersion / UserContact / AuthChallenge；User 新增 principal_kind / auth_generation，条件放宽凭据字段。既有 User 只回填 account / generation=1，不自动验证邮箱、不合并主体。
- Policy 使用显式正整数 seconds 和独立非负 retry_limit；draft 可缺参，active 必须完整且能力证据有效，发布正文不可变。没有生产默认期限。
- rights-auth challenges / verify / rights/me 为最小认证入口；rights:identity 不授予 Family 浏览、Speaker 身份或 Consent。普通账号接口保持形状；旧无类型/无 generation JWT 须重新登录。
- OTP 不保存明文，摘要由服务器密钥和 challenge 上下文绑定；校验有到期、尝试上限、事务消费、重放拒绝、渠道冲突拒绝与当前 generation / Contact 状态校验。错误响应不回显渠道或验证码。
- 生产 encryption / key lifecycle / delivery / rate limiting Provider 未接入，默认 503。测试 opaque memory vault 仅为测试替身，不是生产加密；没有新增生产密钥或默认 TTL。
- migration `c1a7d45e92b0` → down `adf9c60d178d`，单 head。真实专用 PostgreSQL 测试库 upgrade / current / check 已通过；临时 schema 空库迁移及有旧 User 的 backfill、空 C1 安全 downgrade / re-upgrade 已验证。存在 C1 证据、非 account 或 generation 变更时 downgrade 拒绝执行。没有迁移开发/生产库。
- 首轮 fast：125 passed / 17 deselected。此后新增边界用例，最终完整 fast 复验待完成，不能沿用首轮结果作为最新全量通过证明。
- 最新 PostgreSQL integration：17 passed / 139 deselected；Ruff check 通过，format check：104 files already formatted。环境存在 Starlette TestClient/httpx 弃用提示。
- 自动审批审核模型容量不足，阻止最终 fast（本地 socketpair）和 Alembic 最后复查；属于审核服务执行障碍，不是判定操作不安全。当前不满足提交验收条件。
- 未实现 FamilyMembership / FamilyInvitation / InterviewParticipant / Consent / SourceArtifact / Deletion / Sanitization / MemoryCandidate；workflow 未改动，C1 远程 CI 未运行。
- 保留 16 项既有模板删除为 unstaged；ad untouched/untracked；.env.test ignored；staging empty。冻结 SSOT 未修改，9.5.5-B Completed、C Design Frozen、C Implementation In Progress、C2 Not Started、9.6 Planned。

验收命令（Backend 目录；只允许安全 TEST_DATABASE_URL 的测试迁移模式）：

```powershell
python -m ruff check .
python -m ruff format --check .
python -m pytest -m "not integration" -q -p no:cacheprovider
python -m pytest -m integration -q -p no:cacheprovider
$env:TEST_MIGRATION_MODE = '1'
python -m alembic heads
python -m alembic current
python -m alembic check
```

原结论（已由下方最终验证闭环取代）：C1 implementation written / final validation pending。本节状态优先于上文设计归档时的 Implementation Not Started 历史记录。

### C1 Final Validation Closure（2026-10-05）

- Ruff：PASS；format check：PASS（103 files already formatted）。
- 最新完整 Fast：139 passed / 0 failed / 0 skipped / 17 deselected；新增身份与安全边界测试均实际执行。
- C1 定向安全测试：45 passed / 0 failed / 0 skipped。
- PostgreSQL integration：17 passed / 0 failed / 0 skipped / 139 deselected。
- Alembic before/after：single head/current 均为 `c1a7d45e92b0`；两次 `alembic check` 均为 `No new upgrade operations detected`。
- 账号回归：register、login、users/me、Family、Interview 全部通过最新 Fast suite；rights/account token 与 principal 能力隔离通过。
- 安全审计：generation mismatch、Contact revoked、Challenge expired/locked/consumed replay、OTP 非明文、反枚举、敏感错误不回显、legacy email 不自动验证、Policy fail-safe、已发布 Policy 不可普通修改均通过。
- migration 审计：down revision、历史 User account/generation=1 backfill、数据库约束、JSONB/BYTEA/TIMESTAMPTZ、partial unique、RESTRICT FK 与 downgrade guard 符合 C1 范围；没有修改历史 migration。
- Production encryption、contact delivery、key management 与生产 rate limiter 仍为 NOT IMPLEMENTED；默认 fail closed / 503。测试内存 vault 仅为 TEST ONLY。
- 非阻塞警告：Starlette TestClient/httpx 弃用提示；pytest cache 目录 WinError 183。测试与检查退出码均为 0。
- Git：HEAD 未变、staging empty、16 项历史删除 unstaged、`ad` untracked/untouched、`.env.test` ignored；未 commit / push。

结论：C1 Implemented / Validated；Part C 仍为 Implementation In Progress；C2 Not Started / Next；Part 9.6 Planned。READY FOR C1 PRE-COMMIT AUDIT，不代表已获授权暂存或提交。

### Part 9.5.5-C1 Final Documentation Seal（2026-10-06）

- Part：9.5.5-C1 Policy + Identity Foundation。
- Status：Completed / Sealed；Part 9.5.5-C 整体仍为 Implementation In Progress。
- Implementation commit：`35ec7e33a060b07e4834091b04c2caeb852b707c`，`feat: implement policy and identity foundation`。
- Remote：`origin/master`；push 后 HEAD 与 origin/master 一致。
- Remote CI：Backend CI；Run ID `37412935434`；[Run URL](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37412935434)；completed / success。
- Local validation：Fast 139 passed / 17 deselected；targeted security 45 passed；PostgreSQL integration 17 passed / 139 deselected；Ruff PASS；Format PASS；Alembic heads/current/check 及测试后 current/check PASS。
- Security audit：Critical 0；High 0；Medium 0。
- 实施范围：PrivacyPolicyVersion、User principal_kind/auth_generation、UserContact、AuthChallenge、rights_only authentication foundation、Policy capability gate。
- 边界：rights_only authentication 不等于 Speaker identity、Consent、Source ownership 或 Family collaboration permission。
- 生产限制：encryption provider、verification delivery、key management/rotation、production rate limiting 仍未实现，默认 fail closed。
- C2：Next / Not Started；未实现 FamilyMembership、FamilyInvitation、InterviewParticipant、Consent、SourceArtifact、Deletion Pipeline、Sanitization 或 MemoryCandidate。
- Part 9.6：Planned。

## 5. Part 9.5.5-C2A Family Collaboration Foundation 历史本地实施记录

日期：2026-10-06。起始/结束 HEAD：`0add93b755422afcf69c6029c4c72879405eb98d`；本轮未暂存、未提交、未推送。

- 归档 C2 Design Addendum 和 C2A Implementation Task；C2A 与整个 C2 完成状态明确分离。
- 新增 CommandIdempotencyRecord、FamilyInvitation、FamilyMembership；`Family.owner_id` 仍是唯一 Owner 权威，FK 从 CASCADE 调整为 RESTRICT，不为 Owner 创建 Membership，不做历史业务 backfill。
- Membership 仅允许 collaborator；active/revoked/left；revoke、leave、rejoin 递增 generation；新邀请重入复用同一 `(family_id,user_id)` 行。
- Owner 邀请直接 approved；active Collaborator 邀请进入 pending_owner 并需 Owner 审批。accept 在单事务内锁定并校验 Invitation、token、context-bound proof、account/UserContact，再创建或重启 Membership并标记 Invitation accepted。
- 新增 invitation_acceptance challenge 和短期 verification_proof；严格校验 token type、scope、aud/iss、context、account、Contact 和 auth_generation。proof 不能访问 account、Family 或 rights API，也不表示 Participant verified 或 Consent。
- public mutation 使用持久化 Idempotency-Key / canonical digest；同 key 同 digest 重放 operation-specific 强类型安全 snapshot，不同 digest 返回冲突；未知 operation、错误 snapshot、额外字段和未声明嵌套对象默认拒绝。response_body 不保存 OTP、邀请明文 token、proof、Contact PII/hash/ciphertext 或 provider credential；proof 重放保持原始 `iat`/`exp`。
- 新增邀请和 Membership API。可复用 Owner / active Collaborator 门禁只用于协作管理；既有 Family/FamilyMember/Interview/Session/Audio/Transcript/Segment/Message 内容 API 继续 Owner-only。
- revision `b7e2c4d891a0` → down `c1a7d45e92b0`，单 head；新表有 CHECK、partial unique、token digest unique、Membership unique 和明确 FK 删除行为。存在 C2A 业务/幂等证据时 downgrade 拒绝。
- Audit remediation：补齐 active Collaborator 对 Family/FamilyMember/Interview/Session/Audio/Transcript/Segment/Message 的精确 404 与无内容泄露矩阵；验证其仍可发起 pending_owner Invitation。新增 Collaborator create Invitation 与 Owner revoke Membership 的 PostgreSQL 竞争测试，证明现有 Family→Membership 锁顺序线性化，并验证 revoke 后新命令拒绝、Owner 命令不受影响。
- Validation：Ruff PASS；format PASS；Fast 161 passed / 29 integration deselected；PostgreSQL integration 29 passed / 161 non-integration deselected；Alembic heads/current/check 及测试后 current/check PASS；最终 head `b7e2c4d891a0`，无 schema drift。
- PostgreSQL 覆盖 fresh isolated schema migration、JSONB/BYTEA/TIMESTAMPTZ、FK/CHECK/partial unique、身份字段和完成幂等记录不可变约束、double accept、accept/expire、approve/cancel、approve/revoke、rejoin/stale-generation、Membership revoke authorization race、duplicate invitation 和重复幂等命令的竞争结果。
- 非阻塞警告：Starlette TestClient/httpx 弃用提示；pytest cache 目录 WinError 183。所有要求的检查退出码为 0。
- 未实现 InterviewParticipant、`participant_confirmation`、Consent、Source/Provenance、RevisionProposal、Deletion、PrivacyOutbox、Sanitization、MemoryCandidate、Memory 或 Memoir；未修改 workflow，未运行生产 migration。
- Git 安全：staging empty；16 项既有模板删除继续 unstaged；`ad` 保持 untracked；`.env.test` 保持 ignored 且未输出内容。

历史结论（已由下方 Final Documentation Seal 取代）：C2A Implementation Written / Audit Remediation Completed / Pre-Commit Re-Audit Pending；C2B Next / Not Started；Part 9.6 Planned。本节保留实施与审计轨迹，不表示当前状态。

### Part 9.5.5-C2A Final Documentation Seal（2026-10-07）

- Part：9.5.5-C2A Family Collaboration Foundation。
- Status：Completed / Sealed；Part 9.5.5-C 整体仍为 Implementation In Progress。
- Implementation commit：`a33f6eb6160a2e0eb5276b0c08d9a5d9c2534cfd`，`feat: implement family collaboration foundation`。
- Migration：`b7e2c4d891a0`，down revision `c1a7d45e92b0`；单 head；未修改历史 migration，未运行生产 migration。
- Remote CI：Backend CI；Run ID [`37492358055`](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37492358055)；master；completed / success。
- Validation：Fast 163 passed / 29 deselected；PostgreSQL integration 29 passed / 163 deselected；Ruff PASS；Format PASS；Alembic heads / fresh upgrade / current / check / post-integration current/check PASS；Concurrency PASS；Security PASS。
- Audit history：Initial Pre-Commit Audit FAIL；Remediation #1 PASS；Re-Audit #1 FAIL；Remediation #2 PASS；Final Pre-Commit Re-Audit PASS WITH FINDINGS；blocking findings at seal：0。
- 实施范围：CommandIdempotencyRecord、FamilyInvitation、FamilyMembership、Owner / active Collaborator 协作管理门禁、`invitation_acceptance` context-bound verification proof、Invitation / Membership API，以及 `families.owner_id` ON DELETE RESTRICT。
- 安全边界：转发 Invitation token 拒绝；Collaborator 没有既有档案内容访问扩张；Membership revoke race 线性化；幂等响应使用 operation-specific allowlist / default deny；request fingerprint 不保存原始 recipient/token/proof/OTP canonical input；Provider 不可用时 fail closed。
- Membership 只代表 Family collaboration relation，不等于 archive content access。既有 Family、FamilyMember、Interview、Session、Audio、Transcript、Segment、Message API 仍为 Owner-only。
- 未实现：InterviewParticipant、`participant_confirmation`、ConsentGrant / ConsentEvent、Source / Provenance、RevisionProposal、Deletion Pipeline、Sanitization runtime、MemoryCandidate、Memory、Memoir。
- 生产限制：encryption provider、verification/invitation delivery、key management/rotation、production rate limiting 仍未实现；相关入口默认 fail closed。
- 下一阶段（C2A Seal 当时记录）：C2B Next / Not Started；该历史状态已由下方 C2B 本地实施记录取代。Part 9.6 Planned。

## 6. Part 9.5.5-C2B Interview Participant Identity Foundation 实施与 Remediation 记录（2026-10-07）

- 历史状态（已由下方 Final Documentation Seal 取代）：implementation commit `1038313cd57f6a76f5c6c27213912284e5af38fa` 已发布；当时 Remote CI Remediation #1 已完成本地验证，等待独立 remediation commit 与远程 CI，C2B 尚未封板。
- 新增 InterviewParticipant、speaker-only role、eligibility/state 数据库约束、稳定 Interview scope、UserContact 复合归属约束与危险 downgrade 保护。
- 新增 Owner/active Collaborator proposal、account/rights_only `participant_confirmation`、本人 context-bound confirm、成年自主决定声明、本人 inactive 和最小本人读取。
- Participant 身份关系不扩大 Family/Interview/Session/Audio/Transcript/Segment/Message 权限；verified 不产生 Consent、Source 归属、撤回或删除语义。
- migration：`d4f8a1c2b3e6`，down revision `b7e2c4d891a0`，Alembic 单 head，current/check PASS。
- Initial Pre-Commit Audit 的三个 Blocking Medium 已关闭：FamilyMember 真实删除可安全 SET NULL 且普通改绑仍拒绝；新增 `UNIQUE(id, interview_scope_id)`；补齐真实 PostgreSQL FK/CHECK/unique 与 Participant proof、rights-only、幂等安全测试。
- Fast：173 passed / 40 deselected；PostgreSQL integration：40 passed / 173 deselected；C2B PostgreSQL：11 passed；Ruff/format PASS；Alembic 空表 downgrade/re-upgrade、数据存在 downgrade guard、current/check PASS。
- PostgreSQL 验收基线：PostgreSQL 16.x，当前本地集成测试与 GitHub Actions 均使用 16.15；其他 major 版本不作为权威验收证据，major 升级必须另行完成兼容性验证。
- Remote CI Remediation #1：修正两个真实 `DELETE User` 测试的预期 SQLSTATE 为 PostgreSQL 16.15 实际返回的 `23503`；direct Participant FK 测试继续校验动态解析的约束名。16.15 本地结果：目标测试 3 passed、C2B PostgreSQL 11 passed、Fast 173 passed / 40 deselected、PostgreSQL integration 40 passed / 173 deselected、Ruff/format PASS、Alembic heads/fresh upgrade/current/check 及 post-integration current/check PASS。未修改 runtime 或 migration `d4f8a1c2b3e6`。
- Part 9.5.5-C 整体仍为 Implementation In Progress；Part 9.6 仍为 Planned。

### Part 9.5.5-C2B Final Documentation Seal（2026-10-07）

- Part：9.5.5-C2B Interview Participant Identity Foundation。
- Status：Completed / Sealed；Part 9.5.5-C 整体仍为 Design Frozen / Implementation In Progress。
- Implementation commit：`1038313cd57f6a76f5c6c27213912284e5af38fa`。
- Remediation commit：`fbb79b6a8af06b3d50e1d4923eb56169128efcde`。
- Migration：`d4f8a1c2b3e6`；down revision：`b7e2c4d891a0`。
- Remote CI：Backend CI；Run ID [`37627066699`](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37627066699)；commit `fbb79b6a8af06b3d50e1d4923eb56169128efcde`；master；completed / success；PostgreSQL 16.15。
- Validation：targeted remediation 3 passed；C2B PostgreSQL 11 passed；Fast 173 passed / 40 deselected；完整 PostgreSQL integration 40 passed / 173 deselected；Ruff PASS；Format PASS；Alembic heads / fresh upgrade / current / check / post-integration current/check PASS；最终 head `d4f8a1c2b3e6`。
- Implemented scope：InterviewParticipant；speaker-only V1 role；participant state / eligibility constraints；稳定 `interview_scope_id`；Owner / active Collaborator participant proposal；`participant_confirmation` context；context-bound identity verification；account / rights_only 本人最小 Participant access；self confirm；adult declaration；self inactive；durable idempotency reuse；verified `UserContact` ownership binding；FK / CHECK / unique / immutable scope protections；dangerous downgrade protection。
- Security / privacy boundary：Participant verified 不等于 Consent；Participant relationship 不等于 Family archive content access；FamilyMembership 不等于 archive content access。既有 Family、FamilyMember、Interview、Session、Audio、Transcript、Segment、Message 内容 API 继续保持 Owner-only，除已明确新增的 Participant 最小本人 rights path 外。
- Not implemented：ConsentGrant、ConsentEvent、SourceArtifact、Provenance、SourceSpeakerBinding、RevisionProposal、Deletion Pipeline、Privacy Ledger、Outbox、Sanitization runtime、MemoryCandidate、Memory、Memoir。
- Production limits：production encryption provider、verification / invitation delivery、key management / rotation、production distributed rate limiting 均未实现；相关入口默认 fail closed，C2B sealed 不代表 production-ready。
- Remediation history：首次 C2B implementation remote CI 在 PostgreSQL 16 上因 SQLSTATE assertion 失败；最终确认 PostgreSQL 16.15 实际 SQLSTATE 为 `23503`，remediation commit 的 exact Backend CI 已成功闭环。本地 PostgreSQL 18.6 曾观察到不同行为，因此项目冻结 PostgreSQL 16.x baseline、当前验证版本 16.15；不声明支持 PostgreSQL 18，major upgrade 必须单独完成 compatibility validation。
- Next：C3 Artifact Registry + Provenance — Next / Planned，尚未开始；Part 9.6 — Planned。

## 7. Part 9.5.5-C3.0 Final Documentation Seal（2026-10-08）

### A. Contract evidence / Seal condition

- Contract：Completed / Audited / Published；[Implementation Contract Addendum](../03_业务流程/Part9.5.5-C3_Implementation-Contract-Addendum_V1.0.md)。
- Addendum commit：`345f852d36f94752ddea99fba1f889d9d632ded0`。
- Backend CI：[Run 37762742776](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37762742776)；trigger push；exact SHA matched YES；completed / success。
- Final Seal 条件：本次文档封板提交自身的 exact-commit Backend CI 成功后才生效；当前处于 Seal Preparation，未取得未来封板提交的 CI 结果。上面的运行只证明 Addendum commit，不是封板提交证据。
- 成功的 Backend CI 只验证当前 pre-C3 Backend 基线，不证明 C3 功能已实现。

### B. Audit evidence

- Final Contract Re-Audit：PASS。
- BM-01：Sequence parent-row lock protocol CLOSED。
- BM-02：Live Artifact consistency / deletion tombstone retention CLOSED。
- BM-03：Contribution / Artifact state domains separated CLOSED。
- BM-04：Immutable provenance / controlled projection updates reconciled CLOSED。
- Critical / High / Blocking Medium：0 / 0 / 0。

### C. Frozen product scope

- Friend Option A：Owner / active Collaborator 为特定 Interview 发起参与提议；复用 User + InterviewParticipant，不要求 FamilyMembership。
- 朋友必须本人完成身份确认及自己的 SourceSpeakerBinding 确认；不自动获得 Family Archive 访问权。
- 仅被提及的第三人属于内容语义，不进行自动身份推断；人物提取属于 Part 9.6 后续独立设计。

### D. Frozen technical scope — implementation requirements only

- SourceArtifact、SourceSpeakerBinding、ArtifactContribution、DerivedSource。
- 内容与 provenance 原子注册；PostgreSQL advisory transaction lock 与 DAG guard。
- 正向及 deferred reverse consistency；按生命周期区分删除状态例外。
- Message / Segment 序号并发合同；历史确定性 backfill。
- C3-A / C3-B 属于一次 cutover 的迁移合同，不允许部分迁移独立生产 rollout。
- 以上是冻结的实施要求，不是已经完成的实现。

### E. Current limitations

- C3 runtime：NOT IMPLEMENTED。
- C3 migrations：NOT IMPLEMENTED。
- C3 PostgreSQL-specific functional tests：NOT EXECUTED。
- Consent / Access Gate：NOT IMPLEMENTED，属于 C4。
- Production invitation delivery：NOT IMPLEMENTED。
- Memory person extraction：NOT IMPLEMENTED，属于 Part 9.6。
- 后续授权处理之前，C3 不得创建 available Artifact。
- PostgreSQL baseline：16.x；当前已验证版本 16.15。

### F. Next phase

- C3.1 Registry Schema / Models — Next / Planned / NOT STARTED；仅在 C3.0 Final Seal 生效且文档封板提交 exact CI 成功后开始。
- C3 整体实施 NOT STARTED；Part 9.5.5-C 仍为 Design Frozen / Implementation In Progress；C1/C2A/C2B Completed / Sealed；Part 9.6 Planned / NOT STARTED。
- 保留 C2B sealed boundary；不修改其 runtime、状态机、确认语义、migration 或 tests。
