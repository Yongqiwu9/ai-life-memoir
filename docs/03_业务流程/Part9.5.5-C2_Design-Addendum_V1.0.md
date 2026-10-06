# Part 9.5.5-C2 — Design Freeze Addendum V1.0

| Metadata | Value |
| --- | --- |
| Status | ACCEPTED DESIGN ADDENDUM |
| Parent | Part 9.5.5-C Design Freeze V1.0 |
| Scope | C2A + C2B implementation clarification |
| Implementation | PARTIAL — C2A Completed / Sealed; C2B Next / Not Started; overall C2 not complete |
| Baseline | `0add93b755422afcf69c6029c4c72879405eb98d` |

本 Addendum 补充但不推翻 Part 9.5.5-C Design Freeze。未在此处修改的设计继续以父级 Design Freeze 为准。

## 1. InterviewParticipant V1 Domain

### 1.1 Role

`InterviewParticipant.roles` 在 V1 只允许 `speaker`。不得增加 `operator`、`subject`、`observer`、`facilitator` 或 `consenter`：operator 是独立 User 操作事实，`Interview.family_member_id` 表示主要回忆对象，consenter 属于后续 ConsentEvent。

主要回忆对象本人参与访谈时，创建 role=`speaker` 的 Participant，并可显式关联与 Interview subject 相同的 FamilyMember。

### 1.2 Eligibility

`eligibility_state`：

- `unknown`
- `eligible`
- `ineligible`

合法组合：

- `proposed + unknown`
- `verified + eligible`
- `inactive + eligible/ineligible`
- `disputed + unknown/eligible/ineligible`

verified 必须满足：本人即时验证完成、`participant.user_id` 已确定、verified UserContact 属于该 User、成年且能自主决定的本人声明完成、`eligibility_state=eligible`。

### 1.3 State transition authority

- Owner / active Collaborator：只能创建 proposed Participant。
- Participant 本人：可以将自己的 `proposed → verified`、`verified → inactive`。
- System/Service：发现 User、Contact 或 Context 身份冲突时，可以转为 disputed。
- Owner / Collaborator：C2 不提供直接把其他 Participant 改成 verified、inactive 或 disputed 的 API。

Participant inactive 不等于 Consent withdrawal；Participant disputed 不等于 Source deletion；Participant verified 不等于 Consent。

## 2. Context-bound Identity Verification

### 2.1 Challenge contexts

AuthChallenge 支持：

- `rights_auth`
- `invitation_acceptance`
- `participant_confirmation`

C1 的通用 `rights:identity` token 不能直接确认 Invitation 或 Participant。

### 2.2 Public API

- `POST /api/v1/identity-verifications/challenges`
- `POST /api/v1/identity-verifications/challenges/{id}/verify`

验证结果签发短期 `verification_proof`。Proof 至少包含 `sub`、`token_type=verification_proof`、`scope=identity:verify`、`context_kind`、`context_id`、`challenge_id`、`contact_id`、`auth_generation`、`iat`、`exp`、`aud`、`iss`。

Proof 不能访问 Family、Interview、account API 或 `rights/me`，不能代替 account JWT 或 Consent，只能用于 claims 指定的 context。

### 2.3 Invitation binding

Invitation accept 必须同时核验：

- actor 是 account；
- invitation token digest 匹配；
- proof context 是 `invitation_acceptance` 且指向当前 Invitation；
- proof subject 等于当前 account User；
- verified Contact 属于该 User；
- Contact lookup hash 匹配 Invitation recipient hash；
- `recipient_user_id` 非空时等于当前 User。

Invitation verification 的 recipient channel 必须由服务端从 Invitation 解密取得，客户端不得替换。

### 2.4 Participant binding

Participant confirm 必须核验 proof context 指向当前 Participant，Contact 属于 proof subject，Challenge 已 consumed，Challenge/User/Contact/Participant context 一致。

`participant.user_id` 为 NULL 时，确认事务可 claim 为 `proof.sub`；已有 user_id 时必须等于 `proof.sub`。不匹配时 fail closed 并进入身份冲突处理。

