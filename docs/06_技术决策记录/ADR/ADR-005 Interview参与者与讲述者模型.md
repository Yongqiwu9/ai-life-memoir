# ADR-005 Interview参与者与讲述者模型

## Status

Accepted

Implementation: Partial — C1 Identity Foundation Completed / Sealed（commit `35ec7e33a060b07e4834091b04c2caeb852b707c`；Backend CI run `37412935434` success）；InterviewParticipant / Speaker 归属尚未实现。

本 ADR 摘要记录 Part 9.5.5-C 已冻结的统一 User 主体、InterviewParticipant、本人核验和来源讲述者边界。完整表结构、状态机、API 合同、迁移顺序与验收矩阵以 [Part 9.5.5-C Final Implementation Design Freeze](../../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md) 为唯一事实来源。Accepted 表示设计已冻结，不表示功能已经实现。

## Context

“回忆我自己”、代述亲人经历和多人补充同一人物的回忆，都需要区分登录主体、档案人物、访谈参与者、操作人和实际讲述者。只有明确的本人身份与来源归属，才能正确执行 Consent、撤回、删除、修订和派生内容门禁。

## Current Implementation

- C1 扩展现有 `User` 为 account / rights_only / system，增加 auth_generation；email/password_hash 条件可空，非账号主体无密码登录能力。
- C1 新增 UserContact / AuthChallenge 和受限 rights-auth 验证入口；生产加密、投递与限流 Provider 默认不可用，尚未开放生产即时本人验证。rights/me 只返回认证主体及 rights:identity，不能确认 Speaker 资格或来源归属。
- `FamilyMember` 是归属于 Family 的档案人物，当前字段不包含 User、Membership 或 Participant 身份关系。
- `Interview.family_member_id` 为非空外键，一个 Interview 当前关联一个 FamilyMember；这是回忆对象关系，没有独立 Participant 集合。
- Session 只关联 Interview。Message 只关联 Session，并具有 `role`、`source` 和可空的 `transcript_segment_id`；没有实际讲述者字段。
- Message 的 `role=user` 表示消息角色，不能确定是哪位人类讲述。客户端文本输入仅允许 `user/text`；服务端可从 Segment 创建 `user/audio_transcript` 消息。
- `TranscriptSegment.speaker` 是可空字符串，不是 User、Participant 或经确认的授权主体。
- 当前没有 FamilyMembership、InterviewParticipant、本人资格核验、SourceSpeakerBinding、Consent 或多人来源 Memory 实现。

## Decision

### 统一主体与档案人物

- 现有 `User.id` 是唯一认证主体，不新增平行 SpeakerIdentity。User 支持 account、rights_only、system 三种能力类型。
- UserContact 是 User 的手机或邮箱验证渠道，不是另一个身份。rights_only 会话只提供本人 Consent、撤回、恢复和删除能力，不获得普通 Family 浏览或协作权限。
- FamilyMember 继续表示档案人物和 Interview 的单一主要 subject，不是认证主体、Membership 或 Speaker。
- User 与 FamilyMember 的本人关系只能显式确认并审计；不得按姓名、邮箱、STT 标签、Owner 身份或当前调用者自动合并或推断。

### Participant 与来源 Speaker

- InterviewParticipant 表达某个 User 参与某次 Interview 的关系；草稿 Interview 可以有零个 Participant，实际采集前必须至少有一位已确认 Speaker，多人来源必须覆盖全部实际 Speaker。
- Participant 可以显式关联 FamilyMember，用于表达 subject 与 speaker 是同一人；该关联不授予 Family 访问权。
- SourceSpeakerBinding 将具体 Source 与实际 Participant 绑定。Speaker 身份须本人确认；未知、冲突或 disputed 归属保持隔离，不能发布或进入 AI 输入。
- operator、speaker、consenter 分别记录：operator 是执行操作的 User，speaker 是 SourceSpeakerBinding 对应 Participant/User，consenter 是 ConsentEvent 中亲自授权的 User。三者可以是同一人，但不能相互推导。
- Owner 或 Collaborator 可以协助或发起他人录音，不能代替具有自主决定能力的成年 Speaker 确认身份、来源归属或授权。

### V1 本人资格

- V1 只支持能自主决定的成年人。
- 本人确认要求即时手机或邮箱验证、成年自主决定声明、Participant 与本人 Source 归属确认。
- 渠道冲突不自动合并 User；冲突未解决前保持受限。现有邮箱不得回填为 verified，也不能仅凭旧邮箱加密码登录建立有效 Consent。
- Membership 被撤销不影响 Speaker 的 rights_only 本人权利入口。

## Consequences

### Positive

