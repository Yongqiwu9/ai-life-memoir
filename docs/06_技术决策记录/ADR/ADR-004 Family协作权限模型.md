# ADR-004 Family协作权限模型

## Status

Accepted

Implementation: Partial — C2A Implementation Written / Audit Remediation Completed / Pre-Commit Re-Audit Pending；FamilyInvitation / FamilyMembership / durable idempotency 已写入 working tree；Revision 与内容访问门禁尚未实现。

本 ADR 摘要记录 Part 9.5.5-C 已冻结的 Family 协作、邀请、修订审批和权限边界。完整表结构、状态机、API 合同、迁移顺序与验收矩阵以 [Part 9.5.5-C Final Implementation Design Freeze](../../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md) 为唯一事实来源。Accepted 表示设计已冻结，不表示功能已经实现。

## Context

首版需要支持多个账号共同访问同一 Family 档案。档案人物、账号访问关系、访谈参与关系和实际来源讲述者承担不同职责，不能通过同名 FamilyMember、客户端角色或当前调用者相互推定。

## Current Implementation

- `Family.owner_id` 仍是唯一 Owner 权威；其 User FK 已由 CASCADE 改为 RESTRICT。Owner 不建立 Membership。
- C2A 已新增 FamilyInvitation、FamilyMembership 与持久化 CommandIdempotencyRecord。Membership 仅允许 collaborator，状态为 active/revoked/left；revoke、leave、rejoin 均递增 generation，重入复用同一行。
- Owner 可直接创建 approved Invitation；active Collaborator 创建 pending_owner Invitation，由 Owner approve/reject；requester 可 cancel，Owner 可 revoke 未接受邀请。接受要求 account JWT、邀请 token、本人 Contact 即时核验和 invitation-bound verification proof。
- 新增 Owner / active Collaborator authorization primitive 只用于邀请和 Membership 管理。Family、FamilyMember、Interview 及 Session / Message / Audio / Transcript 等既有内容 API 继续沿 Owner 链隔离。
- 所有 C2A public mutation 要求 Idempotency-Key；业务变更与安全响应元数据同事务提交。response_body 只接受按 operation 注册的强类型安全 snapshot，未知字段和未声明嵌套对象默认拒绝；重放不持久化 OTP、邀请明文 token、proof 或 recipient PII，proof 重签保持原始签发与过期时间语义。
- `FamilyMember` 只有 `family_id`、`name` 与基础主键/时间字段，没有与 User 的登录身份映射。
- RevisionProposal、Participant/Consent 门禁、内容共享和 Speaker 权利流程尚未实现；因此 C2A 不是完整 Family Collaboration 上线。

## Decision

### Owner 与 Membership

- `Family.owner_id` 继续作为 Owner 的唯一权威来源。
- FamilyMembership 只保存 Collaborator，不重复建立第二个 Owner 来源；至少记录 active、revoked、left 状态和 generation。
- active Collaborator 可以在 Family 范围内读取允许的元数据、创建 Interview，并追加自己的原始文字来源或协助发起录音。内容读取、录音、处理和分享仍须通过来源、Participant、Consent 和删除门禁。
- Membership 撤销立即取消普通 Family 访问；不删除历史贡献，也不取消 Speaker 的本人权利入口。
- 跨 Family 隔离继续由 Backend Service / 查询层执行。身份、角色和 Owner 标识来自服务端认证及持久化关系，不信任客户端传入值。

### Invitation

- Owner 或 active Collaborator 可以发起邀请。Collaborator 发起后进入 Owner 审批；Owner 发起可直接批准。
- 被邀请账号只有在 Owner 已批准且本人核验并接受后，才建立 active Membership。
- 邀请的拒绝、取消、撤销和过期均不得产生 Membership；重新加入必须经过新邀请。

### 编辑、审批与删除权限

- Collaborator 对已有内容的修改必须形成不可变 RevisionProposal；Owner 按精确目标版本、内容摘要和当前权限门禁审批后才成为当前版本，不能覆盖原始来源。
- Speaker 与 Collaborator 可以提交本人纠错或修订；MemoryCandidate 在后续 9.6 实现中由 Owner 最终批准。批准不能替代当前 Consent、来源归属或删除门禁。
- Owner 可以删除整个 Family Archive。Collaborator 不自动获得整体档案删除权；未明确开放的 FamilyMember / Interview 子树删除入口不得继续直接硬删。
- Owner、Collaborator 和 Worker 都受 Speaker Consent、隔离与删除状态约束。Family 分享不自动允许普通 Collaborator 播放原始 Audio；原音还需要明确的 raw_audio 分享许可。