### 2.5 Account and rights-only isolation

- account 完成核验时，Contact 绑定当前 account，不创建 rights_only User。
- rights_only 完成核验时保持 rights_only，不升级为 account。
- 相同 email/phone 不得自动合并两个 User。

`InterviewParticipant.verification_ref` 保存 AuthChallenge UUID 作为不可变证据引用，本阶段不建立 FK。Service 在确认事务中验证 Challenge 已 consumed，且 context、User、Contact 全部一致。

## 3. Durable Command Idempotency

### 3.1 Model

新增 `CommandIdempotencyRecord`，表名 `command_idempotency_records`：

- `id UUID PK`
- `actor_user_id UUID nullable`
- `operation VARCHAR NOT NULL`
- `idempotency_key UUID NOT NULL`
- `request_digest BYTEA NOT NULL`
- `state VARCHAR NOT NULL`
- `resource_kind VARCHAR nullable`
- `resource_id UUID nullable`
- `response_status INTEGER nullable`
- `response_body JSONB nullable`
- `created_at TIMESTAMPTZ NOT NULL`
- `completed_at TIMESTAMPTZ nullable`
- `expires_at TIMESTAMPTZ nullable`

状态：`processing`、`completed`、`failed_retryable`。`request_digest` 固定 32 字节。

Partial unique：

- `(actor_user_id, operation, idempotency_key)` where actor_user_id is not null；
- `(operation, idempotency_key)` where actor_user_id is null。

C2A public mutation 要求 authenticated account actor。

### 3.2 Transaction and replay

新命令在一个数据库事务中创建 processing record、执行业务 mutation、保存安全结果元数据、转为 completed 并提交。事务回滚时新记录与业务 mutation 一起回滚。

同 actor、operation、key、request digest 返回原业务语义结果；同 actor、operation、key 但 digest 不同返回 409。数据库 unique、事务和锁保证并发命令只有一个真正执行。

verification proof 等短期结果的 replay 不得延长原 exp，也不得重新签发更长授权窗口。

### 3.3 Sensitive-data prohibition

`response_body` 仅接受按 operation 显式注册的强类型安全 DTO snapshot；未知 operation、错误 snapshot 类型、未知字段和任意未声明嵌套对象均默认拒绝。不得提供保存任意 dict 的通用入口，也不得以敏感字段 blocklist 作为安全边界。不得保存 OTP、Invitation 明文 token、JWT、verification proof 原文、Contact 明文/密文/lookup hash、secret、provider credential 或完整异常正文。verification proof 重放只保存原始 `issued_at`、`expires_at`、context 与必要安全标识，重签时不得延长原授权窗口。

`request_digest` 基于规范化请求的单向摘要；不得持久化可恢复的 secret 请求正文。

## 4. Implementation Split

### C2A

- CommandIdempotencyRecord
- FamilyInvitation
- FamilyMembership
- Owner/Collaborator authorization primitive
- invitation_acceptance verification context
- Invitation/Membership API
- PostgreSQL migration and tests

### C2B

- InterviewParticipant
- participant_confirmation verification context
- verification proof dependency reuse
- rights-scoped Participant API
- PostgreSQL migration and tests

C2A revision 接 C1 head；C2B revision 接 C2A。

## 5. Implementation Evidence

- C2A implementation：`a33f6eb6160a2e0eb5276b0c08d9a5d9c2534cfd`（`feat: implement family collaboration foundation`）。
- C2A migration：`b7e2c4d891a0`，down revision `c1a7d45e92b0`。
- Remote validation：Backend CI run [`37492358055`](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37492358055)，completed / success。
- Seal status：C2A Completed / Sealed；C2B Next / Not Started；Part 9.5.5-C Implementation In Progress。

本节只记录 C2A 实施证据，不修改本 Addendum 已接受的 B1 Participant domain、B2 context-bound verification 或 B3 durable idempotency semantics。
