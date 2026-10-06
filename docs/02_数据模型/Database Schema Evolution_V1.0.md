# Database Schema Evolution_V1.0

> 下文 V1–V4 及数据库原则记录既有数据库基线。Part 9.5.5-C 的详细冻结设计见：[Family Collaboration / Participant / Consent Design Freeze V1.0](../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md)；其 `IMPLEMENTATION NOT STARTED` 是归档时的历史状态。当前 Part C 为 Implementation In Progress，C1 已 Completed / Sealed。
> 新增实体、FK 调整、历史资料 fail closed、来源及删除传播的迁移设计以该 SSOT 为准；尚未创建或执行 C 的 Migration。既有 CASCADE 声明不能代替冻结的生命周期政策。

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

-   UUID主键
-   外键约束
-   时间字段timezone-aware
-   Owner Isolation
-   级联删除策略待最终确认