## Consequences

### Positive

- Owner 归属与 Collaborator 访问只有一个清晰来源，不会因重复 Owner Membership 产生冲突。
- 邀请、加入、撤销和重新加入均可审计，协作者不能绕过 Owner 批准扩张访问范围。
- 原始来源与协作者修订分离，Owner 审批精确版本，同时保留来源追溯与 Speaker 权利。

### Trade-offs

- 所有现有 Owner-only 查询都需要按完整资源链切换，不能只放宽 Family 顶层入口。
- 访问判断必须同时考虑 Membership generation、来源归属、Consent epoch、修订版本和删除状态。
- 直接硬删接口需要改为显式删除流程或关闭，不能依赖数据库级联表示业务完成。

## Security & Privacy Impact

FamilyMembership 只表达账号访问关系，不能替代 Participant、Speaker 归属或本人 Consent。revoked Membership 的旧 JWT 不再具有 Family 访问权；rights_only Speaker 会话也不能获得普通 Family 浏览、创建或邀请权限。

Owner 审批只确认协作操作或修订版本，不允许代替自主成年 Speaker 授权，也不能恢复已撤回、隔离、待删除或已删除的来源。

## Migration Impact

C2A revision `b7e2c4d891a0` 已在 working tree 新增 CommandIdempotencyRecord、Invitation、Membership，并将 `Family.owner_id` 外键删除行为调整为 RESTRICT；新业务表不做历史 backfill。RevisionProposal 与完整内容权限切换仍按 SSOT 后续实施。

历史数据不得通过 FamilyMember 姓名推断 User、Collaborator、Participant、Speaker 或 Consent。V1 不开放 User hard delete、Owner 转移或身份自动合并。

## Future Boundaries

- User Account 删除、Owner 转移及账号匿名化继续由 ADR-002 单独决定。
- 实际 Audio 上传、对象存储、STT/LLM 和媒体清理适配器不因本 ADR Accepted 而视为完成。
- Policy 的生产期限与告知文本通过后续能力核验和配置启用；缺值时执行 SSOT 已冻结的 fail-safe。

## Related Documents

- [Part 9.5.5-C Final Implementation Design Freeze](../../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md)
- [系统架构总览](../../01_架构设计/AI人生回忆录平台_系统架构总览_V1.1.md)
- [Memory 生成链路设计](../../04_AI设计/Memory生成链路设计_V1.0.md)
- [ADR-002 User账号删除策略](<ADR-002 User账号删除策略.md>)
- [ADR-003 Family档案删除策略](<ADR-003 Family档案删除策略.md>)
- [ADR-005 Interview参与者与讲述者模型](<ADR-005 Interview参与者与讲述者模型.md>)
- [ADR-006 Consent授权撤回与删除策略](<ADR-006 Consent授权撤回与删除策略.md>)
- [ADR-008 MemoryCandidate确认流程](<ADR-008 MemoryCandidate确认流程.md>)

## Related Code

- [User Model](../../../apps/backend/app/models/user.py)、[Family Model](../../../apps/backend/app/models/family.py)、[FamilyMember Model](../../../apps/backend/app/models/family_member.py)
- [Family Schema](../../../apps/backend/app/schemas/family.py)、[FamilyMember Schema](../../../apps/backend/app/schemas/family_member.py)
- [Family Service](../../../apps/backend/app/services/family.py)、[FamilyMember Service](../../../apps/backend/app/services/family_member.py)、[Interview Service](../../../apps/backend/app/services/interview.py)
- [Family CRUD](../../../apps/backend/app/crud/family.py)、[Family API](../../../apps/backend/app/api/v1/families.py)、[FamilyMember API](../../../apps/backend/app/api/v1/family_members.py)
- [Collaboration Model](../../../apps/backend/app/models/collaboration.py)、[Collaboration Service](../../../apps/backend/app/services/collaboration.py)、[Collaboration API](../../../apps/backend/app/api/v1/collaboration.py)

## Revision History

| 日期 | 版本 | 变更 |
| --- | --- | --- |
| 2026-10-05 | V1.0 | Part 9.5.5-A；记录家庭协作约束与 Proposed 访问关系。 |
| 2026-10-05 | V1.1 | Part 9.5.5-C Design Freeze；冻结 Owner/Membership、邀请、不可变修订、Owner 审批及权限门禁；Implementation Not Started。 |
| 2026-10-06 | V1.2 | C2A Invitation / Membership / durable idempotency implementation written；audit remediation completed，Pre-Commit Re-Audit pending；内容权限与 Revision 仍未实现。 |
