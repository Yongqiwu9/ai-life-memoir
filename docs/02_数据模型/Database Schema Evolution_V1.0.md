# Database Schema Evolution_V1.0

> 下文 V1–V4 及数据库原则记录既有数据库基线。Part 9.5.5-C 的详细冻结设计见：[Family Collaboration / Participant / Consent Design Freeze V1.0](../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md)；其 `IMPLEMENTATION NOT STARTED` 是归档时的历史状态。当前 Part C 为 Implementation In Progress，C1 与 C2A 均已 Completed / Sealed，C2B 为 Implemented / Audit Remediation Completed / Pre-Commit Re-Audit #2 Pending。
> C1/C2A 已有正式增量迁移；C2B 增量迁移仍在未提交工作区。Consent、来源及删除传播仍以 SSOT 为准且尚未实现。既有 CASCADE 声明不能代替冻结的生命周期政策。

## V1 基础模型

User

作为所有资源归属根节点。

## V2 Family模型

新增：

families

family_members

关系：

User \| Family \| FamilyMember

## V3 Interview模型

新增：

interviews

interview_sessions

interview_messages

关系：

FamilyMember \| Interview \| Session \| Message

## V4 Audio/STT模型

新增：

audio_recordings

transcripts

transcript_segments

关系：

Session \| AudioRecording \| Transcript \| TranscriptSegment

Message扩展：

source

transcript_segment_id

## 当前数据库原则

### C1 Policy + Identity Foundation（Completed / Sealed）

Implementation commit：`35ec7e33a060b07e4834091b04c2caeb852b707c`；Backend CI run `37412935434`：completed / success。

- revision：`c1a7d45e92b0`，down revision：`adf9c60d178d`，单 head。
- `users`：新增 `principal_kind`（account/rights_only/system）和 `auth_generation`；email/password_hash 按能力条件可空，CHECK 保证 account 有凭据、非 account 无密码凭据。已有用户仅回填 account / generation=1。
- `privacy_policy_versions`：UUID、version/state、JSONB parameters/notices/capabilities、BYTEA digest、published_at 和 UTC 时间戳；version/digest 唯一，active 部分唯一。完整发布校验及 PostgreSQL trigger 防止改写已发布正文、重激活和删除已发布版本。
- `user_contacts`：User RESTRICT FK、kind、加密接口承载的 BYTEA value_ciphertext、带服务器密钥的 lookup_hash、state、verified_at/revoked_at 和 UTC 时间戳；pending/verified 渠道部分唯一。旧邮箱不自动生成 Contact 或 verified 证据。
- `auth_challenges`：可空 User RESTRICT FK、context、channel_ciphertext/hash、code_digest、state、expires_at/consumed_at、attempt_count 和 UTC 时间戳；上下文/渠道/摘要/到期不可变，消费采用锁和条件状态更新，禁止重放。
- 所有生产 duration 必须显式定义正整数 seconds；无生产默认 retention。生产加密/投递/限流 Provider 未接入，不能把 BYTEA 字段存在表述为生产加密已完成。
- downgrade 仅允许新增表全空、所有 User 仍为 account / generation=1；存在 C1 证据、非账号主体或 generation 变更时拒绝降级，防止静默丢失安全资料。
- 没有新建 FamilyMembership、Participant、Consent、Source、Deletion、Sanitization 或 Memory 表；现有来源正文和身份未做推定 backfill。

完整目标结构仍见 [Part 9.5.5-C Design Freeze](../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md)，本节仅记录 C1 增量。

### C2A Family Collaboration Foundation（Completed / Sealed）

Implementation commit：`a33f6eb6160a2e0eb5276b0c08d9a5d9c2534cfd`；Backend CI run `37492358055`：completed / success。

- revision：`b7e2c4d891a0`，down revision：`c1a7d45e92b0`，单 head；未修改历史 migration。
- `command_idempotency_records`：按 actor/operation/key 持久化 request digest、状态及安全响应元数据；账号与匿名键分别使用部分唯一索引，记录与业务变更在同一事务提交。
- `family_invitations`：加密接口承载 recipient ciphertext、keyed lookup hash、唯一 token digest、状态/version、审批/接受/过期时间；同 Family + recipient 的 pending_owner/approved 邀请使用部分唯一索引。
- `family_memberships`：仅保存 collaborator；active/revoked/left 与 generation；`UNIQUE(family_id,user_id)`；重入复用同一行并递增 generation。
- FK：Family 对 Invitation/Membership 为 CASCADE；User 关系为 RESTRICT；Membership.accepted_invitation_id 为 SET NULL；`families.owner_id` 从 CASCADE 改为 RESTRICT。
- 新表不做历史业务 backfill，不创建 Owner Membership，不按邮箱推定 Collaborator、Participant 或 Consent。
- 没有 Owner Membership backfill、历史 Invitation backfill、Participant backfill 或 Consent backfill。
- PostgreSQL 已验证 CHECK、partial unique、token digest unique、Membership unique、JSONB/BYTEA/TIMESTAMPTZ、FK 行为和并发写入；`alembic check` 无漂移。
- InterviewParticipant、Consent、Source/Provenance、Revision、Deletion、Sanitization、Memory 表均未创建。

### C2B Interview Participant Identity Foundation（Audit Remediation Completed / Pre-Commit Re-Audit #2 Pending）

- 工作区 revision：`d4f8a1c2b3e6`，down revision：`b7e2c4d891a0`，单 head；未修改历史 migration。
- `interview_participants`：稳定 `interview_scope_id`、可空 live Interview / FamilyMember 链接、speaker-only role、proposed/verified/inactive/disputed 状态、eligibility、本人 User/Contact/Challenge 证据和 version。
- FK：Interview / FamilyMember 为 SET NULL；User 为 RESTRICT；`(verified_contact_id,user_id)` 复合 FK 指向新增的 `UNIQUE(user_contacts.id,user_id)`；`verification_ref` 按冻结设计不建 FK。`family_member_id ON DELETE SET NULL` 仅允许真实 FamilyMember 父记录删除触发的 A→NULL 清理；父记录仍存在时手工 A→NULL、A→B，以及创建后 NULL→A 均由 narrow trigger 拒绝。`interview_scope_id` 始终不可变。
- 候选键：`UNIQUE(id,interview_scope_id)` 为后续 SourceSpeakerBinding 同 Interview 复合 FK 预留；既有 partial `UNIQUE(interview_scope_id,user_id) WHERE user_id IS NOT NULL` 保持不变。
- PostgreSQL CHECK 强制状态/资格组合、verified 完整证据、proposed 未认领状态和正 version；数据库 trigger 保护稳定 scope 与验证证据。
- `participant_confirmation` 同时支持 account 与 rights_only 本人核验；Participant verified 不授予 Family/Interview 内容访问，也不创建 Consent 或 Source 归属。
- 本地验证：Fast `173 passed / 40 deselected`；PostgreSQL integration `40 passed / 173 deselected`；C2B PostgreSQL `11 passed`；Alembic 空表 downgrade/re-upgrade、数据存在 downgrade guard、current/check 通过。Audit Remediation #2 已完成，等待 Pre-Commit Re-Audit #2；尚未提交或执行远程 CI。

-   UUID主键
-   外键约束
-   时间字段timezone-aware
-   Owner Isolation
-   级联删除策略待最终确认
