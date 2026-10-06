# Part 9.5.5-C — Final Implementation Design Freeze

## Design Metadata

| Metadata | Value |
| --- | --- |
| Status | DESIGN FROZEN |
| Part | 9.5.5-C |
| Implementation | NOT YET COMPLETE / IMPLEMENTATION NOT STARTED |
| Baseline | 10d28f3b327022f651976089c6ae58a78a0de7c1 |
| Decision scope | Family Collaboration; Interview Participant; Consent; Source Provenance; Revision; Deletion; Sanitization; Privacy Policy |
| Important | DESIGN FROZEN != FEATURE IMPLEMENTED |

本文件是 Part 9.5.5-C 后续 C1–C8 实现的详细设计 SSOT。以下正文完整归档已确认的 Final Implementation Design Freeze；正文中的“本轮”指只读设计冻结讨论，归档任务仅修改文档。Markdown 标记及内部链接已整理，设计语义保持不变。

C2 implementation clarification 见 [Part 9.5.5-C2 Design Freeze Addendum V1.0](Part9.5.5-C2_Design-Addendum_V1.0.md)。该 Addendum 补充 C2 Participant domain、context-bound identity verification 与 durable command idempotency，不推翻本文其他冻结决策。

---

基线已核对：master @ 10d28f3b327022f651976089c6ae58a78a0de7c1。

以下是实施设计，**不代表功能已经实现**。本轮未修改文件、Migration、数据库或 Git，未运行测试；既有模板删除记录保持原样。

你补充确认的两个边界已纳入：

- 撤回用途到期后，清除该用途的分支和副本；其他独立有效用途仍可支持本人材料的受限保存。
- V1 本人核验采用即时手机/邮箱验证、成年自主决定声明、本人来源归属确认；身份冲突不自动合并，未解决前保持受限。

---

## 1. Domain Model

### 1.1 统一身份

**现有 User.id 是唯一认证主体。**

不新增 SpeakerIdentity，不把 FamilyMember 当作账号。

| 概念 | 职责 |
| --- | --- |
| User | 唯一主体；支持 account、rights_only、system 三种能力类型 |
| UserContact | User 的手机/邮箱验证渠道，不是另一个身份 |
| FamilyMember | 档案人物、Interview 的主要回忆对象 |
| FamilyMembership | User 访问某个 Family 的协作关系 |
| InterviewParticipant | User 在某次 Interview 中的参与关系 |
| SourceSpeakerBinding | 某位 Participant 对某份 Source 的实际贡献归属 |
| operator | 操作事件的 User |
| speaker | SourceSpeakerBinding 对应的 Participant/User |
| consenter | ConsentEvent 中亲自授权的 User |

三者分别记录。角色可以由同一个人承担，但不能相互推导。