- 一个统一 User 主体覆盖账号用户与无注册 Speaker，避免第二套身份体系和跨 Interview 身份漂移。
- FamilyMember、Participant、Speaker 归属和协作访问各自承担单一职责。
- 代录与本人授权可以同时表达，operator 不会被误认为 speaker 或 consenter。

### Trade-offs

- 现有 User 凭据模型需要扩展，普通账号 token 与 rights_only token 必须严格隔离能力。
- 每份原始来源和派生贡献都需要稳定的 Participant / Speaker 归属；未知历史数据不能自动开放。
- 多 Speaker、重叠发言和后续纠错需要 Provenance 与来源贡献图支持，不能只依赖 Segment 的字符串标签。

## Security & Privacy Impact

Family 访问、Participant 身份和 Speaker 本人权利分别校验。知道某人的姓名、成为采访参与者或控制一个协作账号，都不能据此读取该 Family 全部档案或代替本人授权。

认证上下文必须决定实际 User 和能力范围。客户端传入的 User ID、Participant ID、role、STT speaker 标签或 operator 身份，均不能单独建立 verified Speaker 或有效 Consent。

## Migration Impact

设计冻结时本 ADR 仅归档设计。C1 已追加 revision `c1a7d45e92b0`（down `adf9c60d178d`），扩展 User 并新增 UserContact / AuthChallenge / PrivacyPolicyVersion；Participant / SourceSpeakerBinding / Provenance 仍待后续实现。

历史 User 仅回填为 account / generation=1；旧邮箱语义保持未验证，C1 不自动生成 Contact，不伪造 ciphertext 或 verified 证据。未验证渠道按 legacy_unverified 规则处理。不得把 Owner 回填为 Speaker，不得按 FamilyMember 姓名或 STT 标签创建 Participant / Speaker 归属。历史来源 fail-closed 门禁属于后续 Source / Consent 实施，C1 未改写既有来源访问行为。

## Future Boundaries

- V1 不开放 User hard delete、共享联系渠道自动合并、失联身份恢复或代理授权。
- User Account 删除、Owner 转移与身份匿名化继续由 ADR-002 单独决定。
- 实际音频剪切、STT Speaker Identification 和 AI 生成不因本 ADR Accepted 而视为完成。

## Related Documents

- [Part 9.5.5-C Final Implementation Design Freeze](../../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md)
- [系统架构总览](../../01_架构设计/AI人生回忆录平台_系统架构总览_V1.1.md)
- [Audio/STT 数据模型设计基线](../../02_数据模型/Part9.5_Audio-STT数据模型设计基线_V1.0.md)
- [Message 事件模型设计](../../03_业务流程/Message事件模型设计_V1.0.md)
- [Memory 生成链路设计](../../04_AI设计/Memory生成链路设计_V1.0.md)
- [ADR-004 Family协作权限模型](<ADR-004 Family协作权限模型.md>)
- [ADR-006 Consent授权撤回与删除策略](<ADR-006 Consent授权撤回与删除策略.md>)
- [ADR-008 MemoryCandidate确认流程](<ADR-008 MemoryCandidate确认流程.md>)

## Related Code

- [User Model](../../../apps/backend/app/models/user.py)、[FamilyMember Model](../../../apps/backend/app/models/family_member.py)、[Interview Model](../../../apps/backend/app/models/interview.py)
- [Message Model](../../../apps/backend/app/models/interview_message.py)、[Segment Model](../../../apps/backend/app/models/transcript_segment.py)
- [FamilyMember Schema](../../../apps/backend/app/schemas/family_member.py)、[Interview Schema](../../../apps/backend/app/schemas/interview.py)、[Message Schema](../../../apps/backend/app/schemas/interview_message.py)、[Segment Schema](../../../apps/backend/app/schemas/transcript_segment.py)
- [Interview Service](../../../apps/backend/app/services/interview.py)、[Message Service](../../../apps/backend/app/services/interview_message.py)
- [Interview API](../../../apps/backend/app/api/v1/interviews.py)、[FamilyMember API](../../../apps/backend/app/api/v1/family_members.py)

## Revision History

| 日期 | 版本 | 变更 |
| --- | --- | --- |
| 2026-10-05 | V1.0 | Part 9.5.5-A；区分账号、档案人物、访问关系和实际讲述者。 |
| 2026-10-05 | V1.1 | Part 9.5.5-C Design Freeze；冻结统一 User、Participant、本人核验及 operator/speaker/consenter 边界；Implementation Not Started。 |
| 2026-10-05 | V1.2 | C1 Identity Foundation Implemented / Validated；普通访问仍 Owner-only，生产验证能力未开放，Participant / Consent 尚未实现。 |