当前 [User 模型](../../apps/backend/app/models/user.py#L18) 要求邮箱和密码非空，需要调整才能支持无注册讲述者；rights_only 会话不能使用现有普通账号权限。

### 1.2 C 阶段与后续范围

| 实体/能力 | 9.5.5-C |
| --- | --- |
| FamilyMembership、FamilyInvitation | 必须实现 |
| UserContact、AuthChallenge、rights_only 权限隔离 | 必须实现 |
| InterviewParticipant、本人资格及归属确认 | 必须实现 |
| ConsentGrant、ConsentEvent | 必须实现 |
| SourceArtifact、SourceSpeakerBinding、SourceConsentBinding | 必须实现 |
| ArtifactContribution、DerivedSource | 必须实现 |
| SourceRestoreRequest | 必须实现 |
| RevisionProposal：不可变修订与 Owner 审批 | 必须实现，承载已确认的协作者编辑规则 |
| DeletionRequest、DeletionTarget、DeletionLedger | 必须实现 |
| PrivacyPolicyVersion、PrivacyOutbox | 必须实现 |
| SanitizationRun、SanitizationConfirmation | 必须实现状态、验收和发布门禁 |
| 实际音频剪切、上传、STT/LLM 集成 | 9.6+ 实现；未接入时不能伪造成功 |
| MemoryCandidate、Memory、MemoirVersion | 9.6+ 建业务表；C 预留来源登记及清理协议 |
| Embedding、Vector index、Cache、Export、Provider copy | C 冻结登记/清理接口；对应适配器随后实现 |

这里的 **Source** 是原始音频文件或原始文字 Message。Transcript、Segment、Message copy、修订、AI 产物属于来源衍生物。

多人净化可以按已确认的 Speaker/Segment 操作；这不开放任意文字片段级授权。

---

## 2. ERD

图中未来业务实体标注为 reserved，不在 C 阶段创建其业务表。

~~~mermaid
erDiagram
    User ||--o{ Family : owns
    User ||--o{ UserContact : verifies
    User ||--o{ AuthChallenge : authenticates
    User ||--o{ FamilyMembership : joins
    User ||--o{ FamilyInvitation : requests
    User ||--o{ InterviewParticipant : participates
    User ||--o{ ConsentEvent : consents
    User ||--o{ DeletionRequest : requests

    Family ||--o{ FamilyMember : contains
    Family ||--o{ FamilyMembership : permits
    Family ||--o{ FamilyInvitation : invites
    FamilyMember ||--o{ Interview : subject
    FamilyMember o|--o{ InterviewParticipant : explicitly_links

    Interview ||--o{ InterviewParticipant : includes
    Interview ||--o{ InterviewSession : contains
    InterviewSession ||--o{ AudioRecording : records
    InterviewSession ||--o{ InterviewMessage : contains
    AudioRecording ||--o{ Transcript : transcribes
    Transcript ||--o{ TranscriptSegment : segments
    TranscriptSegment o|--o{ InterviewMessage : copied_into

    Family o|--o{ SourceArtifact : live_scope
    Interview o|--o{ SourceArtifact : live_scope
    InterviewSession o|--o{ SourceArtifact : live_scope
    SourceArtifact ||--o| AudioRecording : registers
    SourceArtifact ||--o| Transcript : registers
    SourceArtifact ||--o| TranscriptSegment : registers
    SourceArtifact ||--o| InterviewMessage : registers

    SourceArtifact ||--o{ SourceSpeakerBinding : identifies_speakers
    InterviewParticipant ||--o{ SourceSpeakerBinding : contributes
    SourceSpeakerBinding ||--o{ ArtifactContribution : contributes_to
    SourceArtifact ||--o{ ArtifactContribution : contains_contribution

    SourceArtifact ||--o{ DerivedSource : parent
    SourceArtifact ||--o{ DerivedSource : child

    InterviewParticipant ||--o{ ConsentGrant : grants
    ConsentGrant ||--o{ ConsentEvent : records
    ConsentGrant ||--o{ SourceConsentBinding : authorizes
    SourceSpeakerBinding ||--o{ SourceConsentBinding : scopes
    SourceConsentBinding ||--o{ SourceRestoreRequest : restores
    PrivacyPolicyVersion ||--o{ ConsentEvent : governs

    SourceArtifact ||--o{ RevisionProposal : revision_target
    SourceArtifact ||--o| RevisionProposal : revision_artifact
    User ||--o{ RevisionProposal : proposes

    SourceArtifact ||--o{ SanitizationRun : input
    SourceArtifact o|--o{ SanitizationRun : output
    SanitizationRun ||--o{ SanitizationConfirmation : requires
    InterviewParticipant ||--o{ SanitizationConfirmation : confirms

    DeletionRequest ||--o{ DeletionTarget : enumerates
    SourceArtifact o|--o{ DeletionTarget : targets
    DeletionRequest ||--o{ SanitizationRun : permits_attempt
    DeletionRequest ||--o{ DeletionLedger : records
    PrivacyPolicyVersion ||--o{ DeletionRequest : governs
    PrivacyPolicyVersion ||--o{ SourceRestoreRequest : governs
    PrivacyOutbox }o--|| PrivacyPolicyVersion : references

    SourceArtifact ||--o| MemoryCandidate : reserved
    SourceArtifact ||--o| Memory : reserved
    SourceArtifact ||--o| MemoirVersion : reserved
    SourceArtifact ||--o| Embedding : reserved
    SourceArtifact ||--o{ ExternalArtifact : reserved_locations
~~~

Family.owner_id 是 Owner 的唯一权威来源。Membership 只保存 Collaborator，不重复建立第二个 Owner 来源。

草稿 Interview 允许零个 Participant；实际采集必须具有至少一位已确认 Speaker，多人来源必须覆盖全部实际 Speaker。

---

## 3. Table Specification

### 3.1 通用规范

- 主键：id UUID NOT NULL PRIMARY KEY。
- T：TIMESTAMPTZ，UTC。
- ?：nullable；未标 ? 的字段均非空。
- 所有新增表具有 created_at T、updated_at T。
- 追加事件表的 updated_at = created_at；业务操作不得修改既有事件。
- 状态使用 VARCHAR + CHECK，由 Service 转换；客户端不能提交状态。
- FK 默认建立索引。下面明确列出 ondelete。
- RESTRICT 防止意外破坏来源图；清理流程先移除正文和运行记录，再按 Policy 清理最小元数据。
- “不可变”不阻止经过授权的清除流程删除正文；清除不能被实现成普通编辑。
- 稳定 scope UUID 是最小标识快照，**不承担身份认证或授权**。

### 3.2 现有表

未列为调整的已有字段及其类型保持基线。

| 表 | 原字段及类型 | C 调整 |
| --- | --- | --- |
| User | email VARCHAR(320)、password_hash VARCHAR(255)、is_active BOOL、时间字段 | email/password_hash 改条件 nullable；新增 principal_kind VARCHAR、auth_generation BIGINT |
| Family | owner_id UUID→User、name VARCHAR(200)、时间字段 | owner FK：CASCADE→RESTRICT；新增 privacy_state VARCHAR、privacy_generation BIGINT、revision BIGINT、current_revision_id UUID? |
| FamilyMember | family_id UUID→Family、name VARCHAR(200)、时间字段 | 新增 revision BIGINT、current_revision_id UUID? |
| Interview | family_member_id UUID→FamilyMember、title VARCHAR(200)、status/type VARCHAR(32)、started_at/completed_at T?、时间字段 | 新增 revision BIGINT、current_revision_id UUID?；单一 subject 关系保持 |
| InterviewSession | interview_id UUID→Interview、status VARCHAR(32)、started_at/ended_at T?、时间字段 | 不增加客户端可控隐私状态 |
| AudioRecording | session_id UUID→Session、storage_key VARCHAR(512)?、original_filename VARCHAR(255)?、mime_type VARCHAR(100)?、size_bytes/duration_ms INT?、status VARCHAR(32)、开始/结束/时间字段 | 新增 artifact_id UUID，unique，FK RESTRICT；storage_key unique 保持 |
| Transcript | audio_recording_id UUID→Audio、provider/model VARCHAR(100)?、language VARCHAR(32)?、status VARCHAR(32)、text TEXT?、duration_ms INT?、时间字段 | 新增 artifact FK unique/RESTRICT、revision BIGINT、current_revision_id UUID? |
| TranscriptSegment | transcript_id UUID→Transcript、sequence INT、speaker VARCHAR(200)?、text TEXT、start_ms/end_ms INT?、confidence FLOAT?、created_at | 新增 artifact FK unique/RESTRICT、updated_at；unique (transcript_id,sequence) |
| InterviewMessage | session_id UUID→Session、role/source VARCHAR(32)、transcript_segment_id UUID?、content TEXT、sequence INT、created_at | 新增 artifact FK unique/RESTRICT、updated_at、revision/current_revision；unique (session_id,sequence) |

补充约束：

- User kind：account / rights_only / system。account 仍要求现有邮箱密码凭据；rights_only 不要求注册密码。
- User 的普通账号停用不能被解释为撤销 Speaker 权利。
- Family privacy state：active / deletion_pending / deleted。
- current_revision_id → RevisionProposal：SET NULL；读取正文前必须检查隐私门禁，不能因关联消失而绕过限制读取原文。
- 现有内容层级 CASCADE 保留为最终清理工具，不作为删除完成证据。
- Message.transcript_segment_id ON DELETE SET NULL 保持；不增加一对一 unique。
- Message/Segment 正文、原始 Audio 和已完成的机器转写不得被普通 PATCH 覆盖。
- metadata、机器状态、批准后的当前版本指针由 Service 管理。

### 3.3 新增身份与协作表

| 表 | 字段，不含通用字段 | 约束、索引、删除行为 |
| --- | --- | --- |
| **UserContact** | user_id UUID、kind VARCHAR、value_ciphertext BYTEA、lookup_hash BYTEA、state VARCHAR、verified_at T?、revoked_at T? | User FK RESTRICT；kind=email/phone；state=pending/verified/revoked/legacy_unverified；有效渠道 hash partial unique；验证及撤销时间索引 |
| **AuthChallenge** | user_id UUID?、context_kind VARCHAR、context_id UUID?、channel_ciphertext BYTEA、channel_hash BYTEA、code_digest BYTEA、state VARCHAR、expires_at T、consumed_at T?、attempt_count INT | User FK RESTRICT；state=pending/verified/consumed/expired/locked；expires_at 索引；不保存明文验证码；context/code digest 不可变 |
| **FamilyMembership** | family_id UUID、user_id UUID、role VARCHAR、state VARCHAR、generation BIGINT、accepted_invitation_id UUID?、joined_at T、ended_at T? | Family FK CASCADE，仅最终清理时使用；User RESTRICT；Invitation SET NULL；unique (family_id,user_id)；role 固定 collaborator；state=active/revoked/left；index (user_id,state) |
| **FamilyInvitation** | family_id UUID、requested_by_user_id UUID、recipient_hash BYTEA、recipient_ciphertext BYTEA、recipient_user_id UUID?、approved_by_user_id UUID?、token_digest BYTEA?、state VARCHAR、version BIGINT、approved_at/accepted_at/expires_at T? | Family CASCADE；所有 User FK RESTRICT；token digest unique；同 Family/接收渠道的有效邀请 partial unique；state=pending_owner/approved/accepted/rejected/cancelled/revoked/expired；接收对象和申请人不可变 |
| **InterviewParticipant** | interview_id UUID?、interview_scope_id UUID、user_id UUID?、family_member_id UUID?、roles VARCHAR[]、state VARCHAR、eligibility_state VARCHAR、verified_contact_id UUID?、verification_ref UUID?、verified_at T?、adult_declaration_at T?、version BIGINT | Interview、FamilyMember SET NULL；User、Contact RESTRICT；已确定 User 时 unique (interview_scope_id,user_id)；unique (id,interview_scope_id)；state=proposed/verified/inactive/disputed；verified Speaker 必须 User 非空、本人验证及声明齐全 |

现有邮箱不得回填为 verified；渠道冲突不得按姓名或邮箱自动合并 User。

V1 不开放 User hard delete、共享渠道身份合并、失联身份恢复或代理授权。

### 3.4 来源、授权及修订表

| 表 | 字段 | 约束、索引、删除行为 |
| --- | --- | --- |
| **SourceArtifact** | family_id/interview_id/session_id UUID?、family_scope_id UUID、interview_scope_id UUID?、kind VARCHAR、entity_id UUID?、operator_user_id UUID?、state VARCHAR、generation BIGINT、content_digest BYTEA?、locator JSONB?、policy_version_id UUID? | live scope FK SET NULL；operator/Policy RESTRICT；unique (kind,entity_id)；unique (id,interview_scope_id)；index scope/state/generation；不存正文；身份、kind、原始摘要及 scope 不可改写 |
| **SourceSpeakerBinding** | source_artifact_id UUID、participant_id UUID、interview_scope_id UUID、state VARCHAR、confirmed_by_user_id UUID?、confirmation_ref UUID?、confirmed_at T?、origin_binding_id UUID?、sanitization_run_id UUID?、version BIGINT | Source、Participant、User、origin、Run FK RESTRICT；unique (source_artifact_id,participant_id)；复合 FK 保证 Source/Participant 同 Interview；state=proposed/verified/rejected/disputed；确认事实不可覆盖 |
| **ArtifactContribution** | artifact_id UUID、source_speaker_binding_id UUID、locator JSONB?、verification_state VARCHAR | 两个 FK RESTRICT；unique (artifact_id,source_speaker_binding_id)；locator 仅 Segment/时间位置/引用位置；追加且不可改写；未知归属不能发布 |
| **DerivedSource** | parent_artifact_id UUID、child_artifact_id UUID、relation VARCHAR、content_dependency BOOL、sanitization_run_id UUID? | FK RESTRICT；unique (parent,child,relation)；反向索引 child；禁止自环/环；边不可变；sanitized evidence 边必须有已验收 Run |
| **ConsentGrant** | participant_id UUID、purpose VARCHAR、category VARCHAR、state VARCHAR、epoch BIGINT、version BIGINT、current_event_id UUID? | Participant/Event RESTRICT；unique (participant_id,purpose,category)；unique (id,participant_id)；当前投影，不能由客户端改状态 |
| **ConsentEvent** | grant_id UUID?、grant_scope_id UUID、participant_scope_id UUID、sequence BIGINT、action VARCHAR、epoch BIGINT、consenter_user_id UUID、source_binding_id UUID?、policy_version_id UUID、notice_key VARCHAR、notice_digest BYTEA、verification_ref UUID、occurred_at T、idempotency_key UUID | Grant/Binding SET NULL；User/Policy RESTRICT；unique (grant_scope_id,sequence)、(consenter_user_id,idempotency_key)；全部追加且不可变；记录 grant/withdraw/regrant/source_withdraw/source_restore |
| **SourceConsentBinding** | source_speaker_binding_id UUID、grant_id UUID、participant_id UUID、bound_epoch BIGINT、state VARCHAR、version BIGINT、restriction_generation BIGINT、restricted_at/quarantine_expires_at T?、policy_version_id UUID、activation_event_id UUID? | FK RESTRICT；unique (source_speaker_binding_id,grant_id)；复合 FK 确保同 Participant；state=pending/active/restricted/branch_purged；index (state,quarantine_expires_at)；每次激活/限制由 Event 留痕 |
| **SourceRestoreRequest** | binding_id UUID、requested_by_user_id UUID、new_consent_event_id UUID、expected_restriction_generation BIGINT、state VARCHAR、version BIGINT、requested_at/decided_at T?、policy_version_id UUID、idempotency_key UUID | FK RESTRICT；幂等 unique；state=checking/source_restored/derivative_review_pending/completed/denied/unavailable；申请范围不可变 |
| **RevisionProposal** | family_scope_id UUID、target_kind VARCHAR、target_id UUID、target_artifact_id UUID?、revision_artifact_id UUID、proposed_by_user_id UUID、base_version BIGINT、payload JSONB?、payload_digest BYTEA、state VARCHAR、version BIGINT、approved_by_user_id UUID?、submitted_at/decided_at T? | Artifact/User FK RESTRICT；revision artifact unique；index (target_kind,target_id,state)；state=draft/submitted/approved/rejected/withdrawn/stale/purged；提交后 payload/hash/base version 不可变；正文清除后 payload 为空 |

状态及类别定义：

- SourceArtifact：legacy_unknown / available / quarantined / deletion_pending / erased。
- purpose：recording / transcription / ai_analysis / family_share。
- category：前三类为 default；family_share 为 text_derived / raw_audio。
- 原音家庭播放必须同时具有 text_derived 家庭分享及 raw_audio 的明确许可。
- locator 仅存白名单定位信息，不允许原文、Prompt、响应或凭据。
- 原始文字保存以本人提交/确认归档为依据，记录适用保存告知；不要求不存在的“文字录音授权”。

### 3.5 净化、删除与 Policy 表

| 表 | 字段 | 约束、索引、删除行为 |
| --- | --- | --- |
| **SanitizationRun** | deletion_request_id UUID、input_artifact_id UUID、output_artifact_id UUID?、excluded_binding_ids UUID[]、output_version BIGINT、output_digest BYTEA?、manifest_digest BYTEA?、state VARCHAR、attempt_count INT、review_deadline T?、policy_version_id UUID、technical_verified_at T?、evidence_ref UUID? | FK RESTRICT；output artifact unique；index state/deadline；scope、输入、排除范围不可变；state=queued/processing/technical_check/awaiting_speakers/accepted/rejected/abandoned |
| **SanitizationConfirmation** | run_id UUID、participant_id UUID、confirmed_by_user_id UUID、output_version BIGINT、output_digest/manifest_digest BYTEA、decision VARCHAR、verification_ref UUID、decided_at T | FK RESTRICT；unique (run_id,output_version,participant_id)；decision=confirm/reject；追加且不可变；本人只能确认自己的保留贡献 |
| **DeletionRequest** | requested_by_user_id UUID、scope_kind VARCHAR、scope JSONB、origin VARCHAR、parent_request_id UUID?、state VARCHAR、generation BIGINT、policy_version_id UUID?、accepted_at/completed_at T?、idempotency_key UUID | User/Policy/parent RESTRICT；scope 仅标识及用途；unique requester/幂等键；index state/accepted_at；scope 与已承诺期限不可扩宽或延后 |
| **DeletionTarget** | request_id UUID、artifact_id UUID?、artifact_scope_id UUID?、target_kind VARCHAR、target_key_digest BYTEA、locator_ciphertext BYTEA?、stage VARCHAR、state VARCHAR、deadline T?、attempt_count INT、next_attempt_at T?、verified_at T?、evidence_ref UUID?、failure_code VARCHAR? | Request RESTRICT；Artifact SET NULL；unique (request_id,target_kind,target_key_digest)；index state/deadline/next_attempt；定位不保存正文或凭据 |
| **DeletionLedger** | request_scope_id UUID、artifact_scope_id UUID?、scope JSONB、generation BIGINT、entry_kind VARCHAR、target_kind VARCHAR?、status VARCHAR、occurred_at T、provider_target_ref VARCHAR?、evidence_ref UUID?、policy_version_id UUID、control_sequence BIGINT | Policy RESTRICT；scope UUID 为快照，不 FK 到会被清除的正文表；control_sequence unique；scope/generation 索引；追加、不可变、禁止正文 |
| **PrivacyPolicyVersion** | version VARCHAR、state VARCHAR、parameters JSONB、notices JSONB、capabilities JSONB、digest BYTEA、published_at T? | version/digest unique；state=draft/active/retired；发布后不可修改；参数采用强类型校验 |
| **PrivacyOutbox** | event_kind VARCHAR、aggregate_kind VARCHAR、aggregate_id UUID、generation BIGINT、payload JSONB、state VARCHAR、attempt_count INT、next_attempt_at T?、policy_version_id UUID?、idempotency_key UUID | Policy RESTRICT；幂等键 unique；index state/next_attempt；payload 仅控制元数据；state=pending/processing/delivered/blocked；业务事件与门禁事务同提交 |

DeletionRequest scope：

family_archive / whole_source / speaker_contribution / purpose_branch。

DeletionTarget 状态：

pending / running / verified / not_applicable_verified / retryable_failed / blocked / verification_unknown。

### 3.6 Policy 参数

parameters 必须包含：

| 参数 | 类型 |
| --- | --- |
| sanitization_review_window | 正 duration |
| sanitization_retry_limit | 非负整数 |
| online_deletion_deadline | 正 duration |
| third_party_deletion_deadline | 正 duration |
| backup_retention_window | 正 duration |
| object_version_retention_window | 正 duration |
| database_recovery_retention_window | 正 duration |
| withdrawal_quarantine_retention | 正 duration |
| deletion_ledger_retention | 正 duration |
| sanitization_evidence_retention | 正 duration |

另外定义邀请、验证挑战、rights token 和高风险操作再验证窗口，均不冻结生产数值。

约束：

- 净化窗口不得突破原件适用清除上限。
- Ledger 的防恢复覆盖必须覆盖所有允许恢复的备份、对象版本、恢复日志及迟到任务窗口。
- 配置更新不得延长已经向 Speaker 承诺的清除期限。
- draft 可留空；active Policy 必须完整且通过能力校验。

**缺值行为已冻结：**

- 禁止新采集、有效授权签署、历史恢复、净化发布和外部处理。
- Withdrawal/Deletion 仍受理并立即隔离；执行已支持的确定性清理。
- 未配置或未验证的目标保持 blocked/unknown，不伪造期限或最终完成。
- 备份缺少完整控制记录时禁止开放恢复。

---

## 4. Consent Model

### 4.1 两层授权

**Interview 层：**某个 Participant 对某用途的当前 ConsentGrant。有效授权可供同一 Interview 的新 Session、新 Source 使用。

**Source 层：**SourceConsentBinding 固定记录采集/使用时依赖的授权 epoch，支持单 Source 限制。

允许条件：

~~~text
当前 Grant active
且 Source Binding active
且 bound_epoch = Grant 当前 epoch
且本人归属已核验
且该操作全部必要用途有效
且没有删除门禁
~~~

Source-specific restriction 始终高于 Interview allow。

### 4.2 版本与重新授权

- Grant 是当前投影；ConsentEvent 是不可改写历史。
- 撤回立即改变权限、递增 generation，并隔离对应产物及依赖。
- re-consent 创建新事件/epoch，不覆盖旧事件。
- 新 epoch 不批量重绑历史 Source。
- 历史恢复必须本人明确选择 Source、用途和分享类别。
- 恢复一个用途不解除另一个用途的限制。
- 删除范围内的内容不恢复；保留在其他用途下的原始资料可用于新的明确授权流程，但已删除副本不会复活。

### 4.3 用途依赖

| 材料/操作 | 必要条件 |
| --- | --- |
| 新录音、保存原音、本人原音使用 | recording，以及本人来源确认 |
| 原始文字保存 | 本人提交/确认归档及保存告知 |
| STT、Transcript、Segment、转写 Message | 对应 Audio 基础及 transcription |
| AI 分析、Embedding、AI 生成产物 | 全部输入可用且 ai_analysis 有效 |
| Family 文本/衍生读取 | 基础产物用途有效且 family_share/text_derived 有效 |
| Family 原音播放 | 原音基础有效、text_derived 与 raw_audio 分享许可均有效 |
| 已确认 Memory 普通读取 | 来源、用途、分享许可有效，且当前版本 Owner 审批有效 |

“曾经生成成功”不等于现在仍可使用。

到隔离保留期：

- 删除该 Source + Speaker + purpose/category 对应分支及副本。
- 共用物理对象仍有独立有效保留依据时，继续受限保存，并明确不属于该次物理删除范围。
- 没有独立保留依据或必要输入已失效时，清除对象及依赖闭包。
- 不要求恢复 Family 分享才能保存本人材料。

### 4.4 本人核验

Consent 生效要求：

1. 即时本人联系渠道验证；
2. 成年且能自主决定的本人声明；
3. 本人 Participant 与 Source 归属确认；
4. 对明确告知版本的主动授权。

operator 可创建操作意图和绑定提案，不能写有效 consenter。consenter 从验证后的当前 User 获取，并必须等于该 Participant 的 User。

---

## 5. Authorization Matrix

缩写：

- **O**：Owner；**C**：active Collaborator。
- **S**：该来源的 Speaker，通过本人 rights 能力访问。
- **P**：Operator，权限来自其 O/C 身份及操作范围，不额外扩大权限。
- **W**：限定任务、范围和能力的 System/Worker。
- **R**：提交不可变修订提案，不能直接覆盖原文。
- **G**：全部来源、Consent、状态、版本门禁通过。

| 资源 | read | create | update | approve | share | delete / request-delete |
| --- | --- | --- | --- | --- | --- | --- |
| Family | O/C：范围内元数据；内容仍需 G | account 可创建自己的 Family | O；C 通过 R | O 审批修订/邀请 | O 批准成员加入；不替 Speaker 授权 | O 删除整个 Archive |
| Interview | O/C＋G；S 仅本人来源相关信息 | O/C，合法 subject | O；C 通过 R | O 审批已有内容修改 | 依来源 Consent | S 仅本人贡献；其他子树删除未开放 |
| Session | O/C＋G；S 本人相关部分 | O/C；采集前 Speaker 条件齐全 | Service 接受合法操作意图 | 无额外内容审批权 | 依来源 Consent | S 请求删除本人来源 |
| Audio | O/C＋G＋原音许可；S 本人限定入口；W 限定任务 | O/C/P 发起；Speaker 亲自授权 | 原音不可覆盖；W 更新处理元数据 | S 净化确认；W 技术验收 | Speaker 亲自授予 | S 本人贡献；O 通过整个 Archive 删除 |
| Transcript | O/C＋G；S 本人相关材料；W 限定任务 | W，STT 权限有效 | R，新版本 | O 审批修订 | Speaker 的有效分享许可 | S 本人贡献及派生 |
| Message | O/C＋G；S 本人材料 | O/C 自己的文字；W 转写副本 | R，原文不覆盖 | O 审批修订 | 依全部实际 Speaker 分享许可 | S 本人贡献及派生 |
| Consent | S 完整本人记录；O/C 最小状态 | S 本人 | 仅命令生成事件 | 不能由 Owner 代批 | S 授予相应类别 | S 撤回；不删除审计以伪造历史 |
| Deletion | 请求人及必要受影响主体看最小状态 | S 本人范围；O 整个 Archive；W 到期调度 | W 更新目标进度 | 本人范围核验；不需 O 审批 | 不公开私人删除理由 | 无撤销已受理删除的权限 |
| Sanitized Source | 验收前 S 仅本人保留贡献；W 受限处理；验收后 O/C＋G | W 创建候选 | 改内容必须形成新输出版本 | W 技术验收＋各剩余 S 确认 | 所有保留贡献的有效分享许可 | S 删除本人贡献；O 整个 Archive |
| MemoryCandidate | 9.6+：O/C＋G；S 本人相关纠错入口 | W，AI 权限有效 | O/C/S 提交修订 | **O 最终批准** | 当前 Consent，不由批准替代 | S 本人可识别派生；O 整个 Archive |

共同规则：

- revoked Membership 的旧 JWT 不继续获得 Family 访问权。
- Speaker 权利入口不随 Membership 撤销消失。
- Owner 也受 Consent、隔离和删除门禁约束。
- P 不能修改自己的角色或代替 S。
- W 没有任意浏览档案权限；净化/删除读取仅限指定任务。
- 未明确开放的子树删除入口不能继续直接硬删。

---

## 6. State Machines

### 6.1 Consent lifecycle

~~~mermaid
stateDiagram-v2
    [*] --> Unset
    Unset --> Active: 本人核验并明确授权
    Active --> Withdrawn: 本人撤回，立即隔离对应分支
    Withdrawn --> Active: re-consent，新epoch
    Active --> Closed: Participant范围最终关闭
    Withdrawn --> Closed: 范围最终关闭
    Closed --> [*]
~~~

Grant 重新 active 仅自动支持未来新 Source。旧 Event 永不改写，Closed 为终态。

### 6.2 Historical Source Restore lifecycle

~~~mermaid
stateDiagram-v2
    [*] --> Checking
    Checking --> Denied: 身份、归属或授权不通过
    Checking --> Unavailable: 数据已清除或删除已受理
    Checking --> SourceRestored: 明确选源及用途，原子核验通过
    SourceRestored --> DerivativeReviewPending: 衍生版本重新核验
    DerivativeReviewPending --> Completed: 必要重生成且Memory重新Owner审批
    DerivativeReviewPending --> Denied: 当前条件失效
    Denied --> [*]
    Unavailable --> [*]
    Completed --> [*]
~~~

一次申请终结后，后续申请建立新记录。恢复只针对选定用途。

到期调度与恢复锁同一 Binding/generation：只有到期前**实际生效**的恢复可取消尚未受理的对应分支删除；进入 deletion_pending 后不可恢复。

### 6.3 Deletion lifecycle

~~~mermaid
stateDiagram-v2
    [*] --> Requested
    Requested --> Rejected: 请求身份或范围无效
    Requested --> Isolated: 受理与门禁同事务提交
    Isolated --> Propagating
    Propagating --> AwaitingExternalOrBackup: 在线及衍生完成，其他目标未完成
    Propagating --> Blocked: 失败、超期或证据未知
    AwaitingExternalOrBackup --> Blocked: 目标受阻或无法验证
    Blocked --> Propagating: 修复后重试未完成目标
    Propagating --> DoneVerified: 全部声明目标已核验
    AwaitingExternalOrBackup --> DoneVerified: 全部声明目标已核验
    Rejected --> [*]
    DoneVerified --> [*]
~~~

阶段视图分别展示：隔离、在线、衍生、第三方、备份、声明范围完成。清理目标可以并行，不要求串行等待。

DoneVerified、Rejected 为请求终态。Source 的删除门禁没有回到可用的路径。

### 6.4 Sanitization lifecycle

~~~mermaid
stateDiagram-v2
    [*] --> Queued
    Queued --> Processing
    Processing --> TechnicalCheck
    Processing --> Queued: 临时错误且未超期限或重试上限
    TechnicalCheck --> AwaitingSpeakers: 技术检查通过
    TechnicalCheck --> Rejected: 残留、未知或无法可靠分离
    AwaitingSpeakers --> Accepted: 每位剩余Speaker确认准确输出版本
    AwaitingSpeakers --> Rejected: 任一拒绝或验收失败
    Queued --> Abandoned: 清除上限或窗口到达
    Processing --> Abandoned: 清除上限或重试上限到达
    AwaitingSpeakers --> Abandoned: 未确认且窗口到达
    Accepted --> [*]
    Rejected --> [*]
    Abandoned --> [*]
~~~

accepted 仅代表该净化版本通过验收。发布时仍检查 Consent。

输出 hash/manifest 变化使之前确认全部失效。rejected/abandoned 输出进入清理；剩余 Speaker 沉默不延迟原件删除。

### 6.5 Invitation / Membership lifecycle

~~~mermaid
stateDiagram-v2
    [*] --> PendingOwner
    PendingOwner --> Approved: Owner批准
    PendingOwner --> Rejected: Owner拒绝
    PendingOwner --> Cancelled: 发起者取消
    Approved --> Accepted: 被邀请账号核验并接受
    Approved --> Revoked: Owner撤销
    Approved --> Expired: 邀请到期
    Accepted --> MembershipActive
    MembershipActive --> MembershipRevoked: Owner撤销访问
    MembershipActive --> MembershipLeft: 本人退出
    Rejected --> [*]
    Cancelled --> [*]
    Revoked --> [*]
    Expired --> [*]
    MembershipRevoked --> [*]
    MembershipLeft --> [*]
~~~

重新加入必须经过新邀请；Membership generation 递增。

### 6.6 所有流程共同约束

- 验证不完整、Policy 缺值、来源不明：fail closed。
- 迟到 STT/AI 结果、审批和确认重新校验 generation；失效结果不得写入可用正文或索引。
- 重试幂等且不改变 scope，不延长 deadline。
- 已成功清理的目标不回退。
- 完成后发现额外副本，创建关联补充删除请求；原 Source 持续被门禁阻断，并更新范围状态。

---

## 7. Provenance & Deletion Propagation

### 7.1 解决正文复制

当前实现：

TranscriptSegment.text → InterviewMessage.content

[正文复制代码](../../apps/backend/app/services/interview_message.py#L61) 与 [SET NULL 外键](../../apps/backend/app/models/interview_message.py#L25) 不能承担完整来源删除。

冻结以下写入协议：

1. 每个正文对象创建独立 SourceArtifact。
2. Segment → Message 创建不可变 message_copy 边。
3. Message 登记对应 ArtifactContribution。
4. 正文、Artifact、贡献边和复制关系同事务提交。
5. 缺少来源登记的副本不能进入普通读取或 AI 输入。
6. Segment 实体删除后，稳定 Artifact/贡献关系仍能定位 Message 正文副本。

### 7.2 全链路登记

| 对象 | 来源登记与清理方式 |
| --- | --- |
| Audio | Artifact＋存储对象/版本定位 |
| Transcript | Audio 输入边＋全部贡献 |
| Segment | Transcript 分段边＋Speaker 归属 |
| Message copy | Segment 复制边，不依赖可空 FK |
| Candidate | 输入 Artifact 集合＋Speaker 贡献 |
| Memory | Candidate/修订版本及全部输入关系 |
| Memoir version | 引用 Memory/Source 的版本关系 |
| Embedding | 输入版本、模型版本及存储定位 |
| Vector index | 向量对象、namespace/index 标识 |
| Cache | 生成输入、缓存 namespace/key 定位 |
| Export | 服务端导出文件及全部引用范围 |
| Provider copy | Provider 请求及输入/输出对象标识 |

新的派生物或外部副本必须先登记再发布。没有已验证清理能力的适配器不能启用真实处理。

### 7.3 净化传播例外

区分两类关系：

- **内容贡献关系**：用于权限判断及删除传播。
- **处理证据关系**：证明新版本来自旧来源，不表示保留被删贡献。

验收后的净化版本只保留剩余 Speaker 贡献：

- 被可靠移除 Speaker 的贡献不继续传播到新版本。
- 其他 Speaker 的原有 source-specific deny、用途限制及授权历史仍继承。
- 新文件 ID 不能成为绕过限制的手段。
- Family 整体删除仍覆盖净化版本。
- 原件及受污染旧版本继续删除；不等待净化发布。

### 7.4 备份恢复

恢复流程必须：

1. 进入隔离环境；
2. 载入可信最新 DeletionLedger，以及当前 Consent/Source 限制控制记录；
3. 核验控制记录完整性与高水位；
4. 重放 whole-source、contribution、purpose-branch 门禁和清理；
5. 扫描副本及来源闭包；
6. 核验后开放。

只有旧数据库备份、没有最新控制记录时，禁止恢复成普通服务。

最小 Ledger 不存音频、文本、摘要、Prompt、Embedding 或失败响应正文。声明范围完成不等于平台能远程收回已经交付到用户设备的离线文件；受控服务端 Export 纳入清理。

---

## 8. API Contract

### 8.1 通用合同

前缀 /api/v1；列表 page=1,page_size=20，服务端限制最大页大小。

写命令使用：

- Idempotency-Key
- expected_version 或 expected_generation

同键同载荷返回原结果；不同载荷返回 409。

响应使用 DTO；异步操作返回 202 {id,status,version,stages}，不把排队写成完成。

错误：

- 401：身份/验证过期；
- 404：未知或范围外资源；
- 403：已知资源下角色或本人范围不符；
- 409：版本、状态、幂等冲突或删除不可恢复；
- 422：非法用途、载荷或客户端状态字段；
- 429：验证限流；
- 503：Policy/必要能力未配置。

### 8.2 身份、协作、参与者

| Method / path | Actor | Request → Response | 授权及主要失败 |
| --- | --- | --- | --- |
| POST /rights-auth/challenges | 待验证本人 | channel、context → 通用 challenge receipt | 防枚举；不泄露渠道是否存在 |
| POST /rights-auth/challenges/{id}/verify | 本人 | code → rights_only token | 一次性、过期/重放/冲突拒绝 |
| GET /rights/me | S | 无 → 本人最小状态 | 不获得 Family 浏览权 |
| POST /families/{f}/invitations | O/C | recipient、expected_version → invitation | C 为 pending_owner；O 可直接批准 |
| POST /invitations/{id}/approve | O | expected_version → approved | 必须当前 Owner |
| POST /invitations/{id}/reject | O | expected_version → rejected | 终态不能接受 |
| POST /invitations/{id}/cancel | 发起人 | expected_version → cancelled | 仅待审批阶段 |
| POST /invitations/{id}/accept | 被邀请 account | token、expected_version → membership | Owner 已批准、本人接收身份匹配 |
| POST /invitations/{id}/revoke | O | expected_version → revoked | 已加入者走 Membership 撤销 |
| GET /families/{f}/memberships | O/C | 分页 → 最小成员信息 | active 范围；不公开私人验证信息 |
| DELETE /families/{f}/memberships/{m} | O 或本人 | expected_version → revoked/left | 只撤销访问，不删除贡献/本人权利 |
| POST /interviews/{i}/participants | O/C/P | 参与者提案、roles、可选 FamilyMember → proposed | 输入 User ID 不等于本人确认 |
| POST /participants/{p}/confirm | 对应本人 | 成人声明、归属确认、验证凭据 → verified | 渠道、本人及上下文一致 |
| POST /sources/{s}/speaker-bindings | 合法 P | participant、Segment 归属提案 → proposed | 不接受客户端 verified 状态 |
| POST /source-speaker-bindings/{b}/confirm | 对应 S | confirm/reject、expected_version → binding | 不能代确认；争议保持隔离 |

### 8.3 Consent、恢复、修订

| Method / path | Actor | Request → Response | 授权及主要失败 |
| --- | --- | --- | --- |
| GET /interviews/{i}/consents/me | S | 无 → 本人 Grant/Event | 本人 Participant |
| POST /interviews/{i}/consents | S | purposes/categories、notice/policy、验证证明 → events/grants | consenter 从认证确定；每用途独立 |
| POST /consent-grants/{g}/withdrawals | S | expected_version → event＋隔离状态 | 立即门禁；不需要 O |
| POST /consent-grants/{g}/re-consents | S | 新 notice/policy、expected_version → 新 epoch | 不恢复旧 Source |
| POST /sources/{s}/withdrawals | 该 Source S | purposes/categories、expected_generation → restriction | 仅本人贡献；父 Grant 不覆盖 |
| GET /sources/{s}/consent-bindings | S；O/C 最小管理范围 | 无 → 用途状态 | 不返回他人的私人验证证据 |
| POST /sources/{s}/restoration-requests | S | 明确用途、新 ConsentEvent、expected_generation → 202 request | 删除范围永远 409；其他 Speaker 限制仍生效 |
| GET /source-restoration-requests/{r} | 请求人 | 无 → 各阶段状态 | 未完成审查的旧 Memory 不开放 |
| POST /revision-proposals | O/C；S 本人纠错范围 | target、base_version、payload → proposal | 原文不覆盖；登记来源贡献 |
| POST /revision-proposals/{p}/submit | 提案人 | expected_version → submitted | 提交后内容不可改写 |
| POST /revision-proposals/{p}/approve | O | hash、base_version、expected_version → approved | 当前 Consent/删除/版本再次核验 |
| POST /revision-proposals/{p}/reject | O | expected_version → rejected | 不改原文 |

SourceConsentBinding 的建立及 epoch 绑定由 Service 执行，不提供任意状态 PATCH。

### 8.4 删除与净化

| Method / path | Actor | Request → Response | 授权及主要失败 |
| --- | --- | --- | --- |
| POST /deletion-requests | S/O/W | 声明 scope、幂等键、本人证明或到期依据 → 202 request | S 本人；O 整个 Archive；W 已冻结 Policy 到期范围 |
| GET /deletion-requests/{r} | 请求人/必要受影响人 | 无 → 六阶段及最小证据 | 不返回私人理由或正文 |
| DELETE /families/{f} | O | 幂等键/验证 → 202 request | 替换现有直接硬删/204 |
| GET /sanitization-runs/{r}/reviews/me | 剩余 S | 无 → 本人保留内容的限定审查 | 不扩大为原混合来源浏览 |
| POST /sanitization-runs/{r}/confirmations | 对应 S | decision、output_version/hash、manifest_hash → confirmation | 不代确认；确认不延长删除期限 |
| GET /sanitization-runs/{r} | 必要 actor | 无 → 最小状态 | 未验收输出不普通发布 |

内部 Worker 使用限定任务能力，操作条件包括 job/source generation、当前 Consent 和 Policy。Provider callback 不具有直接发布权限。

现有 FamilyMember/Interview DELETE 在未冻结相应子树管理权限前拒绝执行，不能继续先硬删再补 Ledger。

---

## 9. Migration Plan

只新增 revision，接在现有唯一 Alembic head adf9c60d178d 后；不修改封板迁移。

| 顺序 | 操作 | 注意事项 |
| --- | --- | --- |
| 1 | 只读预检数量、孤儿 FK、重复序号、历史来源关系 | 有异常则停，不自行合并身份或重排故事 |
| 2 | 创建 PrivacyPolicyVersion、UserContact、AuthChallenge | 生产参数留 draft；旧邮箱 legacy_unverified |
| 3 | 扩展 User；owner FK 改 RESTRICT | 旧 User 回填 account；不回填本人 Speaker |
| 4 | 创建 Invitation、Membership、Participant | 不根据 FamilyMember 姓名推导账号 |
| 5 | 创建 SourceArtifact、Binding、Contribution、DerivedSource | 暂不建立循环引用 FK |
| 6 | 现有内容表新增 nullable artifact_id；创建 RevisionProposal | 先创建表，后加 current_revision 与循环 FK |
| 7 | 回填历史 Artifact 与确定性来源边 | Audio→Transcript→Segment→Message；全部 legacy_unknown |
| 8 | 创建 ConsentGrant/Event、SourceConsentBinding、RestoreRequest | current_event FK 最后添加；不回填 active Consent |
| 9 | 创建 DeletionRequest/Target/Ledger、Outbox、Sanitization 表 | Run/output/origin 等循环 FK 最后添加 |
| 10 | 校验数量、关系和 contribution 完整性 | 历史 Speaker/Consent 不明仍拒绝正文访问 |
| 11 | 内容 artifact_id 收紧为 NOT NULL＋unique；增加序号 unique | 重复序号阻止该迁移，进入独立数据修复流程 |
| 12 | 切换 Service 权限、删除门禁和旧硬删入口 | 全链路切换，不能只放宽 Family 顶层 |
| 13 | 启用配置完整的功能 | 实际存储/Provider 未接入时继续禁用相应处理 |

历史规则：

- 不创建虚假的 Owner Speaker。
- 不把 STT speaker 标签变成真人身份。
- 不把新授权倒填为历史录音时已授权。
- 历史内容 Owner 也只见必要状态。
- SET NULL 已导致脱链的 Message 无法可靠归属时，保持 legacy_unknown，不当作原始本人文字。
- 隐私事件已经产生后，不能通过 schema downgrade 清除 Ledger 或恢复旧访问；故障采用暂停和向前修复。

---

## 10. Test Matrix

以下为实施验收要求，本轮没有运行。

| 场景 | 必须结果 |
| --- | --- |
| Owner/C 猜测另一 Family ID | 全链路 404，无正文、计数和身份泄漏 |
| 邀请申请、审批、接受 | Owner 批准且本人接受后才 active |
| 重复/过期/撤销邀请 | 不产生额外 active Membership |
| approve/accept/revoke 并发 | Invitation 与 Membership 一致 |
| Membership 撤销、旧 JWT | 普通档案立即拒绝；Speaker rights 继续可用 |
| rights_only 访问 Family 创建/邀请 | 拒绝权限扩大 |
| 同名、共用渠道、账号冲突 | 不自动合并或认领来源 |
| 旧邮箱＋密码登录 | 不作为本人 Consent 的唯一证据 |
| operator ≠ speaker | operator 正确记录，Speaker 本人确认 |
| 伪造 consenter | 拒绝；不能写有效 Grant |
| Consent grant | 告知、Policy、验证、本人归属齐全 |
| 单用途撤回 | 对应产物及依赖隔离；其他用途状态独立 |
| 单 Source 撤回＋Interview regrant | 原 Source 仍受限 |
| 新 Session 复用 | 同 Interview 有效 Grant 可绑定新 Source |
| 历史显式恢复 | 仅选定 Source/用途恢复 |
| deleted/pending Source 恢复 | 永久 409 |
| restore 与到期并发 | 唯一有效结果；删除受理后不恢复 |
| D7 共用物理对象 | 清除撤回用途分支；独立有效保留对象不被误报删除 |
| Memory 历史恢复 | 旧审批不发布；重新 Owner 审批 |
| 多人净化成功 | 技术验收＋所有剩余 Speaker 确认 |
| 剩余 Speaker 未确认 | 不发布；不延迟原件删除 |
| 重叠、未知、残留、验收失败 | 放弃净化、整份删除 |
| 输出版本变化 | 旧确认全部失效 |
| 净化新 ID | 继承剩余 Speaker 单源限制 |
| 净化＋Family 整体删除 | 新版本也在删除范围 |
| 迟到 STT/AI 结果 | 不写可用正文、索引或发布；外部副本仍追踪 |
| Owner approval 与撤回并发 | 当前门禁胜出，旧审批失效 |
| Segment 删除＋Message SET NULL | 正文副本仍被定位并清除 |
| Candidate/Memory/Memoir 多源闭包 | 任一受限贡献使受影响版本受限 |
| Vector/Cache/Export | 读取阻断、删除逐目标验证 |
| 第三方 pending/unknown | 不显示最终删除完成 |
| 备份 pending | 不显示最终删除完成 |
| 备份恢复 | 隔离→最新控制记录/Ledger→传播核验→开放 |
| Owner 阻止/撤销 Speaker 删除 | 拒绝，无回滚入口 |
| Owner 删除整个 Archive | 全范围受理；不产生代替 Speaker Consent |
| 未知历史 Consent | Owner 只见状态，无自动授权 |
| 临时失败、重试、重复 callback | 幂等；成功目标不回退；不延长期限 |
| Policy 缺值 | 处理/恢复/发布关闭；撤回删除仍受理 |
| Ledger/错误日志/证据 | 无正文、音频、Prompt、token 或验证码 |
| Message/Segment 并发追加 | 父级锁＋unique，序号不重复 |
| 旧直接硬删入口 | 已统一 Pipeline 或明确关闭 |

未来验收在 apps/backend、专用测试数据库安全配置下执行：

~~~powershell
python -m ruff check .
python -m ruff format --check .
python -m pytest -m "not integration"

$env:TEST_MIGRATION_MODE = "1"
python -m alembic heads
python -m alembic upgrade head
python -m alembic current
python -m alembic check
python -m pytest -m integration
python -m alembic check
~~~

PostgreSQL 测试必须覆盖真实 FK、unique、事务竞争、Outbox 原子性及恢复门禁；不能用 SQLite 结果替代。

---

## 最终结论

### A. CONFIRMED DESIGN DECISIONS

- 同一 User 主体体系，无平行 Speaker 身份系统。
- FamilyMember 是档案人物；Participant、Membership、Speaker binding 分工明确。
- operator、speaker、consenter 分别记录。
- 协作者可协助录音；本人即时验证和授权不可替代。
- V1 仅支持能自主决定的成年人。
- Interview Grant＋Source override＋事件/epoch。
- 历史 Source 明确选择恢复；Memory 重新 Owner 审批。
- Withdrawal 与 Deletion 分离。
- 用途隔离到期删除对应分支，保留其他独立有效用途。
- 净化验收不延迟原件删除。
- 六阶段删除；全部声明目标核验后最终完成。
- 滚动备份＋最小 Ledger＋隔离恢复。
- 修订不可覆盖原文，Owner 审批精确版本。
- Policy 值未配置时执行已定义的 fail-safe。

### B. REMAINING BLOCKERS

**没有阻塞 C 的 Model、Migration、Schema、Service/API 实现的产品语义问题。**

生产启用条件仍需完成：

- Policy 生产值及 Speaker 告知文本；
- Storage/Backup/STT/LLM 的实际能力核验；
- 清理适配器及证据协议；
- 实施测试与权限审计。

这些条件通过配置与能力门禁处理，不改变本轮已冻结结构。

### C. ADR CHANGES REQUIRED

| ADR | 必须更新 |
| --- | --- |
| ADR-001 | 保持 Accepted；补充复制正文由 Provenance 删除传播处理 |
| ADR-002 | 保持 Proposed；C 不开放账号硬删除、身份合并或所有权转移 |
| ADR-003 | 保持 Accepted；补充显式 Pipeline 与声明范围完成边界 |
| ADR-004 | 更新为本轮协作、邀请、修订审批和权限矩阵 |
| ADR-005 | 更新为统一 User、Participant、本人核验、operator/speaker/consenter |
| ADR-006 | 更新为本轮 Consent、用途分支、净化、删除、恢复及 Policy 合同 |
| ADR-007 | 继续单独处理 Interview/Session 业务状态；隐私门禁不依赖客户端状态 |
| ADR-008 | 冻结 Owner 终审、当前 Consent、恢复后重审批；9.6 业务实现随后 |
| ADR-009 | 冻结登记、迟到结果和清理能力门禁；具体 Provider 选择仍待核验 |

本轮只列变更要求，没有修改 ADR 文件。

### D. DATABASE CHANGES REQUIRED

- 新增上述 C 实体。
- User 支持条件凭据与 rights_only/system 能力。
- Family owner FK 改 RESTRICT。
- 内容表接入 Artifact Registry。
- 新增不可变贡献与衍生关系。
- 新增修订版本指针与审批载体。
- 新增序号 unique。
- 历史数据回填来源图，保持 unknown/restricted。
- 追加迁移，保留旧迁移和单 head。

### E. IMPLEMENTATION ORDER

1. Policy 类型、统一身份、认证 scope。
2. Membership、Invitation、Participant。
3. Artifact Registry、贡献图及历史回填。
4. Consent/Event/Binding 与全部读取门禁。
5. RevisionProposal 与 Owner 审批。
6. DeletionRequest/Target/Ledger/Outbox；封堵硬删。
7. 到期调度与历史恢复。
8. Sanitization 验收及发布门禁。
9. PostgreSQL、API、并发与恢复测试。
10. 权限审计后接入真实存储/STT，再进入 MemoryCandidate。

文件范围集中于现有 Backend 的 models/schemas/crud/services/api/dependencies/core、新增 Alembic revision 和 tests；真实 AI/STT 处理仍通过独立 AI Service。

### F. DESIGN FREEZE STATUS

冻结范围是 **Part 9.5.5-C 的数据结构、权限、授权、版本、删除传播及接口合同**。生产参数留待能力核验，不阻止实施；缺值时的拒绝与隔离行为已经确定。

**PART 9.5.5-C DESIGN FROZEN**

**READY FOR IMPLEMENTATION**
